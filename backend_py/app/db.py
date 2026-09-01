import logging

from beanie import init_beanie
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.models import ALL_MODELS, Job

log = logging.getLogger(__name__)

# Beanie 2.x is built on pymongo's native async client (AsyncMongoClient);
# Motor is deprecated and its database object is not accepted by init_beanie.
_client: AsyncMongoClient | None = None


async def connect_mongo() -> AsyncMongoClient:
    global _client
    settings = get_settings()
    _client = AsyncMongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)

    db = _client.get_default_database()
    if db is None:
        raise RuntimeError(
            "MONGO_URI must include a database name, e.g. "
            "mongodb://localhost:27017/shorts_cuter"
        )

    await init_beanie(database=db, document_models=ALL_MODELS)
    log.info("[backend] mongo connected: %s", db.name)
    return _client


async def close_mongo() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def recover_orphaned_jobs() -> int:
    """Fail jobs left mid-flight by a previous process.

    The Node backend ran the pipeline as a fire-and-forget task, so a restart
    stranded jobs at `processing` forever. Nothing can resume them, so mark
    them failed at startup and let the user retry.
    """
    try:
        result = await Job.find(Job.status == "processing").update(
            {"$set": {"status": "error", "error": "Interrupted by a server restart"}}
        )
    except PyMongoError:
        log.exception("[backend] failed to recover orphaned jobs")
        return 0

    count = getattr(result, "modified_count", 0) or 0
    if count:
        log.warning("[backend] marked %d interrupted job(s) as error", count)
    return count
