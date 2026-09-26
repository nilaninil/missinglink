"""Deterministic synthetic seed: orgs, cases, found records, images, docs, CCTV clip, embeddings, FAISS.

Run:  python -m app.database.seed
"""
import json
import shutil
from datetime import datetime, timedelta
import numpy as np
import cv2
from PIL import Image, ImageDraw

from app.config.settings import (MEDIA_DIR, EMB_DIR, SAMPLE_CCTV_DIR, SAMPLE_DOCS_DIR, DATA_DIR,
                                 DEMO_DATE, FAISS_PATH, HUB_DB_PATH, CALIBRATION_PATH)
from app.config.match_weights import reset_weights
from app.database.db import Base, engine, SessionLocal, init_db
from app.models.orm import Organization, MissingCase, FoundRecord, FaissMap, TimelineEvent
from app.services import synth, image_quality, vector_search, calibration
from app.services.embedding_service import embed_image, encoder_key, load_image

D = datetime.fromisoformat(DEMO_DATE)


def T(hm, day=0):
    h, m = map(int, hm.split(":"))
    return D + timedelta(days=day, hours=h, minutes=m)


SKIN_M = (166, 116, 82)
AARAV = dict(skin=SKIN_M, hair=(25, 20, 18), hair_style="short", shirt=(38, 88, 196), pattern="plain",
             lower=(28, 28, 32), lower_type="trousers", build=1.0, bg=(226, 230, 236))

ORGS = [
    (1, "Anna Nagar Police Station", "police", "Anna Nagar"),
    (2, "Anna Nagar Relief Shelter", "shelter", "Anna Nagar"),
    (3, "Chennai Relief Volunteers (NGO field team)", "ngo", "Koyambedu"),
    (4, "Government Hospital Kilpauk", "hospital", "Kilpauk"),
    (5, "Egmore Women's Shelter", "shelter", "Egmore"),
    (6, "Tambaram Police Station", "police", "Tambaram"),
    (7, "Adyar General Hospital", "hospital", "Adyar"),
    (8, "District Investigation Cell", "investigator", "Egmore"),
    (9, "Field Volunteer Unit (body-scan)", "ngo", "Anna Nagar"),
]


def person(**kw):
    p = dict(AARAV); p.update(kw); return p


