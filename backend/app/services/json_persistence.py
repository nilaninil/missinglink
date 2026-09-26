"""Lightweight local JSON persistence for MissingLink cases, records, and photos."""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

log = logging.getLogger("missinglink.persistence")

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent

# Support multiple standard paths for cases.json so it is accessible wherever expected
PERSISTENCE_PATHS = [
    PROJECT_ROOT / "src" / "data" / "cases.json",
    BACKEND_DIR / "data" / "cases.json",
    PROJECT_ROOT / "frontend" / "data" / "cases.json",
    PROJECT_ROOT.parent / "src" / "data" / "cases.json"
]

def _ensure_dirs():
    for p in PERSISTENCE_PATHS:
        p.parent.mkdir(parents=True, exist_ok=True)

def load_cases_json() -> Dict[str, List[Dict[str, Any]]]:
    _ensure_dirs()
    for p in PERSISTENCE_PATHS:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "missing_cases" in data:
                        return data
                    elif isinstance(data, list):
                        return {"missing_cases": data, "found_records": []}
            except Exception as e:
                log.warning("Could not read %s: %s", p, e)
    return {"missing_cases": [], "found_records": []}

def save_cases_json(data: Dict[str, Any]):
    _ensure_dirs()
    for p in PERSISTENCE_PATHS:
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            log.warning("Could not write %s: %s", p, e)

def save_case(case_data: Dict[str, Any]):
    data = load_cases_json()
    cases = data.get("missing_cases", [])
    # Check if already present by id
    cid = case_data.get("id")
    found = False
    for i, c in enumerate(cases):
        if c.get("id") == cid:
            cases[i] = case_data
            found = True
            break
    if not found:
        cases.append(case_data)
    data["missing_cases"] = cases
    save_cases_json(data)
    log.info("Saved case %s to local cases.json persistence", cid)

def save_record(record_data: Dict[str, Any]):
    data = load_cases_json()
    records = data.get("found_records", [])
    rid = record_data.get("id")
    found = False
    for i, r in enumerate(records):
        if r.get("id") == rid:
            records[i] = record_data
            found = True
            break
    if not found:
        records.append(record_data)
    data["found_records"] = records
    save_cases_json(data)
    log.info("Saved record %s to local cases.json persistence", rid)

def sync_all_from_db(s):
    """Export all current DB cases and found records to cases.json."""
    from app.models.orm import MissingCase, FoundRecord, Organization
    from app.services.matching_engine import record_summary
    
    orgs = {o.id: o for o in s.query(Organization)}
    cases_out = []
    for c in s.query(MissingCase).order_by(MissingCase.created_at.desc()):
        org = orgs.get(c.reporting_org_id)
        photo_url = f"/media/{c.photo_path}" if c.photo_path else None
        # Also check if it's in uploads
        if c.photo_path and "uploads" in c.photo_path:
            photo_url = f"/uploads/{Path(c.photo_path).name}"
        cases_out.append({
            "id": c.id,
            "name": c.name,
            "age": c.age,
            "age_min": c.age_min,
            "age_max": c.age_max,
            "gender": c.gender,
            "last_seen_locality": c.last_seen_locality,
            "last_seen_datetime": c.last_seen_datetime.isoformat() if c.last_seen_datetime else None,
            "clothing_text": c.clothing_text,
            "description": c.description,
            "occupation": c.occupation,
            "photo_url": photo_url,
            "photo_path": c.photo_path,
            "photo_quality": c.photo_quality,
            "status": c.status,
            "reporting_org": org.name if org else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "sync_status": c.sync_status
        })
        
    records_out = []
    for r in s.query(FoundRecord).order_by(FoundRecord.id):
        records_out.append(record_summary(r, orgs, "investigator"))
        
    save_cases_json({
        "missing_cases": cases_out,
        "found_records": records_out
    })
    log.info("Synced %d cases and %d records to cases.json", len(cases_out), len(records_out))
