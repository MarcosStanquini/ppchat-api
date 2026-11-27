import pytest

from src.modules.response.services.model_options import (
    OPTIONS,
    provider_chain,
    public_options,
)
from src.modules.response.services.providers import AnthropicProvider
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


def test_gratis_starts_with_owner_claude_when_allowed(settings_with_keys):
    chain = provider_chain("gratis", None, claude_allowed=True)
    assert [p.label for p in chain] == ["Gratuito · Claude", "Gratuito · Gemini", "Gratuito · OpenRouter"]
    assert isinstance(chain[0], AnthropicProvider) and chain[0].private_ok
    assert not chain[1].private_ok and not chain[2].private_ok


def test_gratis_without_claude_quota_goes_straight_to_free(settings_with_keys):
    chain = provider_chain("gratis", None, claude_allowed=False)
    assert [p.label for p in chain] == ["Gratuito · Gemini", "Gratuito · OpenRouter"]


def test_gratis_uses_only_flash_lite_by_default(settings_with_keys):
    gemini = [p for p in provider_chain("gratis", None) if "Gemini" in p.label]
    assert [p.model for p in gemini] == ["gemini-3.5-flash-lite"]


def test_gratis_skips_unconfigured_openrouter(settings_gemini_only):
    assert all("OpenRouter" not in p.label for p in provider_chain("gratis", None, claude_allowed=True))


def test_gratis_ignores_student_key(settings_with_keys):
    for p in provider_chain("gratis", "chave-do-aluno", claude_allowed=True):
        client = getattr(p, "_client", None) or p.client
        assert client.api_key != "chave-do-aluno"


def test_own_key_options_use_student_key():
    for option, label in (("groq", "Minha chave · Groq"), ("openai", "Minha chave · GPT"),
                          ("gemini", "Minha chave · Gemini")):
        chain = provider_chain(option, "chave-x")
        assert len(chain) == 1 and chain[0].label == label and chain[0]._client.api_key == "chave-x"


def test_claude_own_key_uses_student_key_not_owner():
    chain = provider_chain("claude", "sk-ant-aluno")
    assert len(chain) == 1 and chain[0].label == "Minha chave · Claude"
    assert isinstance(chain[0], AnthropicProvider) and chain[0].client.api_key == "sk-ant-aluno"


def test_no_owner_claude_option_anymore():
    assert "claude-teste" not in OPTIONS and OPTIONS["claude"].own_key


def test_limits():
    assert (OPTIONS["gratis"].per_ip, OPTIONS["gratis"].global_limit) == (30, 400)
    for own in ("openai", "gemini", "groq", "claude"):
        assert (OPTIONS[own].per_ip, OPTIONS[own].global_limit, OPTIONS[own].own_key) == (60, None, True)


def test_public_options_have_no_secrets():
    opts = public_options()
    assert [o["id"] for o in opts] == ["gratis", "openai", "gemini", "groq", "claude"]
    assert all(set(o) == {"id", "label", "own_key"} for o in opts)
