"""Retrieval (FAISS or attribute filters) -> multi-factor scoring -> ranking -> diff."""
import json
import time
from sqlalchemy import func
from app.config.settings import TOP_K
from app.config.match_weights import get_weights
from app.models.orm import FoundRecord, MissingCase, MatchResult, FaissMap, Organization
from app.services import vector_search, profile_builder, timeline
from app.services.embedding_service import encoder_key, encoder_name
from app.services.factors.base import MatchContext
from app.services.scoring import score_pair


class NotFound(Exception):
    pass


def _prefilter_ok(p, rv):
    if p.gender and rv.gender and p.gender.lower() != rv.gender.lower():
        return False
    if p.age_min is not None and rv.age_min is not None:
        if max(0, rv.age_min - p.age_max, p.age_min - rv.age_max) > 10:
            return False
    return True


def record_summary(rec, orgs, role="investigator"):
    org = orgs.get(rec.source_org_id)
    care = rec.care_location_detail
    if role == "volunteer":
        care = None
    return {"id": rec.id, "record_type": rec.record_type, "age_min": rec.age_min, "age_max": rec.age_max,
            "gender": rec.gender, "locality": rec.locality, "care_location_detail": care,
            "found_datetime": rec.found_datetime.isoformat() if rec.found_datetime else None,
            "clothing_text": rec.clothing_text, "description": rec.description,
            "photo_url": f"/media/{rec.photo_path}" if rec.photo_path else None,
            "photo_quality": rec.photo_quality,
            "photo_warnings": json.loads(rec.photo_warnings) if rec.photo_warnings else [],
            "source_org": org.name if org else None, "source_org_type": org.type if org else None,
            "sync_status": rec.sync_status}


