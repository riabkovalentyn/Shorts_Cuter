"""ARQ worker entrypoint.

Run with:  arq app.worker.WorkerSettings
Only needed when REDIS_URL is set; otherwise the API runs the pipeline itself.
"""

import logging

from app.config import get_settings
from app.db import close_mongo, connect_mongo
from app.queue import redis_settings
from app.workflows.ingest_workflow import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("worker")


async def run_ingest(
    _ctx: dict, job_id: str, source_url: str, clip_length_sec: float
) -> None:
    await run_pipeline(job_id, source_url, clip_length_sec)


async def startup(_ctx: dict) -> None:
    settings = get_settings()
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    settings.clips_dir.mkdir(parents=True, exist_ok=True)
    await connect_mongo()
    log.info("[worker] ready")


async def shutdown(_ctx: dict) -> None:
    await close_mongo()


class WorkerSettings:
    functions = [run_ingest]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = redis_settings()
    max_jobs = 1  # ffmpeg is CPU-bound; do not run clips in parallel
    job_timeout = get_settings().download_hard_timeout_sec + 3600
    max_tries = 1
