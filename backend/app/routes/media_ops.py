"""Live body-scan, CCTV and OCR endpoints. Each degrades gracefully."""
import json
import logging
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, Body, Header
from PIL import Image
from app.config.settings import MEDIA_DIR, SAMPLE_CCTV_DIR, SAMPLE_DOCS_DIR, TOP_K
from app.database.db import get_session
from app.models.orm import MissingCase, BodyScan, CCTVSighting, FoundRecord, FaissMap, Organization
from app.services import body_scan, cctv_service, ocr_service, vector_search, profile_builder, connectivity, gazetteer
from app.services.embedding_service import load_image, ImageProcessingError, get_encoder, encoder_key
from app.services.calibration import calibrate
from app.services.evidence_service import add_evidence
from app.services.matching_engine import record_summary
from .common import ApiError, read_upload, parse_dt, parse_int, register_photo, MSG_BAD_IMAGE
from .cases import next_record_id

router = APIRouter()
log = logging.getLogger("missinglink.routes")


# ------------------------------------------------------------------ live body scan
@router.post("/scan/analyze")
async def scan_analyze(scan: UploadFile = File(...), reference: Optional[UploadFile] = File(None),
                       case_id: Optional[str] = Form(None), x_role: Optional[str] = Header(None),
                       s=Depends(get_session)):
    scan_bytes, _ = await read_upload(scan, "image")
    if not scan_bytes:
        raise ApiError("invalid_image", MSG_BAD_IMAGE, 422)
    ref_bytes, _ = await read_upload(reference, "image")
    case = s.get(MissingCase, case_id) if case_id else None
    if case_id and not case:
        raise ApiError("not_found", f"Case {case_id} not found.", 404)
    try:
        scan_img = load_image(scan_bytes)
        if ref_bytes:
            ref_img = load_image(ref_bytes)
        elif case and case.photo_path:
            ref_img = load_image(MEDIA_DIR / case.photo_path)
        else:
            raise ApiError("reference_required", "Add a reference photo of the missing person, or pick a case that has one.", 422)
    except ImageProcessingError:
        raise ApiError("invalid_image", MSG_BAD_IMAGE, 422)
    try:
        result = body_scan.analyse(ref_img, scan_img)
    except ImageProcessingError as e:
        which = "reference photo" if "reference" in str(e) else "scan"
        raise ApiError("invalid_image", f"The {which} is too dark or blurry to analyse. Please capture a clearer image.", 422)
    uid = uuid.uuid4().hex[:8]
    scan_rel, ref_rel = f"scans/scan_{uid}.png", None
    scan_img.save(MEDIA_DIR / scan_rel)
    if ref_bytes:
        ref_rel = f"scans/ref_{uid}.png"
        ref_img.save(MEDIA_DIR / ref_rel)
    elif case:
        ref_rel = case.photo_path
    # also look for similar existing found records (FAISS)
    similar = []
    try:
        vec = get_encoder().embed(scan_img)
        emap = {m.embedding_id: m.entity_id for m in s.query(FaissMap).filter(FaissMap.entity_type == "found_record")}
        orgs = {o.id: o for o in s.query(Organization)}
        for eid, cos in vector_search.search(vec, 3):
            r = s.get(FoundRecord, emap.get(eid))
            if r:
                similar.append({"record": record_summary(r, orgs, (x_role or "").lower()),
                                "visual_similarity": round(min(calibrate(cos, encoder_key()), 0.99), 3)})
    except Exception as e:  # never fail the scan because of this extra
        log.warning("similar-record lookup failed: %s", e)
    bs = BodyScan(case_id=case.id if case else None, reference_path=ref_rel, scan_path=scan_rel,
                  overall_score=result["overall_score"], band=result["band"], result_json=json.dumps(result))
    s.add(bs); s.commit()
    result.update({"scan_id": bs.id, "scan_url": f"/media/{scan_rel}",
                   "reference_url": f"/media/{ref_rel}" if ref_rel else None,
                   "case_id": bs.case_id, "similar_records": similar})
    return result


