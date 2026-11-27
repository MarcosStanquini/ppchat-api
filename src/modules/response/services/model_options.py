"""Opções de IA que o aluno escolhe no chat e a cadeia de provedores de cada uma.

- `gratis` (padrão): chaves do dono no nível grátis — Gemini (um modelo por vez, cada um com cota própria) e,
  por último, o roteador grátis do OpenRouter. Nunca cai no Claude do dono.
- `claude-teste`: o Claude do dono, com limite mais apertado (é a única opção que custa dinheiro ao dono).
- `openai` / `gemini` / `groq`: a chave do próprio aluno, usada só naquela pergunta.
"""
from dataclasses import dataclass

from src.modules.response.services.providers import ChatProvider, OpenAICompatibleProvider, claude_provider
from src.modules.shared.services.settings import get_settings

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OPENROUTER_URL = "https://openrouter.ai/api/v1"
OPENAI_URL = "https://api.openai.com/v1"
GROQ_URL = "https://api.groq.com/openai/v1"


@dataclass(frozen=True)
class ModelOption:
    id: str
    label: str
    own_key: bool
    per_ip: int
    global_limit: int | None  # None = sem teto para o site inteiro


def _options() -> dict[str, ModelOption]:
    current = get_settings()
    return {
        option.id: option
        for option in (
            # O gratuito usa os limites que o site já tinha (configuráveis no Render)
            ModelOption("gratis", "Gratuito", False, current.rate_limit_per_hour, current.global_rate_limit_per_hour),
            ModelOption("claude-teste", "Claude (teste)", False, 10, 100),
            ModelOption("openai", "Minha chave · GPT", True, 60, None),
            ModelOption("gemini", "Minha chave · Gemini", True, 60, None),
            ModelOption("groq", "Minha chave · Groq", True, 60, None),
        )
    }


OPTIONS = _options()

# Chave do aluno: (URL, setting com o modelo, rótulo de quem respondeu)
_OWN_KEY = {
    "openai": (OPENAI_URL, "openai_model", "Minha chave · GPT"),
    "gemini": (GEMINI_URL, "gemini_byok_model", "Minha chave · Gemini"),
    "groq": (GROQ_URL, "groq_model", "Minha chave · Groq"),
}


def provider_chain(option_id: str, api_key: str | None) -> list[ChatProvider]:
    """Provedores a tentar, em ordem. A chave do aluno só vale para as opções `own_key`."""
    current = get_settings()
    if option_id == "gratis":
        chain: list[ChatProvider] = []
        if current.gemini_api_key:
            chain += [OpenAICompatibleProvider(GEMINI_URL, current.gemini_api_key, model, "Gratuito · Gemini")
                      for model in current.gemini_models]
        if current.openrouter_api_key:
            chain.append(OpenAICompatibleProvider(OPENROUTER_URL, current.openrouter_api_key,
                                                  current.openrouter_model, "Gratuito · OpenRouter"))
        return chain
    if option_id == "claude-teste":
        return [claude_provider("Claude (teste)", current.claude_teste_model or current.llm_model)]
    if option_id in _OWN_KEY and api_key:
        url, model_setting, label = _OWN_KEY[option_id]
        return [OpenAICompatibleProvider(url, api_key, getattr(current, model_setting), label)]
    return []


def public_options() -> list[dict]:
    """O que o front precisa para montar o seletor (sem nada de chaves ou modelos)."""
    return [{"id": o.id, "label": o.label, "own_key": o.own_key} for o in OPTIONS.values()]
