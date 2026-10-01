"""AI client - the actual model call, kept separate from the privacy layer.

engine/ai_privacy.py decides WHAT may be sent (a minimal, masked, per-column
prompt). This module SENDS it - and does so honestly about where the data goes:

  * local  - a model on the user's own machine (Ollama at 127.0.0.1). Nothing
             leaves the device.
  * cloud  - Ollama cloud, OpenAI, or Anthropic. The masked prompt leaves the
             device to that provider, under the user's own key/account.

`classify_endpoint` lets the UI warn before anything off-device happens.
Every call is guarded, times out, and fails gracefully to the built-in engine.
"""
from __future__ import annotations

import json
import re
import urllib.request

_LOCAL_HOSTS = ("127.0.0.1", "localhost", "0.0.0.0", "::1")


def classify_endpoint(provider: str, url: str = "", model: str = "") -> dict:
    """Say plainly whether a configuration keeps data on the machine."""
    provider = (provider or "").lower()
    model = (model or "").lower()
    if provider == "ollama":
        host_local = any(h in (url or "") for h in _LOCAL_HOSTS) or not url
        # Ollama cloud models run through the same local port but end in '-cloud'
        # and require an account, so name detection matters.
        if model.endswith("-cloud") or "ollama.com" in (url or ""):
            return {"location": "cloud", "leaves_device": True,
                    "note": "Ollama cloud model - the masked prompt is sent to Ollama's servers under your account."}
        if host_local:
            return {"location": "local", "leaves_device": False,
                    "note": "Local model on this computer - nothing leaves the device."}
        return {"location": "cloud", "leaves_device": True,
                "note": "Remote Ollama host - the masked prompt is sent off this device."}
    if provider == "ollama_cloud":
        return {"location": "cloud", "leaves_device": True,
                "note": "Ollama Cloud - the masked prompt is sent to Ollama's servers under your API key."}
    if provider in ("openai", "anthropic"):
        return {"location": "cloud", "leaves_device": True,
                "note": f"{provider.title()} - the masked prompt is sent to {provider} under your API key."}
    return {"location": "unknown", "leaves_device": True,
            "note": "Unknown provider - treat as off-device."}


import urllib.error
import socket


def _provider_label(provider):
    return {"ollama": "the local AI (Ollama)", "ollama_cloud": "Ollama Cloud",
            "openai": "OpenAI", "anthropic": "Claude"}.get(provider, provider or "the AI service")


def _friendly_error(exc, provider, model=""):
    """Turn any network/auth failure into one plain-English sentence. Never shows
    a raw HTTP code. Covers wrong key, wrong model, service not reachable, no
    internet, local model not running, timeouts, and rate limits."""
    who = _provider_label(provider)
    is_local = provider == "ollama"
    # 1) HTTP errors (the service answered with a status)
    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        if code in (401, 403):
            if is_local:
                return f"Couldn't use {who}. It refused the request. Restart Ollama and try again."
            if provider == "ollama_cloud":
                return ("Your Ollama Cloud key wasn't accepted. Open ✦ AI setup and paste the "
                        "secret key from ollama.com/settings/keys (not the public one), and make "
                        "sure cloud access is enabled on your Ollama account.")
            return (f"Your {who} key wasn't accepted. Open ✦ AI setup and check you pasted the full, "
                    f"active key with no extra spaces.")
        if code == 404:
            return (f"{who} doesn't have a model called \u201c{model or 'that'}\u201d. "
                    f"Open ✦ AI setup and pick a model your account can use"
                    + (" (for example gpt-oss:20b)." if provider == "ollama_cloud" else "."))
        if code == 429:
            return f"{who} is busy or you've hit its rate limit. Wait a moment and try again."
        if 500 <= code <= 599:
            return f"{who} had a server problem on its end. Try again in a minute."
        return f"{who} couldn't complete the request. Try again, or pick a different model in ✦ AI setup."
    # 2) Connection errors (couldn't reach the service at all)
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, (ConnectionRefusedError,)) or "refused" in str(reason).lower():
            if is_local:
                return ("Couldn't reach the local AI. Ollama doesn't seem to be running on this "
                        "computer. Start the Ollama app, then try again. "
                        "If you meant to use the cloud, switch to Ollama Cloud in ✦ AI setup.")
            return f"Couldn't reach {who}. Check your internet connection and try again."
        if isinstance(reason, socket.timeout) or "timed out" in str(reason).lower():
            return (f"{who} took too long to respond. "
                    + ("The local model may still be loading. Try once more." if is_local
                       else "Check your internet connection and try again."))
        if "name or service" in str(reason).lower() or "getaddrinfo" in str(reason).lower() or "nodename" in str(reason).lower():
            return (f"Couldn't find {who} online. Check your internet connection"
                    + ("" if not is_local else ", or confirm the local server address in ✦ AI setup") + ".")
        return f"Couldn't connect to {who}. Check your setup in ✦ AI setup and try again."
    if isinstance(exc, socket.timeout):
        return f"{who} took too long to respond. Try again."
    # 3) anything else
    return f"Couldn't use {who} right now. Try again, or check ✦ AI setup."


