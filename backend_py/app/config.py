from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment configuration.

    Field names map case-insensitively to the same env vars the Node backend
    used (PORT, MONGO_URI, STORAGE_DIR, GOOGLE_CLIENT_ID, ...), so existing
    .env files and Render/compose configs keep working unchanged.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    port: int = 4000
    mongo_uri: str = "mongodb://localhost:27017/shorts_cuter"
    storage_dir: Path = Path("./storage")

    google_client_id: str | None = None
    google_client_secret: str | None = None
    yt_redirect_uri: str = "http://localhost:4000/api/auth/youtube/callback"

    redis_url: str | None = None

    # Pipeline tuning
    max_clips: int = 10
    download_idle_timeout_sec: int = 900
    download_hard_timeout_sec: int = 7200

    # ffmpeg stage timeouts. Analysis decodes the whole video, so it needs a
    # generous budget; probing and per-clip encoding should be quick.
    analysis_timeout_sec: int = 3600
    probe_timeout_sec: int = 120
    clip_timeout_sec: int = 900

    # Keep the downloaded source video after clipping. Off by default: a 4h
    # Twitch VOD is several GB and nothing else reads it once clips exist.
    keep_source_video: bool = False

    # --- Twitch clip format -------------------------------------------------
    # Twitch clips run 5-60s and the payoff lands at the end (its own API
    # defines vod_offset as the clip's END). We mirror that shape.
    clip_min_sec: float = 5.0
    clip_max_sec: float = 60.0

    # --- AI highlight selection ---------------------------------------------
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5"
    ai_effort: str = "high"

    # Transcription feeds the selector. faster-whisper is CTranslate2-based,
    # so this pulls in no torch.
    whisper_model: str = "base"
    whisper_device: str = "auto"
    whisper_compute_type: str = "default"
    whisper_language: str | None = None

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def downloads_dir(self) -> Path:
        return self.storage_dir / "downloads"

    @property
    def clips_dir(self) -> Path:
        return self.storage_dir / "clips"

    @property
    def youtube_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.storage_dir = s.storage_dir.expanduser().resolve()
    return s
