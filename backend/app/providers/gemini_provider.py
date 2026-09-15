from __future__ import annotations

import logging

from app.errors import provider_error_from_litellm, ProviderError
from app.models.schemas import ModelInfo, ProviderId
from app.providers.base_provider import BaseProvider, ChatTurn

logger = logging.getLogger(__name__)


class GeminiProvider(BaseProvider):
    provider_id = ProviderId.GEMINI
    display_name = "Google Gemini"

    @property
    def base_url(self) -> str:
        return "https://generativelanguage.googleapis.com/v1beta"

    async def validate_api_key(self) -> None:
        await self.request("GET", f"{self.base_url}/models?key={self.credentials.api_key}")

    async def list_models(self) -> list[ModelInfo]:
        response = await self.request("GET", f"{self.base_url}/models?key={self.credentials.api_key}")
        result = response.json().get("models", [])
        
        models = []
        for item in result:
            name = item.get("name")
            if not name or "models/" not in name:
                continue
            
            # We filter for models that support generateContent
            methods = item.get("supportedGenerationMethods", [])
            if "generateContent" not in methods:
                continue
                
            model_id = name.split("models/")[1]
            models.append(
                ModelInfo(
                    id=model_id,
                    name=item.get("displayName") or model_id,
                    provider=self.provider_id,
                    context_window=item.get("inputTokenLimit"),
                )
            )

        logger.info("[Gemini] Loaded %d text-generation models", len(models))
        return models

    async def chat(self, model: str, messages: list[ChatTurn]) -> str:
        logger.info("[Gemini] Chat request: model=%s, messages=%d", model, len(messages))
        import litellm
        
        litellm_model = f"gemini/{model}"
        # Detailed logging required by user
        logger.debug(
            "[Gemini] LiteLLM Call: provider=gemini | model=%s | litellm_string=%s | api_base=%s",
            model, litellm_model, self.base_url
        )
        try:
            response = await litellm.acompletion(
                model=litellm_model,
                messages=[{"role": item.role, "content": item.content} for item in messages],
                api_key=self.credentials.api_key,
            )
            return str(response.choices[0].message.content)
        except Exception as exc:
            raise provider_error_from_litellm(exc, self.display_name, model)
