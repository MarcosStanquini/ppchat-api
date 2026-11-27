from uuid import uuid4

import pytest

from src.modules.observability.records import QuestionRecord


def build_record(**overrides) -> QuestionRecord:
    fields = dict(
        id=uuid4(), curso="analise-e-desenvolvimento-de-sistemas", conversa=uuid4(), turno=0,
        pergunta="Como funciona o TCC?", resposta="Resposta [Página 3]", modelo="claude-teste",
        status="ok", erro=None, duracao_ms=1200, primeiro_texto_ms=300, tokens_saida=40,
        tinha_suap=False, disciplinas=0, visitante="a" * 64,
    )
    fields.update(overrides)
    return QuestionRecord(**fields)


@pytest.fixture
def record() -> QuestionRecord:
    return build_record()


@pytest.fixture
def make_record():
    return build_record
