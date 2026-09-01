from fastapi import APIRouter, status
from pydantic import BaseModel, Field, field_validator

from app.workflows.ingest_workflow import start_ingest

router = APIRouter()


class CreateProjectRequest(BaseModel):
    sourceUrl: str
    clipLengthSec: float = Field(default=30)

    @field_validator("sourceUrl")
    @classmethod
    def _must_be_http_url(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("sourceUrl is required")
        if not cleaned.lower().startswith(("http://", "https://")):
            raise ValueError("sourceUrl must be an http(s) URL")
        return cleaned

    @field_validator("clipLengthSec")
    @classmethod
    def _sane_clip_length(cls, value: float) -> float:
        if not value or value < 5:
            return 30.0
        return min(float(value), 600.0)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
@router.post("/", status_code=status.HTTP_202_ACCEPTED, include_in_schema=False)
async def create_project(payload: CreateProjectRequest) -> dict:
    job = await start_ingest(payload.sourceUrl, payload.clipLengthSec)
    return {"jobId": str(job.id), "status": job.status}
