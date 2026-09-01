"""Verification that the Python port matches the Node behaviour it replaces.

These cover the pure logic - highlight scoring, path mapping, metadata
templating, URL classification - which is where a port silently drifts.
Nothing here needs MongoDB or ffmpeg.
"""

import asyncio

import pytest

from app.config import get_settings
from app.services import highlight, ingest, metadata


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("MONGO_URI", "mongodb://localhost:27017/test_db")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


# --------------------------------------------------------------------------
# storage path mapping (the Node version had a broken backslash regex here)
# --------------------------------------------------------------------------


def test_public_url_for_path_inside_storage(storage):
    from app.storage import to_public_url

    clip = storage / "clips" / "abc_0.mp4"
    clip.parent.mkdir(parents=True)
    clip.touch()
    assert to_public_url(clip) == "/storage/clips/abc_0.mp4"


def test_public_url_for_legacy_windows_path():
    """Rows written by the Node backend hold absolute paths with backslashes."""
    from app.storage import to_public_url

    legacy = "C:\\old\\project\\storage\\clips\\64f_0.mp4"
    assert to_public_url(legacy) == "/storage/clips/64f_0.mp4"


def test_public_url_none_passthrough():
    from app.storage import to_public_url

    assert to_public_url(None) is None
    assert to_public_url("") is None


# --------------------------------------------------------------------------
# source URL classification
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,direct",
    [
        ("https://example.com/video.mp4", True),
        ("https://example.com/a/b/clip.MOV", True),
        ("https://example.com/stream.m3u8", False),
        ("https://www.youtube.com/watch?v=abc123", False),
        ("https://youtu.be/abc123", False),
        ("https://www.twitch.tv/videos/12345", False),
    ],
)
def test_direct_media_detection(url, direct):
    assert ingest._is_direct_media(url) is direct


# --------------------------------------------------------------------------
# ffmpeg output parsing
# --------------------------------------------------------------------------


def test_scene_regex_extracts_pts_times():
    stderr = (
        "[Parsed_showinfo_1 @ 000] n:0 pts:1024 pts_time:12.500 pos:1 fmt:yuv420p\n"
        "[Parsed_showinfo_1 @ 000] n:1 pts:2048 pts_time:41.375 pos:2 fmt:yuv420p\n"
    )
    assert highlight._PTS_TIME.findall(stderr) == ["12.500", "41.375"]


def test_silence_regex_pairs_starts_and_ends():
    stderr = (
        "[silencedetect @ 000] silence_start: 10.5\n"
        "[silencedetect @ 000] silence_end: 14.25 | silence_duration: 3.75\n"
        "[silencedetect @ 000] silence_start: 30.0\n"
        "[silencedetect @ 000] silence_end: 32.5 | silence_duration: 2.5\n"
    )
    starts = [float(x) for x in highlight._SILENCE_START.findall(stderr)]
    ends = [float(x) for x in highlight._SILENCE_END.findall(stderr)]
    assert list(zip(starts, ends)) == [(10.5, 14.25), (30.0, 32.5)]


# --------------------------------------------------------------------------
# highlight windowing
# --------------------------------------------------------------------------


def test_activity_is_complement_of_silence():
    activity = highlight._activity_intervals([(10.0, 20.0), (40.0, 45.0)], 60.0)
    assert activity == [(0.0, 10.0), (20.0, 40.0), (45.0, 60.0)]


def test_activity_with_no_silence_is_whole_video():
    assert highlight._activity_intervals([], 30.0) == [(0.0, 30.0)]


def test_overlapping_windows_detected():
    a = highlight.HighlightWindow(start=0.0, duration=30.0, score=1.0)
    b = highlight.HighlightWindow(start=20.0, duration=30.0, score=1.0)
    c = highlight.HighlightWindow(start=30.0, duration=30.0, score=1.0)
    assert highlight._overlaps(a, b) is True
    assert highlight._overlaps(a, c) is False  # touching, not overlapping


def _stub_detection(monkeypatch, duration, scenes, silences):
    async def fake_duration(_path):
        return duration

    async def fake_scenes(_path, threshold=highlight.SCENE_THRESHOLD):
        return scenes

    async def fake_silence(_path):
        return silences

    monkeypatch.setattr(highlight.media, "probe_duration", fake_duration)
    monkeypatch.setattr(highlight, "_detect_scenes", fake_scenes)
    monkeypatch.setattr(highlight, "_detect_silence", fake_silence)


