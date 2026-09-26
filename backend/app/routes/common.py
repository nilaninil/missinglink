"""Shared helpers: structured errors, upload validation, lenient dates, photo registration."""
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from sqlalchemy import func
from app.config.settings import (MEDIA_DIR, IMAGE_EXTS, VIDEO_EXTS, MAX_IMAGE_BYTES, MAX_VIDEO_BYTES, DEMO_DATE)
from app.models.orm import FaissMap
from app.services import image_quality, vector_search
from app.services.embedding_service import load_image, get_encoder, ImageProcessingError


class ApiError(Exception):
    def __init__(self, code, message, status=400, detail=None):
        self.code, self.message, self.status, self.detail = code, message, status, detail


MSG_BAD_IMAGE = "Unable to process image. Please upload a clearer image."
MSG_BAD_TYPE = "Unsupported file format."


async def read_upload(upload, kind="image"):
    if upload is None or not getattr(upload, "filename", None):
        return None, None
    ext = Path(upload.filename).suffix.lower()
    allowed = IMAGE_EXTS if kind == "image" else VIDEO_EXTS
    if ext not in allowed:
        raise ApiError("unsupported_format", MSG_BAD_TYPE, 415, f"Accepted: {', '.join(sorted(allowed))}")
    data = await upload.read()
    limit = MAX_IMAGE_BYTES if kind == "image" else MAX_VIDEO_BYTES
    if len(data) > limit:
        raise ApiError("file_too_large", f"File is larger than {limit // (1024*1024)} MB.", 413)
    if not data:
        raise ApiError("empty_file", MSG_BAD_IMAGE if kind == "image" else "Video file is empty.", 400)
    return data, ext


def parse_dt(v):
    """Lenient: '18:30' (assumes demo date), ISO, 'dd-mm-yyyy HH:MM'. Garbage -> None."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    v = str(v).strip()
    if not v:
        return None
    m = re.fullmatch(r"([01]?\d|2[0-3])[:.]([0-5]\d)", v)
    if m:
        return datetime.fromisoformat(f"{DEMO_DATE}T{int(m.group(1)):02d}:{m.group(2)}")
    try:
        return datetime.fromisoformat(v.replace("Z", ""))
    except ValueError:
        pass
    for fmt in ("%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            pass
    return None


def parse_int(v):
    try:
        return int(str(v).strip()) if v not in (None, "") else None
    except ValueError:
        return None


def next_embedding_id(s):
    m = s.query(func.max(FaissMap.embedding_id)).scalar()
    return (m or 0) + 1


def register_photo(s, data: bytes, subdir: str, entity_type: str, entity_id: str, add_to_index: bool):
    """Validate, quality-check, save, embed and (optionally) index a photo."""
    try:
        img = load_image(data)
    except ImageProcessingError:
        raise ApiError("invalid_image", MSG_BAD_IMAGE, 422)
    q = image_quality.assess(img)
    rel = f"{subdir}/{entity_id}_{uuid.uuid4().hex[:6]}.png"
    (MEDIA_DIR / subdir).mkdir(parents=True, exist_ok=True)
    img.save(MEDIA_DIR / rel)
    
    # Also save to /public/uploads/ and /frontend/uploads/ for lightweight static persistence
    try:
        from app.config.settings import FRONTEND_DIR, BACKEND_DIR
        upload_fname = f"{entity_id}_{Path(rel).name}"
        for u_dir in [FRONTEND_DIR / "uploads", BACKEND_DIR.parent / "public" / "uploads", MEDIA_DIR / "uploads"]:
            u_dir.mkdir(parents=True, exist_ok=True)
            img.save(u_dir / upload_fname)
    except Exception:
        pass
        
    emb_id = None
    if q["quality"] != "unusable":
        vec = get_encoder().embed(img)
        emb_id = next_embedding_id(s)
        vector_search.save_vector(emb_id, vec)
        s.add(FaissMap(embedding_id=emb_id, entity_type=entity_type, entity_id=entity_id))
        s.flush()
        if add_to_index:
            vector_search.add(emb_id, vec)
    return {"path": rel, "quality": q["quality"], "warnings": q["warnings"], "embedding_id": emb_id}
