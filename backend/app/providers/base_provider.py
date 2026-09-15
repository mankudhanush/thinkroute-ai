from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings
from app.errors import ProviderError, provider_error_from_status
from app.models.schemas import ModelInfo, ProviderId

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderCredentials:
    api_key: str | None
    base_url: str | None = None


@dataclass(frozen=True)
class ChatTurn:
    role: str
    content: str


class BaseProvider(ABC):
    provider_id: ProviderId
    display_name: str
    requires_key: bool = True

    def __init__(self, credentials: ProviderCredentials) -> None:
        self.credentials = credentials

    @property
    def timeout(self) -> float:
        return settings.provider_timeout_seconds

    async def connect(self) -> None:
        await self.validate_api_key()

    @abstractmethod
    async def validate_api_key(self) -> None:
        """Validate credentials or provider availability."""

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Return models available to this credential/provider."""

    @abstractmethod
    async def chat(self, model: str, messages: list[ChatTurn]) -> str:
        """Send a chat request using exactly the selected model."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        _model: str | None = None,
    ) -> httpx.Response:
        logger.debug(
            "[%s] %s %s | model=%s",
            self.display_name, method, url, _model or "n/a",
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, headers=headers, json=json)
        except httpx.TimeoutException as exc:
            logger.error("[%s] Timeout: %s %s", self.display_name, method, url)
            raise ProviderError(f"{self.display_name} timed out", 504, "provider_timeout") from exc
        except httpx.RequestError as exc:
            logger.error("[%s] Connection error: %s %s – %s", self.display_name, method, url, exc)
            raise ProviderError(f"{self.display_name} is offline", 503, "provider_offline") from exc

        if response.is_error:
            body = response.text[:1000]
            logger.error(
                "[%s] HTTP %d from %s %s | body=%.500s",
                self.display_name, response.status_code, method, url, body,
            )
            raise provider_error_from_status(
                response.status_code,
                self.display_name,
                model=_model,
                url=url,
                response_body=body,
            )

        logger.debug("[%s] HTTP %d OK from %s %s", self.display_name, response.status_code, method, url)
        return response

    @staticmethod
    def parse_openai_models(provider: ProviderId, payload: dict[str, Any]) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        for item in payload.get("data", []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            models.append(
                ModelInfo(
                    id=str(item["id"]),
                    name=str(item.get("name") or item["id"]),
                    provider=provider,
                    context_window=item.get("context_length") or item.get("max_model_len"),
                    owned_by=item.get("owned_by"),
                )
            )
        return models