# id, type, org, locality, time, age_min, age_max, gender, clothing, appearance, variant, extra
RECORDS = [
    # Candidate A - look-alike at shelter, older
    ("FR-0001", "shelter_resident", 2, "Anna Nagar", T("19:40"), 28, 33, "Male", "Blue shirt, grey trousers",
     person(skin=(150, 104, 72), hair=(58, 44, 36), shirt=(52, 104, 184), lower=(104, 104, 112), build=1.12, bg=(214, 224, 216)), None,
     dict(occupation="delivery worker", care="Shelter hall B, cot 14", desc="Walked in, disoriented, gave no name.")),
    # Candidate B - NGO, checked shirt
    ("FR-0002", "found", 3, "Koyambedu", T("20:10"), 20, 26, "Male", "Blue checked shirt, grey trousers",
     person(skin=(140, 98, 70), shirt=(96, 150, 214), pattern="checked", lower=(98, 98, 106), hair_style="cap",
     cap=(60, 60, 64), bag=(120, 70, 30), build=0.92, bg=(232, 224, 210)), None,
     dict(occupation="student", care="NGO camp tent 3", desc="Found near bus stand, seemed confused.")),
    # Candidate C - true counterpart, low-light hospital photo, age unknown
    ("FR-0003", "unidentified_patient", 4, "Kilpauk", T("19:15"), None, None, "Male", "Shirt (color unclear), dark trousers",
     person(bg=(196, 206, 200)), "lowlight",
     dict(care="Casualty Ward 3, Bed 12", desc="Unidentified patient brought by ambulance; drowsy, unable to state name.")),
    # distractors
    ("FR-0004", "found", 1, "Anna Nagar", T("17:45"), 21, 25, "Male", "Blue shirt, black trousers",
     person(skin=(176, 124, 90), shirt=(44, 80, 176), hair=(30, 24, 20), build=0.95, bg=(222, 222, 230)), None,
     dict(desc="Recorded BEFORE the last-seen time (time contradiction).")),
    ("FR-0005", "shelter_resident", 5, "Egmore", T("21:00"), 20, 25, "Female", "Blue kurta, white leggings",
     person(skin=(170, 120, 90), hair_style="long", hair=(20, 16, 14), shirt=(50, 90, 190), lower=(236, 236, 236), bg=(236, 222, 226)), None,
     dict(care="Women's shelter room 2")),
    ("FR-0006", "found", 1, "Mylapore", T("20:40"), 8, 10, "Male", "Yellow t-shirt, blue shorts",
     person(shirt=(236, 200, 40), lower=(40, 70, 170), lower_type="shorts", build=0.8, bg=(226, 236, 226)), None, {}),
    ("FR-0007", "found", 8, "Porur", T("08:00", 1), 22, 28, "Male", "White shirt, blue jeans", None, None,
     dict(desc="No photo available - field report only.")),
    ("FR-0008", "found", 3, "T. Nagar", T("21:15"), None, None, "Male", "Green t-shirt, black trousers",
     person(shirt=(40, 150, 70), skin=(150, 100, 70), bg=(230, 230, 220)), None, {}),
    ("FR-0009", "found", 3, "Aminjikarai", T("20:30"), 20, 24, "Male", "Red t-shirt, white shorts",
     person(shirt=(200, 40, 40), lower=(232, 232, 232), lower_type="shorts", bg=(236, 226, 222)), None, {}),
    ("FR-0010", "shelter_resident", 6, "Tambaram", T("09:30", 1), 60, 70, "Female", "Green saree",
     person(skin=(150, 105, 80), hair_style="bun", hair=(200, 200, 200), shirt=(40, 130, 70), lower=(40, 130, 70),
     lower_type="saree", bg=(232, 230, 214)), None, dict(care="Tambaram relief camp, block C")),
    ("FR-0011", "unidentified_patient", 7, "Adyar", T("23:10"), 45, 55, "Male", "Grey shirt, brown trousers",
     person(shirt=(130, 130, 136), lower=(110, 80, 50), hair=(120, 120, 120), build=1.2, bg=(220, 226, 230)), None,
     dict(care="Ward 7, Bed 3")),
    ("FR-0012", "found", 8, "Velachery", T("09:00", 1), 23, 27, "Male", "Black t-shirt, blue jeans",
     person(shirt=(30, 30, 34), lower=(50, 80, 150), hair_style="cap", cap=(200, 40, 40), bg=(226, 226, 226)), None, {}),
    ("FR-0013", "sighting", 5, "Perambur", T("21:50"), 18, 22, "Female", "Pink top, black trousers",
     person(shirt=(230, 130, 170), hair_style="long", hair=(30, 22, 18), bg=(240, 230, 236)), None, {}),
    ("FR-0014", "found", 6, "Guindy", T("22:05"), 30, 35, "Male", "Orange shirt, brown trousers",
     person(shirt=(230, 120, 30), lower=(110, 80, 50), build=1.1, bg=(236, 232, 222)), "blurry", {}),
]


def _save(im, rel):
    p = MEDIA_DIR / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    im.save(p)
    return rel


def _embed_store(s, emb_id, entity_type, entity_id, img):
    vec = embed_image(img)
    vector_search.save_vector(emb_id, vec)
    s.add(FaissMap(embedding_id=emb_id, entity_type=entity_type, entity_id=entity_id))
    return vec


def wipe():
    Base.metadata.drop_all(engine)
    for p in (FAISS_PATH, HUB_DB_PATH, CALIBRATION_PATH):
        if p.exists():
            p.unlink()
    for d in (EMB_DIR, MEDIA_DIR):
        if d.exists():
            shutil.rmtree(d)
    for d in (EMB_DIR, MEDIA_DIR, MEDIA_DIR / "scans", MEDIA_DIR / "uploads", MEDIA_DIR / "crops"):
        d.mkdir(parents=True, exist_ok=True)
    reset_weights()


