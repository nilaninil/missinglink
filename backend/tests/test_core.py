"""Database, embeddings, FAISS, scoring rules, ranking and re-ranking."""
import numpy as np
from PIL import Image
from conftest import CASE, ids


def test_db_seeded(fresh):
    cases = fresh.get("/api/cases").json()
    assert {c["id"] for c in cases} >= {"MC-2026-0001", "MC-2026-0002"}
    recs = fresh.get("/api/records").json()
    assert len(recs) == 14


def test_embedding_normalised_and_deterministic():
    from app.services import synth
    from app.services.embedding_service import embed_image
    from app.database.seed import AARAV
    im = synth.person_card(AARAV)
    a, b = embed_image(im), embed_image(im)
    assert abs(np.linalg.norm(a) - 1) < 1e-3
    assert np.allclose(a, b)


def test_faiss_self_retrieval(fresh):
    from app.services import vector_search
    from app.services.vector_search import load_vector
    assert vector_search.count() == 13
    hits = vector_search.search(load_vector(3), 3)   # embedding 3 = FR-0002
    assert hits[0][0] == 3 and hits[0][1] > 0.99


def test_scores_capped_and_missing_is_not_mismatch(fresh):
    res = fresh.post(f"/api/match/{CASE}").json()
    for c in res["candidates"]:
        assert c["overall_score"] <= 0.99
        for f in c["factors"]:
            if f["status"] == "unavailable":
                assert f["score"] is None
    no_photo = next(c for c in res["candidates"] if c["record_id"] == "FR-0007")
    photo = next(f for f in no_photo["factors"] if f["name"] == "photo")
    assert photo["status"] == "unavailable"
    assert no_photo["coverage"] < 7


def test_initial_ranking_and_conflicts(fresh):
    res = fresh.post(f"/api/match/{CASE}").json()
    order = ids(res)
    assert order[:3] == ["FR-0001", "FR-0002", "FR-0003"]
    fr4 = next(c for c in res["candidates"] if c["record_id"] == "FR-0004")
    assert fr4["critical_conflict"] and fr4["band"] == "conflict"
    # conflicted records rank after every uncontradicted one
    first_conflict = min(c["rank"] for c in res["candidates"] if c["critical_conflict"])
    assert all(c["rank"] < first_conflict for c in res["candidates"] if not c["critical_conflict"])


def test_hospital_log_reranks_true_counterpart_to_first(fresh):
    fresh.post(f"/api/match/{CASE}")
    o = fresh.post("/api/ocr/sample/kilpauk_ambulance_log").json()
    r = fresh.post("/api/ocr/attach", json={"case_id": CASE, "fields": o["fields"], "document_type": o["document_type"],
                                            "source_org_id": o.get("source_org_id")}).json()
    assert ids(r)[0] == "FR-0003"
    moved = next(m for m in r["rank_changes"] if m["record_id"] == "FR-0003")
    assert moved["old_rank"] == 3 and moved["new_rank"] == 1
    assert "FR-0003" in (r["explanation"] or "")
    hist = fresh.get(f"/api/match/{CASE}/history").json()
    assert len(hist) == 2


def test_new_factor_can_be_enabled(fresh):
    before = fresh.post(f"/api/match/{CASE}").json()
    assert not any(f["name"] == "occupation" for f in before["candidates"][0]["factors"])   # disabled by default
    r = fresh.put("/api/config/weights", json={"weights": {"occupation": 0.2}, "rerun_case_id": CASE}).json()
    assert r["weights"]["occupation"] == 0.2
    fr2 = next(c for c in r["result"]["candidates"] if c["record_id"] == "FR-0002")
    f = next(f for f in fr2["factors"] if f["name"] == "occupation")
    assert f["status"] == "available" and f["score"] > 0.5   # both "student"
    fresh.post("/api/config/weights/reset")
