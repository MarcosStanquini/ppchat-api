"""Tenta os provedores de uma opção em ordem e transforma as falhas em mensagens para o aluno.

A troca de provedor só acontece antes do primeiro texto: depois disso, recomeçar em outro provedor
duplicaria a resposta na tela. As mensagens são fixas por tipo de falha e nunca levam o texto do
provedor, que pode conter a chave do aluno.
"""
import logging
from collections.abc import AsyncIterator
from typing import Literal

from src.modules.response.services.chat_service import strip_perfil
from src.modules.response.services.providers import (
    ChatProvider,
    ProviderError,
    ProviderUsage,
    StreamEvent,
)

logger = logging.getLogger(__name__)

USER_MESSAGES = {
    "quota_gratis": "O modelo gratuito atingiu o limite de uso agora. Tente mais tarde ou use sua própria chave.",
    "auth": "Sua chave do {provedor} foi recusada. Confira a chave e tente de novo.",
    "quota_own": "Sua chave do {provedor} está sem crédito ou atingiu o limite.",
    "unavailable": "A IA não respondeu agora. Tente de novo em instantes.",
    "not_configured": "O modelo gratuito ainda não foi configurado neste servidor. Use sua própria chave.",
}
Mode = Literal["gratis", "own"]  # chaves do dono (Claude e grátis) ou chave do aluno
_FALL_BACK_ON = {"quota", "unavailable"}


class UserFacingError(Exception):
    """Falha já explicada para o aluno; `message` pode ir direto para a tela."""

    def __init__(self, message: str, kind: str = "unavailable"):
        super().__init__(message)
        self.message = message
        self.kind = kind


def _own_key_message(kind: str, provider: ChatProvider | None) -> str:
    name = provider.label.split(" · ")[-1] if provider else ""
    if kind == "quota":
        return USER_MESSAGES["quota_own"].format(provedor=name)
    if kind == "auth":
        return USER_MESSAGES["auth"].format(provedor=name)
    return USER_MESSAGES["unavailable"]


def _infer_mode(chain: list[ChatProvider]) -> Mode:
    return "own" if any(p.label.startswith("Minha chave") for p in chain) else "gratis"


class FallbackProvider:
    """Uma opção de IA vista como um provedor só: `label` e `usage` são de quem de fato respondeu."""

    def __init__(self, chain: list[ChatProvider], mode: Mode | None = None, consent: bool = True):
        self.chain = chain
        self.answered_by: ChatProvider | None = None
        self.label = chain[0].label if chain else "Gratuito"
        self.usage: ProviderUsage | None = None
        # Só a chave do aluno pode ouvir "sua chave foi recusada"; falhas das chaves do dono têm mensagens próprias
        self.mode: Mode = mode or _infer_mode(chain)
        self.free = self.mode == "gratis"
        # Sem aceite, os dados do SUAP só vão aos provedores que podem recebê-los (Claude do dono, chave do aluno)
        self.consent = consent

    @property
    def complete(self) -> bool:
        """A resposta terminou normalmente (sem corte por limite ou filtro)? Só assim vale guardar."""
        return bool(self.answered_by and getattr(self.answered_by, "complete", False) and self.usage)

    async def stream(self, system: str, context: str, messages: list[dict]) -> AsyncIterator[StreamEvent]:
        kind, provider, started, quota_seen = "unavailable", None, False, False
        for provider in self.chain:
            self.label, self.answered_by, self.usage = provider.label, provider, None
            failed = False
            try:
                sent = messages if self.consent or getattr(provider, "private_ok", False) else strip_perfil(messages)
                async for event in provider.stream(system, context, sent):
                    started = True
                    yield event
            except ProviderError as error:
                failed, kind = True, error.kind
                started = started or not error.before_first_token
            except Exception:  # noqa: BLE001 — falha inesperada: mensagem genérica, sem o texto
                failed, kind = True, "unavailable"
            if not failed:
                self.usage = provider.usage
                return
            # O log leva só o rótulo e o tipo: nada da pergunta, da resposta ou da chave
            logger.warning("provedor %s falhou: %s%s", provider.label, kind, " (no meio da resposta)" if started else "")
            quota_seen = quota_seen or kind == "quota"
            # Depois do primeiro texto não troca (duplicaria a resposta). No gratuito, qualquer falha antes do
            # texto passa para o próximo (até a chave do dono recusada); na chave do aluno só há um provedor
            if started or not (self.free or kind in _FALL_BACK_ON):
                break
        if started:
            message = USER_MESSAGES["unavailable"]
        elif self.mode == "gratis":
            if not self.chain:
                message = USER_MESSAGES["not_configured"]
            else:
                message = USER_MESSAGES["quota_gratis"] if quota_seen else USER_MESSAGES["unavailable"]
        else:
            message = _own_key_message(kind, provider)
        # Fora de qualquer `except`: a exceção nova não carrega a original (que pode ter a chave)
        raise UserFacingError(message, kind)


def stream_with_fallback(chain: list[ChatProvider], system: str, context: str,
                         messages: list[dict]) -> AsyncIterator[StreamEvent]:
    return FallbackProvider(chain).stream(system, context, messages)
