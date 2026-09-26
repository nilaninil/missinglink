"""Build the working profile of a missing person from the case + attached evidence."""
import json
from app.models.orm import Evidence, Organization
from app.services import clothing as cl, gazetteer
from app.services.vector_search import load_vector
from app.services.factors.base import CaseProfile, Observation, RecordView

EVIDENCE_LABELS = {"hospital_record": "Hospital record", "cctv_sighting": "CCTV potential sighting",
                   "ocr_document": "Scanned document", "investigator_note": "Investigator note",
                   "shelter_record": "Shelter record", "body_scan": "Field body-scan"}


def case_age_range(case):
    if case.age_min is not None and case.age_max is not None:
        return case.age_min, case.age_max
    if case.age is not None:
        return case.age - 2, case.age + 2
    return None, None


def build(s, case) -> CaseProfile:
    amin, amax = case_age_range(case)
    origin = Observation(case.last_seen_datetime, gazetteer.resolve(case.last_seen_locality) or case.last_seen_locality,
                         "last seen (original report)")
    p = CaseProfile(case_id=case.id, name=case.name, age_min=amin, age_max=amax, gender=case.gender,
                    clothing_items=cl.parse(case.clothing_text), origin=origin, observations=[origin],
                    photo_vec=load_vector(case.embedding_id), photo_quality=case.photo_quality,
                    occupation=case.occupation)
    orgs = {o.id: o for o in s.query(Organization).all()}
    evs = s.query(Evidence).filter(Evidence.case_id == case.id).order_by(Evidence.id).all()
    for e in evs:
        label = EVIDENCE_LABELS.get(e.evidence_type, e.evidence_type)
        org = orgs.get(e.source_org_id)
        payload = json.loads(e.payload_json) if e.payload_json else {}
        if e.age_min is not None and e.age_max is not None:
            if p.age_min is None:
                p.age_min, p.age_max = e.age_min, e.age_max
            else:
                lo, hi = max(p.age_min, e.age_min), min(p.age_max, e.age_max)
                if lo <= hi:
                    p.age_min, p.age_max = lo, hi
                else:
                    p.notes.append(f"{label} age {e.age_min}–{e.age_max} conflicts with case range; case range kept.")
        if not p.gender and e.gender:
            p.gender = e.gender
        p.clothing_items = cl.merge(p.clothing_items, cl.parse(e.clothing_text))
        # optional earlier waypoint (e.g. ambulance pickup) stored in payload
        pk_loc, pk_time = payload.get("pickup_locality"), payload.get("pickup_datetime")
        if pk_loc and pk_time:
            from datetime import datetime
            try:
                t = datetime.fromisoformat(pk_time)
                if origin.time is None or t >= origin.time:
                    p.observations.append(Observation(t, gazetteer.resolve(pk_loc) or pk_loc, f"{label} pickup"))
            except ValueError:
                pass
        if e.observed_datetime and e.locality and (origin.time is None or e.observed_datetime >= origin.time):
            p.observations.append(Observation(e.observed_datetime, gazetteer.resolve(e.locality) or e.locality, label))
        if e.linked_record_id:
            p.linked.setdefault(e.linked_record_id, []).append({
                "label": label, "org_type": org.type if org else None, "org_name": org.name if org else None,
                "needs_verification": e.needs_verification, "age_min": e.age_min, "age_max": e.age_max,
                "gender": e.gender, "clothing_text": e.clothing_text})
    return p


def record_view(rec, profile: CaseProfile) -> RecordView:
    rv = RecordView(id=rec.id, record_type=rec.record_type, age_min=rec.age_min, age_max=rec.age_max,
                    gender=rec.gender, clothing_items=cl.parse(rec.clothing_text),
                    locality=gazetteer.resolve(rec.locality) or rec.locality, time=rec.found_datetime,
                    photo_vec=load_vector(rec.embedding_id), photo_quality=rec.photo_quality,
                    occupation=rec.occupation)
    for e in profile.linked.get(rec.id, []):
        if rv.age_min is None and e["age_min"] is not None:
            rv.age_min, rv.age_max = e["age_min"], e["age_max"]
            rv.enrichments.append(f"Age {e['age_min']}–{e['age_max']} taken from linked {e['label'].lower()}.")
        if not rv.gender and e["gender"]:
            rv.gender = e["gender"]
            rv.enrichments.append(f"Gender taken from linked {e['label'].lower()}.")
        extra = cl.parse(e["clothing_text"])
        merged = cl.merge(rv.clothing_items, extra)
        if merged != rv.clothing_items:
            rv.enrichments.append(f"Clothing detail from linked {e['label'].lower()}: {cl.describe(extra)}.")
            rv.clothing_items = merged
    return rv


def profile_summary(p: CaseProfile) -> dict:
    lt = p.latest
    return {"age_range": [p.age_min, p.age_max] if p.age_min is not None else None, "gender": p.gender,
            "clothing": cl.describe(p.clothing_items), "last_known_locality": lt.locality,
            "last_known_time": lt.time.isoformat() if lt.time else None, "last_known_source": lt.source,
            "linked_records": list(p.linked.keys()), "notes": p.notes,
            "observations": [{"time": o.time.isoformat() if o.time else None, "locality": o.locality, "source": o.source}
                             for o in sorted(p.observations, key=lambda o: o.time or lt.time)]}
