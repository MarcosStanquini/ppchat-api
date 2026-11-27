import pytest

from src.modules.response.services.fallback import (
    USER_MESSAGES,
    FallbackProvider,
    UserFacingError,
    stream_with_fallback,
)
from src.modules.response.services.providers import (
    OpenAICompatibleProvider,
    ProviderError,
)

QUOTA_GRATIS = "O modelo gratuito atingiu o limite de uso agora. Tente mais tarde ou use sua própria chave."


async def collect(chain):
    return "".join([t async for _, t in stream_with_fallback(chain, "s", "c", [])])


async def test_falls_back_on_quota_before_first_token(fake_provider):
    a = fake_provider(error=ProviderError("quota", before_first_token=True), label="Gratuito · Gemini")
    b = fake_provider(["ok"], label="Gratuito · OpenRouter")
    assert await collect([a, b]) == "ok"


async def test_answered_by_is_the_provider_that_answered(fake_provider):
    a = fake_provider(error=ProviderError("unavailable"), label="Gratuito · Gemini")
    b = fake_provider(["ok"], label="Gratuito · OpenRouter")
    chain = FallbackProvider([a, b])
    [_ async for _ in chain.stream("s", "c", [])]
    assert chain.label == "Gratuito · OpenRouter" and chain.usage is b.usage


async def test_does_not_fall_back_mid_stream(fake_provider):
    a = fake_provider(["meio"], error_after_first=ProviderError("quota", before_first_token=False))
    b = fake_provider(["x"])
    with pytest.raises(UserFacingError):
        await collect([a, b])
    assert b.calls == 0


async def test_gratis_exhausted_message(fake_provider):
    chain = [fake_provider(error=ProviderError("quota", True), label="Gratuito · Gemini") for _ in range(3)]
    with pytest.raises(UserFacingError) as e:
        await collect(chain)
    assert e.value.message == QUOTA_GRATIS == USER_MESSAGES["quota_gratis"]


async def test_empty_gratis_chain_is_unavailable_not_a_crash():
    with pytest.raises(UserFacingError) as e:
        await collect([])
    assert e.value.message == USER_MESSAGES["unavailable"]


async def test_own_key_quota_and_auth_messages(fake_provider):
    with pytest.raises(UserFacingError) as e:
        await collect([fake_provider(error=ProviderError("quota"), label="Minha chave · Groq")])
    assert e.value.message == "Sua chave do Groq está sem crédito ou atingiu o limite."
    with pytest.raises(UserFacingError) as e:
        await collect([fake_provider(error=ProviderError("auth"), label="Minha chave · GPT")])
    assert e.value.message == "Sua chave do GPT foi recusada. Confira a chave e tente de novo."


async def test_unknown_error_is_generic(fake_provider):
    with pytest.raises(UserFacingError) as e:
        await collect([fake_provider(error=ValueError("detalhe interno sk-xyz"), label="Gratuito · Gemini")])
    assert e.value.message == USER_MESSAGES["unavailable"] and "sk-" not in e.value.message


@pytest.mark.parametrize("status, kind", [(401, "auth"), (403, "auth"), (429, "quota"), (402, "quota"),
                                          (503, "unavailable"), (400, "other")])
async def test_openai_errors_are_classified(httpx_mock_openai, status, kind):
    httpx_mock_openai.status = status
    prov = OpenAICompatibleProvider("https://x/v1", "k", "m", "Minha chave · GPT", http_client=httpx_mock_openai.client)
    with pytest.raises(ProviderError) as e:
        [_ async for _ in prov.stream("s", "c", [])]
    assert e.value.kind == kind and e.value.before_first_token


async def test_error_never_contains_key(httpx_mock_openai):
    httpx_mock_openai.status = 401
    httpx_mock_openai.body = {"error": {"message": "Incorrect API key provided: sk-SEGREDO123"}}
    prov = OpenAICompatibleProvider("https://x/v1", "sk-SEGREDO123", "m", "Minha chave · GPT",
                                    http_client=httpx_mock_openai.client)
    with pytest.raises(UserFacingError) as e:
        await collect([prov])
    assert "SEGREDO" not in e.value.message and "sk-" not in e.value.message
    assert "SEGREDO" not in str(e.value) and e.value.__cause__ is None and e.value.__context__ is None


async def test_gratis_falls_back_even_when_owner_key_is_refused(fake_provider):
    a = fake_provider(error=ProviderError("auth"), label="Gratuito · Gemini")
    b = fake_provider(["ok"], label="Gratuito · OpenRouter")
    assert await collect([a, b]) == "ok"