@router.post("/scan/{scan_id}/attach")
def scan_attach(scan_id: int, body: dict = Body(...), x_role: Optional[str] = Header(None), s=Depends(get_session)):
    bs = s.get(BodyScan, scan_id)
    if not bs:
        raise ApiError("not_found", "Scan not found.", 404)
    case_id = body.get("case_id") or bs.case_id
    if not case_id or not s.get(MissingCase, case_id):
        raise ApiError("case_required", "Choose the missing-person case this scan relates to.", 422)
    observed = parse_dt(body.get("observed_datetime")) or datetime.now().replace(microsecond=0)
    locality = body.get("locality") or None
    link = body.get("linked_record_id") or None
    if link and not s.get(FoundRecord, link):
        raise ApiError("unknown_record", f"Record {link} does not exist.", 422)
    amin, amax = parse_int(body.get("age_min")), parse_int(body.get("age_max"))
    created = None
    if not link:
        # create a new "sighting" found record with the scan photo so it enters retrieval + ranking
        rid = next_record_id(s)
        rec = FoundRecord(id=rid, record_type="sighting", age_min=amin, age_max=amax, gender=body.get("gender") or None,
                          locality=locality, found_datetime=observed, clothing_text=body.get("clothing_text") or None,
                          description=f"Field body-scan #{scan_id}. {body.get('notes') or ''}".strip(),
                          source_org_id=9, sync_status=connectivity.sync_status_for_new_rows())
        s.add(rec); s.flush()
        ph = register_photo(s, (MEDIA_DIR / bs.scan_path).read_bytes(), "records", "found_record", rid, True)
        rec.photo_path, rec.photo_quality, rec.embedding_id = ph["path"], ph["quality"], ph["embedding_id"]
        rec.photo_warnings = json.dumps(ph["warnings"])
        created = rid
    bs.case_id, bs.attached_record_id = case_id, link or created
    s.commit()
    res = add_evidence(s, case_id, {
        "evidence_type": "body_scan", "source_org_id": 9, "observed_datetime": observed, "locality": locality,
        "age_min": amin, "age_max": amax, "gender": body.get("gender") or None,
        "clothing_text": body.get("clothing_text") or None, "linked_record_id": link, "needs_verification": True,
        "payload": {"scan_id": scan_id, "visual_agreement": bs.overall_score, "created_record": created}},
        (x_role or "investigator").lower())
    res["created_record_id"] = created
    return res


# ------------------------------------------------------------------ CCTV
def _cctv_run(s, path, camera_name, locality, start, time_scale, case_id):
    case = s.get(MissingCase, case_id) if case_id else None
    if not case:
        raise ApiError("not_found", "Choose a case first — CCTV frames are compared with the case photo.", 422)
    from app.services.vector_search import load_vector
    vec = load_vector(case.embedding_id)
    if vec is None:
        raise ApiError("no_case_photo", "This case has no usable photo, so CCTV frames cannot be compared.", 422)
    last = profile_builder.build(s, case).latest.locality
    try:
        found, n = cctv_service.process(path, vec, camera_name, locality, start, time_scale, case_id, last)
    except Exception as e:
        log.warning("CCTV processing failed: %s", e)
        return {"sightings": [], "frames_analysed": 0,
                "message": "Video could not be fully processed; showing results from frames that were analysed."}
    out = []
    for f in found:
        row = CCTVSighting(case_id=case_id, camera_name=camera_name, locality=locality,
                           frame_datetime=datetime.fromisoformat(f["frame_datetime"]), frame_path=f["frame_path"],
                           crop_path=f["crop_path"], visual_similarity=f["visual_similarity"])
        s.add(row); s.flush()
        f["id"] = row.id
        out.append(f)
    s.commit()
    return {"sightings": out, "frames_analysed": n, "message": None if out else "No potential sightings above the similarity threshold.",
            "disclaimer": "This is a potential visual similarity for authorized investigation, not automatic identification."}


@router.post("/cctv/process")
async def cctv_process(video: UploadFile = File(...), camera_name: str = Form("Camera"), locality: str = Form(""),
                       start_datetime: str = Form(""), case_id: str = Form(""), s=Depends(get_session)):
    data, ext = await read_upload(video, "video")
    if not data:
        raise ApiError("empty_file", "Video file is empty.", 400)
    p = MEDIA_DIR / "uploads" / f"cctv_{uuid.uuid4().hex[:8]}{ext}"
    p.write_bytes(data)
    start = parse_dt(start_datetime) or datetime.now()
    return _cctv_run(s, p, camera_name, gazetteer.resolve(locality) or locality or None, start, 1.0, case_id)


@router.post("/cctv/sample")
def cctv_sample(body: dict = Body(...), s=Depends(get_session)):
    meta_p = SAMPLE_CCTV_DIR / "anna_nagar_checkpoint.json"
    if not meta_p.exists():
        raise ApiError("sample_missing", "Sample video not generated. Run the seed script.", 404)
    meta = json.loads(meta_p.read_text())
    return _cctv_run(s, SAMPLE_CCTV_DIR / "anna_nagar_checkpoint.mp4", meta["camera_name"], meta["locality"],
                     datetime.fromisoformat(meta["start_datetime"]), meta["time_scale"], body.get("case_id"))


@router.post("/cctv/{sighting_id}/attach")
def cctv_attach(sighting_id: int, x_role: Optional[str] = Header(None), s=Depends(get_session)):
    c = s.get(CCTVSighting, sighting_id)
    if not c:
        raise ApiError("not_found", "Sighting not found.", 404)
    if c.added_to_timeline:
        raise ApiError("already_added", "This sighting is already on the evidence timeline.", 409)
    c.added_to_timeline = True
    s.commit()
    return add_evidence(s, c.case_id, {"evidence_type": "cctv_sighting", "source_org_id": 1,
                                       "observed_datetime": c.frame_datetime, "locality": c.locality,
                                       "needs_verification": True,
                                       "payload": {"camera": c.camera_name, "similarity": c.visual_similarity,
                                                   "crop": c.crop_path}}, (x_role or "investigator").lower())


