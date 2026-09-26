import json
from typing import Optional
from fastapi import APIRouter, Depends, UploadFile, File, Form, Header, Body
from sqlalchemy import func
from app.database.db import get_session
from app.models.orm import (MissingCase, FoundRecord, Evidence, TimelineEvent, MatchResult, ReviewFlag,
                            Organization, CCTVSighting, BodyScan)
from app.services import connectivity, timeline, profile_builder, gazetteer, json_persistence
from app.services.evidence_service import add_evidence, LAST_RESULTS
from app.services.matching_engine import record_summary
from .common import ApiError, read_upload, parse_dt, parse_int, register_photo

router = APIRouter()


def role_of(x_role):
    return (x_role or "investigator").lower()


def case_dict(c, orgs=None):
    org = orgs.get(c.reporting_org_id) if orgs else None
    return {"id": c.id, "name": c.name, "age": c.age, "age_min": c.age_min, "age_max": c.age_max, "gender": c.gender,
            "last_seen_locality": c.last_seen_locality,
            "last_seen_datetime": c.last_seen_datetime.isoformat() if c.last_seen_datetime else None,
            "clothing_text": c.clothing_text, "description": c.description, "occupation": c.occupation,
            "photo_url": f"/media/{c.photo_path}" if c.photo_path else None, "photo_quality": c.photo_quality,
            "photo_warnings": json.loads(c.photo_warnings) if c.photo_warnings else [],
            "status": c.status, "reporting_org": org.name if org else None,
            "created_at": c.created_at.isoformat() if c.created_at else None, "sync_status": c.sync_status}


def event_dict(e, orgs):
    o = orgs.get(e.org_id)
    return {"id": e.id, "case_id": e.case_id, "event_type": e.event_type, "title": e.title, "detail": e.detail,
            "locality": e.locality, "org": o.name if o else None, "occurred_at": e.occurred_at.isoformat()}


@router.get("/cases")
def list_cases(s=Depends(get_session)):
    orgs = {o.id: o for o in s.query(Organization)}
    out = []
    for c in s.query(MissingCase).order_by(MissingCase.created_at.desc()):
        d = case_dict(c, orgs)
        last = s.query(func.max(MatchResult.run_id)).filter(MatchResult.case_id == c.id).scalar()
        top = None
        if last:
            m = s.query(MatchResult).filter(MatchResult.case_id == c.id, MatchResult.run_id == last,
                                            MatchResult.rank == 1).first()
            if m:
                top = {"record_id": m.record_id, "score": m.overall_score, "band": m.band, "coverage": m.coverage}
        d["top_candidate"] = top
        d["evidence_count"] = s.query(Evidence).filter(Evidence.case_id == c.id).count()
        out.append(d)
    return out


@router.post("/cases")
async def create_case(name: Optional[str] = Form(None), age: Optional[str] = Form(None),
                      age_min: Optional[str] = Form(None), age_max: Optional[str] = Form(None),
                      gender: Optional[str] = Form(None), last_seen_locality: Optional[str] = Form(None),
                      last_seen_datetime: Optional[str] = Form(None), clothing_text: Optional[str] = Form(None),
                      description: Optional[str] = Form(None), occupation: Optional[str] = Form(None),
                      reporting_org_id: Optional[str] = Form(None), photo: Optional[UploadFile] = File(None),
                      s=Depends(get_session)):
    data, _ = await read_upload(photo, "image")
    name = (name or "").strip() or None
    clothing_text = (clothing_text or "").strip() or None
    if not (data or name or clothing_text):
        raise ApiError("insufficient_information", "Insufficient information for matching.", 422,
                       "Provide at least a photo, a name or a clothing description.")
    n = s.query(MissingCase).count() + 1
    cid = f"MC-2026-{n:04d}"
    while s.get(MissingCase, cid):
        n += 1; cid = f"MC-2026-{n:04d}"
    a = parse_int(age)
    lo, hi = parse_int(age_min), parse_int(age_max)
    if a is not None and lo is None:
        lo, hi = a - 2, a + 2
    c = MissingCase(id=cid, name=name, age=a, age_min=lo, age_max=hi, gender=(gender or None),
                    last_seen_locality=last_seen_locality or None, last_seen_datetime=parse_dt(last_seen_datetime),
                    clothing_text=clothing_text, description=description, occupation=occupation or None,
                    reporting_org_id=parse_int(reporting_org_id), status="open",
                    sync_status=connectivity.sync_status_for_new_rows())
    warnings = []
    if data:
        ph = register_photo(s, data, "cases", "missing_case", cid, add_to_index=False)
        c.photo_path, c.photo_quality, c.embedding_id = ph["path"], ph["quality"], ph["embedding_id"]
        c.photo_warnings = json.dumps(ph["warnings"])
        warnings += ph["warnings"]
        if ph["quality"] == "unusable":
            warnings.append("Photo unusable — matching will use attribute filters.")
    if last_seen_locality and not gazetteer.resolve(last_seen_locality):
        warnings.append("Locality not in offline gazetteer — location factor will be unavailable.")
    if last_seen_datetime and not c.last_seen_datetime:
        warnings.append("Could not read the last-seen date/time — time factor will be unavailable.")
    s.add(c)
    timeline.add_event(s, cid, "report", "Missing report filed", f"Case {cid} created.",
                       c.last_seen_locality, c.reporting_org_id)
    s.commit()
    try:
        orgs = {o.id: o for o in s.query(Organization)}
        json_persistence.save_case(case_dict(c, orgs))
    except Exception as e:
        pass
    partial = not (c.photo_path and c.age_min is not None and c.gender and c.last_seen_locality and c.last_seen_datetime)
    return {"case": case_dict(c), "warnings": warnings,
            "message": "Partial information received." if partial else "Case created.", "partial": partial}


