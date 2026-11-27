from collections.abc import AsyncIterator, Sequence
from typing import Literal, TypedDict

from src.modules.knowledge.services.knowledge_base import KnowledgeBase
from src.modules.response.services.prompts import system_instructions
from src.modules.response.services.providers import ChatProvider, StreamEvent
from src.modules.shared.services.courses import get_registry

__all__ = ["ChatSession", "HistoryTurn", "StreamEvent", "strip_perfil"]

PERFIL_START = "Dados acadêmicos do estudante, importados por ele mesmo do SUAP."
PERFIL_END = "</perfil_aluno>"


def strip_perfil(messages: list[dict]) -> list[dict]:
    """Cópia das mensagens sem os dados do SUAP (que só vão na pergunta atual, a última)."""
    if not messages:
        return messages
    last = dict(messages[-1])
    content = last.get("content")
    if isinstance(content, str) and PERFIL_START in content:
        start = content.index(PERFIL_START)
        end = content.index(PERFIL_END, start) + len(PERFIL_END)
        last["content"] = (content[:start] + content[end:]).lstrip()
    return [*messages[:-1], last]


class HistoryTurn(TypedDict, total=False):
    role: Literal["user", "assistant"]
    text: str
    disciplinas: list[str]  # só em turnos do usuário


class ChatSession:
    """Uma conversa multi-turno sobre o PPC, respondida por qualquer provedor de IA.

    O PPC inteiro vai como contexto em toda pergunta (o Claude o guarda em cache de 1 h; os outros
    provedores reaproveitam sozinhos a entrada repetida). O histórico é texto puro, então a conversa pode
    trocar de IA no meio.

    A API é sem estado: cada requisição cria uma sessão com o `history` enviado pelo navegador.
    É assíncrona para que uma resposta possa ser interrompida a qualquer momento cancelando a task que
    consome `stream_events`.
    """

    def __init__(self, knowledge_base: KnowledgeBase, provider: ChatProvider,
                 history: Sequence[HistoryTurn] = ()):
        self.knowledge_base = knowledge_base
        self.provider = provider
        self.messages: list[dict] = [
            {
                "role": turn["role"],
                "content": self._user_content(turn["text"], turn.get("disciplinas") or ())
                if turn["role"] == "user"
                else turn["text"],
            }
            for turn in history
        ]
        self.system = system_instructions(knowledge_base.course.nome, get_registry().campus, knowledge_base.notes)
        self.context = knowledge_base.full_context

    def _user_content(self, question: str, focus: Sequence[str], perfil: str | None = None) -> str:
        # Contexto extra entra na própria mensagem (depois do prefixo em cache), nunca no system
        blocks = []
        if perfil:
            blocks.append(
                f"{PERFIL_START} Use para personalizar "
                "a resposta (o que já cursou, o que está cursando, o que falta):\n"
                f"<perfil_aluno>\n{perfil}\n</perfil_aluno>"
            )
        focus_sheet = self.knowledge_base.render_disciplinas(list(focus)) if focus else ""
        if focus_sheet:
            blocks.append(
                "O estudante selecionou estas disciplinas como foco da pergunta:\n"
                f"<disciplinas_selecionadas>\n{focus_sheet}\n</disciplinas_selecionadas>"
            )
        return "\n\n".join([*blocks, question])

    async def stream_events(
        self, question: str, focus: Sequence[str] = (), perfil: str | None = None
    ) -> AsyncIterator[StreamEvent]:
        """Envia a pergunta e devolve ("thinking", resumo) e ("text", resposta) à medida que chegam.

        `focus` são códigos de disciplinas selecionadas no chat; a ficha delas vai junto da pergunta.
        `perfil` é o resumo acadêmico do aluno importado do SUAP (só na pergunta atual).
        """
        self.messages.append({"role": "user", "content": self._user_content(question, focus, perfil)})
        parts = []
        try:
            async for kind, text in self.provider.stream(self.system, self.context, self.messages):
                if kind == "text":
                    parts.append(text)
                yield kind, text
        except BaseException:
            # Inclui o cancelamento: mantém o histórico válido (sempre user/assistant alternados)
            self.messages.pop()
            raise
        self.messages.append({"role": "assistant", "content": "".join(parts)})

    @property
    def answered_by(self) -> tuple[str, int | None]:
        """(quem de fato respondeu, como o aluno vê; tokens gerados)."""
        usage = self.provider.usage
        return self.provider.label, usage.output_tokens if usage else None

    async def stream(self, question: str, focus: Sequence[str] = (), perfil: str | None = None
                     ) -> AsyncIterator[str]:
        """Só o texto da resposta, em pedaços."""
        async for kind, text in self.stream_events(question, focus, perfil):
            if kind == "text":
                yield text

    async def ask(self, question: str, focus: Sequence[str] = (), perfil: str | None = None) -> str:
        return "".join([chunk async for chunk in self.stream(question, focus, perfil)])