def seed(generate_assets=True):
    wipe()
    init_db()
    vector_search.reset()
    s = SessionLocal()
    for oid, name, typ, loc in ORGS:
        s.add(Organization(id=oid, name=name, type=typ, locality=loc))

    emb = 1
    # --- missing cases
    case_img = synth.person_card(AARAV)
    rel = _save(case_img, "cases/MC-2026-0001.png")
    q = image_quality.assess(case_img)
    _embed_store(s, emb, "missing_case", "MC-2026-0001", case_img)
    s.add(MissingCase(id="MC-2026-0001", name="Aarav Kumar", age=22, age_min=20, age_max=24, gender="Male",
                      last_seen_locality="Anna Nagar", last_seen_datetime=T("18:30"),
                      clothing_text="Blue shirt, black trousers", occupation="student",
                      description="College student, 22. Last seen leaving a friend's house on Anna Nagar 2nd Avenue.",
                      photo_path=rel, photo_quality=q["quality"], photo_warnings=json.dumps(q["warnings"]),
                      embedding_id=emb, reporting_org_id=1, status="open", created_at=T("20:05")))
    emb += 1
    s.add(MissingCase(id="MC-2026-0002", name="Lakshmi R.", age=None, age_min=62, age_max=68, gender="Female",
                      last_seen_locality="Tambaram", last_seen_datetime=T("16:00"), clothing_text="Green saree",
                      description="Elderly woman, may be confused. No recent photo available.",
                      reporting_org_id=6, status="open", created_at=T("19:00")))

    # --- found records
    vecs = []
    for (rid, rtype, org, loc, t, amin, amax, g, cloth, look, variant, extra) in RECORDS:
        rec = FoundRecord(id=rid, record_type=rtype, age_min=amin, age_max=amax, gender=g, locality=loc,
                          found_datetime=t, clothing_text=cloth, source_org_id=org,
                          care_location_detail=extra.get("care"), description=extra.get("desc"),
                          occupation=extra.get("occupation"), created_at=t or T("23:00"))
        if look is not None:
            im = synth.person_card(look)
            if variant == "lowlight":
                im = synth.lowlight(synth.side_angle(im), 0.3, seed=3)
            elif variant == "blurry":
                im = synth.blurry(im, 5)
            rec.photo_path = _save(im, f"records/{rid}.png")
            q = image_quality.assess(im)
            rec.photo_quality, rec.photo_warnings = q["quality"], json.dumps(q["warnings"])
            rec.embedding_id = emb
            v = _embed_store(s, emb, "found_record", rid, im)
            vector_search.add(emb, v)
            vecs.append(v)
            emb += 1
        s.add(rec)
    calibration.compute_and_store(encoder_key(), vecs)

    # --- timeline
    s.add(TimelineEvent(case_id="MC-2026-0001", event_type="report", title="Last seen",
                        detail="Last seen on Anna Nagar 2nd Avenue wearing a blue shirt and black trousers.",
                        locality="Anna Nagar", org_id=1, occurred_at=T("18:30")))
    s.add(TimelineEvent(case_id="MC-2026-0001", event_type="report", title="Missing report filed",
                        detail="Family reported Aarav Kumar missing at Anna Nagar Police Station.",
                        locality="Anna Nagar", org_id=1, occurred_at=T("20:05")))
    s.add(TimelineEvent(case_id="MC-2026-0002", event_type="report", title="Missing report filed",
                        detail="Lakshmi R. reported missing; no photo available.", locality="Tambaram", org_id=6,
                        occurred_at=T("19:00")))
    s.commit()
    s.close()
    if generate_assets:
        make_documents()
        make_cctv_video()
        make_field_capture()
    return True


DOCS = {
    "kilpauk_ambulance_log": dict(
        title="GOVT HOSPITAL KILPAUK - AMBULANCE / CASUALTY LOG",
        lines=[("Date", "25-09-2026"), ("Patient", "Unidentified male"), ("Gender", "Male"),
               ("Approx Age", "21"), ("Pickup Location", "Anna Nagar 2nd Avenue"), ("Pickup Time", "18:55"),
               ("Clothing", "Blue shirt, dark trousers"), ("Destination", "Govt Hospital Kilpauk"),
               ("Admitted", "19:15"), ("Record Ref", "FR-0003")],
        truth=dict(document_type="hospital_record", org_id=4, name=None, age_min=19, age_max=23, gender="Male",
                   locality="Kilpauk", observed_time="19:15", pickup_locality="Anna Nagar", pickup_time="18:55",
                   clothing="Blue shirt, dark trousers", linked_record_id="FR-0003"),
        quality="good"),
    "anna_nagar_shelter_intake": dict(
        title="ANNA NAGAR RELIEF SHELTER - INTAKE FORM",
        lines=[("Date", "25-09-2026"), ("Name", "Not given"), ("Gender", "Male"), ("Approx Age", "30"),
               ("Location", "Anna Nagar"), ("Time", "19:40"), ("Clothing", "Blue shirt, grey trousers"),
               ("Record Ref", "FR-0001")],
        truth=dict(document_type="shelter_record", org_id=2, age_min=28, age_max=32, gender="Male", locality="Anna Nagar",
                   observed_time="19:40", clothing="Blue shirt, grey trousers", linked_record_id="FR-0001"),
        quality="good"),
    "partial_police_report": dict(
        title="POLICE FIELD REPORT (PARTIAL COPY)",
        lines=[("Date", "25-09-2026"), ("Name", "Aarav K"), ("Gender", "Male"), ("Age", "2?"),
               ("Location", "Koyambedu"), ("Time", "2?:1?"), ("Clothing", "shirt, trousers")],
        truth=dict(document_type="investigator_note", org_id=1, gender="Male", locality="Koyambedu",
                   clothing="shirt, trousers"),
        quality="poor"),
}


