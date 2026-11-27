"""Onde as perguntas são guardadas: Postgres em produção, memória nos testes, nada sem banco."""
from typing import Protocol
from uuid import UUID

from src.modules.observability.records import EventType, QuestionRecord


class Store(Protocol):
    async def save_question(self, record: QuestionRecord) -> None: ...

    async def save_event(self, pergunta_id: UUID, tipo: EventType, valor: str) -> bool:
        """Grava um sinal (voto, cópia, página aberta); False se a pergunta não existe."""
        ...

    async def purge(self, days: int = 180) -> None: ...

    async def close(self) -> None: ...


class MemoryStore:
    """Usada nos testes da API."""

    def __init__(self) -> None:
        self.questions: dict[UUID, QuestionRecord] = {}
        self.events: list[tuple[UUID, str, str]] = []

    async def save_question(self, record: QuestionRecord) -> None:
        self.questions.setdefault(record.id, record)  # id repetido não sobrescreve

    async def save_event(self, pergunta_id: UUID, tipo: EventType, valor: str) -> bool:
        if pergunta_id not in self.questions:
            return False
        self.events.append((pergunta_id, tipo, valor))
        return True

    async def purge(self, days: int = 180) -> None:
        pass

    async def close(self) -> None:
        pass


class NullStore:
    """Sem DATABASE_URL (ex.: no PC do dono): nada é gravado e o site funciona igual."""

    async def save_question(self, record: QuestionRecord) -> None:
        pass

    async def save_event(self, pergunta_id: UUID, tipo: EventType, valor: str) -> bool:
        return True

    async def purge(self, days: int = 180) -> None:
        pass

    async def close(self) -> None:
        pass
