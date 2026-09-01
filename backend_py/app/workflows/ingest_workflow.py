"""The end-to-end pipeline: download -> detect highlights -> cut -> metadata."""

import asyncio
import logging

from app.config import get_settings
from app.models import Job
from app.services import clipper, highlight, ingest, metadata

log = logging.getLogger(__name__)

# Keep strong references so in-process tasks are not garbage collected midway.
_background_tasks: set[asyncio.Task] = set()


async def run_pipeline(job_id: str, source_url: str, clip_length_sec: float) -> None:
    settings = get_settings()
    job = await Job.get(job_id)
    if job is None:
        log.error("[pipeline] job %s disappeared before it started", job_id)
        return

    try:
        job.status = "processing"
        job.error = None
        await job.save()

        source = await ingest.download(source_url, job_id)

        windows = await highlight.detect_highlights(
            source, clip_length_sec, max_clips=settings.max_clips
        )
        if windows:
            clips = await clipper.slice_windows(source, windows, job_id)
        else:
            clips = await clipper.slice_fixed(source, clip_length_sec, job_id)

        await metadata.populate(clips)

        if not clips:
            raise RuntimeError("Pipeline produced no clips")

        job.status = "done"
        await job.save()
        log.info("[pipeline] job %s done with %d clip(s)", job_id, len(clips))
    except Exception as exc:  # noqa: BLE001 - record the failure on the job
        log.exception("[pipeline] job %s failed", job_id)
        refreshed = await Job.get(job_id)
        if refreshed is not None:
            refreshed.status = "error"
            refreshed.error = str(exc)[:1000]
            await refreshed.save()


async def start_ingest(source_url: str, clip_length_sec: float) -> Job:
    """Create the Job and kick off processing, returning immediately."""
    from app import queue

    job = Job(sourceUrl=source_url, status="processing")
    await job.insert()
    job_id = str(job.id)

    if await queue.enqueue_ingest(job_id, source_url, clip_length_sec):
        return job

    task = asyncio.create_task(run_pipeline(job_id, source_url, clip_length_sec))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return job
