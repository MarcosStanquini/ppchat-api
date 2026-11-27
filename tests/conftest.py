from uuid import uuid4

import pytest

from src.modules.observability.records import QuestionRecord


def build_record(**overrides) -> QuestionRecord:
    fields = {
        "id": uuid4(), "curso": "analise-e-desenvolvimento-de-sistemas", "conversa": uuid4(), "turno": 0,
        "pergunta": "Como funciona o TCC?", "resposta": "Resposta [Página 3]", "modelo": "claude-teste",
        "status": "ok", "erro": None, "duracao_ms": 1200, "primeiro_texto_ms": 300, "tokens_saida": 40,
        "tinha_suap": False, "disciplinas": 0, "visitante": "a" * 64,
    }
    fields.update(overrides)
    return QuestionRecord(**fields)


@pytest.fixture
def record() -> QuestionRecord:
    return build_record()


@pytest.fixture
def make_record():
    return build_record


def _env_value(name: str):
    """Lê do ambiente ou do .env local (os testes de Postgres usam o branch dev do Neon)."""
    import os
    from pathlib import Path

    if os.environ.get(name):
        return os.environ[name]
    env = Path(__file__).resolve().parents[1] / ".env"
    if env.exists():
        for line in env.read_text("utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip().strip('"').strip("'") or None
    return None


TEST_DATABASE_URL = _env_value("TEST_DATABASE_URL")


@pytest.fixture
async def pg():
    if not TEST_DATABASE_URL:
        pytest.skip("sem TEST_DATABASE_URL")
    from src.modules.observability.postgres_store import PostgresStore

    store = await PostgresStore.open(TEST_DATABASE_URL)
    await store.execute("truncate perguntas cascade")
    yield store
    await store.close()
