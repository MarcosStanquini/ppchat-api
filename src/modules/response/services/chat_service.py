from typing import AsyncIterator, List, Literal, Tuple

from anthropic import BetaFallbackState
from anthropic.types.beta import BetaMessage, BetaMessageParam

from src.modules.knowledge.services.knowledge_base import KnowledgeBase, get_knowledge_base
from src.modules.response.services.prompts import SYSTEM_INSTRUCTIONS
from src.modules.shared.services.llm_client import get_async_llm_client
from src.modules.shared.services.settings import get_settings

StreamEvent = Tuple[Literal["thinking", "text"], str]


class ChatSession:
    """Uma conversa multi-turno sobre o PPC.

    Custo: o PPC inteiro (~140 mil tokens) vai no system prompt com cache de 1 h, então só a
    primeira pergunta paga a leitura completa; as seguintes leem do cache (~10% do preço).
    O `cache_control` de topo move um segundo ponto de cache para o fim do histórico a cada turno.

    É assíncrona para que uma resposta possa ser interrompida a qualquer momento (inclusive
    enquanto o modelo ainda pensa) cancelando a task que consome `stream_events`.
    """

    def __init__(self, knowledge_base: KnowledgeBase | None = None):
        self.settings = get_settings()
        self.client = get_async_llm_client()
        self.knowledge_base = knowledge_base or get_knowledge_base()
        self.messages: List[BetaMessageParam] = []
        self.fallback_state = BetaFallbackState()  # fixa a conversa no modelo de fallback se houver recusa
        self.last_message: BetaMessage | None = None
        self.system = [
            {"type": "text", "text": SYSTEM_INSTRUCTIONS},
            {
                "type": "text",
                "text": self.knowledge_base.full_context,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            },
        ]

    async def stream_events(self, question: str) -> AsyncIterator[StreamEvent]:
        """Envia a pergunta e devolve ("thinking", resumo) e ("text", resposta) à medida que chegam."""
        self.messages.append({"role": "user", "content": question})
        try:
            with self.fallback_state:
                async with self.client.beta.messages.stream(
                    model=self.settings.llm_model,
                    max_tokens=self.settings.max_output_tokens,
                    # "summarized" devolve um resumo legível do raciocínio, mostrado enquanto o modelo pensa
                    thinking={"type": "adaptive", "display": "summarized"},
                    output_config={"effort": self.settings.chat_effort},
                    cache_control={"type": "ephemeral"},
                    system=self.system,
                    messages=self.messages,
                ) as stream:
                    async for event in stream:
                        if event.type != "content_block_delta":
                            continue
                        if event.delta.type == "thinking_delta":
                            yield "thinking", event.delta.thinking
                        elif event.delta.type == "text_delta":
                            yield "text", event.delta.text
                    message = await stream.get_final_message()
        except BaseException:
            # Inclui o cancelamento: mantém o histórico válido (sempre user/assistant alternados)
            self.messages.pop()
            raise

        # Devolve o conteúdo completo (inclui blocos de thinking) para preservar o raciocínio entre turnos
        self.messages.append({"role": "assistant", "content": message.content})
        self.last_message = message
        if message.stop_reason == "refusal":
            yield "text", "\n\n[O modelo não pôde responder a esta pergunta.]"
        elif message.stop_reason == "max_tokens":
            yield "text", "\n\n[Resposta interrompida pelo limite de tokens.]"

    async def stream(self, question: str) -> AsyncIterator[str]:
        """Só o texto da resposta, em pedaços."""
        async for kind, text in self.stream_events(question):
            if kind == "text":
                yield text

    async def ask(self, question: str) -> str:
        return "".join([chunk async for chunk in self.stream(question)])
