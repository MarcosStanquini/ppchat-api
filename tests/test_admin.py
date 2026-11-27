from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src.modules.api import admin
from src.modules.api import app as app_module
from src.modules.api.rate_limit import RateLimiter
from src.modules.observability import costs, recorder
from src.modules.observability.store import NullStore
from src.modules.shared.services.settings import get_settings

TOKEN = "senha-de-teste-bem-longa"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class FakeAdminStore(NullStore):
    def __init__(self):
        self.calls = []

    async def summary(self, dias, curso):
        self.calls.append(("summary", dias, curso))
        return {"perguntas": 3, "visitantes": 2, "votadas": 1, "positivas": 1, "paradas": 0, "reformuladas": 0, "erros": 0}

    async def top_questions(self, dias, curso, limit=20):
        return [{"pergunta": "Como funciona o TCC?", "vezes": 2}]

    async def negatives(self, dias, curso, limit=50):
        return []

    async def questions(self, dias, curso, busca, pagina, por_pagina=30):
        self.calls.append(("questions", dias, curso, busca, pagina))
        return {"itens": [], "total": 0}

    balance = None

    async def set_balance(self, valor_usd):
        self.balance = {"valor_usd": valor_usd, "em": datetime.now(UTC) - timedelta(hours=3)}

    async def get_balance(self):
        return self.balance


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_token", TOKEN)
    monkeypatch.setattr(admin, "failed_logins", RateLimiter(*admin.FAILED_LOGIN_LIMITS))
    return TestClient(app_module.app)


@pytest.fixture
def fake_store():
    store = FakeAdminStore()
    recorder.set_store(store)
    yield store
    recorder.set_store(NullStore())


def test_admin_404_without_token_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_token", None)
    client = TestClient(app_module.app)
    assert client.get("/admin").status_code == 404
    assert client.get("/admin/api/resumo", headers=AUTH).status_code == 404


def test_admin_page_is_served_and_noindex(client):
    response = client.get("/admin")
    assert response.status_code == 200 and "noindex" in response.text
    assert response.headers["x-robots-tag"] == "noindex"


def test_admin_api_requires_token(client, fake_store):
    assert client.get("/admin/api/resumo").status_code == 401
    assert client.get("/admin/api/resumo", headers={"Authorization": "Bearer errada"}).status_code == 401
    assert client.get("/admin/api/resumo", headers={"Authorization": TOKEN}).status_code == 401


def test_admin_api_wrong_token_rate_limited(client, fake_store):
    codes = [client.get("/admin/api/resumo", headers={"Authorization": "Bearer x"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[-1] == 429


def test_admin_api_ok_with_token(client, fake_store):
    response = client.get("/admin/api/resumo?dias=30&curso=analise-e-desenvolvimento-de-sistemas", headers=AUTH)
    assert response.status_code == 200 and response.json()["perguntas"] == 3
    assert fake_store.calls[-1] == ("summary", 30, "analise-e-desenvolvimento-de-sistemas")
    assert client.get("/admin/api/mais-feitas", headers=AUTH).json()[0]["vezes"] == 2
    assert client.get("/admin/api/negativas", headers=AUTH).json() == []
    page = client.get("/admin/api/perguntas?pagina=2&busca=tcc", headers=AUTH)
    assert page.json() == {"itens": [], "total": 0} and fake_store.calls[-1] == ("questions", 7, None, "tcc", 2)


def test_admin_api_validates_filters(client, fake_store):
    assert client.get("/admin/api/resumo?dias=8", headers=AUTH).status_code == 422
    assert client.get("/admin/api/resumo?curso=inexistente", headers=AUTH).status_code == 400
    assert client.get("/admin/api/perguntas?pagina=0", headers=AUTH).status_code == 422
    assert client.get("/admin/api/perguntas?busca=" + "x" * 201, headers=AUTH).status_code == 422


def test_admin_api_without_database_is_503(client):
    recorder.set_store(NullStore())
    assert client.get("/admin/api/resumo", headers=AUTH).status_code == 503


def test_courses_list_for_filter(client, fake_store):
    cursos = client.get("/admin/api/cursos", headers=AUTH).json()
    assert any(c["slug"] == "analise-e-desenvolvimento-de-sistemas" for c in cursos)


def test_locked_out_ip_cannot_use_correct_token(client, fake_store):
    for _ in range(10):
        client.get("/admin/api/resumo", headers={"Authorization": "Bearer x"})
    assert client.get("/admin/api/resumo", headers=AUTH).status_code == 429


def test_spoofed_ips_hit_global_limit(client, fake_store):
    codes = [client.get("/admin/api/resumo", headers={"Authorization": "Bearer x", "X-Forwarded-For": f"10.0.0.{i}"}).status_code
             for i in range(51)]
    assert codes[-1] == 429


def test_store_missing_admin_queries_is_503(client):
    class Partial(NullStore):
        async def summary(self, dias, curso):
            return {}

    recorder.set_store(Partial())
    try:
        assert client.get("/admin/api/perguntas", headers=AUTH).status_code == 503
    finally:
        recorder.set_store(NullStore())


class FakeCosts:
    def __init__(self, error=None):
        self.error, self.since = error, []

    async def report(self, dias):
        if self.error:
            raise self.error
        return {"total_usd": 12.5, "por_dia": [], "por_modelo": [], "dados_ate": "2026-11-27T06:00:00+00:00"}

    async def spent_since(self, when):
        self.since.append(when)
        return Decimal("2.25"), None


@pytest.fixture
def fake_costs(monkeypatch):
    service = FakeCosts()
    monkeypatch.setattr(get_settings(), "anthropic_admin_key", "sk-ant-admin-teste")
    costs.set_service(service)
    yield service
    costs.set_service(None)


def test_costs_not_configured_without_admin_key(client, fake_store, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_admin_key", None)
    assert client.get("/admin/api/custos", headers=AUTH).json() == {"configurado": False}


def test_costs_require_password(client, fake_store, fake_costs):
    assert client.get("/admin/api/custos").status_code == 401
    assert client.post("/admin/api/saldo", json={"valor_usd": 10}).status_code == 401


def test_costs_without_balance_reference(client, fake_store, fake_costs):
    body = client.get("/admin/api/custos?dias=30", headers=AUTH).json()
    assert body["configurado"] and body["total_usd"] == 12.5 and body["saldo"] is None


def test_costs_with_balance_reference(client, fake_store, fake_costs):
    assert client.post("/admin/api/saldo", json={"valor_usd": "40.00"}, headers=AUTH).status_code == 204
    saldo = client.get("/admin/api/custos", headers=AUTH).json()["saldo"]
    assert saldo["informado_usd"] == 40.0 and saldo["gasto_desde_usd"] == 2.25 and saldo["estimado_usd"] == 37.75
    assert fake_costs.since == [fake_store.balance["em"]]


def test_costs_error_is_502_and_hides_details(client, fake_store, fake_costs):
    fake_costs.error = RuntimeError("sk-ant-admin-segredo")
    response = client.get("/admin/api/custos", headers=AUTH)
    assert response.status_code == 502 and "sk-ant" not in response.text


def test_balance_value_is_validated(client, fake_store, fake_costs):
    for bad in (-1, 100_001, "abc"):
        assert client.post("/admin/api/saldo", json={"valor_usd": bad}, headers=AUTH).status_code == 422
