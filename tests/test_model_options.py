import pytest

from src.modules.response.services.model_options import OPTIONS, provider_chain, public_options
from src.modules.shared.services.settings import get_settings


@pytest.fixture
def settings_with_keys(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "gemini-dono")
    monkeypatch.setattr(s, "openrouter_api_key", "or-dono")


@pytest.fixture
def settings_gemini_only(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "gemini_api_key", "gemini-dono")
    monkeypatch.setattr(s, "openrouter_api_key", None)


def test_gratis_chain_order(settings_with_keys):
    chain = provider_chain("gratis", None)
    assert [p.label for p in chain] == ["Gratuito · Gemini", "Gratuito · Gemini", "Gratuito · OpenRouter"]
    assert [p.model for p in chain[:2]] == get_settings().gemini_models


def test_gratis_skips_unconfigured_openrouter(settings_gemini_only):
    assert all("OpenRouter" not in p.label for p in provider_chain("gratis", None))


def test_gratis_ignores_student_key(settings_with_keys):
    assert all(p._client.api_key != "chave-do-aluno" for p in provider_chain("gratis", "chave-do-aluno"))


def test_byok_uses_student_key_and_has_no_claude():
    assert "anthropic" not in OPTIONS and "claude" not in OPTIONS
    chain = provider_chain("groq", "gsk_x")
    assert len(chain) == 1 and chain[0].label == "Minha chave · Groq" and chain[0]._client.api_key == "gsk_x"
    assert provider_chain("openai", "sk-x")[0].label == "Minha chave · GPT"
    assert provider_chain("gemini", "g-x")[0].label == "Minha chave · Gemini"


def test_claude_teste_is_a_single_claude_provider():
    chain = provider_chain("claude-teste", None)
    assert [p.label for p in chain] == ["Claude (teste)"]


def test_limits_match_spec():
    assert (OPTIONS["gratis"].per_ip, OPTIONS["gratis"].global_limit) == (30, 400)
    assert (OPTIONS["claude-teste"].per_ip, OPTIONS["claude-teste"].global_limit) == (10, 100)
    for own in ("openai", "gemini", "groq"):
        assert (OPTIONS[own].per_ip, OPTIONS[own].global_limit, OPTIONS[own].own_key) == (60, None, True)


def test_public_options_have_no_secrets():
    opts = public_options()
    assert [o["id"] for o in opts] == ["gratis", "claude-teste", "openai", "gemini", "groq"]
    assert all(set(o) == {"id", "label", "own_key"} for o in opts)
