"""Fill in clip titles, descriptions and hashtags.

Straight port of the Node metadataService: templated text derived from the
source platform and clip timing. This is the obvious place to swap in
transcript- or LLM-driven metadata later.
"""

import logging
import re
from datetime import date

from app.models import Clip, Job

log = logging.getLogger(__name__)

_PLATFORM_PATTERNS = [
    (re.compile(r"youtu\.?be|youtube", re.I), "YouTube"),
    (re.compile(r"twitch\.tv", re.I), "Twitch"),
    (re.compile(r"vk\.com", re.I), "VK"),
]


def detect_platform(source_url: str | None) -> str | None:
    if not source_url:
        return None
    for pattern, name in _PLATFORM_PATTERNS:
        if pattern.search(source_url):
            return name
    return None


def _mmss(seconds: float | None) -> str:
    if seconds is None:
        return "0:00"
    minutes = int(seconds // 60)
    rest = int(seconds % 60)
    return str(minutes) + ":" + str(rest).zfill(2)


async def populate(clips: list[Clip], keep_text: bool = False) -> None:
    """Fill in hashtags, and (unless `keep_text`) title and description.

    `keep_text=True` is used when the AI selector already wrote per-clip titles
    and descriptions - templated text would only make them worse.
    """
    if not clips:
        return

    source_url: str | None = None
    job_id = clips[0].jobId
    if job_id is not None:
        job = await Job.get(job_id)
        source_url = job.sourceUrl if job else None

    platform = detect_platform(source_url)

    base_tags = ["#Shorts", "#Stream"]
    if platform:
        base_tags.append("#" + platform)

    for i, clip in enumerate(clips, start=1):
        start, span = clip.startSec, clip.durationSec
        if start is not None and span is not None:
            timing = "at " + _mmss(start) + " (" + _mmss(span) + ")"
        else:
            timing = "part " + str(i)

        if not keep_text:
            prefix = platform + " " if platform else ""
            clip.title = prefix + "Highlight " + str(i) + " — " + timing
            clip.description = "\n".join(
                part
                for part in (
                    "Clip " + str(i) + " " + timing + ".",
                    "Source: " + source_url if source_url else None,
                    "Generated on "
                    + date.today().isoformat()
                    + " by Shorts Cuter.",
                )
                if part
            )

        specific = [tag for tag in (("#" + platform) if platform else None,) if tag]
        if not keep_text:
            # Timing tags are noise on YouTube; keep them only on the legacy
            # templated path so existing behaviour is unchanged there.
            if start is not None:
                specific.append("#Start_" + str(int(start)) + "s")
            if span is not None:
                specific.append("#Duration_" + str(int(span)) + "s")
            specific.append("#Clip" + str(i))

        clip.hashtags = list(dict.fromkeys(base_tags + specific))
        await clip.save()

    log.info("[metadata] populated %d clip(s), platform=%s", len(clips), platform)
