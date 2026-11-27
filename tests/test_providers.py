from src.modules.response.services.providers import OpenAICompatibleProvider


async def test_openai_compatible_sends_system_and_context_once(httpx_mock_openai):
    prov = OpenAICompatibleProvider("https://x/v1", "k", "m", "Teste", http_client=httpx_mock_openai.client)
    out = [t async for _, t in prov.stream("SYS", "CTX", [{"role": "user", "content": "q"}])]
    sent = httpx_mock_openai.last_request_json
    assert sent["messages"][0] == {"role": "system", "content": "SYS\n\nCTX"} and sent["stream"] is True
    assert sent["messages"][1] == {"role": "user", "content": "q"} and sent["model"] == "m"
    assert "".join(out) == "Olá mundo"
    assert (prov.usage.input_tokens, prov.usage.output_tokens) == (10, 2)


async def test_openai_compatible_marks_cut_answers_incomplete(httpx_mock_openai):
    prov = OpenAICompatibleProvider("https://x/v1", "k", "m", "Teste", http_client=httpx_mock_openai.client)
    [_ async for _ in prov.stream("s", "c", [])]
    assert prov.complete is True
    httpx_mock_openai.finish_reason = "length"
    [_ async for _ in prov.stream("s", "c", [])]
    assert prov.complete is False
