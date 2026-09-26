@echo off
cd /d "%~dp0backend"
call .venv\Scripts\activate.bat
echo MissingLink running at http://localhost:8000  (close this window to stop)
start "" http://localhost:8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
