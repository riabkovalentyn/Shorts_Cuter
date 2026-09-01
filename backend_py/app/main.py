import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import queue
from app.config import get_settings
from app.db import close_mongo, connect_mongo, recover_orphaned_jobs
from app.routes import auth, clips, jobs, projects

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    settings.clips_dir.mkdir(parents=True, exist_ok=True)
    log.info("[backend] storage dir: %s", settings.storage_dir)

    await connect_mongo()

    # Only safe when this process owns the pipeline. With ARQ the worker may
    # still be running jobs that this API restart did not interrupt.
    if not queue.queue_enabled():
        await recover_orphaned_jobs()
    else:
        log.info("[backend] REDIS_URL set - using the ARQ worker for ingest")

    yield

    await queue.close_pool()
    await close_mongo()


app = FastAPI(title="Shorts Cuter API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# The frontend reads `error` off failed responses (it was written against the
# Express backend), so keep that shape instead of FastAPI's `detail`.
@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
    message = first.get("msg", "Invalid request")
    detail = (field + ": " + message) if field else message
    return JSONResponse(status_code=400, content={"error": detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


@app.middleware("http")
async def storage_guard(request: Request, call_next):
    """Reject zero-byte media and path traversal before StaticFiles sees it.

    A zero-byte file makes browsers raise RangeNotSatisfiable, so the Node
    backend turned those into a 404; same behaviour here.
    """
    path = request.url.path
    if path.startswith("/storage/"):
        settings = get_settings()
        relative = unquote(path[len("/storage/") :])
        try:
            target = (settings.storage_dir / relative).resolve()
        except OSError:
            return Response(status_code=400)
        if not target.is_relative_to(settings.storage_dir):
            return Response(status_code=400)
        if target.is_file() and target.stat().st_size == 0:
            return JSONResponse(status_code=404, content={"error": "File is empty"})
    return await call_next(request)


app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(clips.router, prefix="/api/clips", tags=["clips"])
app.include_router(auth.router, prefix="/api/auth/youtube", tags=["auth"])


@app.get("/")
async def root() -> dict:
    return {
        "ok": True,
        "name": "Shorts Cuter API",
        "health": "/health",
        "api": "/api",
        "docs": "/docs",
    }


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


def _mount_storage() -> None:
    storage_dir: Path = get_settings().storage_dir
    storage_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/storage", StaticFiles(directory=storage_dir), name="storage")


_mount_storage()
