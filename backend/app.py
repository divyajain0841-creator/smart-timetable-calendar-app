
import os
import uuid
import json
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .parser import parse_timetable, parse_academic_calendar

BASE = Path(__file__).resolve().parent.parent
UPLOADS = BASE / "uploads"
UPLOADS.mkdir(exist_ok=True)

app = FastAPI(title="Smart Timetable Calendar")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/app", StaticFiles(directory=BASE / "frontend", html=True), name="frontend")

@app.get("/")
def root():
    return FileResponse(BASE / "frontend" / "index.html")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/api/parse-academic-calendar")
async def academic_calendar(file: UploadFile = File(...)):
    data=await file.read()
    suffix=Path(file.filename or "").suffix.lower()
    path=UPLOADS / f"academic-{uuid.uuid4().hex}{suffix}"
    path.write_bytes(data)
    try:
        return parse_academic_calendar(path)
    except Exception as exc:
        raise HTTPException(422, f"Academic calendar parsing failed: {exc}") from exc

@app.post("/api/parse-timetable")
async def parse_endpoint(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    allowed = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
    if suffix not in allowed:
        raise HTTPException(400, "Upload PNG, JPG, JPEG, WEBP or PDF.")

    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(413, "File is larger than 25 MB.")

    path = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
    path.write_bytes(data)

    try:
        result = parse_timetable(path)
        result["file"] = file.filename
        return result
    except Exception as exc:
        raise HTTPException(422, f"Timetable parsing failed: {exc}") from exc

# Optional Google Calendar endpoints. They are activated when GOOGLE_CLIENT_ID
# and GOOGLE_CLIENT_SECRET are configured. The frontend also supports ICS
# export, which works without OAuth.
from .calendar_api import google_router
app.include_router(google_router, prefix="/api/google")

@app.post("/api/export-ics")
def export_ics(payload: dict = Body(...)):
    from .calendar_api import build_ics
    ics = build_ics(payload)
    out = UPLOADS / f"timetable-{uuid.uuid4().hex}.ics"
    out.write_text(ics, encoding="utf-8")
    return FileResponse(out, filename="timetable.ics", media_type="text/calendar")
