#!/usr/bin/env bash
# MissingLink setup (macOS / Linux). Needs internet once; afterwards everything runs offline.
set -e
cd "$(dirname "$0")/backend"
PY=${PYTHON:-python3}
$PY -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-ocr.txt || echo "WARNING: OCR engine could not be installed — the document scanner will use sample metadata only."
if [ "$1" = "--with-clip" ]; then
  pip install -r requirements-clip.txt && python download_models.py || echo "WARNING: CLIP skipped — fallback encoder will be used."
fi
python -m app.database.seed
echo
echo "Setup complete. Start MissingLink with ./start.sh"