@router.get("/cases/{case_id}")
def get_case(case_id: str, x_role: Optional[str] = Header(None), s=Depends(get_session)):
    c = s.get(MissingCase, case_id)
    if not c:
        raise ApiError("not_found", f"Case {case_id} not found.", 404)
    orgs = {o.id: o for o in s.query(Organization)}
    prof = profile_builder.build(s, c)
    evs = []
    for e in s.query(Evidence).filter(Evidence.case_id == case_id).order_by(Evidence.id):
        o = orgs.get(e.source_org_id)
        evs.append({"id": e.id, "evidence_type": e.evidence_type, "label": profile_builder.EVIDENCE_LABELS.get(e.evidence_type, e.evidence_type),
                    "source_org": o.name if o else None, "locality": e.locality,
                    "observed_datetime": e.observed_datetime.isoformat() if e.observed_datetime else None,
                    "clothing_text": e.clothing_text, "age_min": e.age_min, "age_max": e.age_max, "gender": e.gender,
                    "linked_record_id": e.linked_record_id, "needs_verification": e.needs_verification,
                    "ocr_confidence": e.ocr_confidence, "sync_status": e.sync_status,
                    "payload": json.loads(e.payload_json or "{}")})
    flags = [{"record_id": f.record_id, "role": f.flagged_by_role, "decision": f.decision, "note": f.note,
              "created_at": f.created_at.isoformat()} for f in s.query(ReviewFlag).filter(ReviewFlag.case_id == case_id)]
    cctv = [{"id": x.id, "camera_name": x.camera_name, "locality": x.locality,
             "frame_datetime": x.frame_datetime.isoformat() if x.frame_datetime else None,
             "crop_url": f"/media/{x.crop_path}" if x.crop_path else None, "visual_similarity": x.visual_similarity,
             "added_to_timeline": x.added_to_timeline} for x in s.query(CCTVSighting).filter(CCTVSighting.case_id == case_id)]
    scans = [{"id": b.id, "overall_score": b.overall_score, "band": b.band, "scan_url": f"/media/{b.scan_path}",
              "attached_record_id": b.attached_record_id, "created_at": b.created_at.isoformat()}
             for b in s.query(BodyScan).filter(BodyScan.case_id == case_id)]
    return {"case": case_dict(c, orgs), "profile": profile_builder.profile_summary(prof), "evidence": evs,
            "flags": flags, "cctv_sightings": cctv, "body_scans": scans, "last_result": LAST_RESULTS.get(case_id)}


@router.get("/cases/{case_id}/timeline")
def case_timeline(case_id: str, s=Depends(get_session)):
    orgs = {o.id: o for o in s.query(Organization)}
    rows = s.query(TimelineEvent).filter(TimelineEvent.case_id == case_id).order_by(TimelineEvent.occurred_at).all()
    return [event_dict(e, orgs) for e in rows]


@router.get("/timeline")
def global_timeline(limit: int = 40, s=Depends(get_session)):
    orgs = {o.id: o for o in s.query(Organization)}
    rows = s.query(TimelineEvent).order_by(TimelineEvent.id.desc()).limit(limit).all()
    return [event_dict(e, orgs) for e in rows]


@router.post("/cases/{case_id}/evidence")
def post_evidence(case_id: str, body: dict = Body(...), x_role: Optional[str] = Header(None), s=Depends(get_session)):
    f = dict(body)
    f["observed_datetime"] = parse_dt(f.get("observed_datetime"))
    for k in ("age_min", "age_max", "source_org_id"):
        f[k] = parse_int(f.get(k))
    if f.get("age") and f.get("age_min") is None:
        a = parse_int(f.get("age"))
        if a is not None:
            f["age_min"], f["age_max"] = a - 2, a + 2
    if f.get("linked_record_id") and not s.get(FoundRecord, f["linked_record_id"]):
        raise ApiError("unknown_record", f"Record {f['linked_record_id']} does not exist.", 422)
    if not any(f.get(k) for k in ("locality", "observed_datetime", "age_min", "gender", "clothing_text", "linked_record_id")):
        raise ApiError("insufficient_information", "Insufficient information for matching.", 422,
                       "Evidence needs at least one of: locality, time, age, gender, clothing or a linked record.")
    return add_evidence(s, case_id, f, role_of(x_role))


