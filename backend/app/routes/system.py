from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Body
from sqlalchemy import func
from app.database.db import get_session
from app.config.match_weights import get_weights, set_weights, reset_weights, BANDS
from app.config.settings import TOP_K
from app.models.orm import MissingCase, FoundRecord, Evidence, MatchResult, Organization, ReviewFlag
from app.services import connectivity, vector_search, sync_service, ocr_service
from app.services.embedding_service import encoder_name
from app.services.evidence_service import LAST_RESULTS, run_and_cache

router = APIRouter()


@router.get("/system/status")
def status(s=Depends(get_session)):
    try:
        s.query(MissingCase).count(); db_ok = True
    except Exception:
        db_ok = False
    st = connectivity.status()
    return {**st, "encoder": encoder_name(), "faiss_count": vector_search.count(), "db_ok": db_ok,
            "ocr_engine": ocr_service.engine_name(), "pending_sync": sum(sync_service.pending(s).values())}


@router.post("/system/offline")
def set_offline(body: dict = Body(...)):
    v = body.get("offline")
    connectivity.set_simulated(None if v is None else bool(v))
    return connectivity.status()


@router.get("/dashboard/stats")
def stats(s=Depends(get_session)):
    active = s.query(MissingCase).filter(MissingCase.status.in_(["open", "under_review"])).count()
    potential = 0
    for (cid,) in s.query(MissingCase.id):
        last = s.query(func.max(MatchResult.run_id)).filter(MatchResult.case_id == cid).scalar()
        if last:
            potential += s.query(MatchResult).filter(MatchResult.case_id == cid, MatchResult.run_id == last,
                                                     MatchResult.band.in_(["high_priority", "possible", "conflict"])).count()
    since = datetime.now() - timedelta(hours=24)
    new_ev = s.query(Evidence).filter(Evidence.created_at >= since).count()
    pending_ver = s.query(Evidence).filter(Evidence.needs_verification.is_(True)).count() + \
        s.query(ReviewFlag).filter(ReviewFlag.decision == "needs_review").count()
    pend = sync_service.pending(s)
    orgs = []
    for o in s.query(Organization):
        n = s.query(FoundRecord).filter(FoundRecord.source_org_id == o.id).count()
        if n:
            orgs.append({"name": o.name, "type": o.type, "records": n})
    return {"active_cases": active, "potential_matches": potential, "new_evidence_24h": new_ev,
            "pending_verification": pending_ver, "pending_sync": sum(pend.values()),
            "found_records": s.query(FoundRecord).count(), "org_breakdown": sorted(orgs, key=lambda x: -x["records"])}


@router.get("/organizations")
def organizations(s=Depends(get_session)):
    return [{"id": o.id, "name": o.name, "type": o.type, "locality": o.locality} for o in s.query(Organization)]


@router.get("/config/weights")
def weights():
    return {"weights": get_weights(), "bands": BANDS, "top_k": TOP_K}


@router.put("/config/weights")
def put_weights(body: dict = Body(...), s=Depends(get_session)):
    w = set_weights(body.get("weights") or {})
    rerun = None
    case_id = body.get("rerun_case_id")
    if case_id and s.get(MissingCase, case_id):
        rerun = run_and_cache(s, case_id, "Weights changed in Settings")
    return {"weights": w, "result": rerun}


@router.post("/config/weights/reset")
def reset():
    reset_weights()
    return {"weights": get_weights()}


@router.get("/sync/status")
def sync_status(s=Depends(get_session)):
    p = sync_service.pending(s)
    online = connectivity.is_online()
    return {"online": online, "pending": p, "pending_total": sum(p.values()), "hub_rows": sync_service.hub_count(),
            "message": (f"Sync Available ({sum(p.values())} records)" if online and sum(p.values()) else
                        "Offline — records will sync when connectivity returns." if not online else "Everything is synced.")}


@router.post("/sync/run")
def sync_run(s=Depends(get_session)):
    if not connectivity.is_online():
        from .common import ApiError
        raise ApiError("offline", "Cannot sync while offline. Records are safe locally and marked Pending Sync.", 409)
    n = sync_service.run(s)
    return {"synced": n, "hub_rows": sync_service.hub_count()}


@router.get("/localities")
def localities():
    from app.services.gazetteer import LOCALITIES
    return sorted(LOCALITIES.keys())
