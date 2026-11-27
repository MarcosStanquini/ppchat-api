import json
import logging

import pytest
from fastapi.testclient import TestClient

from src.modules.api import app as app_module

CURSO = "analise-e-desenvolvimento-de-sistemas"


@pytest.fixture
def client():
    return TestClient(app_module.app)  # cache e limites zerados pelo fixture automático do conftest


class FakeChain:
    def __init__(self, fake_provider):
        self.fake_provider, self.calls, self.options, self.keys, self.providers = fake_provider, 0, [], [], []

    def __call__(self, option_id, api_key):
        self.calls += 1
        self.options.append(option_id)
        self.keys.append(api_key)
        label = {"gratis": "Gratuito · Gemini", "claude-teste": "Claude (teste)"}.get(option_id, "Minha chave · GPT")
        provider = self.fake_provider(["resposta"], label=label)
        self.providers.append(provider)
        return [provider]

    @property
    def last_user_content(self):
        return self.providers[-1].last_messages[-1]["content"]


@pytest.fixture
def fake_chain(monkeypatch, fake_provider):
    chain = FakeChain(fake_provider)
    monkeypatch.setattr(app_module, "provider_chain", chain)
    return chain


def stream(client, **body):
    body.setdefault("question", "q")
    response = client.post("/chat/stream", json={"curso": CURSO, **body})
    return response, [json.loads(line) for line in response.text.splitlines() if line]


def test_models_lists_options(client):
    ids = [o["id"] for o in client.get("/models").json()["opcoes"]]
    assert ids == ["gratis", "claude-teste", "openai", "gemini", "groq"]


def test_old_client_without_modelo_uses_gratis(client, fake_chain):
    _, events = stream(client)
    done = events[-1]
    assert done["type"] == "done" and done["modelo"] == "gratis" and done["provedor"] == "Gratuito · Gemini"
    assert done["cache"] is False and fake_chain.options == ["gratis"]


def test_unknown_modelo_is_400(client, fake_chain):
    assert client.post("/chat", json={"question": "q", "modelo": "x"}).status_code == 400
    assert client.post("/chat/stream", json={"question": "q", "modelo": "x"}).status_code == 400
    assert fake_chain.calls == 0


def test_byok_without_key_is_400(client, fake_chain):
    assert client.post("/chat", json={"question": "q", "modelo": "groq"}).status_code == 400
    assert fake_chain.calls == 0


def test_student_key_reaches_provider_only_for_own_key_options(client, fake_chain):
    stream(client, modelo="openai", chave="sk-aluno")
    stream(client, question="outra", chave="sk-aluno")  # gratis ignora a chave
    assert fake_chain.keys == ["sk-aluno", None]


def test_perfil_dropped_for_gratis_without_consent(client, fake_chain):
    stream(client, perfil="MEUS DADOS")
    assert "MEUS DADOS" not in fake_chain.last_user_content
    stream(client, question="q2", perfil="MEUS DADOS", consentimento_gratis=True)
    assert "MEUS DADOS" in fake_chain.last_user_content
    stream(client, question="q3", perfil="MEUS DADOS", modelo="claude-teste")
    assert "MEUS DADOS" in fake_chain.last_user_content


def test_cache_hit_skips_provider_and_rate_limit(client, fake_chain, monkeypatch):
    for _ in range(2):
        response = client.post("/chat", json={"question": "Como funciona o TCC?", "curso": CURSO})
        assert response.status_code == 200 and response.json()["answer"] == "resposta"
    assert fake_chain.calls == 1
    _, events = stream(client, question="como funciona o tcc")
    assert events[-1]["cache"] is True and "".join(e["text"] for e in events if e["type"] == "text") == "resposta"
    assert fake_chain.calls == 1
    assert len(app_module.limiters["gratis"].global_hits) == 1


def test_claude_teste_has_own_limit(client, fake_chain):
    codes = [stream(client, question=f"q{i}", modelo="claude-teste")[0].status_code for i in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429
    assert stream(client, question="livre", modelo="gratis")[0].status_code == 200


def test_user_facing_error_goes_to_stream(client, monkeypatch, fake_provider):
    from src.modules.response.services.providers import ProviderError

    monkeypatch.setattr(app_module, "provider_chain",
                        lambda option, key: [fake_provider(error=ProviderError("quota"), label="Gratuito · Gemini")])
    _, events = stream(client)
    assert events[-1] == {"type": "error", "message":
                          "O modelo gratuito atingiu o limite de uso agora. Tente mais tarde ou use sua própria chave."}


def test_unexpected_error_text_is_not_shown(client, monkeypatch):
    from src.modules.response.services.chat_service import ChatSession

    async def boom(self, question, focus=(), perfil=None):
        raise RuntimeError("detalhe interno sk-SEGREDO")
        yield

    monkeypatch.setattr(ChatSession, "stream_events", boom)
    _, events = stream(client)
    assert events[-1]["type"] == "error" and "SEGREDO" not in events[-1]["message"]


def test_key_not_in_logs(client, fake_chain, caplog):
    caplog.set_level(logging.DEBUG)
    stream(client, modelo="openai", chave="sk-SEGREDO")
    client.post("/chat", json={"question": "q", "modelo": "openai", "chave": "sk-SEGREDO"})
    assert "SEGREDO" not in caplog.text


def test_cache_hit_is_recorded_as_saved_answer(client, fake_chain):
    import time
    from uuid import uuid4

    from src.modules.observability import recorder
    from src.modules.observability.store import MemoryStore, NullStore

    store = MemoryStore()
    recorder.set_store(store)
    try:
        stream(client, question="Tem estágio?")
        rid = uuid4()
        stream(client, question="tem estagio", request_id=str(rid))
        for _ in range(50):
            if rid in store.questions:
                break
            time.sleep(0.02)
        assert store.questions[rid].modelo == "Gratuito · Gemini · guardada"
        assert store.questions[rid].resposta == "resposta"
    finally:
        recorder.set_store(NullStore())
