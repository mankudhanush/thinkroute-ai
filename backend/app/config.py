from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    database_path: Path
    secret_key: str
    encryption_key: str | None
    provider_timeout_seconds: float
    cors_origins: tuple[str, ...]
    ollama_base_url: str
    cloudflare_account_id: str | None


def _settings() -> Settings:
    database_path = Path(os.getenv("DATABASE_PATH", "./data/thinkroute.db"))
    if not database_path.is_absolute():
        database_path = BACKEND_ROOT / database_path

    encryption_key = os.getenv("ENCRYPTION_KEY") or None
    cloudflare_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID") or None

    return Settings(
        app_name=os.getenv("APP_NAME", "ThinkRoute AI API"),
        environment=os.getenv("APP_ENV", "development"),
        database_path=database_path,
        secret_key=os.getenv("SECRET_KEY", "thinkroute-development-secret"),
        encryption_key=encryption_key,
        provider_timeout_seconds=float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "30")),
        cors_origins=_csv(os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3002,http://127.0.0.1:3002,http://localhost:3003,http://127.0.0.1:3003,http://localhost:3004,http://127.0.0.1:3004,http://localhost:3005,http://127.0.0.1:3005")),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        cloudflare_account_id=cloudflare_account_id,
    )


settings = _settings()
