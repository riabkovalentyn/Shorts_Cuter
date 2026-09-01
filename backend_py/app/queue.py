"""Optional ARQ (Redis) queue.

Mirrors the Node behaviour: when REDIS_URL is set the pipeline runs in a
separate worker process, otherwise it runs as an in-process background task.
"""

import logging

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings

log = logging.getLogger(__name__)

_pool: ArqRedis | None = None


def queue_enabled() -> bool:
    return bool(get_settings().redis_url)


def redis_settings() -> RedisSettings:
    url = get_settings().redis_url
    if not url:
        raise RuntimeError(
            "REDIS_URL is not set. The ARQ worker is only needed when you want "
            "the pipeline to run outside the API process; without REDIS_URL the "
            "API runs it in-process and no worker should be started."
        )
    return RedisSettings.from_dsn(url)


async def get_pool() -> ArqRedis | None:
    global _pool
    if not queue_enabled():
        return None
    if _pool is None:
        _pool = await create_pool(redis_settings())
        log.info("[queue] connected to redis")
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def enqueue_ingest(job_id: str, source_url: str, clip_length_sec: float) -> bool:
    pool = await get_pool()
    if pool is None:
        return False
    await pool.enqueue_job("run_ingest", job_id, source_url, clip_length_sec)
    log.info("[queue] enqueued ingest for job %s", job_id)
    return True
