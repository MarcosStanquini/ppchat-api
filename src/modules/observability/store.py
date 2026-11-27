"""Onde as perguntas são guardadas: Postgres em produção, memória nos testes, nada sem banco."""
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from src.modules.observability.records import EventType, QuestionRecord


class Store(Protocol):
    async def save_question(self, record: QuestionRecord) -> None: ...

    async def save_event(self, pergunta_id: UUID, tipo: EventType, valor: str) -> bool:
        """Grava um sinal (voto, cópia, página aberta); False se a pergunta não existe."""
        ...

    async def purge(self, days: int = 180) -> None: ...

    async def close(self) -> None: ...


@runtime_checkable
class AdminQueries(Protocol):
    """Consultas da página /admin (só o Postgres tem)."""

    async def summary(self, dias: int, curso: str | None) -> dict: ...

    async def top_questions(self, dias: int, curso: str | None, limit: int = 20) -> list: ...

    async def negatives(self, dias: int, curso: str | None, limit: int = 50) -> list: ...

    async def questions(self, dias: int, curso: str | None, busca: str | None, pagina: int,
                        por_pagina: int = 30) -> dict: ...

    async def set_balance(self, valor_usd: Decimal) -> None: ...

    async def get_balance(self) -> dict | None:
        """{"valor_usd": Decimal, "em": datetime} ou None se o dono nunca informou."""
        ...


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
