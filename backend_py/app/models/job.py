from datetime import datetime, timezone
from typing import Literal, Optional

from beanie import Document
from pydantic import Field

JobStatus = Literal["pending", "processing", "done", "error"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Document):
    """Mirrors the Mongoose `Job` model.

    NOTE: field names are camelCase on purpose. The documents were written by
    the previous Node/Mongoose backend and the frontend reads the same keys, so
    keeping Python attribute == Mongo field == JSON key means zero data
    migration and zero frontend changes.
    """

    sourceUrl: str
    status: JobStatus = "pending"
    error: Optional[str] = None
    createdAt: datetime = Field(default_factory=_utcnow)

    class Settings:
        name = "jobs"
