"""Provedores de IA do chat: o Claude (SDK da Anthropic) e um adaptador único para APIs compatíveis com a
OpenAI (OpenAI, Gemini, Groq, OpenRouter).

Todos recebem o mesmo pedido — instruções (`system`), o PPC inteiro (`context`) e as mensagens em texto
puro — e devolvem eventos ("thinking", texto) e ("text", texto). Assim a conversa pode trocar de IA no meio.
"""
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

StreamEvent = tuple[Literal["thinking", "text"], str]
ErrorKind = Literal["quota", "auth", "unavailable", "refused", "other"]


@dataclass
class ProviderUsage:
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None


class ProviderError(Exception):
    """Falha do provedor já classificada. Nunca carrega o texto do provedor (pode conter a chave)."""

    def __init__(self, kind: ErrorKind, before_first_token: bool = True):
        super().__init__(kind)
        self.kind = kind
        self.before_first_token = before_first_token


def classify(error: Exception) -> ErrorKind:
    """Tipo da falha a partir da exceção dos SDKs (Anthropic e OpenAI têm a mesma família de erros)."""
    name = type(error).__name__
    status = getattr(error, "status_code", None)
    if name in ("AuthenticationError", "PermissionDeniedError") or status in (401, 403):
        return "auth"
    if name == "RateLimitError" or status in (402, 429):
        return "quota"
    if name in ("APITimeoutError", "APIConnectionError", "TimeoutError") or (status or 0) >= 500:
        return "unavailable"
    return "other"


async def _guarded(events: AsyncIterator[StreamEvent]) -> AsyncIterator[StreamEvent]:
    """Converte qualquer falha do provedor em ProviderError, dizendo se já tinha saído texto.

    A exceção original não é encadeada: a mensagem dela pode trazer a chave ou o corpo da resposta.
    """
    started = False
    failure: ErrorKind | None = None
    try:
        async for event in events:
            started = True
            yield event
    except ProviderError:
        raise
    except Exception as error:  # noqa: BLE001 — classificado abaixo, sem guardar o texto
        failure = classify(error)
    if failure is not None:
        raise ProviderError(failure, before_first_token=not started)


class ChatProvider(Protocol):
    label: str  # quem respondeu, como o aluno vê: "Gratuito · Claude", "Gratuito · Gemini", "Minha chave · GPT"...
    usage: ProviderUsage | None  # preenchido ao fim da resposta
    complete: bool  # terminou normalmente (não cortada por limite de tokens ou filtro)
    # Pode receber os dados do SUAP sem aceite? Sim para o Claude do dono e para a chave do próprio aluno;
    # não para os serviços gratuitos de terceiros (Gemini, OpenRouter), que podem usar os dados
    private_ok: bool

    def stream(self, system: str, context: str, messages: list[dict]) -> AsyncIterator[StreamEvent]: ...


class AnthropicProvider:
    """O Claude, como antes: PPC em cache de 1 h, raciocínio resumido e reserva em caso de recusa."""

    private_ok = True

    def __init__(self, client, model: str, effort: str, label: str, max_tokens: int = 64000):
        self.client, self.model, self.effort, self.label, self.max_tokens = client, model, effort, label, max_tokens
        self.usage: ProviderUsage | None = None
        self.complete = False

    def stream(self, system: str, context: str, messages: list[dict]) -> AsyncIterator[StreamEvent]:
        return _guarded(self._stream(system, context, messages))

    async def _stream(self, system: str, context: str, messages: list[dict]) -> AsyncIterator[StreamEvent]:
        from anthropic import BetaFallbackState

        self.usage, self.complete = None, False
        with BetaFallbackState():  # fixa a resposta no modelo de reserva se o principal recusar
            async with self.client.beta.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                # "summarized" devolve um resumo legível do raciocínio, mostrado enquanto o modelo pensa
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": self.effort},
                # Segundo ponto de cache no fim do histórico; o PPC tem o seu, de 1 h
                cache_control={"type": "ephemeral"},
                system=[
                    {"type": "text", "text": system},
                    {"type": "text", "text": context, "cache_control": {"type": "ephemeral", "ttl": "1h"}},
                ],
                messages=messages,
            ) as stream:
                async for event in stream:
                    if event.type != "content_block_delta":
                        continue
                    if event.delta.type == "thinking_delta":
                        yield "thinking", event.delta.thinking
                    elif event.delta.type == "text_delta":
                        yield "text", event.delta.text
                message = await stream.get_final_message()
        self.usage = ProviderUsage(
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            cache_read_input_tokens=message.usage.cache_read_input_tokens or 0,
            cache_creation_input_tokens=message.usage.cache_creation_input_tokens or 0,
        )
        self.complete = message.stop_reason == "end_turn"
        if message.stop_reason == "refusal":
            yield "text", "\n\n[O modelo não pôde responder a esta pergunta.]"
        elif message.stop_reason == "max_tokens":
            yield "text", "\n\n[Resposta interrompida pelo limite de tokens.]"


class OpenAICompatibleProvider:
    """OpenAI, Gemini, Groq e OpenRouter pelo mesmo formato de API; muda só a URL, a chave e o modelo.

    Instruções e PPC vão numa única mensagem de sistema (esses provedores reaproveitam sozinhos a entrada
    repetida). Não há resumo de raciocínio: só eventos de texto.
    """

    def __init__(self, base_url: str, api_key: str, model: str, label: str, timeout: float = 60,
                 http_client=None, private_ok: bool = False):
        from openai import AsyncOpenAI

        # Sem novas tentativas: a reserva entre provedores é decidida pela cadeia, não pelo SDK
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0,
                                   http_client=http_client)
        self.model, self.label, self.private_ok = model, label, private_ok
        self.usage: ProviderUsage | None = None
        self.complete = False

    def stream(self, system: str, context: str, messages: list[dict]) -> AsyncIterator[StreamEvent]:
        return _guarded(self._stream(system, context, messages))

    async def _stream(self, system: str, context: str, messages: list[dict]) -> AsyncIterator[StreamEvent]:
        self.usage, self.complete = None, False
        finish = None
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": f"{system}\n\n{context}"}, *messages],
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in response:
            if chunk.usage:
                self.usage = ProviderUsage(model=chunk.model or self.model, input_tokens=chunk.usage.prompt_tokens,
                                           output_tokens=chunk.usage.completion_tokens)
            for choice in chunk.choices:
                finish = choice.finish_reason or finish
                if choice.delta and choice.delta.content:
                    yield "text", choice.delta.content
        self.complete = finish == "stop"


def claude_provider(label: str = "Gratuito · Claude", model: str | None = None,
                    api_key: str | None = None) -> AnthropicProvider:
    """O Claude: com a chave do dono (padrão) ou com a chave do aluno, usada só nesta pergunta."""
    from src.modules.shared.services.llm_client import get_async_llm_client
    from src.modules.shared.services.settings import get_settings

    current = get_settings()
    if api_key:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key, max_retries=0)
    else:
        client = get_async_llm_client()
    return AnthropicProvider(client, model or current.llm_model, current.chat_effort, label,
                             current.max_output_tokens)
