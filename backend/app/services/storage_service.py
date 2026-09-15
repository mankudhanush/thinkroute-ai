from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Any

from cryptography.fernet import Fernet

from app.config import settings
from app.database.database import Database, utc_now
from app.models.schemas import ModelInfo, ProviderId


class SecretStore:
    def __init__(self) -> None:
        key = settings.encryption_key
        derived = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
        self.fernet = Fernet(key.encode() if key else derived)

    def encrypt(self, value: str | None) -> str | None:
        return self.fernet.encrypt(value.encode()).decode() if value else None

    def decrypt(self, value: str | None) -> str | None:
        return self.fernet.decrypt(value.encode()).decode() if value else None


class StorageService:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.secrets = SecretStore()

    def save_provider(self, provider: ProviderId, api_key: str | None, base_url: str | None, models: list[ModelInfo]) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO providers(provider, api_key, base_url, connected, models_json, connected_at)
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET api_key=excluded.api_key, base_url=excluded.base_url,
                    connected=1, models_json=excluded.models_json, connected_at=excluded.connected_at
                """,
                (provider.value, self.secrets.encrypt(api_key), base_url, self.database.json_dumps([m.model_dump(mode="json") for m in models]), utc_now()),
            )

    def delete_provider(self, provider: ProviderId) -> None:
        with self.database.connection() as connection:
            connection.execute("DELETE FROM providers WHERE provider = ?", (provider.value,))

    def get_provider(self, provider: ProviderId) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM providers WHERE provider = ?", (provider.value,)).fetchone()
        return dict(row) if row else None

    def get_credentials(self, provider: ProviderId) -> tuple[str | None, str | None]:
        record = self.get_provider(provider)
        if not record or not record["connected"]:
            return None, None
        return self.secrets.decrypt(record["api_key"]), record["base_url"]

    def list_provider_records(self) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT * FROM providers ORDER BY provider").fetchall()
        return [dict(row) for row in rows]

    def get_models(self, provider: ProviderId) -> list[ModelInfo]:
        record = self.get_provider(provider)
        return [ModelInfo.model_validate(item) for item in self.database.json_loads(record["models_json"])] if record else []

    def select_model(self, provider: ProviderId, model: str) -> None:
        with self.database.connection() as connection:
            connection.execute("INSERT INTO model_selection(id, provider, model, selected_at) VALUES (1, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET provider=excluded.provider, model=excluded.model, selected_at=excluded.selected_at", (provider.value, model, utc_now()))

    def current_model(self) -> dict[str, str] | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT provider, model FROM model_selection WHERE id = 1").fetchone()
        return dict(row) if row else None

    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        provider: ProviderId,
        model: str,
        thread_id: str | None = None,
        keywords: str | None = None,
    ) -> str:
        created_at = utc_now()
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO chat_messages(conversation_id, role, content, provider, model, created_at, thread_id, keywords) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (conversation_id, role, content, provider.value, model, created_at, thread_id, keywords),
            )
        return created_at

    def history(self, conversation_id: str) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT id, role, content, provider, model, created_at, thread_id, keywords "
                "FROM chat_messages WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_model_validation(self, provider: ProviderId, model: str, validated: bool, latency: float | None, failure_reason: str | None) -> None:
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO model_validation(provider, model, validated, latency, last_tested, failure_reason)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, model) DO UPDATE SET validated=excluded.validated, latency=excluded.latency,
                    last_tested=excluded.last_tested, failure_reason=excluded.failure_reason
                """,
                (provider.value, model, 1 if validated else 0, latency, utc_now(), failure_reason),
            )

    def get_valid_models(self, provider: ProviderId) -> list[str]:
        with self.database.connection() as connection:
            rows = connection.execute("SELECT model, last_tested, validated FROM model_validation WHERE provider = ?", (provider.value,)).fetchall()
        
        now = datetime.now(timezone.utc)
        valid_models = []
        for row in rows:
            if not row["validated"]:
                continue
            last_tested = datetime.fromisoformat(row["last_tested"])
            if now - last_tested <= timedelta(minutes=30):
                valid_models.append(row["model"])
        return valid_models
    
    def get_known_bad_models(self, provider: ProviderId) -> list[str]:
        """Models ever confirmed failing for this provider, regardless of how
        stale that result is. A past failure (deprecated model, quota, etc.)
        is a much stronger signal than a past success going stale, so this
        is not time-boxed the way get_valid_models is."""
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT model FROM model_validation WHERE provider = ? AND validated = 0",
                (provider.value,),
            ).fetchall()
        return [row["model"] for row in rows]

    def clear_model_validation(self, provider: ProviderId) -> None:
        with self.database.connection() as connection:
            connection.execute("DELETE FROM model_validation WHERE provider = ?", (provider.value,))

