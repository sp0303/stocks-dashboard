"""Application settings loaded from environment / .env."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# Explicitly load .env file
env_file_path = BASE_DIR / ".env"
if env_file_path.exists():
    load_dotenv(env_file_path)


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

    # Kite data caching (avoid rate limit exhaustion)
    kite_sync_cache_ttl_seconds: int = 86400  # 24 hours

    # Angel One SmartAPI — preferred quote + historical source. Logs in programmatically
    # via TOTP (no browser redirect), free, and includes historical candles. When all
    # four are set, quotes/history come from Angel; otherwise the app falls back to Yahoo.
    angel_api_key: str = ""
    angel_client_id: str = ""
    angel_pin: str = ""
    angel_totp_secret: str = ""

    @property
    def angel_enabled(self) -> bool:
        return bool(
            self.angel_api_key.strip() and self.angel_client_id.strip()
            and self.angel_pin.strip() and self.angel_totp_secret.strip()
        )

    # Kite broker API — persistent session, auto-authenticate from .env
    kite_enabled: bool = False
    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_user_id: str = ""
    kite_password: str = ""
    kite_totp_secret: str = ""

    @property
    def kite_ready(self) -> bool:
        return bool(
            self.kite_enabled and self.kite_api_key.strip()
            and self.kite_api_secret.strip() and self.kite_user_id.strip()
            and self.kite_password.strip() and self.kite_totp_secret.strip()
        )

    # CORS — the React dev server / GitHub Pages origin
    cors_origins: str = "*"

    # Ollama — local, free narration provider (tried before Cloudflare). Requires
    # `ollama serve` running on the same host with the model already pulled.
    ollama_enabled: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"

    # Cloudflare Workers AI — narration for the holding-summary insight card.
    # Leave cf_api_token empty to disable narration (structured metrics still work).
    cf_account_id: str = ""
    cf_api_token: str = ""
    cf_model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

    # Watchlist email alerts — fire when a target price is reached or an alert date
    # arrives, emailed to the owning manager. Requires a Gmail App Password in
    # alert_smtp_password (a normal account password will NOT work with Gmail SMTP);
    # until that's set, alert checks run but send nothing.
    alerts_enabled: bool = True
    alert_email_from: str = "jacobinclu@gmail.com"
    alert_smtp_host: str = "smtp.gmail.com"
    alert_smtp_port: int = 587
    alert_smtp_user: str = ""       # defaults to alert_email_from when empty
    alert_smtp_password: str = ""   # Gmail App Password — REQUIRED to actually send
    alert_check_interval_seconds: int = 900  # 15 min

    @property
    def alerts_ready(self) -> bool:
        return self.alerts_enabled and bool(self.alert_smtp_password.strip())

    @property
    def use_mongo(self) -> bool:
        return bool(self.mongodb_url.strip())


settings = Settings()
