from functools import lru_cache

from anthropic import Anthropic, AsyncAnthropic, BetaRefusalFallbackMiddleware

from src.modules.shared.services.settings import get_settings


def _fallback_middleware() -> list:
    # Reenvia ao `fallback_model` qualquer requisição que o modelo principal recuse.
    # Só atua em `client.beta.messages`, por isso o resto do código usa essa superfície.
    return [BetaRefusalFallbackMiddleware([{"model": get_settings().fallback_model}])]


@lru_cache
def get_llm_client() -> Anthropic:
    """Cliente síncrono, usado na ingestão."""
    return Anthropic(api_key=get_settings().anthropic_api_key, middleware=_fallback_middleware())


@lru_cache
def get_async_llm_client() -> AsyncAnthropic:
    """Cliente assíncrono, usado no chat: cancelar a task do asyncio encerra a resposta na hora."""
    return AsyncAnthropic(api_key=get_settings().anthropic_api_key, middleware=_fallback_middleware())
