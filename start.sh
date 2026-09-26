#!/usr/bin/env bash
cd "$(dirname "$0")/backend"
source .venv/bin/activate
echo "MissingLink running at http://localhost:8000  (Ctrl+C to stop)"
( sleep 2; (command -v xdg-open >/dev/null && xdg-open http://localhost:8000) || (command -v open >/dev/null && open http://localhost:8000) ) >/dev/null 2>&1 &
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
