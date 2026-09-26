"""Body scan, OCR and CCTV services."""
from PIL import Image
from conftest import CASE, ids


def _img(path):
    from app.config.settings import MEDIA_DIR
    return Image.open(MEDIA_DIR / path).convert("RGB")


def test_body_scan_orders_same_person_above_different_people(fresh):
    from app.services import body_scan, synth
    from app.database.seed import AARAV
    ref = _img("cases/MC-2026-0001.png")
    scene = Image.new("RGB", (640, 480), (150, 160, 150))
    scene.paste(synth.person_card(AARAV).resize((200, 300)), (220, 120))
    same = body_scan.analyse(ref, scene)["overall_score"]
    red = body_scan.analyse(ref, _img("records/FR-0009.png"))["overall_score"]
    saree = body_scan.analyse(ref, _img("records/FR-0010.png"))["overall_score"]
    assert same >= 0.8 and same > red + 0.4 and same > saree + 0.4
    assert same <= 0.99


def test_body_scan_api_analyse_and_attach(fresh):
    from app.config.settings import DATA_DIR
    data = (DATA_DIR / "sample_scans" / "field_capture.png").read_bytes()
    r = fresh.post("/api/scan/analyze", files={"scan": ("s.png", data, "image/png")}, data={"case_id": CASE})
    assert r.status_code == 200, r.text
    j = r.json()
    assert 0.6 <= j["overall_score"] <= 0.99
    assert j["status_text"] == "Requires Human Verification"
    assert len(j["components"]) == 5
    a = fresh.post(f"/api/scan/{j['scan_id']}/attach", json={"case_id": CASE, "locality": "Kilpauk"}).json()
    assert a["created_record_id"].startswith("FR-")
    assert a["created_record_id"] in ids(a)


def test_body_scan_needs_reference(fresh):
    from app.config.settings import DATA_DIR
    data = (DATA_DIR / "sample_scans" / "field_capture.png").read_bytes()
    r = fresh.post("/api/scan/analyze", files={"scan": ("s.png", data, "image/png")}, data={"case_id": "MC-2026-0002"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "reference_required"


def test_ocr_reads_ambulance_log(fresh):
    j = fresh.post("/api/ocr/sample/kilpauk_ambulance_log").json()
    f = {k: v["value"] for k, v in j["fields"].items()}
    assert f.get("record_ref") == "FR-0003"
    assert f.get("gender") == "Male"
    assert j["document_type"] == "hospital_record"


def test_cctv_finds_sighting(fresh):
    j = fresh.post("/api/cctv/sample", json={"case_id": CASE}).json()
    assert j["frames_analysed"] > 0
    assert j["sightings"], j
    best = max(j["sightings"], key=lambda s: s["visual_similarity"])
    assert best["frame_datetime"].startswith("2026-09-25T18:4")
