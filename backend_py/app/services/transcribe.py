"""Speech-to-text for the source VOD.

Uses faster-whisper (CTranslate2, not torch) so the dependency stays around
150 MB rather than several GB. The transcript is what the AI selector reads -
without it there is nothing to reason about except pixels and silence.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings

log = logging.getLogger(__name__)

_model = None
_model_key: tuple[str, str, str] | None = None


class TranscriptionUnavailable(RuntimeError):
    """faster-whisper is not installed, or the model could not be loaded."""


@dataclass
class Segment:
    start: float
    end: float
    text: str


def _load_model():
    """Load and cache the Whisper model (loading costs seconds, so reuse it)."""
    global _model, _model_key
    settings = get_settings()
    key = (
        settings.whisper_model,
        settings.whisper_device,
        settings.whisper_compute_type,
    )
    if _model is not None and _model_key == key:
        return _model

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise TranscriptionUnavailable(
            "faster-whisper is not installed. Install it with "
            "`pip install faster-whisper` to enable AI highlight selection."
        ) from exc

    log.info(
        "[transcribe] loading whisper model=%s device=%s compute=%s",
        *key,
    )
    _model = WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    _model_key = key
    return _model


def _transcribe_blocking(path: Path) -> list[Segment]:
    settings = get_settings()
    model = _load_model()
    segments, info = model.transcribe(
        str(path),
        language=settings.whisper_language,
        vad_filter=True,
        beam_size=1,
    )
    # `segments` is a generator - iterating is what actually does the work.
    out = [
        Segment(start=float(s.start), end=float(s.end), text=s.text.strip())
        for s in segments
        if (s.text or "").strip()
    ]
    log.info(
        "[transcribe] language=%s segments=%d",
        getattr(info, "language", "?"),
        len(out),
    )
    return out


async def transcribe(path: Path) -> list[Segment]:
    """Transcribe `path`, returning timestamped segments."""
    return await asyncio.to_thread(_transcribe_blocking, path)


def to_prompt_text(segments: list[Segment], max_chars: int | None = None) -> str:
    """Render segments as `[H:MM:SS] text` lines for the model.

    Timestamps are absolute so the model can name exact cut points.
    """
    lines: list[str] = []
    for seg in segments:
        total = int(seg.start)
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        stamp = (
            f"{hours}:{minutes:02d}:{seconds:02d}"
            if hours
            else f"{minutes}:{seconds:02d}"
        )
        lines.append(f"[{stamp}] {seg.text}")
    text = "\n".join(lines)
    if max_chars is not None and len(text) > max_chars:
        # Never silently drop the tail: say so, so the caller can chunk.
        raise ValueError(
            f"Transcript is {len(text)} chars, over the {max_chars} limit"
        )
    return text
