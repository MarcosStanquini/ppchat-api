from functools import lru_cache

from anthropic import Anthropic, AsyncAnthropic, BetaRefusalFallbackMiddleware

from src.modules.shared.services.settings import get_settings


def _fallback_middleware() -> list:
    s = get_settings()
    models = s.fallback_models or [s.fallback_model]
    return [BetaRefusalFallbackMiddleware([{"model": m} for m in models])]


@lru_cache
def get_llm_client() -> Anthropic:
    """Cliente sincrono, usado na ingestao."""
    s = get_settings()
    return Anthropic(api_key=s.openrouter_api_key or s.anthropic_api_key, base_url=s.anthropic_base_url, middleware=_fallback_middleware())


@lru_cache
def get_async_llm_client() -> AsyncAnthropic:
    """Cliente assincrono, usado no chat."""
    s = get_settings()
    return AsyncAnthropic(api_key=s.openrouter_api_key or s.anthropic_api_key, base_url=s.anthropic_base_url, middleware=_fallback_middleware())
