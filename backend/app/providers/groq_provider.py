from __future__ import annotations

import logging

from app.models.schemas import ModelInfo, ProviderId
from app.providers.base_provider import BaseProvider, ChatTurn

logger = logging.getLogger(__name__)


class GroqProvider(BaseProvider):
    provider_id = ProviderId.GROQ
    display_name = "Groq"

    @property
    def base_url(self) -> str:
        return self.credentials.base_url or "https://api.groq.com/openai/v1"

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.credentials.api_key}", "Content-Type": "application/json"}

    async def validate_api_key(self) -> None:
        await self.request("GET", f"{self.base_url}/models", headers=self.headers())

    async def list_models(self) -> list[ModelInfo]:
        response = await self.request("GET", f"{self.base_url}/models", headers=self.headers())
        models = self.parse_openai_models(self.provider_id, response.json())
        logger.info("[Groq] Loaded %d models", len(models))
        return models

    async def chat(self, model: str, messages: list[ChatTurn]) -> str:
        logger.info("[Groq] Chat request: model=%s, messages=%d", model, len(messages))
        from app.errors import provider_error_from_litellm
        import litellm
        
        litellm_model = f"groq/{model}"
        logger.debug(
            "[Groq] LiteLLM Call: provider=groq | model=%s | litellm_string=%s | api_base=%s",
            model, litellm_model, self.base_url
        )
        try:
            response = await litellm.acompletion(
                model=litellm_model,
                messages=[{"role": item.role, "content": item.content} for item in messages],
                api_key=self.credentials.api_key,
                api_base=self.base_url,
            )
            return str(response.choices[0].message.content)
        except Exception as exc:
            raise provider_error_from_litellm(exc, self.display_name, model)
