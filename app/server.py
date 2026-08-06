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

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from engine.ingest import read_any
from engine.pipeline import run_plan
from engine.profile import profile_dataframe, profile_to_plan
from engine.review import column_overview, spotcheck

app = FastAPI(title="1864 Prep engine", version="0.1")

UI_DIR = Path(__file__).resolve().parents[1] / "prototype" / "ui"


def _save(upload: UploadFile) -> Path:
    suffix = Path(upload.filename or "upload").suffix or ".csv"
    tmp = Path(tempfile.mkstemp(suffix=suffix)[1])
    tmp.write_bytes(upload.file.read())
    return tmp


@app.post("/api/profile")
async def api_profile(file: UploadFile = File(...)):
    path = _save(file)
    try:
        df, rep = read_any(path)
        profs = profile_dataframe(df)
        return {
            "ingest": rep.summary(),
            "rows": len(df), "cols": len(df.columns),
            "columns": [{"name": p.column, "type": p.semantic_type,
                         "confidence": round(p.confidence, 2)} for p in profs],
        }
    finally:
        path.unlink(missing_ok=True)


@app.post("/api/clean")
async def api_clean(file: UploadFile = File(...)):
    path = _save(file)
    try:
        df, rep = read_any(path)
        profs = profile_dataframe(df)
        plan = profile_to_plan(profs, "auto")
        types = {p.column: p.semantic_type for p in profs}
        cleaned, report, _ = run_plan(df, plan, "web")
        flags = {c["source_column"]: c.get("flagged", 0) for c in report.columns}
        return {
            "ingest": rep.summary(),
            "overview": column_overview(df, cleaned, types, flags),
            "spotcheck": spotcheck(df, cleaned, pool_size=40, seed=1),
        }
    except Exception as e:  # never 500 silently in a demo
        return JSONResponse(status_code=422, content={"error": str(e)})
    finally:
        path.unlink(missing_ok=True)


@app.get("/api/health")
async def health():
    return {"ok": True}


# serve the prototype UI at / (mounted last so /api/* wins)
if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
