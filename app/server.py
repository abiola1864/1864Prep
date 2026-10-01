"""A thin web service around the cleaning engine.

Used two ways from ONE codebase:
  * deploy to Render (or any host) for a live demo - synthetic data only;
  * called locally by the desktop shell so the same endpoints work offline.

Endpoints
  GET  /                 -> the prototype UI (static)
  POST /api/profile      -> read a file, report what was detected + column types
  POST /api/clean        -> read + auto-clean, return before/after overview + a
                            random spot-check sample (the review data)
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from engine.ingest import read_any
from engine.pipeline import run_plan
from engine.profile import profile_dataframe, profile_to_plan
import os
try:
    import regions as _regions          # richer module if present in the repo/bundle
except ModuleNotFoundError:
    from engine import regions_fallback as _regions   # built-in minimal fallback so the app always runs
_regions.set_active_region(os.environ.get("PREP_REGION", "generic"))
from engine.review import column_overview, spotcheck

app = FastAPI(title="1864 Prep engine", version="0.1")


@app.middleware("http")
async def _no_cache(request, call_next):
    """Guarantee the browser (and any CDN) never serves a stale build: the app page,
    its scripts, and API responses are always fetched fresh. The client never has to
    clear a cache or hard-refresh."""
    resp = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css")) or path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp

UI_DIR = Path(__file__).resolve().parents[1] / "prototype" / "ui"


def _save(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload").suffix or ".csv"
    tmp = Path(tempfile.mkstemp(suffix=suffix)[1])
    tmp.write_bytes(upload.file.read())
    return tmp




def _admin_checks(df, profs):
    """For columns detected as Nigerian State or LGA, validate every value against
    the full official set: typo suggestions, wrong-level and unknown (city) flags."""
    from engine.domains import detect_domain
    from engine import ng_admin as NG
    out = []
    for p in profs:
        if p.semantic_type not in ("geo", "categorical", "name", "free_text"):
            continue
        col = df[p.column]
        dom = detect_domain(col.tolist(), p.column)
        if dom not in ("ng_state", "ng_lga"):
            continue
        level = "state" if dom == "ng_state" else "lga"
        items, seen = [], set()
        for i, v in enumerate(col.tolist()):
            s = str(v).strip()
            if not s or s in seen:
                continue
            r = NG.validate_state_value(s) if level == "state" else NG.validate_lga_value(s)
            if r["kind"] in ("unknown", "is_state", "is_lga"):
                seen.add(s)
                items.append({"row": i, "value": s, "kind": r["kind"],
                              "suggestion": r.get("suggestion"), "note": r.get("note", "")})
            if len(items) >= 50:
                break
        if items:
            out.append({"column": p.column, "level": level, "items": items})
    return out


def _dup_payload(df):
    """Duplicate groups with per-row previews + the true total of removable rows."""
    from engine.dedupe import near_duplicate_rows
    groups = near_duplicate_rows(df)
    total = sum(len(g["rows"]) - 1 for g in groups)
    def prev(i):
        return " \u00b7 ".join(str(v) for v in df.iloc[i].tolist() if str(v).strip())[:90]
    out = []
    for g in groups[:50]:
        out.append({"rows": g["rows"], "kind": g["kind"], "similarity": g["similarity"],
                    "keep_row": g["rows"][0], "remove_rows": g["rows"][1:],
                    "preview": prev(g["rows"][0]),
                    "row_previews": [{"row": i, "text": prev(i)} for i in g["rows"]]})
    return out, total


@app.post("/api/profile")
async def api_profile(file: UploadFile = File(...), region: str = Form(None), types_prior: str = Form("[]"), sheet: str = Form(None)):
    if region:
        _regions.set_active_region(region)
    path = _save(file)
    import json as _json
    try:
        _prior = set(_json.loads(types_prior)) if types_prior else set()
    except Exception:
        _prior = set()
    try:
        df, rep = read_any(path, sheet=sheet)
        _ref = _regions.load_reference()
        # columns-first is a FAST structural pass: rule-based typing only, no ML/NLP
        # or embeddings load, so "Reading the columns" returns in a moment even on
        # large files. The heavy work happens later, during the actual clean.
        profs = profile_dataframe(df, _ref["gazetteers"], _ref["place_index"], use_ml=False, use_nlp=False, type_prior=_prior)
        from engine.headers import propose_headers, abnormal_count
        from engine import domains as _D
        _doms = [_D.detect_domain(df[c].head(300).tolist(), str(c)) for c in df.columns]
        header_rows = propose_headers(df, profs, _doms)
        from engine.structure import detect_structure
        _struct = detect_structure(df)
        # what IS this sheet — a data table, a form, or a list?
        _shape = {"kind": "table"}
        try:
            from engine.sheetshape import classify_sheet
            import pandas as _pd
            raw = _pd.read_excel(path, sheet_name=(sheet or getattr(rep, "sheet", None) or 0), header=None, dtype=str).fillna("").values.tolist() \
                if str(path).lower().endswith((".xlsx", ".xls", ".xlsm")) else None
            if raw is not None:
                _shape = classify_sheet(raw)
        except Exception:
            pass
        if getattr(rep, "is_form", False):
            _struct = {"kind": "form"}
        return {
            "ingest": rep.summary(),
            "is_form": bool(getattr(rep, "is_form", False)),
                "skipped_rows": rep.skipped_rows, "header_row": rep.header_row,
            "region": _regions.get_active_region().name,
            "rows": len(df), "cols": len(df.columns),
            "headers": header_rows, "headers_abnormal": abnormal_count(header_rows),
            "preview": df.head(50).astype(str).to_dict(orient="records"),
            "columns": [{"name": p.column, "type": p.semantic_type,
                         "confidence": round(p.confidence, 2)} for p in profs],
            "structure": _struct,
            "shape": _shape,
            "notes": list(getattr(rep, "notes", []) or []),
        }
    except Exception as e:
        msg = str(e)
        if "empty" in msg.lower():
            return {"error": msg}
        return {"error": f"Couldn't read this file's columns ({msg}). Check it opens in Excel, or try saving it as CSV."}
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/codebook")
async def api_codebook(payload: dict):
    """Build a codebook for a cleaned session: variable name, original label/question,
    type, and a short description. Stored as a downloadable result (result_id)."""
    import uuid, pandas as pd
    cols = payload.get("columns", [])   # [{name, label, type, reason}]
    rows = []
    for c in cols:
        name = c.get("name") or c.get("original") or ""
        label = c.get("label") or c.get("original") or name
        typ = c.get("type") or ""
        reason = (c.get("reason") or "").strip()
        # description: AI reason if present, else a plain sentence from label+type
        desc = reason or f"{label}." if label and label != name else (reason or f"{typ} field.")
        rows.append({"variable": name, "label": label, "type": typ, "description": desc})
    df = pd.DataFrame(rows, columns=["variable", "label", "type", "description"])
    rid = uuid.uuid4().hex[:12]
    _RESULTS[rid] = {"df": df, "title": "Codebook"}
    return {"codebook_id": rid, "rows": len(df)}


@app.post("/api/export/combine")
async def api_export_combine(payload: dict):
    """Combine several cleaned sheet results into ONE multi-tab Excel workbook."""
    ids = payload.get("result_ids", []); names = payload.get("sheet_names", [])
    frames = []
    for i, rid in enumerate(ids):
        r = _RESULTS.get(rid)
        if r is not None:
            nm = (names[i] if i < len(names) else f"Sheet{i+1}")[:31]
            frames.append((nm, r["df"]))
    if not frames:
        return {"error": "no cleaned sheets to combine"}
    import uuid as _uuid
    from engine.exporters import to_xlsx_multi
    cid = _uuid.uuid4().hex[:12]
    _RESULTS[cid] = {"multi": frames, "title": "All sheets"}
    return {"combined_id": cid, "sheets": len(frames)}


@app.post("/api/sheets")
async def api_sheets(file: UploadFile = File(...)):
    """List the sheets in an uploaded workbook so the user can pick which to clean."""
    path = _save(file)
    try:
        from engine.ingest import list_sheets
        return {"sheets": list_sheets(path)}
    except Exception as e:
        return {"sheets": [], "error": str(e)}
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/reshape_long")
async def api_reshape_long(file: UploadFile = File(...), region: str = Form(None),
                          id_cols: str = Form("[]"), value_cols: str = Form("[]"),
                          axis_name: str = Form("year"), value_name: str = Form("value")):
    """Reshape an uploaded wide/panel file to long, then re-profile the result so
    the columns review shows the tidy long columns."""
    if region:
        _regions.set_active_region(region)
    path = _save(file)
    import json as _json
    try:
        ids = _json.loads(id_cols); vals = _json.loads(value_cols)
        df, rep = read_any(path)
        from engine.reshape import to_long
        long = to_long(df, ids, vals, axis_name=axis_name, value_name=value_name)
        import uuid as _uuid
        reshaped_id = _uuid.uuid4().hex[:12]
        _RESHAPED[reshaped_id] = long
        _ref = _regions.load_reference()
        profs = profile_dataframe(long, _ref["gazetteers"], _ref["place_index"], use_ml=False, use_nlp=False)
        from engine.headers import propose_headers, abnormal_count
        from engine import domains as _D
        _doms = [_D.detect_domain(long[c].head(300).tolist(), str(c)) for c in long.columns]
        header_rows = propose_headers(long, profs, _doms)
        return {"rows": len(long), "cols": len(long.columns), "reshaped_id": reshaped_id,
                "headers": header_rows, "headers_abnormal": abnormal_count(header_rows),
                "preview": long.head(50).astype(str).to_dict(orient="records"),
                "columns": [{"name": p.column, "type": p.semantic_type,
                             "confidence": round(p.confidence, 2)} for p in profs],
                "structure": {"kind": "flat"}}
    except Exception as e:
        return {"error": f"Could not reshape: {e}"}
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/clean")
async def api_clean(file: UploadFile = File(...), region: str = Form(None)):
    if region:
        _regions.set_active_region(region)
    path = _save(file)
    try:
        df, rep = read_any(path)
        _ref = _regions.load_reference()
        profs = profile_dataframe(df, _ref["gazetteers"], _ref["place_index"], use_ml=True, use_nlp=True)
        plan = profile_to_plan(profs, "auto", _ref["gazetteer_refs"])
        types = {p.column: p.semantic_type for p in profs}
        cleaned, report, _ = run_plan(df, plan, "web")
        flags = {c["source_column"]: c.get("flagged", 0) for c in report.columns}

        # --- data for the "needs your attention" worklist ---
        from engine.dedupe import cluster_similar, duplicate_columns, near_duplicate_rows
        flagged = []
        for c in report.columns:
            fl = c.get("flags") or []
            if fl:
                flagged.append({"column": c["source_column"],
                                "values": [{"row": x["row"], "value": x["value"],
                                            "reason": x["reason"]} for x in fl[:50]]})
        dups, _dup_total = _dup_payload(df)
        similar = []
        for p in profs[:12]:
            if p.semantic_type in ("categorical", "name", "free_text"):
                nun = df[p.column].nunique()
                if 2 <= nun <= 400:
                    gs = cluster_similar(df[p.column].tolist(), semantic=True)[:20]
                    if gs:
                        similar.append({"column": p.column,
                                        "groups": [{"representative": g["representative"],
                                                    "members": g["members"][:20],
                                                    "size": g["size"],
                                                    "confidence": g["confidence"],
                                                    "score": g["score"]} for g in gs]})
        rid = None
        import uuid as _uuid
        sid = _uuid.uuid4().hex[:12]
        _SESSIONS[sid] = {"df": df, "types": types, "plan": plan}
        admin_flags = _admin_checks(df, profs)
        from engine.headers import propose_headers, abnormal_count
        from engine import domains as _Dh
        _doms_h = [_Dh.detect_domain(df[c].tolist(), str(c)) for c in df.columns]
        header_rows = propose_headers(df, profs, _doms_h)
        return {
            "ingest": rep.summary(),
                "skipped_rows": rep.skipped_rows, "header_row": rep.header_row,
            "region": _regions.get_active_region().name,
            "session_id": sid,
            "headers": header_rows, "headers_abnormal": abnormal_count(header_rows),
            "overview": column_overview(df, cleaned, types, flags),
            "spotcheck": spotcheck(df, cleaned, pool_size=40, seed=1),
            "worklist": {"flagged": flagged, "admin": admin_flags, "duplicates": dups, "duplicates_total": _dup_total, "similar": similar,
                         "repeated_columns": duplicate_columns(df)},
        }
    except Exception as e:  # never 500 silently in a demo
        return JSONResponse(status_code=422, content={"error": str(e)})
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/clean_stream")
async def api_clean_stream(file: UploadFile = File(...), region: str = Form(None), rename: str = Form("{}"), types: str = Form("{}"), sheet: str = Form(None), reshaped_id: str = Form(None), drop: str = Form("[]")):
    """Same as /api/clean but streams real progress (one tick per column) so the
    bar reflects the actual workload instead of an estimate. `rename` and `types`
    are the person's confirmed column names and data types from the columns-first step."""
    if region:
        _regions.set_active_region(region)
    path = _save(file)
    fname = file.filename
    import json as _json
    try:
        _rename_map = _json.loads(rename) if rename else {}
    except Exception:
        _rename_map = {}
    try:
        _type_map = _json.loads(types) if types else {}
    except Exception:
        _type_map = {}

    def gen():
        import json
        import uuid as _uuid
        from engine.profile import profile_column, profile_to_plan
        from engine.dedupe import cluster_similar, duplicate_columns, near_duplicate_rows
        try:
            _job = _uuid.uuid4().hex[:12]
            yield json.dumps({"t": "job", "job_id": _job}) + "\n"
            yield json.dumps({"t": "progress", "pct": 0.04, "stage": "Reading the file"}) + "\n"
            if reshaped_id and reshaped_id in _RESHAPED:
                df = _RESHAPED[reshaped_id].copy(); rep = None   # clean the reshaped (long) data
            else:
                df, rep = read_any(path, sheet=sheet)
            try:
                _drop = json.loads(drop or "[]")
                if _drop:
                    df = df.drop(columns=[c for c in _drop if c in df.columns], errors="ignore")
            except Exception:
                pass
            if _rename_map:                      # apply the confirmed column names first
                df = df.rename(columns={k: v for k, v in _rename_map.items() if k in df.columns})
            _ref = _regions.load_reference()
            cols = list(df.columns); N = max(1, len(cols))
            profs = []
            for i, c in enumerate(cols):
                if _is_cancelled(_job):
                    _CANCELLED.discard(_job)
                    yield json.dumps({"t": "cancelled"}) + "\n"; return
                profs.append(profile_column(df[c], c, _ref["gazetteers"], _ref["place_index"], use_ml=True, use_nlp=True))
                if i % 2 == 0 or i == N - 1:
                    yield json.dumps({"t": "progress", "pct": 0.05 + 0.75 * (i + 1) / N,
                                      "stage": f"Checking column {i+1} of {N}"}) + "\n"
            plan = profile_to_plan(profs, "auto", _ref["gazetteer_refs"])
            if _type_map:                        # honour the person's confirmed data types
                for p in profs:
                    if p.column in _type_map and _type_map[p.column]:
                        p.semantic_type = _type_map[p.column]
                plan = profile_to_plan(profs, "auto", _ref["gazetteer_refs"])
            types = {p.column: p.semantic_type for p in profs}
            yield json.dumps({"t": "progress", "pct": 0.82, "stage": "Cleaning values"}) + "\n"
            cleaned, report, _ = run_plan(df, plan, "web")
            flags = {c["source_column"]: c.get("flagged", 0) for c in report.columns}
            flagged = []
            for c in report.columns:
                fl = c.get("flags") or []
                if fl:
                    flagged.append({"column": c["source_column"],
                                    "values": [{"row": x["row"], "value": x["value"], "reason": x["reason"]} for x in fl[:50]]})
            yield json.dumps({"t": "progress", "pct": 0.86, "stage": "Checking for duplicate rows"}) + "\n"
            admin_flags = _admin_checks(df, profs)
            dups, _dup_total = _dup_payload(df)
            # similar-value scan across ALL text columns, with real per-column progress
            text_cols = [p for p in profs if p.semantic_type in ("categorical", "name", "free_text", "geo")]
            M = max(1, len(text_cols))
            similar = []
            for k, p in enumerate(text_cols):
                nun = df[p.column].nunique()
                if 2 <= nun <= 400:
                    from engine.domains import detect_domain
                    _dom = detect_domain(df[p.column].tolist(), p.column)
                    # Look for near-duplicates AFTER cleaning, so case/spacing variants
                    # the engine already fixed ('AISHA BELLO' vs 'Aisha Bello') are not
                    # offered again as something to decide.
                    _vals = (cleaned[p.column] if p.column in cleaned.columns else df[p.column]).tolist()
                    gs = cluster_similar(_vals, domain=_dom)[:20]
                    _person = p.semantic_type == "name"
                    out_g = []
                    for g in gs:
                        conf = g["confidence"]
                        # Two similar names can be two different people. Never pre-tick
                        # a merge of person names; the user must choose it.
                        if _person and conf == "high":
                            conf = "medium"
                        out_g.append({"representative": g["representative"], "members": g["members"][:20],
                                      "size": g["size"], "confidence": conf, "score": g["score"],
                                      "people": _person})
                    if out_g:
                        similar.append({"column": p.column, "type": p.semantic_type, "groups": out_g})
                if k % 2 == 0 or k == M - 1:
                    yield json.dumps({"t": "progress", "pct": 0.88 + 0.10 * (k + 1) / M,
                                      "stage": f"Finding matches ({k+1} of {M})"}) + "\n"
            sid = _uuid.uuid4().hex[:12]
            _SESSIONS[sid] = {"df": df, "types": types, "plan": plan}
            from engine.headers import propose_headers, abnormal_count
            from engine.domains import detect_domain as _dd
            _doms_s = [_dd(df[c].tolist(), str(c)) for c in cols]
            header_rows = propose_headers(df, profs, _doms_s)
            payload = {
                "ingest": (rep.summary() if rep else {}),
                "skipped_rows": (rep.skipped_rows if rep else 0), "header_row": (rep.header_row if rep else 0),
                "region": _regions.get_active_region().name,
                "session_id": sid,
                "headers": header_rows, "headers_abnormal": abnormal_count(header_rows),
                "overview": column_overview(df, cleaned, types, flags),
                "spotcheck": spotcheck(df, cleaned, pool_size=40, seed=1),
                "worklist": {"flagged": flagged, "admin": admin_flags, "duplicates": dups, "duplicates_total": _dup_total, "similar": similar,
                             "repeated_columns": duplicate_columns(df)},
            }
            yield json.dumps({"t": "result", "payload": payload}) + "\n"
        except Exception as e:
            yield json.dumps({"t": "error", "error": str(e)}) + "\n"
        finally:
            path.unlink(missing_ok=True)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.get("/api/regions")
