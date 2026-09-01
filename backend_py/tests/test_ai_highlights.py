"""Tests for AI clip selection.

Covers the Twitch clip-shape rules applied to whatever the model returns:
5-60s, non-overlapping, in-bounds, payoff preserved at the end. No API key
and no network needed - the model call itself is not exercised here.
"""

import asyncio

import pytest

from app.config import get_settings
from app.services import ai_highlights
from app.services.ai_highlights import AIUnavailable, _Plan, _to_windows
from app.services.transcribe import Segment, to_prompt_text


@pytest.fixture(autouse=True)
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost:27017/test_db")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def plan(*clips: dict) -> _Plan:
    base = {
        "title": "A title",
        "description": "A description",
        "score": 80.0,
        "reason": "It lands.",
    }
    return _Plan.model_validate({"clips": [{**base, **c} for c in clips]})


# --------------------------------------------------------------------------
# Twitch clip shape: 5-60s
# --------------------------------------------------------------------------


def test_overlong_clip_is_trimmed_from_the_start():
    """Twitch clips cap at 60s, and the payoff lives at the END.

    So an over-long pick must lose its opening, never its ending.
    """
    windows = _to_windows(plan({"start_sec": 100.0, "end_sec": 300.0}), duration=600.0)
    assert len(windows) == 1
    assert windows[0].duration == pytest.approx(60.0)
    assert windows[0].start + windows[0].duration == pytest.approx(300.0)


def test_too_short_clip_is_extended_backwards():
    """Extending backwards keeps the payoff at the end."""
    windows = _to_windows(plan({"start_sec": 100.0, "end_sec": 102.0}), duration=600.0)
    assert len(windows) == 1
    assert windows[0].duration == pytest.approx(5.0)
    assert windows[0].start + windows[0].duration == pytest.approx(102.0)


def test_clip_too_close_to_the_start_to_extend_is_dropped():
    windows = _to_windows(plan({"start_sec": 0.0, "end_sec": 2.0}), duration=600.0)
    assert windows == []


def test_every_window_respects_the_configured_envelope():
    windows = _to_windows(
        plan(
            {"start_sec": 10.0, "end_sec": 400.0},
            {"start_sec": 500.0, "end_sec": 503.0},
            {"start_sec": 520.0, "end_sec": 545.0},
        ),
        duration=600.0,
    )
    cfg = get_settings()
    for w in windows:
        assert cfg.clip_min_sec <= w.duration <= cfg.clip_max_sec


# --------------------------------------------------------------------------
# bounds, overlaps, ordering
# --------------------------------------------------------------------------


def test_end_past_the_vod_is_clamped_to_duration():
    windows = _to_windows(plan({"start_sec": 80.0, "end_sec": 999.0}), duration=100.0)
    assert len(windows) == 1
    assert windows[0].start + windows[0].duration <= 100.0 + 1e-6


def test_inverted_clip_is_dropped():
    windows = _to_windows(plan({"start_sec": 200.0, "end_sec": 100.0}), duration=600.0)
    assert windows == []


def test_overlapping_clips_keep_the_higher_score():
    windows = _to_windows(
        plan(
            {"start_sec": 100.0, "end_sec": 130.0, "score": 40.0, "title": "weak"},
            {"start_sec": 110.0, "end_sec": 140.0, "score": 90.0, "title": "strong"},
        ),
        duration=600.0,
    )
    assert len(windows) == 1
    assert windows[0].title == "strong"


def test_windows_are_sorted_by_start_time():
    windows = _to_windows(
        plan(
            {"start_sec": 400.0, "end_sec": 430.0, "score": 90.0},
            {"start_sec": 100.0, "end_sec": 130.0, "score": 50.0},
            {"start_sec": 250.0, "end_sec": 280.0, "score": 70.0},
        ),
        duration=600.0,
    )
    assert [w.start for w in windows] == [100.0, 250.0, 400.0]


def test_variable_lengths_are_preserved():
    """Twitch clips are not all one length - do not normalise them."""
    windows = _to_windows(
        plan(
            {"start_sec": 100.0, "end_sec": 112.0},
            {"start_sec": 200.0, "end_sec": 245.0},
            {"start_sec": 300.0, "end_sec": 322.0},
        ),
        duration=600.0,
    )
    durations = sorted(round(w.duration) for w in windows)
    assert durations == [12, 22, 45]


def test_title_is_truncated_to_youtube_limit():
    windows = _to_windows(
        plan({"start_sec": 10.0, "end_sec": 40.0, "title": "x" * 250}),
        duration=600.0,
    )
    assert len(windows[0].title) == 100


