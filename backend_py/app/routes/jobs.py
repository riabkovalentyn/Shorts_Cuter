from beanie import PydanticObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException

from app.models import Job
from app.serializers import job_to_dict

router = APIRouter()


@router.get("/{job_id}")
async def get_job(job_id: str) -> dict:
    try:
        object_id = PydanticObjectId(job_id)
    except (InvalidId, ValueError):
        raise HTTPException(status_code=404, detail="Not found") from None

    job = await Job.get(object_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Not found")
    return job_to_dict(job)
