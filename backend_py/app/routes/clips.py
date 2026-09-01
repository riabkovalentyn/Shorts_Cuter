import logging

from beanie import PydanticObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query

from app.models import Clip
from app.serializers import clip_to_dict
from app.services import youtube
from app.services.youtube import YouTubeNotConfigured, YouTubeNotConnected

log = logging.getLogger(__name__)
router = APIRouter()


def _object_id(raw: str) -> PydanticObjectId:
    try:
        return PydanticObjectId(raw)
    except (InvalidId, ValueError):
        raise HTTPException(status_code=404, detail="Not found") from None


@router.get("")
@router.get("/", include_in_schema=False)
async def list_clips(jobId: str | None = Query(default=None)) -> list[dict]:
    if jobId:
        clips = await Clip.find(Clip.jobId == _object_id(jobId)).to_list()
    else:
        clips = await Clip.find_all().to_list()
    clips.sort(key=lambda c: (c.index if c.index is not None else 0))
    return [clip_to_dict(clip) for clip in clips]


@router.post("/{clip_id}/upload")
async def upload_clip(clip_id: str) -> dict:
    clip = await Clip.get(_object_id(clip_id))
    if clip is None:
        raise HTTPException(status_code=404, detail="Not found")

    try:
        updated = await youtube.upload_clip(clip)
    except (YouTubeNotConfigured, YouTubeNotConnected) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - surface the API error to the UI
        log.exception("[clips] upload failed for %s", clip_id)
        clip.status = "error"
        await clip.save()
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return clip_to_dict(updated)
