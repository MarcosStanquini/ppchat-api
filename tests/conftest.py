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


MARKER_TABLE = "ppchat_test_marker"


async def require_test_database(store) -> None:
    """Os testes apagam as tabelas: só rodam num banco marcado como de teste (nunca no de produção)."""
    if not await store.fetch_value("select to_regclass(%s) is not null", (MARKER_TABLE,)):
        await store.close()
        pytest.exit(f"TEST_DATABASE_URL sem a tabela {MARKER_TABLE}: não parece um banco de testes. "
                    f"Crie com `create table {MARKER_TABLE} ()` só no banco de testes.", returncode=2)


@pytest.fixture
async def pg():
    if not TEST_DATABASE_URL:
        pytest.skip("sem TEST_DATABASE_URL")
    from src.modules.observability.postgres_store import PostgresStore

    store = await PostgresStore.open(TEST_DATABASE_URL)
    await require_test_database(store)
    await store.execute("truncate perguntas, saldo_referencia cascade")
    yield store
    await store.close()


# ── Multi-IA: provedor falso, base de conhecimento real e transporte HTTP falso para o SDK da OpenAI ──
class FakeProvider:
    """Provedor de IA falso: devolve `chunks` e grava o que recebeu."""

    def __init__(self, chunks=(), error=None, error_after_first=None, label="Falso"):
        self.chunks, self.error, self.error_after_first, self.label = list(chunks), error, error_after_first, label
        self.calls, self.usage, self.last_system, self.last_context, self.last_messages = 0, None, None, None, None

    async def stream(self, system, context, messages):
        from src.modules.response.services.providers import ProviderUsage

        self.calls += 1
        self.last_system, self.last_context, self.last_messages = system, context, [dict(m) for m in messages]
        if self.error is not None:
            raise self.error
        for i, chunk in enumerate(self.chunks):
            yield "text", chunk
            if i == 0 and self.error_after_first is not None:
                raise self.error_after_first
        self.usage = ProviderUsage(model="falso", input_tokens=1, output_tokens=len(self.chunks))


@pytest.fixture
def fake_provider():
    return FakeProvider


@pytest.fixture(scope="session")
def kb():
    from src.modules.knowledge.services.knowledge_base import get_knowledge_base
    from src.modules.shared.services.courses import LEGACY_COURSE

    return get_knowledge_base(LEGACY_COURSE)


class OpenAIMock:
    """Responde como a API de chat da OpenAI (SSE) e guarda o último corpo enviado."""

    def __init__(self):
        import httpx2

        self.last_request_json, self.status, self.body = None, 200, None
        self.client = httpx2.AsyncClient(transport=httpx2.MockTransport(self._handle))

    def _handle(self, request):
        import json

        import httpx2

        self.last_request_json = json.loads(request.content)
        if self.status != 200:
            return httpx2.Response(self.status, json=self.body or {"error": {"message": "erro"}})
        chunks = [
            {"id": "1", "object": "chat.completion.chunk", "created": 0, "model": "m",
             "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
            for text in ("Olá", " mundo")
        ]
        chunks.append({"id": "1", "object": "chat.completion.chunk", "created": 0, "model": "m", "choices": [],
                       "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})
        sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx2.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"})


@pytest.fixture
def httpx_mock_openai():
    return OpenAIMock()


@pytest.fixture(autouse=True)
def fresh_chat_state(monkeypatch):
    """Cada teste começa com o cache de respostas e os limites de perguntas zerados."""
    from src.modules.api import app as app_module
    from src.modules.response.services import answer_cache as cache_module
    from src.modules.response.services.answer_cache import AnswerCache

    fresh = AnswerCache()
    monkeypatch.setattr(cache_module, "answer_cache", fresh)
    monkeypatch.setattr(app_module, "answer_cache", fresh)
    monkeypatch.setattr(app_module, "limiters", app_module.build_limiters())