def test_detect_highlights_picks_non_overlapping_and_sorts_by_start(monkeypatch, tmp_path):
    # Scenes cluster around 100s; the 0-60s stretch is silent.
    _stub_detection(
        monkeypatch,
        duration=180.0,
        scenes=[10.0, 100.0, 105.0, 110.0, 150.0],
        silences=[(0.0, 60.0)],
    )
    windows = asyncio.run(
        highlight.detect_highlights(tmp_path / "v.mp4", clip_length_sec=30, max_clips=3)
    )

    assert windows, "expected at least one window"
    assert len(windows) <= 3
    # Sorted by start time for stable clip indexes.
    assert [w.start for w in windows] == sorted(w.start for w in windows)
    # No two picked windows may overlap.
    for i, a in enumerate(windows):
        for b in windows[i + 1 :]:
            assert not highlight._overlaps(a, b)
    # The dense, non-silent region must beat the silent opening.
    assert max(windows, key=lambda w: w.score).start >= 60.0


def test_no_scenes_yields_a_single_leading_window(monkeypatch, tmp_path):
    """Known quirk, faithfully carried over from the Node implementation.

    `candidates` always seeds with 0.0, so `picked` is never empty and the
    "evenly spaced" fallback below it is unreachable. A 95s video with no
    detected scene cuts therefore produces ONE clip covering 0-30s rather
    than three. See test_even_spacing_fallback_is_unreachable.
    """
    _stub_detection(monkeypatch, duration=95.0, scenes=[], silences=[(0.0, 95.0)])
    windows = asyncio.run(
        highlight.detect_highlights(tmp_path / "v.mp4", clip_length_sec=30, max_clips=5)
    )
    assert [w.start for w in windows] == [0.0]


def test_even_spacing_fallback_is_unreachable(monkeypatch, tmp_path):
    """Pin the dead-code bug so a future fix has to update this test."""
    for duration in (1.0, 10.0, 95.0, 3600.0):
        _stub_detection(monkeypatch, duration=duration, scenes=[], silences=[])
        windows = asyncio.run(
            highlight.detect_highlights(
                tmp_path / "v.mp4", clip_length_sec=30, max_clips=5
            )
        )
        # Always exactly one window starting at 0 - the fallback never fires.
        assert len(windows) == 1 and windows[0].start == 0.0


def test_detect_highlights_returns_empty_for_zero_duration(monkeypatch, tmp_path):
    _stub_detection(monkeypatch, duration=0.0, scenes=[], silences=[])
    windows = asyncio.run(
        highlight.detect_highlights(tmp_path / "v.mp4", clip_length_sec=30)
    )
    assert windows == []


def test_windows_never_exceed_video_duration(monkeypatch, tmp_path):
    _stub_detection(monkeypatch, duration=40.0, scenes=[0.0, 25.0], silences=[])
    windows = asyncio.run(
        highlight.detect_highlights(tmp_path / "v.mp4", clip_length_sec=30, max_clips=5)
    )
    for w in windows:
        assert w.start + w.duration <= 40.0 + 1e-6


# --------------------------------------------------------------------------
# metadata templating
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,platform",
    [
        ("https://www.youtube.com/watch?v=x", "YouTube"),
        ("https://youtu.be/x", "YouTube"),
        ("https://www.twitch.tv/videos/1", "Twitch"),
        ("https://vk.com/video1_2", "VK"),
        ("https://example.com/a.mp4", None),
        (None, None),
    ],
)
def test_platform_detection(url, platform):
    assert metadata.detect_platform(url) == platform


@pytest.mark.parametrize(
    "seconds,formatted",
    [(None, "0:00"), (0, "0:00"), (5, "0:05"), (65, "1:05"), (600, "10:00")],
)
def test_mmss_formatting(seconds, formatted):
    assert metadata._mmss(seconds) == formatted


# --------------------------------------------------------------------------
# output discovery
# --------------------------------------------------------------------------


def test_find_output_prefers_mp4(tmp_path):
    base = tmp_path / "job1"
    (tmp_path / "job1.webm").touch()
    (tmp_path / "job1.mp4").touch()
    assert ingest._find_output(base).name == "job1.mp4"


def test_find_output_returns_none_when_absent(tmp_path):
    assert ingest._find_output(tmp_path / "nothing") is None


def test_cleanup_fragments_removes_only_fragments(tmp_path):
    base = tmp_path / "job1"
    (tmp_path / "job1.mp4").touch()
    (tmp_path / "job1.f251.webm").touch()
    (tmp_path / "job1.mp4.part").touch()
    ingest._cleanup_fragments(base)
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == ["job1.mp4"]