@router.get("/records")
def list_records(x_role: Optional[str] = Header(None), s=Depends(get_session)):
    orgs = {o.id: o for o in s.query(Organization)}
    return [record_summary(r, orgs, role_of(x_role)) for r in s.query(FoundRecord).order_by(FoundRecord.id)]


@router.get("/records/{record_id}")
def get_record(record_id: str, x_role: Optional[str] = Header(None), s=Depends(get_session)):
    r = s.get(FoundRecord, record_id)
    if not r:
        raise ApiError("not_found", f"Record {record_id} not found.", 404)
    return record_summary(r, {o.id: o for o in s.query(Organization)}, role_of(x_role))


def next_record_id(s):
    ids = [int(r.id.split("-")[1]) for r in s.query(FoundRecord.id) if r.id.startswith("FR-")]
    return f"FR-{(max(ids) if ids else 0) + 1:04d}"


@router.post("/records")
async def create_record(record_type: str = Form("found"), age_min: Optional[str] = Form(None),
                        age_max: Optional[str] = Form(None), age: Optional[str] = Form(None),
                        gender: Optional[str] = Form(None), locality: Optional[str] = Form(None),
                        found_datetime: Optional[str] = Form(None), clothing_text: Optional[str] = Form(None),
                        description: Optional[str] = Form(None), care_location_detail: Optional[str] = Form(None),
                        occupation: Optional[str] = Form(None), source_org_id: Optional[str] = Form(None),
                        photo: Optional[UploadFile] = File(None), s=Depends(get_session)):
    data, _ = await read_upload(photo, "image")
    rid = next_record_id(s)
    lo, hi = parse_int(age_min), parse_int(age_max)
    a = parse_int(age)
    if a is not None and lo is None:
        lo, hi = a - 2, a + 2
    if record_type not in ("found", "unidentified_patient", "shelter_resident", "sighting"):
        record_type = "found"
    r = FoundRecord(id=rid, record_type=record_type, age_min=lo, age_max=hi, gender=gender or None,
                    locality=locality or None, found_datetime=parse_dt(found_datetime),
                    clothing_text=clothing_text or None, description=description or None,
                    care_location_detail=care_location_detail or None, occupation=occupation or None,
                    source_org_id=parse_int(source_org_id), sync_status=connectivity.sync_status_for_new_rows())
    warnings = []
    s.add(r); s.flush()
    if data:
        ph = register_photo(s, data, "records", "found_record", rid, add_to_index=True)
        r.photo_path, r.photo_quality, r.embedding_id = ph["path"], ph["quality"], ph["embedding_id"]
        r.photo_warnings = json.dumps(ph["warnings"])
        warnings += ph["warnings"]
    usable = any([r.embedding_id, r.age_min is not None, r.gender, r.clothing_text, r.locality, r.found_datetime])
    s.commit()
    try:
        orgs = {o.id: o for o in s.query(Organization)}
        json_persistence.save_record(record_summary(r, orgs, "investigator"))
    except Exception as e:
        pass
    msg = "Record saved." if usable else "Insufficient information for matching."
    if usable and not (r.photo_path and r.age_min is not None and r.locality and r.found_datetime):
        msg = "Partial information received."
    return {"record": record_summary(r, {o.id: o for o in s.query(Organization)}), "message": msg,
            "draft": not usable, "warnings": warnings}


@router.post("/review/flag")
def flag(body: dict = Body(...), s=Depends(get_session)):
    if not body.get("case_id") or not body.get("record_id"):
        raise ApiError("bad_request", "case_id and record_id are required.", 422)
    decision = body.get("decision") or "needs_review"
    if decision not in ("needs_review", "verified_by_investigator", "rejected", "more_information"):
        decision = "needs_review"
    f = ReviewFlag(case_id=body["case_id"], record_id=body["record_id"], flagged_by_role=body.get("role", "investigator"),
                   decision=decision, note=body.get("note"))
    s.add(f)
    titles = {"needs_review": "Marked for human review", "verified_by_investigator": "Investigator verification recorded",
              "rejected": "Candidate rejected by investigator", "more_information": "More information requested"}
    timeline.add_event(s, body["case_id"], "review", f"{titles[decision]}: {body['record_id']}", body.get("note"))
    s.commit()
    return {"ok": True, "decision": decision}
