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
    if provider in ("openai", "anthropic"):
        return {"location": "cloud", "leaves_device": True,
                "note": f"{provider.title()} - the masked prompt is sent to {provider} under your API key."}
    return {"location": "unknown", "leaves_device": True,
            "note": "Unknown provider - treat as off-device."}


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
    try:
        provider = (provider or "ollama").lower()
        if provider == "ollama":
            base = (url or "http://127.0.0.1:11434").rstrip("/")
            model = model or "llama3.2"
            # check the model is actually installed, so we can give a clear message
            try:
                tags = _get(base + "/api/tags", timeout=5)
                names = [m.get("name","") for m in (tags.get("models") or [])]
                base_names = [n.split(":")[0] for n in names]
                if names and model not in names and model.split(":")[0] not in base_names:
                    out["error"] = ("model '%s' is not installed in Ollama. Installed: %s. "
                                    "Run:  ollama pull %s" % (model, ", ".join(names) or "(none)", model))
                    return out
            except Exception:
                pass  # if /api/tags fails, fall through and let the generate call report
            resp = _post(base + "/api/generate",
                         {"model": model, "prompt": question, "stream": False},
                         {}, timeout)
            out["text"] = (resp.get("response") or "").strip(); out["ok"] = True
        elif provider == "openai":
            resp = _post("https://api.openai.com/v1/chat/completions",
                         {"model": model or "gpt-4o-mini",
                          "messages": [{"role": "user", "content": question}]},
                         {"Authorization": f"Bearer {api_key}"}, timeout)
            out["text"] = resp["choices"][0]["message"]["content"].strip(); out["ok"] = True
        elif provider == "anthropic":
            resp = _post("https://api.anthropic.com/v1/messages",
                         {"model": model or "claude-3-5-haiku-latest", "max_tokens": 256,
                          "messages": [{"role": "user", "content": question}]},
                         {"x-api-key": api_key, "anthropic-version": "2023-06-01"}, timeout)
            out["text"] = resp["content"][0]["text"].strip(); out["ok"] = True
        else:
            out["error"] = f"unknown provider {provider!r}"
    except Exception as e:
        out["error"] = str(e)
    return out


def parse_suggestion(text: str) -> dict:
    """Pull a structured hint out of the model's reply, tolerantly. Expects the
    model to answer with a type/label; falls back to the raw text."""
    if not text:
        return {"suggestion": "", "raw": ""}
    m = re.search(r"\b(date|datetime|numeric|identifier|boolean|gender|email|phone|geo|currency|categorical|name|free[_ ]?text)\b",
                  text, re.I)
    return {"suggestion": (m.group(1).lower().replace(" ", "_") if m else ""), "raw": text.strip()[:400]}
