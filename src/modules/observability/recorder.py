"""Grava perguntas em segundo plano: banco lento ou fora do ar nunca atrasa nem quebra o chat."""
import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

from src.modules.observability.records import QuestionRecord, Status, visitor_hash
from src.modules.observability.store import NullStore, Store

logger = logging.getLogger("ppchat.observability")
SAVE_TIMEOUT = 3.0
MAX_RESPOSTA = 20_000

_store: Store = NullStore()
_pending: set = set()  # referências às tasks até terminarem (senão o coletor de lixo pode cancelá-las)


def get_store() -> Store:
    return _store


def set_store(store: Store) -> None:
    global _store
    _store = store


async def _save(record: QuestionRecord) -> None:
    try:
        await asyncio.wait_for(_store.save_question(record), SAVE_TIMEOUT)
    except Exception as error:  # noqa: BLE001 - qualquer falha do banco só vira aviso
        logger.warning("não consegui gravar a pergunta %s: %s", record.id, type(error).__name__)


def record_in_background(record: QuestionRecord) -> None:
    task = asyncio.create_task(_save(record))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


def parse_uuid(value: str | None) -> UUID | None:
    try:
        return UUID(value) if value else None
    except ValueError:
        return None


class AnswerTracker:
    """Acompanha uma resposta (texto, tempos, desfecho) e monta o registro no fim."""

    def __init__(self, *, request_id: str | None, curso: str, conversa: UUID | None, turno: int,
                 pergunta: str, modelo: str, tinha_suap: bool, disciplinas: int, ip: str, secret: str):
        self.id = parse_uuid(request_id) or uuid4()
        self.fields = {"curso": curso, "conversa": conversa, "turno": turno, "pergunta": pergunta, "modelo": modelo,
                       "tinha_suap": tinha_suap, "disciplinas": disciplinas}
        self.visitante = visitor_hash(ip, secret, datetime.now(UTC).date())
        self.started = time.monotonic()
        self.first_text_ms: int | None = None
        self._parts: list[str] = []

    def add_text(self, text: str) -> None:
        if self.first_text_ms is None:
            self.first_text_ms = int((time.monotonic() - self.started) * 1000)
        self._parts.append(text)

    @asynccontextmanager
    async def track(self, meta: Callable[[], tuple[str | None, int | None]]) -> AsyncIterator["AnswerTracker"]:
        """Grava a resposta ao sair do bloco: ok, parada (cancelada) ou erro (só o tipo, nunca a mensagem).

        `meta` devolve (modelo que respondeu, tokens gerados), lido só no fim.
        """
        status: Status = "parada"
        erro = None
        try:
            yield self
            status = "ok"
        except asyncio.CancelledError:
            raise
        except Exception as error:
            status, erro = "erro", type(error).__name__
            raise
        finally:
            modelo, tokens = meta()
            self.finish(status, erro, modelo, tokens)

    def finish(self, status: Status, erro: str | None = None, modelo: str | None = None,
               tokens_saida: int | None = None) -> None:
        # Resposta a quem importou o SUAP costuma repetir notas, reprovações, matrícula: não é guardada
        resposta = "" if self.fields["tinha_suap"] else "".join(self._parts)[:MAX_RESPOSTA]
        fields = {**self.fields, "modelo": modelo or self.fields["modelo"]}
        record = QuestionRecord(
            id=self.id, resposta=resposta, status=status, erro=erro,
            duracao_ms=int((time.monotonic() - self.started) * 1000), primeiro_texto_ms=self.first_text_ms,
            tokens_saida=tokens_saida, visitante=self.visitante, **fields,
        )
        record_in_background(record)