def test_ai_metadata_is_carried_onto_the_window():
    windows = _to_windows(
        plan(
            {
                "start_sec": 10.0,
                "end_sec": 40.0,
                "title": "He finally admits it",
                "description": "The streamer caves after ten minutes.",
                "reason": "Payoff to a long running bit.",
            }
        ),
        duration=600.0,
    )
    assert windows[0].title == "He finally admits it"
    assert windows[0].description.startswith("The streamer caves")
    assert windows[0].reason.startswith("Payoff")


# --------------------------------------------------------------------------
# preconditions
# --------------------------------------------------------------------------


def test_select_requires_an_api_key():
    with pytest.raises(AIUnavailable, match="ANTHROPIC_API_KEY"):
        asyncio.run(ai_highlights.select_highlights([], duration=600.0, max_clips=5))


def test_select_requires_a_transcript(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_settings.cache_clear()
    with pytest.raises(AIUnavailable, match="Transcript is empty"):
        asyncio.run(ai_highlights.select_highlights([], duration=600.0, max_clips=5))


def test_empty_plan_yields_no_windows():
    assert _to_windows(_Plan(clips=[]), duration=600.0) == []


# --------------------------------------------------------------------------
# transcript rendering
# --------------------------------------------------------------------------


def test_transcript_timestamps_are_absolute():
    segments = [
        Segment(start=5.0, end=8.0, text="hello"),
        Segment(start=65.5, end=70.0, text="a minute in"),
        Segment(start=3725.0, end=3730.0, text="an hour in"),
    ]
    rendered = to_prompt_text(segments).splitlines()
    assert rendered[0] == "[0:05] hello"
    assert rendered[1] == "[1:05] a minute in"
    assert rendered[2] == "[1:02:05] an hour in"


def test_transcript_over_the_limit_raises_rather_than_truncating():
    segments = [Segment(start=0.0, end=1.0, text="x" * 500)]
    with pytest.raises(ValueError, match="over the"):
        to_prompt_text(segments, max_chars=100)


# --------------------------------------------------------------------------
# pipeline fallback: AI trouble must never sink the job
# --------------------------------------------------------------------------


def _run_select(monkeypatch, ai_behaviour, tmp_path):
    from app.services import highlight
    from app.workflows import ingest_workflow

    heuristic = [highlight.HighlightWindow(start=0.0, duration=30.0, score=1.0)]

    async def fake_probe(_path):
        return 600.0

    async def fake_transcribe(_path):
        return [Segment(start=0.0, end=5.0, text="hi")]

    async def fake_detect(_path, _len, max_clips=5):
        return heuristic

    monkeypatch.setattr(ingest_workflow.media, "probe_duration", fake_probe)
    monkeypatch.setattr(ingest_workflow, "transcribe", fake_transcribe)
    monkeypatch.setattr(ingest_workflow.highlight, "detect_highlights", fake_detect)
    monkeypatch.setattr(
        ingest_workflow.ai_highlights, "select_highlights", ai_behaviour
    )
    return asyncio.run(ingest_workflow._select_windows(tmp_path / "v.mp4", 30.0))


def test_ai_refusal_falls_back_to_the_heuristic(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_settings.cache_clear()

    async def refuses(*_a, **_k):
        raise AIUnavailable("Claude declined this transcript")

    windows, from_ai = _run_select(monkeypatch, refuses, tmp_path)
    assert from_ai is False
    assert len(windows) == 1


def test_unexpected_ai_error_falls_back_rather_than_raising(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_settings.cache_clear()

    async def explodes(*_a, **_k):
        raise RuntimeError("connection reset")

    windows, from_ai = _run_select(monkeypatch, explodes, tmp_path)
    assert from_ai is False
    assert len(windows) == 1


def test_ai_success_is_used_and_flagged(monkeypatch, tmp_path):
    from app.services import highlight

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    get_settings.cache_clear()

    async def succeeds(*_a, **_k):
        return [
            highlight.HighlightWindow(
                start=90.0, duration=22.0, score=95.0, title="AI title"
            )
        ]

    windows, from_ai = _run_select(monkeypatch, succeeds, tmp_path)
    assert from_ai is True
    assert windows[0].title == "AI title"


def test_no_api_key_skips_the_ai_path_entirely(monkeypatch, tmp_path):
    async def must_not_run(*_a, **_k):
        raise AssertionError("AI must not be called without a key")

    windows, from_ai = _run_select(monkeypatch, must_not_run, tmp_path)
    assert from_ai is False
    assert len(windows) == 1