def make_documents():
    for key, d in DOCS.items():
        im = synth.document(d["title"], d["lines"], d["quality"])
        im.save(SAMPLE_DOCS_DIR / f"{key}.png")
        (SAMPLE_DOCS_DIR / f"{key}.json").write_text(json.dumps(d["truth"], indent=2))


def make_cctv_video():
    path = SAMPLE_CCTV_DIR / "anna_nagar_checkpoint.mp4"
    w, h, fps, secs = 640, 360, 10, 15
    bg = Image.new("RGB", (w, h), (120, 122, 126))
    dr = ImageDraw.Draw(bg)
    dr.rectangle((0, 0, w, 120), fill=(168, 176, 184))          # buildings
    for x in range(0, w, 90):
        dr.rectangle((x + 10, 20, x + 70, 110), fill=(140, 146, 156))
    dr.rectangle((0, 290, w, h), fill=(92, 94, 98))              # road
    for x in range(0, w, 80):
        dr.rectangle((x, 320, x + 40, 326), fill=(230, 230, 200))
    figs = [  # (appearance, start_s, end_s, direction, y)
        (person(shirt=(200, 40, 40), lower=(232, 232, 232), lower_type="shorts"), 0.0, 6.0, 1, 150),
        (person(shirt=(40, 150, 70), skin=(150, 100, 70)), 3.0, 10.0, -1, 158),
        (AARAV, 8.0, 14.5, 1, 152),
        (person(shirt=(230, 120, 30), lower=(110, 80, 50), build=1.1), 10.0, 15.0, -1, 160),
    ]
    sprites = [synth.person_card(f[0], transparent=True).resize((90, 135)) for f in figs]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    start = T("18:40")
    time_scale = 10  # time-lapse: 1 s of footage = 10 s real time
    for i in range(fps * secs):
        t = i / fps
        fr = bg.copy()
        for (look, s0, s1, direction, y), sp in zip(figs, sprites):
            if s0 <= t <= s1:
                prog = (t - s0) / (s1 - s0)
                x = int(-90 + prog * (w + 90)) if direction == 1 else int(w - prog * (w + 90))
                fr.paste(sp, (x, y), sp)
        d = ImageDraw.Draw(fr)
        d.rectangle((0, 0, w, 26), fill=(0, 0, 0))
        stamp = start + timedelta(seconds=t * time_scale)
        d.text((8, 5), "CAM-03 ANNA NAGAR CHECKPOINT", fill=(255, 255, 255), font=synth.font(14, True))
        d.text((450, 5), stamp.strftime("%Y-%m-%d %H:%M:%S"), fill=(255, 255, 0), font=synth.font(14))
        writer.write(cv2.cvtColor(np.asarray(fr), cv2.COLOR_RGB2BGR))
    writer.release()
    (SAMPLE_CCTV_DIR / "anna_nagar_checkpoint.json").write_text(json.dumps(
        {"camera_name": "CAM-03 Anna Nagar Checkpoint", "locality": "Anna Nagar",
         "start_datetime": start.isoformat(), "time_scale": time_scale}))


def make_field_capture():
    """A synthetic 'camera' capture of the found person in a dim hospital ward (for the demo body-scan)."""
    d = DATA_DIR / "sample_scans"
    d.mkdir(parents=True, exist_ok=True)
    scene = Image.new("RGB", (720, 540), (176, 190, 184))
    dr = ImageDraw.Draw(scene)
    dr.rectangle((0, 400, 720, 540), fill=(150, 146, 138))            # floor
    dr.rectangle((470, 250, 700, 420), fill=(214, 220, 226))          # bed
    dr.rectangle((470, 230, 520, 260), fill=(236, 236, 240))          # pillow
    dr.rectangle((40, 60, 200, 200), fill=(196, 208, 204))            # window
    card = synth.person_card(dict(AARAV, bg=(176, 190, 184)))
    card = card.resize((230, 345))
    scene.paste(card, (230, 110))
    scene = synth.lowlight(scene, 0.72, seed=7)
    scene.save(d / "field_capture.png")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    seed()
    from app.services.embedding_service import encoder_name
    print(f"Seed complete. Encoder: {encoder_name()}. FAISS vectors: {vector_search.count()}")
