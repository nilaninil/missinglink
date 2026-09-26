"""Central paths, thresholds and offline flags."""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
is_vercel = bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
if is_vercel:
    DATA_DIR = Path(os.environ.get("MISSINGLINK_DATA", "/tmp/missinglink_data"))
else:
    DATA_DIR = Path(os.environ.get("MISSINGLINK_DATA", BACKEND_DIR / "data"))

MODELS_DIR = BACKEND_DIR / "models"
MEDIA_DIR = DATA_DIR / "media"
EMB_DIR = DATA_DIR / "embeddings"
SAMPLE_CCTV_DIR = DATA_DIR / "sample_cctv"
SAMPLE_DOCS_DIR = DATA_DIR / "sample_docs"
DB_PATH = DATA_DIR / "missinglink.db"
HUB_DB_PATH = DATA_DIR / "hub.db"
FAISS_PATH = DATA_DIR / "faiss.index"
CALIBRATION_PATH = DATA_DIR / "calibration.json"
WEIGHTS_OVERRIDE_PATH = DATA_DIR / "weights_override.json"
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"

TOP_K = int(os.environ.get("MISSINGLINK_TOP_K", 8))
EMBED_DIM = 512
DEMO_DATE = "2026-09-25"

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".avi"}

CCTV_SAMPLE_FPS = 1.0
CCTV_MAX_FRAMES = 60
CCTV_MIN_SIMILARITY = 0.35

# Force offline model loading once setup has downloaded weights.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HOME", str(MODELS_DIR / "hf"))

# If on Vercel and source data exists, copy initial data to /tmp
if is_vercel and not DATA_DIR.exists() and (BACKEND_DIR / "data").exists():
    try:
        import shutil
        shutil.copytree(str(BACKEND_DIR / "data"), str(DATA_DIR))
    except Exception:
        pass

for d in (DATA_DIR, MEDIA_DIR, EMB_DIR, SAMPLE_CCTV_DIR, SAMPLE_DOCS_DIR, MODELS_DIR,
          MEDIA_DIR / "scans", MEDIA_DIR / "uploads", MEDIA_DIR / "crops"):
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

