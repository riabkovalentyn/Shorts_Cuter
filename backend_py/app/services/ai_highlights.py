"""AI highlight selection.

Reads the VOD transcript and asks Claude which moments a viewer would actually
clip, in Twitch's clip shape: 5-60s, self-contained, payoff near the end.

This replaces the arithmetic scorer (`active_seconds + 0.75 * scene_count`),
which measured how *busy* a window was rather than whether anything happened.
"""

import json
import logging

from pydantic import BaseModel, Field, ValidationError

from app.config import get_settings
from app.services.highlight import HighlightWindow
from app.services.transcribe import Segment, to_prompt_text

log = logging.getLogger(__name__)


class AIUnavailable(RuntimeError):
    """No API key, SDK missing, or the model declined to answer."""


class _Clip(BaseModel):
    start_sec: float
    end_sec: float
    title: str
    description: str
    score: float = Field(ge=0, le=100)
    reason: str


class _Plan(BaseModel):
    clips: list[_Clip]


_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_sec": {
                        "type": "number",
                        "description": "Clip start, in seconds from the VOD start.",
                    },
                    "end_sec": {
                        "type": "number",
                        "description": (
                            "Clip end, in seconds. The payoff must land in the "
                            "final third of the clip."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "YouTube title, at most 100 characters.",
                    },
                    "description": {"type": "string"},
                    "score": {
                        "type": "number",
                        "description": "0-100: how likely a viewer would clip this.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "One sentence on why this moment lands.",
                    },
                },
                "required": [
                    "start_sec",
                    "end_sec",
                    "title",
                    "description",
                    "score",
                    "reason",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}

_SYSTEM = """You select clip-worthy moments from livestream VODs.

You are replicating what Twitch viewers do when they hit the Clip button, so \
match that behaviour exactly:

- A viewer clips AFTER something happens. Twitch captures the seconds \
LEADING UP TO the press, so the payoff belongs in the FINAL THIRD of the clip, \
never at the start.
- Clips run 5-60 seconds. Vary the length to fit the moment; do not default to \
one length.
- A clip must stand alone. Include just enough lead-in for the payoff to make \
sense to someone who has not watched the stream, and no more.

What gets clipped: punchlines and jokes that land, genuine reactions (shock, \
laughter, rage), clutch plays and dramatic failures, strong or spicy opinions, \
surprising admissions or stories, moments where the streamer's energy visibly \
spikes.

What does NOT get clipped: routine chatter, greetings, reading donations or \
subs, technical or setup talk, long explanations, setup with no payoff, or \
anything that is only interesting if you watched the last hour.

Be selective. A four-hour stream rarely contains more than a handful of \
genuinely clip-worthy moments. Returning six strong clips is far better than \
twenty mediocre ones. If the stream simply has no good moments, return fewer \
clips or an empty list - do not pad.

Titles must describe what actually happens, in the streamer's register, with \
no clickbait filler ("You won't believe...", "INSANE!!!"). No hashtags in the \
title."""


def _build_prompt(transcript: str, max_clips: int, duration: float) -> str:
    minutes = int(duration // 60)
    return (
        f"Below is the timestamped transcript of a {minutes}-minute livestream "
        f"VOD.\n\nSelect up to {max_clips} clip-worthy moments. Timestamps in "
        "your response must be in SECONDS from the start of the VOD, and must "
        "fall inside the stream's duration of "
        f"{duration:.0f} seconds.\n\nClips must not overlap each other.\n\n"
        "<transcript>\n"
        f"{transcript}\n"
        "</transcript>"
    )


def _to_windows(plan: _Plan, duration: float) -> list[HighlightWindow]:
    """Validate the model's picks and coerce them into the Twitch clip shape."""
    settings = get_settings()
    windows: list[HighlightWindow] = []

    for clip in sorted(plan.clips, key=lambda c: -c.score):
        start = max(0.0, float(clip.start_sec))
        end = min(float(duration), float(clip.end_sec))
        if end <= start:
            log.warning("[ai] dropping clip with non-positive length at %.1fs", start)
            continue

        # Clamp to Twitch's 5-60s envelope, trimming from the START so the
        # payoff at the end survives.
        span = end - start
        if span > settings.clip_max_sec:
            start = end - settings.clip_max_sec
            span = settings.clip_max_sec
        if span < settings.clip_min_sec:
            start = max(0.0, end - settings.clip_min_sec)
            span = end - start
            if span < settings.clip_min_sec:
                log.warning("[ai] dropping too-short clip at %.1fs", start)
                continue

        candidate = HighlightWindow(
            start=start,
            duration=span,
            score=float(clip.score),
            title=clip.title.strip()[:100] or None,
            description=clip.description.strip() or None,
            reason=clip.reason.strip() or None,
        )
        if any(_overlaps(candidate, picked) for picked in windows):
            log.info("[ai] dropping overlapping clip at %.1fs", candidate.start)
            continue
        windows.append(candidate)

    windows.sort(key=lambda w: w.start)
    return windows


def _overlaps(a: HighlightWindow, b: HighlightWindow) -> bool:
    return not (
        a.start + a.duration <= b.start or b.start + b.duration <= a.start
    )


async def select_highlights(
    segments: list[Segment], duration: float, max_clips: int
) -> list[HighlightWindow]:
    """Ask Claude which moments to clip. Raises AIUnavailable if it cannot."""
    settings = get_settings()
    if not settings.ai_enabled:
        raise AIUnavailable("ANTHROPIC_API_KEY is not set")
    if not segments:
        raise AIUnavailable("Transcript is empty - nothing to select from")

    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise AIUnavailable(
            "The anthropic SDK is not installed (`pip install anthropic`)"
        ) from exc

    transcript = to_prompt_text(segments)
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    log.info(
        "[ai] selecting up to %d clips from %d transcript segments",
        max_clips,
        len(segments),
    )

    try:
        async with client.beta.messages.stream(
            model=settings.anthropic_model,
            max_tokens=16000,
            system=_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": _build_prompt(transcript, max_clips, duration),
                }
            ],
            thinking={"type": "adaptive"},
            output_config={
                "effort": settings.ai_effort,
                "format": {"type": "json_schema", "schema": _SCHEMA},
            },
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            message = await stream.get_final_message()
    except anthropic.APIError as exc:
        raise AIUnavailable(f"Claude request failed: {exc}") from exc

    if message.stop_reason == "refusal":
        detail = getattr(message.stop_details, "category", None)
        raise AIUnavailable(f"Claude declined this transcript (category={detail})")

    text = next((b.text for b in message.content if b.type == "text"), None)
    if not text:
        raise AIUnavailable("Claude returned no text block")

    try:
        plan = _Plan.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AIUnavailable(f"Could not parse the model's response: {exc}") from exc

    windows = _to_windows(plan, duration)
    usage = message.usage
    log.info(
        "[ai] model returned %d clip(s), %d usable (in=%s out=%s tokens)",
        len(plan.clips),
        len(windows),
        getattr(usage, "input_tokens", "?"),
        getattr(usage, "output_tokens", "?"),
    )
    return windows