async def api_regions():
    return {"active": _regions.get_active_region().key,
            "regions": [{"key": k, "name": _regions.get_region(k).name} for k in _regions.list_regions()]}


@app.get("/api/tools")
async def api_tools():
    from engine.toolkit import TOOLS
    return {"tools": [{"id": k, "name": v[0], "desc": v[1], "kind": v[2]} for k, v in TOOLS.items()]}


class _Recent(dict):
    """A dict that keeps only the most recent N entries, so a long day of
    cleaning files doesn't slowly fill the computer's memory."""
    def __init__(self, cap):
        super().__init__(); self.cap = cap
    def __setitem__(self, k, v):
        if k in self: super().__delitem__(k)
        super().__setitem__(k, v)
        while len(self) > self.cap:
            super().__delitem__(next(iter(self)))


_RESULTS: dict = _Recent(60)
_SESSIONS: dict = _Recent(12)
_RESHAPED: dict = _Recent(6)   # reshaped (long) dataframes, so cleaning uses the reshaped shape


@app.post("/api/export")
async def api_export(session_id: str = Form(...), decisions: str = Form("{}"), ai_cols: str = Form("[]")):
    """Apply the person's decisions to the remembered upload and produce a
    genuinely cleaned dataset + an audit log. Returns a result_id to download."""
    import json
    import uuid
    from engine.dedupe import near_duplicate_rows
    from engine.pipeline import run_plan

    sess = _SESSIONS.get(session_id)
    if not sess:
        return JSONResponse(status_code=404, content={"error": "session expired; re-upload the file"})
    df = sess["df"].copy()
    plan = sess["plan"]
    dec = json.loads(decisions or "{}")
    try:
        ai_set = {str(x).strip().lower() for x in json.loads(ai_cols or "[]")}
    except Exception:
        ai_set = set()
    rejected = set(dec.get("reject", []))
    setall = dec.get("setall", {}) or {}
    merges = dec.get("merges", []) or []
    remove_dupes = bool(dec.get("remove_duplicates"))

    def _src(col):
        return "AI" if str(col).strip().lower() in ai_set else "engine"

    audit = []
    # 1) apply the plan, minus rejected columns (those pass through unchanged)
    kept = {"name": plan.get("name", "auto"),
            "mappings": [m for m in plan["mappings"] if m["source_column"] not in rejected]}
    cleaned, report, _ = run_plan(df, kept, "export")
    for c in report.columns:
        if c.get("changed"):
            audit.append({"column": c["source_column"], "action": f"cleaned ({c['transform']})",
                          "count": c["changed"], "by": _src(c["source_column"])})
    for col in rejected:
        audit.append({"column": col, "action": "kept original (your choice)", "count": "", "by": "you"})

    # 2) set-all / flagged fixes
    for col, val in setall.items():
        if col in cleaned.columns:
            n = int((cleaned[col].astype(str) != str(val)).sum())
            cleaned[col] = val
            audit.append({"column": col, "action": f"set all to '{val}'", "count": n, "by": "you"})

    # 3) confirmed similar-value merges
    for mg in merges:
        col, into, members = mg.get("column"), mg.get("into"), set(mg.get("members", []))
        if col in cleaned.columns and into and members:
            mask = cleaned[col].astype(str).isin(members)
            if col in df.columns:
                mask = mask | df[col].astype(str).str.strip().isin({str(m).strip() for m in members}).reindex(cleaned.index, fill_value=False)
            n = int(mask.sum())
            cleaned.loc[mask, col] = into
            audit.append({"column": col, "action": f"merged {len(members)} spellings into '{into}'", "count": n, "by": "you"})

    # 4) remove duplicate rows
    if remove_dupes:
        groups = near_duplicate_rows(df)
        drop = set()
        for g in groups:
            drop.update(sorted(g["rows"])[1:])
        if drop:
            cleaned = cleaned.drop(index=list(drop)).reset_index(drop=True)
            audit.append({"column": "(rows)", "action": "removed duplicate rows", "count": len(drop)})

    rid = uuid.uuid4().hex[:12]
    _RESULTS[rid] = {"df": cleaned, "title": "Cleaned data"}
    _RESULTS[rid + "_audit"] = {"df": __import__("pandas").DataFrame(audit), "title": "Change log"}
    return {"result_id": rid, "audit_id": rid + "_audit", "rows_out": len(cleaned),
            "cols_out": len(cleaned.columns), "audit": audit[:200],
            "changes_total": sum(int(a["count"]) for a in audit if str(a["count"]).isdigit())}


