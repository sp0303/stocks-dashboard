"""Settings configuration for pi_api using pydantic-settings."""

from typing import List
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.v2", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Portfolio Intelligence API"
    VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    HOST: str = "127.0.0.1"
    PORT: int = 8200

    # PostgreSQL Database URL
    # Required in every deployed environment (set in /etc/pi/api.env). The default only
    # reaches a local, password-less dev database — never production (AGENTS §13).
    DATABASE_URL: str = "postgresql://localhost:5432/portfolio"
    DB_POOL_MIN_SIZE: int = 2
    DB_POOL_MAX_SIZE: int = 10

    # Redis URLs
    REDIS_CACHE_URL: str = "redis://127.0.0.1:6390/0"
    REDIS_STREAMS_URL: str = "redis://127.0.0.1:6391/0"

    # Security
    # Dev-only default; refused outside ENVIRONMENT=development (see _require_real_secret).
    JWT_SECRET: str = "dev-only-insecure-jwt-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    CORS_ORIGINS: List[str] = [
        "http://localhost:5180",
        "http://localhost:5182",
        "http://127.0.0.1:5180",
        "http://127.0.0.1:5182",
        "https://sarey.tech",
    ]

    @model_validator(mode="after")
    def _require_real_secret(self) -> "Settings":
        if self.ENVIRONMENT != "development" and self.JWT_SECRET == "dev-only-insecure-jwt-secret":
            raise ValueError("JWT_SECRET must be set via env outside development.")
        return self


settings = Settings()
