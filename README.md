# MissingLink

**Offline-first, AI-assisted missing-person matching — decision support for authorized investigators.**

MissingLink connects fragmented records from police, hospitals, shelters and NGO field teams. It retrieves
visually similar candidates locally, combines several pieces of evidence, explains why each candidate is ranked
where it is, and re-ranks when new evidence arrives — including a **live body scan** from a camera in the field.

> MissingLink never identifies anyone. Every result is a *potential* match that **requires human verification**.
> Final identification must be performed by an authorized investigator. The demo uses synthetic data only —
> every person, photo and document is procedurally generated.

---

## Quick start

Requirements: **Python 3.10–3.12**, a modern browser (Chrome, Edge, Firefox, Safari). Internet is needed once for setup.

**Windows**
```
setup.bat
start.bat
```

**macOS / Linux**
```
./setup.sh
./start.sh
```

Then open **http://localhost:8000**. The database is seeded with the demo scenario automatically.

Optional stronger visual encoder (CLIP ViT-B/32, about 600 MB): run `setup.bat --with-clip` or
`./setup.sh --with-clip`. Without it, MissingLink uses its built-in fallback encoder automatically.
If you add CLIP after the first setup, reset the demo data (Settings → Reset demo data) so all photos are re-indexed with the same encoder.

Run the tests: `cd backend`, activate `.venv`, then `python -m pytest -q tests` (19 tests).

## Five-minute demo

1. Open **Demo investigation** and press **Run all steps**. Each step calls the real local services:
   case load → FAISS retrieval → ranked candidates → *Why this match?* → OCR of a hospital ambulance log →
   automatic re-ranking (the low-light hospital patient FR-0003 moves from #3 to #1, with a plain-language explanation) →
   CCTV potential sighting → field body-scan at the hospital → timeline and ranking history.
2. Press **Toggle offline and replay** to show that steps 1–6 run with no network.
3. Open **Live body scan** and try it yourself (below).

## Live body scan

1. **Missing person's photo** — pick a case to use its photo, or upload any reference photo.
2. **Person in the field** — press **Scan the body**. The camera opens with a head-to-toe guide frame; stand the
   person inside it and press **Capture** (or **Capture in 3 s**). Only the area inside the frame is analysed.
   You can also upload a photo, or press **Use sample field capture**.
3. **Analyse match** — you get an overall visual-agreement percentage and a breakdown of five checks:

   | Check | Weight | What it compares |
   |---|---|---|
   | Overall appearance | 0.35 | Whole-person embedding (CLIP or fallback) |
   | Upper-body clothing | 0.20 | Dominant colour (lighting-invariant) and pattern |
   | Lower-body clothing | 0.15 | Same, lower body |
   | Face / head region | 0.15 | Face region if a face is found in both images, else head/hair colour |
   | Body shape and build | 0.15 | Silhouette (HOG) and proportions |

   Low-quality images reduce the weight of appearance and face checks, and every warning is shown.
4. **Add this scan to the case** — link it to an existing found record, or create a new *sighting* record from the
   scan. The scan becomes evidence, the timeline updates and all candidates are re-ranked.

**Camera notes.** Browsers only allow live camera access on `http://localhost` or HTTPS. On a phone opening the app
over your Wi-Fi (e.g. `http://192.168.x.x:8000`), use **Use phone camera / file** — it opens the phone's camera app
directly. To serve on your network, start uvicorn with `--host 0.0.0.0`.

## How matching works

```
 Missing report ──► Case (MC-2026-xxxx) ──► Working profile  ◄── evidence: hospital logs (OCR), CCTV, body scans, notes
                                                  │
 Found records (police / hospital / shelter / NGO)│
        │                                         ▼
        └─► embeddings ─► FAISS index ─► top-K visual candidates ∪ no-photo records passing attribute filters
                                                  │                 ∪ records linked by evidence
                                                  ▼
                        Factor registry: photo · age · gender · clothing · location · time · corroboration
                                                  │  (weights renormalise over AVAILABLE evidence only)
                                                  ▼
                        Combined score (capped at 99%) → band → ranked list → "Why this match?"
                                                  │
                                                  ▼
                              Investigator: mark for review / request info / record verification / reject
```

- **Missing is not a mismatch.** A factor with no data is marked *unavailable* and excluded; the remaining weights are renormalised. Coverage is always shown ("Matching using 5 of 7 evidence sources").
- **Conflicts** (e.g. gender differs, record time before last-seen time) are shown in red and such candidates are ranked after all uncontradicted ones.
- **Bands:** High-Priority Potential Match (≥ 80%, 3+ factors, no critical conflict) · Potential Match (≥ 60%) · Low Evidence · Possible Match — Conflict Detected.
- **Re-ranking:** attaching evidence rebuilds the working profile (e.g. an ambulance log moves the last-known place and time), re-scores everything and explains the biggest move.
- **Weights** live in `backend/app/config/match_weights.py` and can be changed live in **Settings**.

### Adding a new evidence factor

1. Create `backend/app/services/factors/my_factor.py` subclassing `Factor` (see `occupation.py` for a complete example) and return `available`, `unavailable` or `conflict` with a reason.
2. Register it in `backend/app/services/factors/__init__.py`.
3. Give it a weight in `match_weights.py` (or in Settings). `tests/test_core.py::test_new_factor_can_be_enabled` shows the occupation example being switched on.

## Offline and sync

All core features — embeddings, FAISS search, scoring, OCR (RapidOCR/ONNX), CCTV and body-scan analysis — run on the
device. No external API is ever called at runtime. Rows created while offline are marked **Pending Sync**; when the
connection returns, **Offline and sync → Sync now** copies them into `backend/data/hub.db`, a simulated regional hub.
To test: turn off Wi-Fi, or click the **ONLINE / OFFLINE** pill in the header to simulate it.

## Privacy and ethics

- Synthetic data only in the demo. No real faces or documents.
- No biometric identification claims; scores are capped at 99% and always labelled *Requires Human Verification*.
- Role-based view: switch to **Field volunteer** in the header and exact care locations (ward, bed) are hidden.
- Every review decision is logged on the evidence timeline.
- Families should be contacted only through the verifying organisation, using protected questions.

## Project layout

```
missinglink/
  setup.bat / setup.sh / start.bat / start.sh
  frontend/            vanilla JS single-page app (no CDN, system fonts — works offline)
  backend/
    app/main.py        FastAPI app, error handling, static serving
    app/routes/        cases, match, body scan / CCTV / OCR, system, demo
    app/services/      embeddings, FAISS, scoring + factors, profile builder, body_scan, cctv, ocr, sync
    app/database/      SQLite models + synthetic seed
    tests/             pytest suite
    data/              created at first run (DB, media, FAISS index, hub.db)
```

## Known limitations

- Ranking thresholds were tuned with the **fallback encoder**; CLIP could not be tested in the build environment. With CLIP, scores recalibrate automatically from the seeded records, but the exact demo ordering may differ.
- The corroboration factor weight was raised from 0.10 to 0.20 so that a directly linked hospital record can overturn a visually stronger look-alike.
- Person detection in body scans uses OpenCV's HOG detector with a foreground-segmentation fallback. Busy backgrounds, several people in frame, or very dark images reduce accuracy — use the guide frame and good light.
- Face comparison is region-level visual similarity, not face recognition.
- The frontend is a lightweight vanilla-JS app served by FastAPI rather than Next.js, so the whole system runs from one offline process.
