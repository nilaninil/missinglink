"""MissingLink — offline-first, AI-assisted missing-person matching (decision support only)."""
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config.settings import MEDIA_DIR, SAMPLE_DOCS_DIR, FRONTEND_DIR, DB_PATH, DATA_DIR
from app.database.db import init_db
from app.routes import cases, match, media_ops, system, demo
from app.routes.common import ApiError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("missinglink")

app = FastAPI(title="MissingLink API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
                                                  "http://localhost:8000", "http://127.0.0.1:8000"],
                   allow_methods=["*"], allow_headers=["*"])


def err(status, code, message, detail=None):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "detail": detail}})


@app.exception_handler(ApiError)
async def api_error(_: Request, e: ApiError):
    return err(e.status, e.code, e.message, e.detail)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, e: RequestValidationError):
    return err(422, "invalid_request", "Some required information is missing or invalid.",
               [x.get("msg") for x in e.errors()][:5])


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, e: StarletteHTTPException):
    return err(e.status_code, "http_error", str(e.detail))


@app.exception_handler(Exception)
async def unhandled(_: Request, e: Exception):
    log.exception("Unhandled error")
    return err(500, "internal_error", "Something went wrong while processing this request. Your data is safe.", str(e)[:200])


from app.routes import cases, match, media_ops, system, demo, upload
from app.services import json_persistence

for r in (cases.router, match.router, media_ops.router, system.router, demo.router, upload.router):
    app.include_router(r, prefix="/api")


@app.on_event("startup")
def startup():
    init_db()
    first_run = False
    from app.database.db import SessionLocal
    from app.models.orm import MissingCase
    with SessionLocal() as s:
        first_run = s.query(MissingCase).count() == 0
        if first_run:
            log.info("Empty database — seeding synthetic demo data")
            from app.database.seed import seed
            seed()
        # Always synchronize cases and records to local cases.json persistence
        try:
            json_persistence.sync_all_from_db(s)
        except Exception as e:
            log.warning("Could not sync cases.json on startup: %s", e)
    from app.services import vector_search
    from app.services.embedding_service import encoder_name
    log.info("Encoder: %s | FAISS vectors: %d", encoder_name(), vector_search.count())


app.mount("/media", StaticFiles(directory=str(MEDIA_DIR)), name="media")
app.mount("/samples/docs", StaticFiles(directory=str(SAMPLE_DOCS_DIR)), name="docs")
(DATA_DIR / "sample_scans").mkdir(parents=True, exist_ok=True)
app.mount("/samples/scans", StaticFiles(directory=str(DATA_DIR / "sample_scans")), name="scans")

# Mount /uploads for photo persistence
uploads_dir = FRONTEND_DIR / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

