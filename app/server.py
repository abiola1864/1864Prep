"""A thin web service around the cleaning engine.

Used two ways from ONE codebase:
  * deploy to Render (or any host) for a live demo — synthetic data only;
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
import regions as _regions
_regions.set_active_region(os.environ.get("PREP_REGION", "generic"))
from engine.review import column_overview, spotcheck

app = FastAPI(title="1864 Prep engine", version="0.1")

UI_DIR = Path(__file__).resolve().parents[1] / "prototype" / "ui"


def _save(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload").suffix or ".csv"
    tmp = Path(tempfile.mkstemp(suffix=suffix)[1])
    tmp.write_bytes(upload.file.read())
    return tmp



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
async def api_profile(file: UploadFile = File(...), region: str = Form(None)):
    if region:
        _regions.set_active_region(region)
    path = _save(file)
    try:
        df, rep = read_any(path)
        _ref = _regions.load_reference()
        profs = profile_dataframe(df, _ref["gazetteers"], _ref["place_index"], use_ml=True, use_nlp=True)
        return {
            "ingest": rep.summary(),
                "skipped_rows": rep.skipped_rows, "header_row": rep.header_row,
            "region": _regions.get_active_region().name,
            "rows": len(df), "cols": len(df.columns),
            "columns": [{"name": p.column, "type": p.semantic_type,
                         "confidence": round(p.confidence, 2)} for p in profs],
        }
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
        return {
            "ingest": rep.summary(),
                "skipped_rows": rep.skipped_rows, "header_row": rep.header_row,
            "region": _regions.get_active_region().name,
            "session_id": sid,
            "overview": column_overview(df, cleaned, types, flags),
            "spotcheck": spotcheck(df, cleaned, pool_size=40, seed=1),
            "worklist": {"flagged": flagged, "duplicates": dups, "duplicates_total": _dup_total, "similar": similar,
                         "repeated_columns": duplicate_columns(df)},
        }
    except Exception as e:  # never 500 silently in a demo
        return JSONResponse(status_code=422, content={"error": str(e)})
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/clean_stream")
async def api_clean_stream(file: UploadFile = File(...), region: str = Form(None)):
    """Same as /api/clean but streams real progress (one tick per column) so the
    bar reflects the actual workload instead of an estimate."""
    if region:
        _regions.set_active_region(region)
    path = _save(file)
    fname = file.filename

    def gen():
        import json
        import uuid as _uuid
        from engine.profile import profile_column, profile_to_plan
        from engine.dedupe import cluster_similar, duplicate_columns, near_duplicate_rows
        try:
            yield json.dumps({"t": "progress", "pct": 0.04, "stage": "Reading the file"}) + "\n"
            df, rep = read_any(path)
            _ref = _regions.load_reference()
            cols = list(df.columns); N = max(1, len(cols))
            profs = []
            for i, c in enumerate(cols):
                profs.append(profile_column(df[c], c, _ref["gazetteers"], _ref["place_index"], use_ml=True, use_nlp=True))
                if i % 2 == 0 or i == N - 1:
                    yield json.dumps({"t": "progress", "pct": 0.05 + 0.75 * (i + 1) / N,
                                      "stage": f"Checking column {i+1} of {N}"}) + "\n"
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
            _dup_groups = near_duplicate_rows(df)
            _dup_total = sum(len(g["rows"]) - 1 for g in _dup_groups)
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
                    gs = cluster_similar(df[p.column].tolist(), domain=_dom)[:20]
                    if gs:
                        similar.append({"column": p.column,
                                        "groups": [{"representative": g["representative"], "members": g["members"][:20],
                                                    "size": g["size"], "confidence": g["confidence"], "score": g["score"]} for g in gs]})
                if k % 2 == 0 or k == M - 1:
                    yield json.dumps({"t": "progress", "pct": 0.88 + 0.10 * (k + 1) / M,
                                      "stage": f"Finding matches ({k+1} of {M})"}) + "\n"
            sid = _uuid.uuid4().hex[:12]
            _SESSIONS[sid] = {"df": df, "types": types, "plan": plan}
            payload = {
                "ingest": rep.summary(),
                "skipped_rows": rep.skipped_rows, "header_row": rep.header_row,
                "region": _regions.get_active_region().name,
                "session_id": sid,
                "overview": column_overview(df, cleaned, types, flags),
                "spotcheck": spotcheck(df, cleaned, pool_size=40, seed=1),
                "worklist": {"flagged": flagged, "duplicates": dups, "duplicates_total": _dup_total, "similar": similar,
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


_RESULTS: dict = {}
_SESSIONS: dict = {}


@app.post("/api/export")
async def api_export(session_id: str = Form(...), decisions: str = Form("{}")):
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
    rejected = set(dec.get("reject", []))
    setall = dec.get("setall", {}) or {}
    merges = dec.get("merges", []) or []
    remove_dupes = bool(dec.get("remove_duplicates"))

    audit = []
    # 1) apply the plan, minus rejected columns (those pass through unchanged)
    kept = {"name": plan.get("name", "auto"),
            "mappings": [m for m in plan["mappings"] if m["source_column"] not in rejected]}
    cleaned, report, _ = run_plan(df, kept, "export")
    for c in report.columns:
        if c.get("changed"):
            audit.append({"column": c["source_column"], "action": f"cleaned ({c['transform']})",
                          "count": c["changed"]})
    for col in rejected:
        audit.append({"column": col, "action": "kept original (your choice)", "count": ""})

    # 2) set-all / flagged fixes
    for col, val in setall.items():
        if col in cleaned.columns:
            n = int((cleaned[col].astype(str) != str(val)).sum())
            cleaned[col] = val
            audit.append({"column": col, "action": f"set all to '{val}'", "count": n})

    # 3) confirmed similar-value merges
    for mg in merges:
        col, into, members = mg.get("column"), mg.get("into"), set(mg.get("members", []))
        if col in cleaned.columns and into and members:
            mask = cleaned[col].astype(str).isin(members)
            n = int(mask.sum())
            cleaned.loc[mask, col] = into
            audit.append({"column": col, "action": f"merged {len(members)} spellings into '{into}'", "count": n})

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
async def api_tool_download(rid: str, fmt: str = "csv"):
    import tempfile
    from pathlib import Path
    from engine import exporters as ex
    item = _RESULTS.get(rid)
    if not item:
        return JSONResponse(status_code=404, content={"error": "result expired; run the tool again"})
    ext = {"csv": "csv", "xlsx": "xlsx", "excel": "xlsx", "docx": "docx", "word": "docx"}.get(fmt.lower(), "csv")
    out = Path(tempfile.mkdtemp()) / f"{item['title'].replace(' ', '_')}.{ext}"
    ex.export(item["df"], fmt, out, title=item["title"], intro="Generated by 1864 Prep — Data Toolkit.")
    media = {"csv": "text/csv",
             "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}[ext]
    from fastapi.responses import FileResponse as _FR
    return _FR(str(out), media_type=media, filename=out.name)


@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/")
async def root():
    index = UI_DIR / "1864_prep_app.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"service": "1864 Prep engine", "ui": "not bundled",
                         "try": ["/api/health", "/api/profile", "/api/clean"]})


# serve any other UI assets (e.g. cleaning_review.html) under /ui
if UI_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
