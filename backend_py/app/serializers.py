"""Response shaping.

The frontend was written against the Mongoose/Express JSON, so these builders
emit exactly the same keys - notably `_id` rather than Pydantic's `id`.
"""

from typing import Any

from app.models import Clip, Job
from app.storage import to_public_url


def job_to_dict(job: Job) -> dict[str, Any]:
    return {
        "_id": str(job.id),
        "sourceUrl": job.sourceUrl,
        "clipLengthSec": job.clipLengthSec,
        "status": job.status,
        "error": job.error,
        "createdAt": job.createdAt.isoformat() if job.createdAt else None,
    }


def clip_to_dict(clip: Clip) -> dict[str, Any]:
    return {
        "_id": str(clip.id),
        "jobId": str(clip.jobId) if clip.jobId else None,
        "index": clip.index,
        "startSec": clip.startSec,
        "durationSec": clip.durationSec,
        "score": clip.score,
        "title": clip.title,
        "description": clip.description,
        "hashtags": clip.hashtags or [],
        "status": clip.status,
        "youtube": clip.youtube.model_dump() if clip.youtube else None,
        "filePath": clip.filePath,
        "thumbPath": clip.thumbPath,
        "fileUrl": to_public_url(clip.filePath),
        "thumbUrl": to_public_url(clip.thumbPath),
    }
