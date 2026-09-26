import json
from app.models.orm import Evidence, MissingCase, Organization
from app.services import timeline, connectivity, matching_engine
from app.services.profile_builder import EVIDENCE_LABELS

LAST_RESULTS = {}  # case_id -> last full match payload (for UI refresh without a new run)


def run_and_cache(s, case_id, trigger="Manual search", trigger_label=None, role="investigator"):
    res = matching_engine.run_match(s, case_id, trigger, trigger_label, role)
    LAST_RESULTS[case_id] = res
    return res


def add_evidence(s, case_id, f: dict, role="investigator"):
    case = s.get(MissingCase, case_id)
    if not case:
        raise matching_engine.NotFound(f"Case {case_id} not found.")
    etype = f.get("evidence_type") or "investigator_note"
    ev = Evidence(case_id=case_id, evidence_type=etype, source_org_id=f.get("source_org_id"),
                  observed_datetime=f.get("observed_datetime"), locality=f.get("locality"),
                  age_min=f.get("age_min"), age_max=f.get("age_max"), gender=f.get("gender"),
                  clothing_text=f.get("clothing_text"), linked_record_id=f.get("linked_record_id") or None,
                  ocr_confidence=f.get("ocr_confidence"), needs_verification=bool(f.get("needs_verification")),
                  payload_json=json.dumps(f.get("payload") or {}),
                  sync_status=connectivity.sync_status_for_new_rows())
    s.add(ev)
    org = s.get(Organization, f["source_org_id"]) if f.get("source_org_id") else None
    label = EVIDENCE_LABELS.get(etype, etype)
    bits = [b for b in [f.get("locality"), f.get("observed_datetime") and f["observed_datetime"].strftime("%d %b %H:%M"),
                        f.get("clothing_text"), f.get("linked_record_id") and f"links to {f['linked_record_id']}"] if b]
    timeline.add_event(s, case_id, etype, f"{label} added" + (f" — {org.name}" if org else ""),
                       "; ".join(bits) or f.get("notes"), f.get("locality"), f.get("source_org_id"),
                       occurred_at=f.get("observed_datetime"))
    if case.status == "open":
        case.status = "under_review"
    s.commit()
    res = run_and_cache(s, case_id, trigger=f"{label} added", trigger_label=label, role=role)
    res["evidence_id"] = ev.id
    res["evidence_sync_status"] = ev.sync_status
    return res