def run_match(s, case_id: str, trigger: str = "Manual search", trigger_label: str = None, role="investigator"):
    t0 = time.perf_counter()
    case = s.get(MissingCase, case_id)
    if not case:
        raise NotFound(f"Case {case_id} not found.")
    profile = profile_builder.build(s, case)
    ctx = MatchContext(encoder_key=encoder_key(), weights=get_weights())
    records = s.query(FoundRecord).all()
    by_id = {r.id: r for r in records}
    views = {r.id: profile_builder.record_view(r, profile) for r in records}
    t1 = time.perf_counter()

    photo_ok = profile.photo_vec is not None and profile.photo_quality != "unusable"
    search_ms = 0.0
    if photo_ok:
        ts = time.perf_counter()
        hits = vector_search.search(profile.photo_vec, TOP_K)
        search_ms = (time.perf_counter() - ts) * 1000
        emap = {m.embedding_id: m.entity_id for m in s.query(FaissMap).filter(FaissMap.entity_type == "found_record")}
        visual_ids = [emap[i] for i, _ in hits if i in emap and emap[i] in by_id]
        # Records whose photo cannot be represented fairly (missing / low quality) are
        # added through attribute filters so visual retrieval never silently drops them.
        attr_ids = [rid for rid, rv in views.items() if rid not in visual_ids and
                    (rv.photo_vec is None or rv.photo_quality in ("low", "unusable")) and _prefilter_ok(profile, rv)]
        linked_ids = [rid for rid in profile.linked if rid in by_id and rid not in visual_ids and rid not in attr_ids]
        cand_ids = visual_ids + attr_ids + linked_ids
        n_photo = sum(1 for rv in views.values() if rv.photo_vec is not None)
        path = {"mode": "faiss",
                "text": f"Visual retrieval via FAISS (top {len(visual_ids)} of {n_photo} photo records)"
                        + (f" + {len(attr_ids)} low-quality/no-photo records via attribute filters" if attr_ids else "")
                        + (f" + {len(linked_ids)} evidence-linked" if linked_ids else ""),
                "visual_count": len(visual_ids), "attribute_count": len(attr_ids), "total_records": len(records)}
    else:
        cand_ids = [rid for rid, rv in views.items() if _prefilter_ok(profile, rv)]
        for rid in profile.linked:
            if rid in by_id and rid not in cand_ids:
                cand_ids.append(rid)
        path = {"mode": "attributes",
                "text": f"No usable photo — candidates retrieved by attribute filters ({len(cand_ids)} of {len(records)} records)",
                "visual_count": 0, "attribute_count": len(cand_ids), "total_records": len(records)}
    t2 = time.perf_counter()

    scored = [score_pair(profile, views[rid], ctx) for rid in cand_ids]
    # A critical contradiction (gender / time) is a real conflict: such records are listed
    # after every uncontradicted candidate, then by score.
    scored.sort(key=lambda r: (r["critical_conflict"], -r["raw_score"], r["record_id"]))
    t3 = time.perf_counter()

    prev_run = s.query(func.max(MatchResult.run_id)).filter(MatchResult.case_id == case_id).scalar()
    run_id = (prev_run or 0) + 1
    prev = {}
    if prev_run:
        for m in s.query(MatchResult).filter(MatchResult.case_id == case_id, MatchResult.run_id == prev_run):
            prev[m.record_id] = {"rank": m.rank, "factors": {f["name"]: f for f in json.loads(m.factor_json)}}

    orgs = {o.id: o for o in s.query(Organization).all()}
    for i, r in enumerate(scored, 1):
        r["rank"] = i
        r["previous_rank"] = prev.get(r["record_id"], {}).get("rank")
        r["record"] = record_summary(by_id[r["record_id"]], orgs, role)
        s.add(MatchResult(case_id=case_id, record_id=r["record_id"], run_id=run_id, rank=i,
                          overall_score=r["overall_score"], band=r["band"], factor_json=json.dumps(r["factors"]),
                          coverage=r["coverage"], trigger=trigger))

    rank_changes, explanation = [], None
    if prev:
        for r in scored:
            old = prev.get(r["record_id"])
            if old and old["rank"] != r["rank"]:
                deltas = {}
                for f in r["factors"]:
                    o = old["factors"].get(f["name"])
                    before = (o["score"] or 0) if o and o["status"] != "unavailable" else 0.0
                    after = (f["score"] or 0) if f["status"] != "unavailable" else 0.0
                    if abs(after - before) > 0.005:
                        deltas[f["name"]] = {"delta": round(after - before, 3),
                                             "newly_available": (not o or o["status"] == "unavailable") and f["status"] != "unavailable"}
                rank_changes.append({"record_id": r["record_id"], "old_rank": old["rank"], "new_rank": r["rank"],
                                     "factor_deltas": deltas})
        if rank_changes:
            mover = sorted(rank_changes, key=lambda c: (c["new_rank"] - c["old_rank"], c["new_rank"]))[0]
            if mover["new_rank"] < mover["old_rank"]:
                explanation = _explain(mover, trigger_label or trigger)
                timeline.add_event(s, case_id, "ranking", "Ranking updated", explanation)
    s.commit()
    t4 = time.perf_counter()
    return {"case_id": case_id, "run_id": run_id, "trigger": trigger, "retrieval": path,
            "retrieval_note": "FAISS retrieves visually similar candidates first, reducing the number of records that need detailed comparison.",
            "encoder": encoder_name(), "profile": profile_builder.profile_summary(profile),
            "timings_ms": {"profile": round((t1 - t0) * 1000, 1), "search": round(search_ms, 2),
                           "retrieval": round((t2 - t1) * 1000, 1), "scoring": round((t3 - t2) * 1000, 1),
                           "total": round((t4 - t0) * 1000, 1)},
            "candidates": scored, "rank_changes": rank_changes, "explanation": explanation}


def _explain(ch, label):
    parts = []
    corr = False
    for name, d in sorted(ch["factor_deltas"].items(), key=lambda kv: -kv[1]["delta"]):
        if d["delta"] <= 0:
            continue
        if name == "corroboration":
            corr = True
            continue
        parts.append(f"{name} ({'+' if d['delta'] >= 0 else ''}{d['delta']:.2f}{', newly available' if d['newly_available'] else ''})")
    parts = parts[:3]
    txt = f"Candidate {ch['record_id']} moved from #{ch['old_rank']} to #{ch['new_rank']}"
    if parts:
        txt += f" because the new {label.lower()} provided stronger " + ", ".join(parts[:-1]) + \
               (" and " if len(parts) > 1 else "") + parts[-1] + " compatibility"
    if corr:
        txt += (", and " if parts else " because the new evidence ") + "directly corroborates this record"
    return txt + "."


def history(s, case_id):
    rows = s.query(MatchResult).filter(MatchResult.case_id == case_id).order_by(MatchResult.run_id, MatchResult.rank).all()
    runs = {}
    for m in rows:
        r = runs.setdefault(m.run_id, {"run_id": m.run_id, "trigger": m.trigger,
                                       "created_at": m.created_at.isoformat(), "ranks": {}, "scores": {}})
        r["ranks"][m.record_id] = m.rank
        r["scores"][m.record_id] = m.overall_score
    return list(runs.values())
