from datetime import datetime, timezone
from typing import Optional

from beanie import Document
from pydantic import Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Token(Document):
    """Mirrors the Mongoose `Token` model (see note in job.py about casing)."""

    provider: str
    refreshToken: str
    accessToken: Optional[str] = None
    scope: Optional[str] = None
    tokenType: Optional[str] = None
    expiryDate: Optional[int] = None
    createdAt: datetime = Field(default_factory=_utcnow)
    updatedAt: datetime = Field(default_factory=_utcnow)

    class Settings:
        name = "tokens"
        indexes = ["provider"]
