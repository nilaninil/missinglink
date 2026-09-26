from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Header
from app.config.settings import TOP_K
from app.database.db import get_session
from app.models.orm import FaissMap, FoundRecord, Organization
from app.services import vector_search, matching_engine, image_quality
from app.services.evidence_service import run_and_cache
from app.services.embedding_service import load_image, get_encoder, encoder_key, ImageProcessingError
from app.services.calibration import calibrate
from .common import ApiError, read_upload, MSG_BAD_IMAGE

router = APIRouter()


@router.post("/match/image")
async def match_image(photo: UploadFile = File(...), x_role: Optional[str] = Header(None), s=Depends(get_session)):
    data, _ = await read_upload(photo, "image")
    if not data:
        raise ApiError("invalid_image", MSG_BAD_IMAGE, 422)
    try:
        img = load_image(data)
    except ImageProcessingError:
        raise ApiError("invalid_image", MSG_BAD_IMAGE, 422)
    q = image_quality.assess(img)
    vec = get_encoder().embed(img)
    import time
    t = time.perf_counter()
    hits = vector_search.search(vec, TOP_K)
    ms = (time.perf_counter() - t) * 1000
    emap = {m.embedding_id: m.entity_id for m in s.query(FaissMap).filter(FaissMap.entity_type == "found_record")}
    orgs = {o.id: o for o in s.query(Organization)}
    out = []
    for eid, cos in hits:
        r = s.get(FoundRecord, emap.get(eid))
        if r:
            out.append({"record": matching_engine.record_summary(r, orgs, (x_role or "").lower()),
                        "visual_similarity": round(min(calibrate(cos, encoder_key()), 0.99), 4), "raw_cosine": round(cos, 4)})
    return {"quality": q, "results": out, "search_ms": round(ms, 2), "status_text": "Requires Human Verification"}


@router.post("/match/{case_id}")
def match_case(case_id: str, x_role: Optional[str] = Header(None), s=Depends(get_session)):
    try:
        return run_and_cache(s, case_id, "Manual search", role=(x_role or "investigator").lower())
    except matching_engine.NotFound as e:
        raise ApiError("not_found", str(e), 404)


@router.get("/match/{case_id}/history")
def match_history(case_id: str, s=Depends(get_session)):
    return matching_engine.history(s, case_id)
