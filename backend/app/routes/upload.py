"""Lightweight photo upload and cases.json persistence endpoints."""
import os
import re
import uuid
import logging
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from app.config.settings import FRONTEND_DIR, MEDIA_DIR, DATA_DIR, BACKEND_DIR
from app.routes.common import read_upload, ApiError
from app.services import json_persistence

router = APIRouter()
log = logging.getLogger("missinglink.upload")

PROJECT_ROOT = BACKEND_DIR.parent
PUBLIC_UPLOADS_DIR = PROJECT_ROOT / "public" / "uploads"
FRONTEND_UPLOADS_DIR = FRONTEND_DIR / "uploads"
BACKEND_UPLOADS_DIR = MEDIA_DIR / "uploads"

# Ensure all target upload directories exist
for d in [PUBLIC_UPLOADS_DIR, FRONTEND_UPLOADS_DIR, BACKEND_UPLOADS_DIR, DATA_DIR / "uploads"]:
    d.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_photo(file: UploadFile = File(...)):
    """Save uploaded missing/found person images directly into the local /public/uploads/ directory.
    Returns relative path e.g. /uploads/person_123.jpg.
    """
    data, ext = await read_upload(file, "image")
    if not data:
        raise ApiError("invalid_image", "Invalid or empty image file uploaded.", 400)
    
    orig_name = Path(file.filename or "photo.jpg").stem
    clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", orig_name) or "person"
    uid = uuid.uuid4().hex[:8]
    filename = f"{clean_name}_{uid}{ext or '.jpg'}"
    
    # Save to public uploads and frontend uploads
    for dest_dir in [PUBLIC_UPLOADS_DIR, FRONTEND_UPLOADS_DIR, BACKEND_UPLOADS_DIR, DATA_DIR / "uploads"]:
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / filename).write_bytes(data)
        except Exception as e:
            log.warning("Could not write upload to %s: %s", dest_dir, e)
            
    rel_path = f"/uploads/{filename}"
    log.info("Saved photo upload: %s (%d bytes)", rel_path, len(data))
    return {
        "url": rel_path,
        "path": rel_path,
        "filename": filename,
        "size": len(data)
    }


@router.get("/cases_json")
@router.get("/data/cases")
def get_cases_json():
    """Read from cases.json so created records are accessible directly."""
    return json_persistence.load_cases_json()
