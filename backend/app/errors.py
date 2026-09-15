import logging

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, detail: str, status_code: int = 400, code: str = "bad_request") -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.code = code


class ProviderError(AppError):
    pass


class ProviderNotFoundError(AppError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"Unsupported provider: {provider}", 400, "unsupported_provider")


class MissingApiKeyError(AppError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"An API key is required for {provider}", 401, "missing_api_key")


class ModelNotFoundError(AppError):
    def __init__(self, provider: str, model: str) -> None:
        super().__init__(f"Model '{model}' was not found for {provider}", 404, "model_not_found")


def provider_error_from_status(
    status_code: int,
    provider: str,
    *,
    model: str | None = None,
    url: str | None = None,
    response_body: str | None = None,
) -> ProviderError:
    """Build a structured ProviderError that includes actionable context."""
    context = f" (model={model})" if model else ""

    # Always log the raw details so they appear in server logs.
    logger.error(
        "Provider %s returned HTTP %d%s | url=%s | body=%.500s",
        provider, status_code, context, url or "?", response_body or "<empty>",
    )

    if status_code in (401, 403):
        return ProviderError(f"Invalid API key for {provider}", 401, "invalid_api_key")
    if status_code == 404:
        detail = f"Model '{model}' not found on {provider}" if model else f"Endpoint not found on {provider}"
        return ProviderError(detail, 404, "model_not_found" if model else "not_found")
    if status_code == 429:
        return ProviderError(f"{provider} rate limit exceeded", 429, "rate_limited")
    if status_code >= 500:
        return ProviderError(f"{provider} is unavailable (HTTP {status_code})", 503, "provider_offline")
    return ProviderError(f"{provider} request failed (HTTP {status_code})", 502, "provider_request_failed")


def provider_error_from_litellm(
    exc: Exception,
    provider: str,
    model: str,
) -> ProviderError:
    """Build a structured ProviderError from a LiteLLM exception."""
    logger.error(
        "Provider %s LiteLLM Error (model=%s): %s",
        provider, model, str(exc),
        exc_info=exc,
    )
    import litellm
    if isinstance(exc, litellm.AuthenticationError):
        return ProviderError(f"Invalid API key for {provider}", 401, "invalid_api_key")
    if isinstance(exc, litellm.NotFoundError):
        return ProviderError(f"Model '{model}' not found on {provider}", 404, "model_not_found")
    if isinstance(exc, litellm.RateLimitError):
        return ProviderError(f"{provider} rate limit exceeded", 429, "rate_limited")
    if isinstance(exc, litellm.APIConnectionError) or isinstance(exc, litellm.ServiceUnavailableError) or isinstance(exc, litellm.APIError):
        return ProviderError(f"{provider} is unavailable", 503, "provider_offline")
    if isinstance(exc, litellm.Timeout):
        return ProviderError(f"{provider} request timed out", 504, "provider_timeout")
    return ProviderError(f"{provider} request failed: {str(exc)}", 502, "provider_request_failed")
