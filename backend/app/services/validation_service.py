from __future__ import annotations
import asyncio
import logging
import litellm
import time
from app.models.schemas import ModelInfo, ProviderId
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

class ValidationAgent:
    def __init__(self, storage: StorageService) -> None:
        self.storage = storage

    async def validate_models(
        self, 
        provider: ProviderId, 
        models: list[ModelInfo], 
        api_key: str | None, 
        base_url: str | None
    ) -> list[ModelInfo]:
        """
        Runs the full validation suite concurrently, updates the DB, 
        and returns only the valid models.
        """
        logger.info("[Validation] Starting validation agent for %s with %d models", provider.value, len(models))

        # 1. Filter out known bad models (embeddings, audio, etc) before testing
        filtered_models = self._pre_filter(provider, models)
        
        # 2. Concurrently test the remaining models
        # Local models (Ollama) must be tested sequentially to avoid VRAM thrashing
        max_concurrent = 1 if provider == ProviderId.OLLAMA else 5
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def test_and_save(model: ModelInfo) -> ModelInfo | None:
            async with semaphore:
                valid, latency, error = await self._test_model(provider, model.id, api_key, base_url)
                
                logger.info("Testing model: %s", model.id)
                logger.info("Provider: %s", provider.value)
                logger.info("Latency: %s", f"{latency:.2f}s" if latency is not None else "N/A")
                logger.info("Success: %s", valid)
                if not valid:
                    logger.info("Failure reason: %s", error)
                
                self.storage.save_model_validation(provider, model.id, valid, latency, error)
                return model if valid else None

        results = await asyncio.gather(*(test_and_save(m) for m in filtered_models))
        
        valid_models = [m for m in results if m is not None]
        logger.info("[Validation] %s validation complete. %d/%d passed.", provider.value, len(valid_models), len(models))
        return valid_models

    def _pre_filter(self, provider: ProviderId, models: list[ModelInfo]) -> list[ModelInfo]:
        filtered = []
        for model in models:
            name = model.name.lower()
            model_id = model.id.lower()
            
            if provider == ProviderId.GEMINI:
                if "embedding" in model_id or "vision" in model_id or "aqa" in model_id or "experimental" in model_id or "audio" in model_id:
                    continue
            elif provider == ProviderId.GROQ:
                if "whisper" in model_id or "embedding" in model_id:
                    continue
            elif provider == ProviderId.CLOUDFLARE:
                if "translation" in model_id or "vision" in model_id or "embedding" in model_id:
                    continue
            elif provider == ProviderId.OLLAMA:
                if "embed" in model_id:
                    continue
            
            filtered.append(model)
            
        return filtered

    async def _test_model(self, provider: ProviderId, model_id: str, api_key: str | None, base_url: str | None) -> tuple[bool, float | None, str | None]:
        litellm_model = f"{provider.value}/{model_id}"
        messages = [{"role": "user", "content": 'Say only the word "Working".'}]
        
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        
        if provider == ProviderId.CLOUDFLARE:
            if base_url:
                if "/accounts/" in base_url:
                    kwargs["api_base"] = f"https://api.cloudflare.com/client/v4/accounts/{base_url.rstrip('/').split('/accounts/')[1].split('/')[0]}/ai/run/"
                else:
                    kwargs["api_base"] = f"https://api.cloudflare.com/client/v4/accounts/{base_url}/ai/run/"
        elif provider == ProviderId.OLLAMA:
            kwargs["api_base"] = base_url or "http://localhost:11434"
        elif provider == ProviderId.GROQ and base_url:
            kwargs["api_base"] = base_url
            
        start_time = time.time()
        try:
            async def run_completion():
                return await litellm.acompletion(
                    model=litellm_model,
                    messages=messages,
                    **kwargs
                )
                
            timeout_sec = 45.0 if provider == ProviderId.OLLAMA else 15.0
            response = await asyncio.wait_for(run_completion(), timeout=timeout_sec)
            latency = time.time() - start_time
            
            content = response.choices[0].message.content
            if not content or not content.strip():
                return False, latency, "Empty response"
                
            return True, latency, None
        except asyncio.TimeoutError:
            latency = time.time() - start_time
            return False, latency, "timeout"
        except Exception as exc:
            latency = time.time() - start_time
            error_msg = str(exc)
            
            if "404" in error_msg:
                return False, latency, "404 endpoint not found"
            if "401" in error_msg or "403" in error_msg or "PermissionDenied" in error_msg:
                return False, latency, "permission denied"
            if "500" in error_msg:
                return False, latency, "500 internal server error"
            if "Unsupported" in error_msg or "not a chat model" in error_msg:
                return False, latency, "unsupported model"
            if "deprecated" in error_msg:
                return False, latency, "model deprecated"
            if "unavailable" in error_msg:
                return False, latency, "model unavailable"
                
            return False, latency, f"litellm exception: {error_msg[:100]}"
