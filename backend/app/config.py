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

    # News pipeline — offline-first (see docs/06-news-pipeline.md). "rules" needs no
    # setup at all; "local" needs Ollama running; "claude" needs an API key. Any tier
    # falls back to rules automatically if its dependency isn't actually available.
    news_pdf_min_page_chars: int = 400  # below this, a page is ad/light and skipped
    news_enricher: str = "rules"  # rules | local | claude
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    anthropic_api_key: str = ""  # only used when news_enricher=claude
    news_rss_enrichment: bool = True  # set false for fully air-gapped operation
    news_rss_max_related: int = 3

    @property
    def use_mongo(self) -> bool:
        return bool(self.mongodb_url.strip())


settings = Settings()
