@echo off
REM MissingLink setup (Windows). Needs internet once; afterwards everything runs offline.
cd /d "%~dp0backend"
py -3 -m venv .venv || python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || goto :fail
pip install -r requirements-ocr.txt || echo WARNING: OCR engine could not be installed - document scanner will use sample metadata only.
if "%1"=="--with-clip" (
  pip install -r requirements-clip.txt && python download_models.py
)
python -m app.database.seed || goto :fail
echo.
echo Setup complete. Start MissingLink with start.bat
goto :eof
:fail
echo Setup failed. Check that Python 3.10-3.12 is installed and try again.
exit /b 1
