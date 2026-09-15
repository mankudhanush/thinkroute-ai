from __future__ import annotations
import logging
from app.errors import ProviderError, provider_error_from_litellm
from app.models.schemas import ModelInfo, ProviderId
from app.providers.base_provider import BaseProvider, ChatTurn

logger = logging.getLogger(__name__)

class OllamaProvider(BaseProvider):
    provider_id = ProviderId.OLLAMA
    display_name = "Ollama"

    def headers(self) -> dict[str, str]:
        return {}

    @property
    def base_url(self) -> str:
        url = self.credentials.base_url or "http://localhost:11434"
        return url.rstrip("/")

    async def validate_api_key(self) -> None:
        await self.request("GET", f"{self.base_url}/api/tags")

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await self.request("GET", f"{self.base_url}/api/tags")
            data = response.json()
        except Exception as exc:
            logger.error("[Ollama] Error listing models: %s", exc)
            return []

        models = []
        for item in data.get("models", []):
            name = item.get("name")
            if not name:
                continue
            models.append(
                ModelInfo(
                    id=name,
                    name=name,
                    provider=self.provider_id,
                )
            )
        logger.info("[Ollama] Loaded %d models", len(models))
        return models

    async def chat(self, model: str, messages: list[ChatTurn]) -> str:
        import litellm
        
        litellm_model = f"ollama/{model}"
        logger.debug("[Ollama] LiteLLM Call: provider=ollama | model=%s", model)
        try:
            response = await litellm.acompletion(
                model=litellm_model,
                messages=[{"role": item.role, "content": item.content} for item in messages],
                api_base=self.base_url,
            )
            return str(response.choices[0].message.content)
        except Exception as exc:
            raise provider_error_from_litellm(exc, self.display_name, model)
