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
