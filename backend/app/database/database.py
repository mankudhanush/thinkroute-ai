from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS providers (
                    provider TEXT PRIMARY KEY,
                    api_key TEXT,
                    base_url TEXT,
                    connected INTEGER NOT NULL DEFAULT 0,
                    models_json TEXT NOT NULL DEFAULT '[]',
                    connected_at TEXT
                );

                CREATE TABLE IF NOT EXISTS model_selection (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    selected_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS model_validation (
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    validated INTEGER NOT NULL,
                    latency REAL,
                    last_tested TEXT NOT NULL,
                    failure_reason TEXT,
                    PRIMARY KEY (provider, model)
                );

                CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation
                    ON chat_messages(conversation_id, id);
                """
            )
            self._migrate(connection)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        """Additive, idempotent column migrations for existing databases."""
        existing = {row["name"] for row in connection.execute("PRAGMA table_info(chat_messages)")}
        # Context-Aware Memory Engine: thread grouping + cached keywords.
        # Nullable so pre-existing rows remain valid (legacy = threadless).
        if "thread_id" not in existing:
            connection.execute("ALTER TABLE chat_messages ADD COLUMN thread_id TEXT")
        if "keywords" not in existing:
            connection.execute("ALTER TABLE chat_messages ADD COLUMN keywords TEXT")

    @staticmethod
    def json_dumps(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"))

    @staticmethod
    def json_loads(value: str) -> Any:
        return json.loads(value)

