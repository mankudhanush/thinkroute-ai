from __future__ import annotations

import logging

from app.config import settings
from app.errors import ProviderError
from app.models.schemas import ModelInfo, ProviderId
from app.providers.base_provider import BaseProvider, ChatTurn

logger = logging.getLogger(__name__)

SUPPORTED_MODELS = (
    ("@cf/meta/llama-3.1-8b-instruct", "Llama 3.1 8B Instruct"),
    ("@cf/meta/llama-3.1-70b-instruct", "Llama 3.1 70B Instruct"),
    ("@cf/mistral/mistral-7b-instruct-v0.2", "Mistral 7B Instruct"),
    ("@cf/qwen/qwen1.5-14b-chat-awq", "Qwen 1.5 14B Chat"),
)


class CloudflareProvider(BaseProvider):
    provider_id = ProviderId.CLOUDFLARE
    display_name = "Cloudflare Workers AI"

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.credentials.api_key}", "Content-Type": "application/json"}

    @property
    def account_id(self) -> str:
        if self.credentials.base_url:
            if "/accounts/" in self.credentials.base_url:
                return self.credentials.base_url.rstrip("/").split("/accounts/")[1].split("/")[0]
            return self.credentials.base_url
        if settings.cloudflare_account_id:
            return settings.cloudflare_account_id
        raise ProviderError("A Cloudflare Account ID is required", 400, "missing_account_id")

    @property
    def base_url(self) -> str:
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai"

    async def validate_api_key(self) -> None:
        await self.request("GET", f"{self.base_url}/models/search", headers=self.headers())

    async def list_models(self) -> list[ModelInfo]:
        response = await self.request("GET", f"{self.base_url}/models/search", headers=self.headers())
        result = response.json().get("result", [])

        # BUG 4 FIX: Filter to only text-generation models that support chat.
        models = []
        for item in result:
            name = item.get("name")
            if not name:
                continue
            # Only include models whose task is Text Generation.
            task = item.get("task", {})
            task_name = task.get("name", "") if isinstance(task, dict) else ""
            if task_name and task_name.lower() != "text generation":
                continue
            models.append(
                ModelInfo(
                    id=str(name),
                    name=str(item.get("description") or name),
                    provider=self.provider_id,
                    context_window=item.get("context_length"),
                )
            )

        logger.info("[Cloudflare] Loaded %d text-generation models (from %d total)", len(models), len(result))
        return models or self.static_models()

    @staticmethod
    def static_models() -> list[ModelInfo]:
        return [ModelInfo(id=model_id, name=name, provider=ProviderId.CLOUDFLARE) for model_id, name in SUPPORTED_MODELS]

    async def chat(self, model: str, messages: list[ChatTurn]) -> str:
        logger.info("[Cloudflare] Chat request: model=%s, messages=%d", model, len(messages))
        from app.errors import provider_error_from_litellm
        import litellm
        
        litellm_model = f"cloudflare/{model}"
        logger.debug(
            "[Cloudflare] LiteLLM Call: provider=cloudflare | model=%s | litellm_string=%s | api_base=%s",
            model, litellm_model, self.base_url
        )
        try:
            # LiteLLM needs api_base configured with /run/ directly
            response = await litellm.acompletion(
                model=litellm_model,
                messages=[{"role": item.role, "content": item.content} for item in messages],
                api_key=self.credentials.api_key,
                api_base=f"{self.base_url}/run/",
            )
            return str(response.choices[0].message.content)
        except Exception as exc:
            raise provider_error_from_litellm(exc, self.display_name, model)