def _post(url: str, payload: dict, headers: dict, timeout: float = 30.0) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get(url: str, timeout: float = 10.0) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def ask(question: str, provider: str = "ollama", url: str = "", model: str = "",
        api_key: str = "", timeout: float = 30.0) -> dict:
    """Send an already-safe, masked prompt to the chosen model and return the text.
    Returns {ok, text, location, leaves_device, error?}. Never raises."""
    loc = classify_endpoint(provider, url, model)
    out = {"ok": False, "text": "", **loc}
    # one place to clean a pasted key for ANY cloud provider (stray spaces/newlines,
    # surrounding quotes, or an accidental "Bearer " prefix are the usual 401 causes)
    key = (api_key or "").strip().strip('"').strip("'")
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    try:
        provider = (provider or "ollama").lower()
        if provider == "ollama":
            base = (url or "http://127.0.0.1:11434").strip().rstrip("/")
            if base and not base.startswith(("http://", "https://")):
                base = "http://" + base          # 'localhost:11434' -> 'http://localhost:11434'
            model = model or "llama3.2"
            # check the model is actually installed, so we can give a clear message
            try:
                tags = _get(base + "/api/tags", timeout=5)
                names = [m.get("name","") for m in (tags.get("models") or [])]
                base_names = [n.split(":")[0] for n in names]
                if names and model not in names and model.split(":")[0] not in base_names:
                    out["error"] = ("The local AI doesn't have the model \u201c%s\u201d yet. "
                                    "In a terminal run:  ollama pull %s  (installed now: %s)."
                                    % (model, model, ", ".join(names) or "none"))
                    return out
            except Exception:
                pass  # if /api/tags fails, fall through and let the generate call report
            resp = _post(base + "/api/generate",
                         {"model": model, "prompt": question, "stream": False},
                         {}, timeout)
            out["text"] = (resp.get("response") or "").strip(); out["ok"] = True
        elif provider == "ollama_cloud":
            resp = _post("https://ollama.com/v1/chat/completions",
                         {"model": model or "gpt-oss:20b",
                          "messages": [{"role": "user", "content": question}]},
                         {"Authorization": f"Bearer {key}"}, timeout)
            out["text"] = resp["choices"][0]["message"]["content"].strip(); out["ok"] = True
        elif provider == "openai":
            resp = _post("https://api.openai.com/v1/chat/completions",
                         {"model": model or "gpt-4o-mini",
                          "messages": [{"role": "user", "content": question}]},
                         {"Authorization": f"Bearer {key}"}, timeout)
            out["text"] = resp["choices"][0]["message"]["content"].strip(); out["ok"] = True
        elif provider == "anthropic":
            resp = _post("https://api.anthropic.com/v1/messages",
                         {"model": model or "claude-3-5-haiku-latest", "max_tokens": 256,
                          "messages": [{"role": "user", "content": question}]},
                         {"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout)
            out["text"] = resp["content"][0]["text"].strip(); out["ok"] = True
        else:
            out["error"] = "That AI provider is not set up. Open \u2726 AI setup and choose Local, Ollama Cloud, OpenAI, or Claude."
    except Exception as e:
        out["error"] = _friendly_error(e, provider, model)
    return out


def parse_review(text: str) -> dict:
    """Pull per-column verdicts out of a whole-file reply, tolerantly (JSON or lines)."""
    import re as _re
    cols=[]; note=""
    if not text: return {"columns": [], "note": ""}
    try:
        s=text.index("{"); e=text.rindex("}")+1; obj=json.loads(text[s:e])
        if isinstance(obj, dict):
            note=str(obj.get("note",""))[:300]
            for c in (obj.get("columns") or obj.get("fields") or []):
                if isinstance(c, dict):
                    cols.append({"name":str(c.get("name","")),
                                 "suggested_type":str(c.get("type") or c.get("suggested_type") or "").lower(),
                                 "reason":str(c.get("reason",""))[:160]})
            if cols: return {"columns": cols, "note": note}
    except Exception:
        pass
    for line in text.splitlines():
        m=_re.match(r"\s*[-*]?\s*(.+?)\s*[:\-]\s*(date|datetime|numeric|number|identifier|id|boolean|gender|email|phone|geo|place|currency|categorical|category|name|free[_ ]?text)\b", line, _re.I)
        if m:
            t=m.group(2).lower().replace(" ","_")
            t={"number":"numeric","id":"identifier","place":"geo","category":"categorical"}.get(t,t)
            cols.append({"name":m.group(1).strip(),"suggested_type":t,"reason":""})
    return {"columns": cols, "note": note}


def review(headers, sample_rows, provider="ollama", url="", model="", timeout=30.0, api_key="", context="") -> dict:
    """ONE whole-file pass. Works on local or cloud; only a masked header + small
    sample is sent. The caller decides whether leaving the device is acceptable."""
    loc=classify_endpoint(provider, url, model)
    out={"ok": False, "columns": [], "note": "", "raw": "", **loc}
    hdr=", ".join(str(h) for h in (headers or []))
    sample=json.dumps(sample_rows[:8])[:3000]
    prompt=("You are a data analyst. Given a table's header and sample rows, identify each "
            "column's best data type. Types: date, datetime, numeric, identifier, boolean, gender, "
            "email, phone, geo, currency, categorical, name, free_text. Reply ONLY with JSON: "
            "{\"columns\":[{\"name\":\"...\",\"type\":\"...\",\"reason\":\"...\"}],\"note\":\"...\"}.\n"
            "Header: "+hdr+"\nSample rows: "+sample
            +("\nAbout this file: "+context if context else "")
            +"\nColumns named by year, month or quarter are separate time periods, never duplicates. "
             "Values like '..' or 'n/a' mean missing data. Only suggest types; never suggest removing a column.")
    # pass the key through: without it every cloud review was sent unauthenticated
    # (401 -> "key wasn't accepted") even though the connection test had passed
    res=ask(prompt, provider=provider, url=url, model=model, timeout=timeout, api_key=api_key)
    out["ok"]=res.get("ok", False); out["raw"]=(res.get("text") or "")[:1500]
    if res.get("error"): out["error"]=res["error"]
    if out["ok"]:
        p=parse_review(res.get("text","")); out["columns"]=p["columns"]; out["note"]=p["note"]
    return out


def parse_suggestion(text: str) -> dict:
    """Pull a structured hint out of the model's reply, tolerantly. Expects the
    model to answer with a type/label; falls back to the raw text."""
    if not text:
        return {"suggestion": "", "raw": ""}
    m = re.search(r"\b(date|datetime|numeric|identifier|boolean|gender|email|phone|geo|currency|categorical|name|free[_ ]?text)\b",
                  text, re.I)
    return {"suggestion": (m.group(1).lower().replace(" ", "_") if m else ""), "raw": text.strip()[:400]}
