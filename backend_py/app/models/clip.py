from typing import List, Literal, Optional

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field

ClipStatus = Literal["ready", "uploaded", "error"]


class YouTubeRef(BaseModel):
    id: Optional[str] = None
    publishedAt: Optional[str] = None


class Clip(Document):
    """Mirrors the Mongoose `Clip` model (see note in job.py about casing)."""

    jobId: Optional[PydanticObjectId] = None
    filePath: str
    thumbPath: Optional[str] = None
    index: Optional[int] = None
    startSec: Optional[float] = None
    durationSec: Optional[float] = None
    score: Optional[float] = None
    title: Optional[str] = None
    description: Optional[str] = None
    hashtags: List[str] = Field(default_factory=list)
    status: ClipStatus = "ready"
    youtube: Optional[YouTubeRef] = None

    class Settings:
        name = "clips"
        indexes = ["jobId"]