@app.post("/api/tool/{name}")
async def api_tool(name: str, files: list[UploadFile] = File(...),
                   how: str = Form("outer"), region: str = Form(None)):
    if region:
        _regions.set_active_region(region)
    import uuid
    from engine import toolkit as tk
    from engine.ingest import read_any

    dfs = []
    for f in files:
        p = _save(f)
        try:
            df, _ = read_any(p)
            dfs.append(df)
        finally:
            p.unlink(missing_ok=True)
    if not dfs:
        return JSONResponse(status_code=422, content={"error": "no files"})

    try:
        if name == "duplicates":
            res, summ = tk.find_duplicates(dfs[0])
        elif name == "outliers":
            res, summ = tk.find_outliers(dfs[0])
        elif name == "match":
            res, summ = tk.match_files(dfs, how=how)
        elif name == "validate":
            res, summ = tk.validate(dfs[0])
        elif name == "summarise":
            res, summ = tk.summarise(dfs[0])
        elif name == "dedupe":
            res, summ = tk.dedupe_file(dfs[0])
        elif name == "compare":
            res, summ = tk.compare_files(dfs)
        elif name == "combine":
            res, summ = tk.combine_files(dfs)
        elif name == "anonymise":
            res, summ = tk.anonymise(dfs[0])
        elif name == "quick_clean":
            res, summ = tk.quick_clean(dfs[0])
        elif name == "guess_gender":
            # 'how' is the merge-join string form field; gender wants a dict (optional column)
            res, summ = tk.guess_gender(dfs[0], {"column": how} if how and how != "outer" else None)
        else:
            return JSONResponse(status_code=404, content={"error": f"unknown tool '{name}'"})
    except Exception as e:
        return JSONResponse(status_code=422, content={"error": str(e)})

    rid = uuid.uuid4().hex[:12]
    title = tk.TOOLS.get(name, (name,))[0]
    _RESULTS[rid] = {"df": res, "title": title}
    res = res.astype(object).where(res.notna(), "")
    return {
        "tool": name, "summary": summ, "result_id": rid,
        "columns": list(res.columns),
        "rows_total": len(res),
        "preview": res.head(50).values.tolist(),
    }