# ------------------------------------------------------------------ OCR
SAMPLE_DOCS = {"kilpauk_ambulance_log": "Kilpauk ambulance log", "anna_nagar_shelter_intake": "Shelter intake form",
               "partial_police_report": "Partial police report (low quality)"}


def _ocr_image(img, fallback_truth=None):
    rows = ocr_service.read_lines(img)
    if rows is None:
        if fallback_truth:
            f = {k: {"value": v, "confidence": 0.65, "needs_verification": True}
                 for k, v in _truth_to_fields(fallback_truth).items() if v}
            return {"engine": None, "fields": f, "document_type": fallback_truth.get("document_type", "ocr_document"),
                    "raw_text": "", "message": "OCR engine unavailable — fields loaded from the sample document's metadata. Please verify."}
        raise ApiError("ocr_unavailable", "OCR engine unavailable.", 503)
    fields, doc_type = ocr_service.extract_fields(rows)
    needs = any(v["needs_verification"] for v in fields.values()) or len(fields) < 3
    return {"engine": ocr_service.engine_name(), "fields": fields, "document_type": doc_type,
            "raw_text": "\n".join(t for t, _ in rows),
            "message": "Some fields require verification." if needs else "All fields read with good confidence."}


def _truth_to_fields(t):
    age = None
    if t.get("age_min") is not None:
        age = str((t["age_min"] + t["age_max"]) // 2)
    return {"age": age, "gender": t.get("gender"), "destination": t.get("locality"), "admitted": t.get("observed_time"),
            "pickup_location": t.get("pickup_locality"), "pickup_time": t.get("pickup_time"),
            "clothing": t.get("clothing"), "record_ref": t.get("linked_record_id")}


@router.get("/ocr/samples")
def ocr_samples():
    return [{"key": k, "label": v, "url": f"/samples/docs/{k}.png"} for k, v in SAMPLE_DOCS.items()
            if (SAMPLE_DOCS_DIR / f"{k}.png").exists()]


@router.post("/ocr/sample/{key}")
def ocr_sample(key: str):
    if key not in SAMPLE_DOCS or not (SAMPLE_DOCS_DIR / f"{key}.png").exists():
        raise ApiError("not_found", "Sample document not found.", 404)
    truth = json.loads((SAMPLE_DOCS_DIR / f"{key}.json").read_text())
    res = _ocr_image(Image.open(SAMPLE_DOCS_DIR / f"{key}.png"), truth)
    res["source_org_id"] = truth.get("org_id")
    res["image_url"] = f"/samples/docs/{key}.png"
    return res


@router.post("/ocr/extract")
async def ocr_extract(image: UploadFile = File(...)):
    data, _ = await read_upload(image, "image")
    if not data:
        raise ApiError("invalid_image", MSG_BAD_IMAGE, 422)
    try:
        img = load_image(data)
    except ImageProcessingError:
        raise ApiError("invalid_image", MSG_BAD_IMAGE, 422)
    return _ocr_image(img)


@router.post("/ocr/attach")
def ocr_attach(body: dict = Body(...), x_role: Optional[str] = Header(None), s=Depends(get_session)):
    case_id = body.get("case_id")
    if not case_id:
        raise ApiError("case_required", "Choose a case to attach this document to.", 422)
    fields = body.get("fields") or {}
    doc_type = body.get("document_type") or "ocr_document"
    ev = ocr_service.to_evidence(fields, doc_type)
    confs = [v.get("confidence", 1.0) for v in fields.values() if isinstance(v, dict)]
    needs = any(isinstance(v, dict) and v.get("needs_verification") and not v.get("edited") for v in fields.values())
    date = ev.get("date") or None

    def dt(hm):
        if not hm:
            return None
        return parse_dt(f"{date}T{hm}") if date and parse_dt(hm) else parse_dt(hm)
    link = ev.get("linked_record_id")
    if link and not s.get(FoundRecord, link):
        link = None
    obs = dt(ev.get("observed_time"))
    pk = dt(ev.get("pickup_time"))
    return add_evidence(s, case_id, {
        "evidence_type": doc_type if doc_type in ("hospital_record", "shelter_record", "investigator_note") else "ocr_document",
        "source_org_id": parse_int(body.get("source_org_id")), "observed_datetime": obs,
        "locality": ev.get("locality"), "age_min": ev.get("age_min"), "age_max": ev.get("age_max"),
        "gender": ev.get("gender"), "clothing_text": ev.get("clothing_text"), "linked_record_id": link,
        "ocr_confidence": round(min(confs), 3) if confs else None, "needs_verification": needs,
        "payload": {"pickup_locality": ev.get("pickup_locality"), "pickup_datetime": pk.isoformat() if pk else None,
                    "source": "ocr"}}, (x_role or "investigator").lower())
