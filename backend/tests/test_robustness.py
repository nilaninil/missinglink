"""Invalid input, offline behaviour and forbidden wording."""
import re
from pathlib import Path
from conftest import CASE

FORBIDDEN = ["identity confirmed", "person identified", "identified by ai", "100% match", "confirmed match"]


def test_invalid_image_rejected(fresh):
    r = fresh.post("/api/match/image", files={"photo": ("x.jpg", b"not an image", "image/jpeg")})
    assert r.status_code in (400, 415, 422)
    assert "error" in r.json()


def test_wrong_file_type_rejected(fresh):
    r = fresh.post("/api/cases", files={"photo": ("x.exe", b"MZ....", "application/octet-stream")}, data={"name": "Test"})
    assert r.status_code in (400, 415, 422)


def test_empty_case_rejected(fresh):
    r = fresh.post("/api/cases", data={})
    assert r.status_code == 422
    assert r.json()["error"]["message"] == "Insufficient information for matching."


def test_unknown_case_404(fresh):
    r = fresh.post("/api/match/MC-9999-9999")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_partial_case_still_matches(fresh):
    r = fresh.post("/api/cases", data={"clothing_text": "green saree", "gender": "Female"}).json()
    assert r["partial"]
    res = fresh.post(f"/api/match/{r['case']['id']}").json()
    assert res["candidates"]


def test_offline_mode_marks_pending_and_syncs(fresh):
    fresh.post("/api/system/offline", json={"offline": True})
    res = fresh.post(f"/api/match/{CASE}")
    assert res.status_code == 200                          # core matching works offline
    c = fresh.post("/api/cases", data={"name": "Offline Test", "clothing_text": "red shirt"}).json()
    assert c["case"]["sync_status"] == "pending_sync"
    assert fresh.get("/api/sync/status").json()["pending_total"] >= 1
    assert fresh.post("/api/sync/run").status_code == 409  # cannot sync while offline
    fresh.post("/api/system/offline", json={"offline": False})
    j = fresh.post("/api/sync/run").json()
    assert j["synced"] >= 1 and j["hub_rows"] >= 1
    assert fresh.get("/api/sync/status").json()["pending_total"] == 0
    fresh.post("/api/system/offline", json={"offline": None})


def test_no_forbidden_language_in_ui_or_api(fresh):
    root = Path(__file__).resolve().parents[2] / "frontend"
    for p in list(root.rglob("*.js")) + list(root.rglob("*.html")):
        text = p.read_text(encoding="utf-8").lower()
        for w in FORBIDDEN:
            assert w not in text, f"'{w}' found in {p.name}"
    blobs = [fresh.post(f"/api/match/{CASE}").text]
    for n in range(1, 10):
        blobs.append(fresh.post(f"/api/demo/step/{n}").text)
    body = " ".join(blobs).lower()
    for w in FORBIDDEN:
        assert w not in body, f"'{w}' in API response"
