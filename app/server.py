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


@app.post("/api/profile")
async def api_profile(file: UploadFile = File(...), region: str = Form(None)):
    if region:
        _regions.set_active_region(region)
    path = _save(file)
    try:
        df, rep = read_any(path)
        _ref = _regions.load_reference()
        profs = profile_dataframe(df, _ref["gazetteers"], _ref["place_index"], use_ml=True)
        return {
            "ingest": rep.summary(),
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
        profs = profile_dataframe(df, _ref["gazetteers"], _ref["place_index"], use_ml=True)
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
        dups = []
        for g in near_duplicate_rows(df)[:50]:
            r0 = g["rows"][0]
            preview = " · ".join(str(v) for v in df.iloc[r0].tolist()[:4] if str(v).strip())
            dups.append({"rows": g["rows"], "kind": g["kind"],
                         "similarity": g["similarity"], "preview": preview})
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
        return {
            "ingest": rep.summary(),
            "region": _regions.get_active_region().name,
            "overview": column_overview(df, cleaned, types, flags),
            "spotcheck": spotcheck(df, cleaned, pool_size=40, seed=1),
            "worklist": {"flagged": flagged, "duplicates": dups, "similar": similar,
                         "repeated_columns": duplicate_columns(df)},
        }
    except Exception as e:  # never 500 silently in a demo
        return JSONResponse(status_code=422, content={"error": str(e)})
    finally:
        path.unlink(missing_ok=True)


@app.get("/api/regions")
async def api_regions():
    return {"active": _regions.get_active_region().key,
            "regions": [{"key": k, "name": _regions.get_region(k).name} for k in _regions.list_regions()]}


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
