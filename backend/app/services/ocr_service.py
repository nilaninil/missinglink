"""Offline OCR (RapidOCR / ONNX) + field extraction with per-field confidence."""
import re
import logging
import numpy as np
from app.services import gazetteer
from app.services.clothing import parse as parse_clothing

log = logging.getLogger("missinglink.ocr")
_engine = None
_engine_name = None


def get_engine():
    global _engine, _engine_name
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
            _engine_name = "RapidOCR (ONNX, local)"
        except Exception as e:
            log.warning("RapidOCR unavailable: %s", e)
            try:
                import pytesseract
                pytesseract.get_tesseract_version()
                _engine, _engine_name = "tesseract", "Tesseract (local)"
            except Exception:
                _engine, _engine_name = False, None
    return _engine


def engine_name():
    get_engine()
    return _engine_name or "OCR engine unavailable"


def read_lines(img):
    """Return rows [(text, confidence)] ordered top-to-bottom."""
    eng = get_engine()
    if not eng:
        return None
    arr = np.asarray(img.convert("RGB"))
    if eng == "tesseract":
        import pytesseract
        d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        rows = {}
        for i, t in enumerate(d["text"]):
            if t.strip():
                key = (d["block_num"][i], d["line_num"][i])
                rows.setdefault(key, []).append((t, max(0, float(d["conf"][i])) / 100))
        return [(" ".join(t for t, _ in v), float(np.mean([c for _, c in v]))) for v in rows.values()]
    res, _ = eng(arr)
    if not res:
        return []
    boxes = []
    for box, text, score in res:
        ys = [p[1] for p in box]; xs = [p[0] for p in box]
        boxes.append((float(np.mean(ys)), float(min(xs)), float(max(ys) - min(ys)), text, float(score)))
    boxes.sort()
    rows, cur, cur_y = [], [], None
    for y, x, h, t, sc in boxes:
        if cur_y is None or abs(y - cur_y) < max(12, h * 0.6):
            cur.append((x, t, sc)); cur_y = y if cur_y is None else (cur_y + y) / 2
        else:
            rows.append(cur); cur, cur_y = [(x, t, sc)], y
    if cur:
        rows.append(cur)
    out = []
    for r in rows:
        r.sort()
        out.append((" ".join(t for _, t, _ in r), float(np.mean([s for _, _, s in r]))))
    return out


TIME_RE = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
LABELS = {
    "name": r"^(name|patient)\b", "age": r"age\b", "gender": r"^(gender|sex)\b",
    "pickup_location": r"pick\s*-?\s*up\s*loc", "pickup_time": r"pick\s*-?\s*up\s*time",
    "location": r"^(location|place|found at)\b", "destination": r"^(destination|taken to)\b",
    "admitted": r"^admitted\b", "time": r"^time\b", "date": r"^date\b", "clothing": r"^(clothing|dress|wearing)\b",
    "record_ref": r"record\s*ref",
}


def _value(row, label_re):
    t = re.sub(label_re, "", row, count=1, flags=re.I).strip(" :-.\t")
    return t


def extract_fields(rows):
    fields = {}

    def put(k, v, conf, certain=1.0):
        c = round(conf * certain, 3)
        if v not in (None, "") and (k not in fields or fields[k]["confidence"] < c):
            fields[k] = {"value": v, "confidence": c, "needs_verification": c < 0.7}

    full = "\n".join(t for t, _ in rows)
    for text, conf in rows:
        low = text.lower().strip()
        for key, pat in LABELS.items():
            if not re.search(pat, low, re.I):
                continue
            val = _value(text, r".*?" + pat.lstrip("^").replace(r"\b", "") + r"[a-z]*")
            if key == "age":
                m = re.search(r"(\d{1,3})(\?)?", val)
                if m:
                    put("age", m.group(1) + ("?" if "?" in val else ""), conf, 0.4 if "?" in val else 1.0)
                elif val:
                    put("age", val, conf, 0.3)
            elif key == "gender":
                g = "Male" if re.search(r"\bm(ale)?\b", val, re.I) else "Female" if re.search(r"\bf(emale)?\b", val, re.I) else None
                put("gender", g or val, conf, 1.0 if g else 0.3)
            elif key in ("pickup_location", "location", "destination"):
                canon = gazetteer.resolve(val)
                put(key, canon or val, conf, 1.0 if canon else 0.4)
            elif key in ("pickup_time", "admitted", "time"):
                m = TIME_RE.search(val)
                put(key, f"{int(m.group(1)):02d}:{m.group(2)}" if m else val, conf, 1.0 if m and "?" not in val else 0.3)
            elif key == "date":
                m = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", val)
                put("date", f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else val, conf, 1.0 if m else 0.4)
            elif key == "clothing":
                items = parse_clothing(val)
                known = sum(1 for i in items if i["color"])
                put("clothing", val, conf, 1.0 if items and known == len(items) else 0.6 if items else 0.3)
            elif key == "name":
                put("name", val, conf, 0.9)
            elif key == "record_ref":
                m = re.search(r"FR[-\s]?(\d{4})", val, re.I)
                put("record_ref", f"FR-{m.group(1)}" if m else val, conf, 1.0 if m else 0.3)
            break
    if "record_ref" not in fields:
        m = re.search(r"FR[-\s]?(\d{4})", full, re.I)
        if m:
            put("record_ref", f"FR-{m.group(1)}", 0.8)
    low = full.lower()
    doc_type = "hospital_record" if ("hospital" in low or "ambulance" in low or "casualty" in low) else \
        "shelter_record" if "shelter" in low else "investigator_note"
    return fields, doc_type


def to_evidence(fields: dict, doc_type: str) -> dict:
    """Convert (possibly edited) OCR fields into evidence form values."""
    f = {k: (v["value"] if isinstance(v, dict) else v) for k, v in fields.items()}
    age = str(f.get("age") or "")
    amin = amax = None
    m = re.match(r"^(\d{1,3})$", age)
    if m:
        a = int(m.group(1)); amin, amax = a - 2, a + 2
    locality = f.get("destination") or f.get("location") or f.get("pickup_location")
    observed = f.get("admitted") or f.get("time") or f.get("pickup_time")
    return {"evidence_type": doc_type, "age_min": amin, "age_max": amax, "gender": f.get("gender"),
            "locality": locality, "observed_time": observed, "date": f.get("date"),
            "pickup_locality": f.get("pickup_location"), "pickup_time": f.get("pickup_time"),
            "clothing_text": f.get("clothing"), "linked_record_id": f.get("record_ref"), "name": f.get("name")}
