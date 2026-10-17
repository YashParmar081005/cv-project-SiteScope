"""Application settings, read from environment variables (and `.env` in development)."""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .paths import DATA_DIR, PROJECT_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(PROJECT_ROOT / ".env",), extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = True

    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "sitescope"

    jwt_secret: str | None = None
    jwt_expire_minutes: int = 12 * 60
    cookie_secure: bool = False
    password_iterations: int = 600_000
    allow_registration: bool = True
    admin_email: str | None = None
    admin_password: str | None = None
    admin_name: str = "Administrator"

    storage_dir: Path = DATA_DIR / "storage"
    frontend_dir: Path | None = PROJECT_ROOT / "frontend"  # static HTML/CSS/JS served at "/"
    max_upload_mb: int = 15

    @model_validator(mode="after")
    def _secrets(self) -> "Settings":
        if not self.jwt_secret:
            if self.app_env == "production":
                raise ValueError("JWT_SECRET must be set in production")
            self.jwt_secret = secrets.token_urlsafe(48)  # dev only: sessions reset on restart
        elif self.app_env == "production" and len(self.jwt_secret) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters in production")
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
