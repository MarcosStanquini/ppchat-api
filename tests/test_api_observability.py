import asyncio
import time
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.modules.api import app as app_module
from src.modules.observability import recorder
from src.modules.observability.store import MemoryStore, NullStore
from src.modules.response.services.chat_service import ChatSession

CURSO = "analise-e-desenvolvimento-de-sistemas"


@pytest.fixture
def store():
    memory = MemoryStore()
    recorder.set_store(memory)
    yield memory
    recorder.set_store(NullStore())


@pytest.fixture
def client():
    return TestClient(app_module.app)  # sem `with`: não roda o lifespan (que abriria o banco)


@pytest.fixture
def fake_answer(monkeypatch):
    def install(chunks, error=None):
        async def stream_events(self, question, focus=(), perfil=None):
            for chunk in chunks:
                yield "text", chunk
            if error is not None:
                raise error

        monkeypatch.setattr(ChatSession, "stream_events", stream_events)

    return install


def wait_for_record(store, rid, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if rid in store.questions:
            return store.questions[rid]
        time.sleep(0.02)
    raise AssertionError("pergunta não foi gravada")


def ask(client, **body):
    payload = {"question": "Como funciona o TCC?", "curso": CURSO, **body}
    with client.stream("POST", "/chat/stream", json=payload) as response:
        return response.status_code, "".join(response.iter_text())


def test_stream_records_ok_without_suap_data(client, store, fake_answer):
    fake_answer(["Olá", " mundo"])
    rid, conv = uuid4(), uuid4()
    history = [{"role": "user", "text": "HIST-SECRETO"}, {"role": "assistant", "text": "b"}]
    status, _ = ask(client, request_id=str(rid), conversa=str(conv), perfil="DADOS-SUAP", history=history,
                    consentimento_gratis=True,
                    disciplinas=["X1", "X2"])
    assert status == 200
    record = wait_for_record(store, rid)
    # com SUAP a resposta não é guardada (pode repetir notas e matrícula)
    assert (record.status, record.resposta, record.curso, record.conversa) == ("ok", "", CURSO, conv)
    assert record.tinha_suap and record.turno == 1 and record.disciplinas == 2
    assert record.primeiro_texto_ms is not None and record.duracao_ms >= 0
    assert "DADOS-SUAP" not in repr(record) and "HIST-SECRETO" not in repr(record)
    assert "testclient" not in record.visitante and len(record.visitante) == 64


def test_stopped_answer_is_recorded_with_partial_text(client, store, fake_answer):
    fake_answer(["Ol"], error=asyncio.CancelledError())
    rid = uuid4()
    ask(client, request_id=str(rid))
    record = wait_for_record(store, rid)
    assert record.status == "parada" and record.resposta == "Ol"


def test_error_records_class_name_not_message(client, store, fake_answer):
    fake_answer(["meio"], error=RuntimeError("sk-segredo"))
    rid = uuid4()
    ask(client, request_id=str(rid))
    record = wait_for_record(store, rid)
    assert record.status == "erro" and record.erro == "RuntimeError" and record.resposta == "meio"
    assert "sk-segredo" not in repr(record)


def test_error_before_text_has_no_first_text_time(client, store, fake_answer):
    fake_answer([], error=RuntimeError("x"))
    rid = uuid4()
    ask(client, request_id=str(rid))
    assert wait_for_record(store, rid).primeiro_texto_ms is None


def test_db_failure_does_not_break_chat(client, fake_answer):
    class Broken(MemoryStore):
        async def save_question(self, record):
            raise ConnectionError("banco fora")

    recorder.set_store(Broken())
    try:
        fake_answer(["tudo", " certo"])
        status, body = ask(client, request_id=str(uuid4()))
        assert status == 200 and "tudo" in body and '"done"' in body
    finally:
        recorder.set_store(NullStore())


def test_slow_db_does_not_delay_answer(client, fake_answer):
    class Slow(MemoryStore):
        async def save_question(self, record):
            await asyncio.sleep(5)

    recorder.set_store(Slow())
    try:
        fake_answer(["rápido"])
        started = time.monotonic()
        ask(client, request_id=str(uuid4()))
        assert time.monotonic() - started < 2
    finally:
        recorder.set_store(NullStore())


def test_non_uuid_request_id_still_recorded(client, store, fake_answer):
    fake_answer(["ok"])
    ask(client, request_id="nao-e-uuid")
    deadline = time.monotonic() + 2
    while not store.questions and time.monotonic() < deadline:
        time.sleep(0.02)
    assert len(store.questions) == 1 and isinstance(next(iter(store.questions)), UUID)


def test_answer_without_suap_is_stored(client, store, fake_answer):
    fake_answer(["Olá", " mundo"])
    rid = uuid4()
    ask(client, request_id=str(rid))
    assert wait_for_record(store, rid).resposta == "Olá mundo"


def test_plain_chat_endpoint_records(client, store, fake_answer):
    fake_answer(["resposta"])
    response = client.post("/chat", json={"question": "q", "curso": CURSO, "request_id": str(uuid4())})
    assert response.status_code == 200
    deadline = time.monotonic() + 2
    while not store.questions and time.monotonic() < deadline:
        time.sleep(0.02)
    assert next(iter(store.questions.values())).resposta == "resposta"


def test_events(client, store, fake_answer):
    fake_answer(["ok"])
    rid = uuid4()
    ask(client, request_id=str(rid))
    wait_for_record(store, rid)
    assert client.post("/eventos", json={"pergunta_id": str(rid), "tipo": "voto", "valor": "up"}).status_code == 204
    assert store.events == [(rid, "voto", "up")]
    assert client.post("/eventos", json={"pergunta_id": str(uuid4()), "tipo": "voto", "valor": "up"}).status_code == 404
    assert client.post("/eventos", json={"pergunta_id": str(rid), "tipo": "voto", "valor": "x"}).status_code == 400
    assert client.post("/eventos", json={"pergunta_id": "abc", "tipo": "voto", "valor": "up"}).status_code == 422


def test_no_database_means_events_204(client):
    recorder.set_store(NullStore())
    response = client.post("/eventos", json={"pergunta_id": str(uuid4()), "tipo": "copiou"})
    assert response.status_code == 204


def test_answer_with_suap_data_is_not_stored(client, store, fake_answer):
    fake_answer(["Você já concluiu", " Banco de Dados com nota 8,5"])
    rid = uuid4()
    ask(client, request_id=str(rid), perfil="Matrícula 123", consentimento_gratis=True)
    record = wait_for_record(store, rid)
    assert record.tinha_suap and record.resposta == ""


def test_records_model_that_actually_answered(client, store, monkeypatch):
    from src.modules.response.services.providers import ProviderUsage

    async def stream_events(self, question, focus=(), perfil=None):
        yield "text", "ok"
        # Quem respondeu é o provedor que terminou a resposta (pode ser a reserva), pelo rótulo que o aluno vê
        self.provider.label = "Gratuito · OpenRouter"
        self.provider.usage = ProviderUsage(model="modelo-reserva", input_tokens=1, output_tokens=7)

    monkeypatch.setattr(ChatSession, "stream_events", stream_events)
    rid = uuid4()
    ask(client, request_id=str(rid))
    record = wait_for_record(store, rid)
    assert record.modelo == "Gratuito · OpenRouter" and record.tokens_saida == 7


def test_slow_event_save_returns_503(client, fake_answer):
    class SlowEvents(MemoryStore):
        async def save_event(self, pergunta_id, tipo, valor):
            await asyncio.sleep(10)

    recorder.set_store(SlowEvents())
    try:
        started = time.monotonic()
        response = client.post("/eventos", json={"pergunta_id": str(uuid4()), "tipo": "copiou"})
        assert response.status_code == 503 and time.monotonic() - started < 6
    finally:
        recorder.set_store(NullStore())