@app.get("/api/tool/download/{rid}")
async def api_tool_download(rid: str, fmt: str = "csv", name: str = ""):
    import tempfile
    from pathlib import Path
    from engine import exporters as ex
    item = _RESULTS.get(rid)
    if not item:
        return JSONResponse(status_code=404, content={"error": "result expired; run the tool again"})
    # multi-sheet combined workbook
    if item.get("multi"):
        out = Path(tempfile.mkdtemp()) / "All_cleaned_sheets.xlsx"
        ex.to_xlsx_multi(item["multi"], out)
        from fastapi.responses import FileResponse as _FR
        return _FR(str(out), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=out.name)
    ext = {"csv": "csv", "xlsx": "xlsx", "excel": "xlsx", "docx": "docx", "word": "docx"}.get(fmt.lower(), "csv")
    fname = (name or item['title']).replace(' ', '_')
    out = Path(tempfile.mkdtemp()) / f"{fname}.{ext}"
    ex.export(item["df"], fmt, out, title=item["title"], intro="Generated by 1864 Prep - Data Toolkit.")
    media = {"csv": "text/csv",
             "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}[ext]
    from fastapi.responses import FileResponse as _FR
    return _FR(str(out), media_type=media, filename=out.name)


@app.post("/api/ai/ask")
async def ai_ask(payload: dict):
    """Real AI assist for ONE column, privacy-first. Body:
    {column, values, task?, mode?, provider?, url?, model?, api_key?}.
    Builds the masked, per-column prompt (never full rows), sends it to the chosen
    model, and returns the suggestion plus a clear note on where the data went."""
    from engine.ai_privacy import build_column_query, is_full_dataset
    from engine.ai_client import ask, parse_suggestion, classify_endpoint
    column = payload.get("column", "")
    values = payload.get("values", [])
    if not isinstance(values, list):
        return {"error": "values must be a list from a single column"}
    q = build_column_query(column, values, task=payload.get("task", "type"), mode=payload.get("mode"))
    q["single_column_guaranteed"] = not is_full_dataset(q)
    provider = payload.get("provider", "ollama"); url = payload.get("url", ""); model = payload.get("model", "")
    where = classify_endpoint(provider, url, model)
    # what actually gets sent to the model - the masked question + sample values
    prompt = (q["question"] + "\nSample values: " + ", ".join(map(str, q["sent_values"]))
              + "\nAnswer with one data type (date, numeric, identifier, phone, email, gender, geo, categorical, name, free_text).")
    res = ask(prompt, provider=provider, url=url, model=model, api_key=payload.get("api_key", ""), timeout=20)
    parsed = parse_suggestion(res.get("text", "")) if res.get("ok") else {"suggestion": "", "raw": ""}
    return {"sent": q, "where": where, "ok": res.get("ok", False),
            "error": res.get("error"), "suggestion": parsed["suggestion"], "raw": parsed["raw"]}


@app.post("/api/ai/structure")
async def ai_structure(payload: dict):
    """Opt-in: ask the model for a SECOND OPINION on the table's structure - which
    row is the header and each column's type. Sends the header row + a small,
    masked sample of rows (never the full file). Returns suggestions the user
    applies in the review; the engine's own detection remains the default."""
    from engine.ai_privacy import _mask, looks_sensitive
    from engine.ai_client import ask, classify_endpoint
    headers = payload.get("headers", [])
    sample_rows = payload.get("sample", [])[:8]
    provider = payload.get("provider", "ollama"); url = payload.get("url", ""); model = payload.get("model", "")
    where = classify_endpoint(provider, url, model)
    # mask sensitive-looking columns in the sample before it leaves
    masked = []
    for row in sample_rows:
        mr = {}
        for k, v in (row or {}).items():
            mr[k] = _mask(str(v)) if looks_sensitive(str(k)) else v
        masked.append(mr)
    import json as _json
    prompt = ("Given this table header and a few sample rows, say which columns look like "
              "date, numeric, identifier, phone, email, gender, geo, categorical, name or free_text. "
              "Reply as 'column: type' lines.\nHeaders: " + ", ".join(map(str, headers))
              + "\nSample: " + _json.dumps(masked)[:1500])
    res = ask(prompt, provider=provider, url=url, model=model, api_key=payload.get("api_key", ""))
    return {"where": where, "ok": res.get("ok", False), "error": res.get("error"),
            "raw": (res.get("text", "") or "")[:1200]}


@app.post("/api/cluster_values")
async def api_cluster_values(payload: dict):
    """Instant, offline value clustering (no AI, no network). Groups variant
    spellings of the same value. Returns {merges: {canonical: [variants]}}."""
    from engine.valuecluster import cluster_values
    from engine.ai_privacy import looks_sensitive
    col = payload.get("column", "")
    if looks_sensitive(str(col)):
        return {"merges": {}, "note": "sensitive column skipped"}
    try:
        return {"merges": cluster_values(payload.get("values", []))}
    except Exception as e:
        return {"merges": {}, "error": str(e)}


@app.post("/api/ai/values")
async def ai_values(payload: dict):
    """AI value cleaning for ONE column: given its distinct messy values, ask the
    model to group variant spellings under a canonical value (e.g. Kastina/Katsina).
    Masked, local-first. Returns {merges: {canonical: [variants...]}}."""
    from engine.ai_privacy import build_column_query, looks_sensitive
    from engine.ai_client import ask, classify_endpoint
    import json as _json, re as _re
    column = payload.get("column", ""); values = payload.get("values", [])
    if looks_sensitive(str(column)):
        return {"merges": {}, "note": "sensitive column skipped"}
    provider = payload.get("provider", "ollama"); url = payload.get("url", ""); model = payload.get("model", "")
    where = classify_endpoint(provider, url, model)
    distinct = []
    for v in values:
        s = str(v).strip()
        if s and s.lower() not in ("nan", "none", "") and s not in distinct:
            distinct.append(s)
        if len(distinct) >= 60:
            break
    if len(distinct) < 3:
        return {"merges": {}, "where": where}
    prompt = ("These are distinct values from one column. Group variant spellings/casing of the "
              "SAME thing under one canonical value. Reply ONLY JSON: {\"merges\":{\"Canonical\":[\"variant1\",\"variant2\"]}}. "
              "Only include groups with a real duplicate; leave clean values out.\nValues: " + _json.dumps(distinct))
    res = ask(prompt, provider=provider, url=url, model=model, api_key=payload.get("api_key", ""), timeout=30)
    out = {"where": where, "ok": res.get("ok", False), "merges": {}}
    if res.get("error"): out["error"] = res["error"]
    if res.get("ok"):
        try:
            t = res.get("text", ""); s = t.index("{"); e = t.rindex("}") + 1
            obj = _json.loads(t[s:e]); m = obj.get("merges", {})
            out["merges"] = {k: v for k, v in m.items() if isinstance(v, list) and v}
        except Exception:
            pass
    return out


@app.post("/api/ai/review")
async def ai_review(payload: dict):
    """ONE whole-file AI pass, LOCAL ONLY. Body: {headers, sample, provider, url, model}.
    Masks sensitive columns, sends header + compact sample once, returns per-column verdicts."""
    from engine.ai_privacy import _mask, looks_sensitive
    from engine.ai_client import review
    headers = payload.get("headers", [])
    sample = payload.get("sample", [])[:15]
    masked = []
    for row in sample:
        mr = {}
        for k, v in (row or {}).items():
            mr[k] = _mask(str(v)) if looks_sensitive(str(k)) else v
        masked.append(mr)
    return review(headers, masked, provider=payload.get("provider", "ollama"),
                  url=payload.get("url", ""), model=payload.get("model", ""), api_key=payload.get("api_key", ""))


def _store_path():
    from pathlib import Path as _P
    d = _P(os.environ.get("PREP_HOME") or (_P.home() / ".1864prep"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "app_state.json"


@app.get("/api/local_state")
async def get_local_state():
    """Desktop/local only: the app's saved state (setup, owner, AI settings).
    Kept in a file in the user's home folder so it survives restarts, because
    the browser storage is tied to a port that changes on every launch.
    The hosted demo never stores anything here."""
    if os.environ.get("PREP_DEMO"):
        return {}
    import json as _json
    try:
        return _json.loads(_store_path().read_text())
    except Exception:
        return {}


@app.post("/api/local_state")
async def set_local_state(payload: dict):
    if os.environ.get("PREP_DEMO"):
        return {"ok": False, "note": "demo does not store state"}
    import json as _json
    p = _store_path()
    clean = {k: v for k, v in (payload or {}).items()
             if isinstance(k, str) and k.startswith("prep_") and isinstance(v, str)}
    tmp = p.with_suffix(".tmp")
    tmp.write_text(_json.dumps(clean))
    try:
        os.chmod(tmp, 0o600)   # only this user can read it (it can hold an API key)
    except Exception:
        pass
    tmp.replace(p)
    return {"ok": True, "keys": len(clean)}


@app.get("/api/config")
async def api_config():
    """Front-end reads this at boot. On the hosted demo (PREP_DEMO=1) the app
    starts fresh each load; the local desktop app (PREP_DESKTOP=1) saves downloads
    straight to the Downloads folder instead of relying on a browser download."""
    return {"demo": bool(os.environ.get("PREP_DEMO")), "desktop": bool(os.environ.get("PREP_DESKTOP"))}


@app.post("/api/save_to_disk")
async def api_save_to_disk(payload: dict):
    """Desktop only: write a result to the user's Downloads folder and return the
    path, so downloads work reliably inside the native window."""
    rid = payload.get("result_id"); fmt = (payload.get("fmt") or "xlsx").lower()
    item = _RESULTS.get(rid)
    if not item:
        return {"error": "result expired; produce the file again"}
    from pathlib import Path as _P
    dl = _P.home() / "Downloads"
    dl.mkdir(parents=True, exist_ok=True)
    title = (payload.get("name") or item.get("title") or "cleaned").replace(" ", "_")
    import engine.exporters as ex
    try:
        if item.get("multi"):
            out = dl / "All_cleaned_sheets.xlsx"; ex.to_xlsx_multi(item["multi"], out)
        else:
            df = item["df"]
            if fmt == "csv":   out = dl / f"{title}.csv";  df.to_csv(out, index=False)
            elif fmt == "docx": out = dl / f"{title}.docx"; ex.to_docx(item.get("title","Cleaned data"), df, out)
            else:              out = dl / f"{title}.xlsx"; ex.to_xlsx(df, out)
        return {"saved": str(out), "folder": str(dl)}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/health")
async def health():
    return {"ok": True}


# --- cancellable jobs: a job registers a token; the clean loop checks it ---
_CANCELLED: set[str] = set()


@app.post("/api/job/{job_id}/cancel")
async def cancel_job(job_id: str):
    """Mark a running clean/tool job as cancelled. Long loops check this and stop
    cleanly, so a user can abandon a big file mid-way."""
    _CANCELLED.add(job_id)
    return {"job_id": job_id, "cancelled": True}


def _is_cancelled(job_id: str | None) -> bool:
    return bool(job_id) and job_id in _CANCELLED


@app.post("/api/structure")
async def api_structure(payload: dict):
    """Header-review-first: return the full structure + per-column identity for a
    file so the person can confirm names/types/orientation BEFORE value cleaning.
    Body: {path} (server-side) or a prior session_id."""
    import pandas as pd
    from engine.ingest import read_any
    from engine.headers import propose_headers, abnormal_count
    from engine import domains as _D
    from engine.context import DatasetContext, ColumnContext
    path = payload.get("path")
    sid = payload.get("session_id")
    if sid and sid in _SESSIONS:
        df = _SESSIONS[sid]["df"]; rep = _SESSIONS[sid].get("rep")
    elif path:
        df, rep = read_any(path)
    else:
        return {"error": "provide path or session_id"}
    profs = profile_dataframe(df, use_ml=True)
    doms = [_D.detect_domain(df[c].tolist(), str(c)) for c in df.columns]
    headers = propose_headers(df, profs, doms)
    ctx = DatasetContext(
        source=str(path or sid), file_type=(getattr(rep, "kind", "") if rep else ""),
        sheet_name=(getattr(rep, "sheet", "") if rep else ""),
        sheets_all=(getattr(rep, "sheets_found", []) if rep else []),
        structure={"notes": (getattr(rep, "notes", []) if rep else []),
                   "header_row": (getattr(rep, "header_row", None) if rep else None)},
    )
    for p, h, d in zip(profs, headers, doms):
        exp = {}
        if d: exp["allowed_set"] = d
        ctx.columns.append(ColumnContext(
            raw_header=h["original"], proposed_name=h["suggested"],
            semantic_type=p.semantic_type, expected=exp,
            evidence=f"confidence {round(p.confidence,2)}",
            context_note=(f"looks like {d}" if d else p.semantic_type)).to_dict())
    return {"dataset": ctx.to_dict(), "headers_abnormal": abnormal_count(headers)}


@app.post("/api/distribution")
async def api_distribution(payload: dict):
    """See-your-distribution: pass {rows} for one dataset, or {raw, clean} for a
    before/after reveal. Returns chart-ready histograms, mean/median, outliers."""
    import pandas as pd
    from engine.distribution import distribution_profile, before_after
    if "raw" in payload and "clean" in payload:
        raw = pd.DataFrame(payload["raw"]); clean = pd.DataFrame(payload["clean"])
        return before_after(raw, clean)
    rows = payload.get("rows")
    sid = payload.get("session_id")
    if sid and sid in _SESSIONS:
        df = _SESSIONS[sid]["df"]
    elif rows is not None:
        df = pd.DataFrame(rows)
    else:
        return {"error": "provide rows, session_id, or raw+clean"}
    return {"columns": distribution_profile(df)}


@app.get("/api/tool/{name}/flow")
async def tool_flow(name: str):
    """The ordered, tool-specific steps the interface should render for this tool."""
    from engine.flows import get_flow
    from engine.toolkit import TOOLS
    if name not in TOOLS:
        return {"error": f"unknown tool {name!r}"}
    title, desc, kind = TOOLS[name]
    return {"tool": name, "title": title, "output": kind, "steps": get_flow(name)}


@app.post("/api/tool/outliers/evaluate")
async def tool_outlier_evaluate(payload: dict):
    """The 'look at the spread' step: per-column distribution read-out."""
    import pandas as pd
    from engine.toolkit import outlier_evaluate
    rows = payload.get("rows"); cols = payload.get("columns")
    sid = payload.get("session_id")
    if sid and sid in _SESSIONS:
        df = _SESSIONS[sid]["df"]
    elif rows is not None:
        df = pd.DataFrame(rows)
    else:
        return {"error": "provide session_id or rows"}
    return {"columns": outlier_evaluate(df, cols)}


@app.post("/api/tool/duplicates/confusion")
async def tool_dupe_confusion(payload: dict):
    """The 'check confusing columns' step before finalising duplicates."""
    import pandas as pd
    from engine.toolkit import dedupe_confusion
    rows = payload.get("rows"); subset = payload.get("columns")
    sid = payload.get("session_id")
    if sid and sid in _SESSIONS:
        df = _SESSIONS[sid]["df"]
    elif rows is not None:
        df = pd.DataFrame(rows)
    else:
        return {"error": "provide session_id or rows"}
    return {"warnings": dedupe_confusion(df, subset)}


# --- AI assist (optional, off by default; the base tool is fully offline) ---
@app.get("/api/ai/status")
async def ai_status():
    """The interface uses this to show an online/offline switch. AI assist is
    off unless a key is present AND the user turns it on; enabling it goes
    online, and only small per-column samples are ever sent."""
    import os
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    return {
        "available": has_key,
        "enabled_by_default": False,
        "offline_by_default": True,
        "banner": ("AI assist is available. Turning it on goes online and sends "
                   "only a few sample values from one column at a time, never your dataset."),
        "what_is_sent": "One column's distinct sample values (optionally masked). Never full rows, never row counts.",
    }


@app.post("/api/ai/preview")
async def ai_preview(payload: dict):
    """Show EXACTLY what would be sent for one column, without sending anything.
    Body: {column, values:[...], task?, mode?}. Returns the safe request."""
    from engine.ai_privacy import build_column_query, is_full_dataset
    column = payload.get("column", "")
    values = payload.get("values", [])
    if not isinstance(values, list):
        return {"error": "values must be a list from a single column"}
    q = build_column_query(column, values, task=payload.get("task", "type"), mode=payload.get("mode"))
    q["single_column_guaranteed"] = not is_full_dataset(q)
    return q


@app.get("/test")
async def test_page():
    """Feature scoreboard. Served fresh so it always reflects the latest code."""
    try:
        import sys as _sys
        root = str(Path(__file__).resolve().parents[1])
        if root not in _sys.path:
            _sys.path.insert(0, root)
        from tests.benchmark import run_benchmark, build_page
        from fastapi.responses import HTMLResponse
        return HTMLResponse(build_page(run_benchmark()))
    except Exception:
        page = UI_DIR / "test.html"          # fall back to the last generated file
        if page.exists():
            return FileResponse(str(page))
        return JSONResponse(status_code=500, content={"error": "benchmark unavailable"})


@app.post("/api/benchmark")
async def api_benchmark():
    import sys as _sys
    root = str(Path(__file__).resolve().parents[1])
    if root not in _sys.path:
        _sys.path.insert(0, root)
    from tests.benchmark import run_benchmark
    return {"results": run_benchmark()}


_NOCACHE = {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache", "Expires": "0"}


@app.get("/")
async def root():
    index = UI_DIR / "1864_prep_app.html"
    if index.exists():
        # Never let a browser hold a stale copy of the app — always serve fresh.
        return FileResponse(str(index), headers=_NOCACHE)
    return JSONResponse({"service": "1864 Prep engine", "ui": "not bundled",
                         "try": ["/api/health", "/api/profile", "/api/clean", "/test"]})


# serve any other UI assets (e.g. cleaning_review.html) under /ui
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
