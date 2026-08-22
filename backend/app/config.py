"""Application settings loaded from environment / .env."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # Mongo — leave empty to use the JSON-file fallback store (works with no DB).
    mongodb_url: str = ""
    mongodb_db: str = "stocks"

    # Where the JSON fallback store persists (used only when mongodb_url is empty).
    data_dir: str = str(BASE_DIR / "app" / "data")

    # Market data
    quote_cache_ttl_seconds: int = 900  # 15 min
    yf_suffix_default: str = ".NS"       # NSE; BSE-only symbols fall back to .BO

    # CORS — the React dev server / GitHub Pages origin
    cors_origins: str = "*"

    @property
    def use_mongo(self) -> bool:
        return bool(self.mongodb_url.strip())


settings = Settings()
