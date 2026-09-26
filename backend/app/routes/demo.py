"""Guided demo: every step calls the real services."""
import json
from datetime import datetime
from fastapi import APIRouter, Depends
from PIL import Image
from app.config.settings import SAMPLE_DOCS_DIR, MEDIA_DIR, DATA_DIR
from app.database.db import get_session, SessionLocal
from app.models.orm import MissingCase, CCTVSighting, BodyScan
from app.services import body_scan, matching_engine
from app.services.evidence_service import LAST_RESULTS, run_and_cache, add_evidence
from .common import ApiError
from . import media_ops, cases as cases_routes

router = APIRouter()
CASE = "MC-2026-0001"
STATE = {}


@router.post("/demo/reset")
def reset():
    from app.database import seed as seed_mod
    need_assets = not (SAMPLE_DOCS_DIR / "kilpauk_ambulance_log.png").exists() or \
        not (DATA_DIR / "sample_scans" / "field_capture.png").exists()
    seed_mod.seed(generate_assets=need_assets)
    LAST_RESULTS.clear(); STATE.clear()
    return {"ok": True}


@router.post("/demo/step/{n}")
def step(n: int, s=Depends(get_session)):
    if n == 1:
        s.close()
        reset()
        with SessionLocal() as s2:
            return {"step": 1, "title": "Case loaded", "case": cases_routes.case_dict(s2.get(MissingCase, CASE))}
    if n == 2:
        res = run_and_cache(s, CASE, "Local visual matching (FAISS)")
        return {"step": 2, "title": "Local visual matching", "retrieval": res["retrieval"],
                "timings_ms": res["timings_ms"], "note": res["retrieval_note"]}
    res = LAST_RESULTS.get(CASE) or run_and_cache(s, CASE, "Local visual matching (FAISS)")
    if n == 3:
        return {"step": 3, "title": "Ranked candidates", "result": res}
    if n == 4:
        return {"step": 4, "title": "Why this match?", "candidate": res["candidates"][0]}
    if n == 5:
        o = media_ops.ocr_sample("kilpauk_ambulance_log")
        STATE["ocr"] = o
        return {"step": 5, "title": "Scanned ambulance log read locally", "ocr": o}
    if n == 6:
        o = STATE.get("ocr") or media_ops.ocr_sample("kilpauk_ambulance_log")
        r = media_ops.ocr_attach({"case_id": CASE, "fields": o["fields"], "document_type": o["document_type"],
                                  "source_org_id": o.get("source_org_id")}, None, s)
        return {"step": 6, "title": "Automatic re-ranking", "result": r}
    if n == 7:
        c = media_ops.cctv_sample({"case_id": CASE}, s)
        attached = None
        if c["sightings"]:
            best = max(c["sightings"], key=lambda x: x["visual_similarity"])
            attached = media_ops.cctv_attach(best["id"], None, s)
        return {"step": 7, "title": "CCTV potential sighting", "cctv": c, "result": attached}
    if n == 8:
        cap = DATA_DIR / "sample_scans" / "field_capture.png"
        case = s.get(MissingCase, CASE)
        r = body_scan.analyse(Image.open(MEDIA_DIR / case.photo_path).convert("RGB"), Image.open(cap).convert("RGB"))
        rel = "scans/demo_field_capture.png"
        Image.open(cap).save(MEDIA_DIR / rel)
        bs = BodyScan(case_id=CASE, reference_path=case.photo_path, scan_path=rel, overall_score=r["overall_score"],
                      band=r["band"], result_json=json.dumps(r))
        s.add(bs); s.commit()
        r.update({"scan_id": bs.id, "scan_url": f"/media/{rel}", "reference_url": f"/media/{case.photo_path}"})
        att = media_ops.scan_attach(bs.id, {"case_id": CASE, "linked_record_id": "FR-0003", "locality": "Kilpauk",
                                            "observed_datetime": "2026-09-25T21:30", "gender": "Male",
                                            "clothing_text": "Blue shirt, black trousers",
                                            "notes": "Volunteer scan at Kilpauk casualty ward."}, None, s)
        return {"step": 8, "title": "Field body-scan at hospital", "scan": r, "result": att}
    if n == 9:
        return {"step": 9, "title": "Evidence timeline & ranking history",
                "timeline": cases_routes.case_timeline(CASE, s), "history": matching_engine.history(s, CASE)}
    raise ApiError("bad_step", "Unknown demo step.", 404)
