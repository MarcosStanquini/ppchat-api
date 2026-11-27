from src.modules.response.services.chat_service import ChatSession


async def test_session_streams_text_from_any_provider(fake_provider, kb):
    session = ChatSession(kb, fake_provider(["Olá", " mundo"]))
    out = [t async for k, t in session.stream_events("oi") if k == "text"]
    assert "".join(out) == "Olá mundo"


async def test_history_is_plain_text_for_switching_providers(fake_provider, kb):
    hist = [{"role": "user", "text": "a"}, {"role": "assistant", "text": "b"}]
    session = ChatSession(kb, fake_provider(["c"]), history=hist)
    [_ async for _ in session.stream_events("d")]
    assert all(isinstance(m["content"], str) for m in session.messages)
    assert session.messages[-1] == {"role": "assistant", "content": "c"}


async def test_perfil_and_focus_go_in_user_turn_not_system(fake_provider, kb):
    p = fake_provider(["ok"])
    session = ChatSession(kb, p)
    [_ async for _ in session.stream_events("q", focus=["X"], perfil="PERFIL")]
    assert "PERFIL" in p.last_messages[-1]["content"] and "PERFIL" not in p.last_system
    assert p.last_context == kb.full_context


async def test_failed_answer_keeps_history_valid(fake_provider, kb):
    session = ChatSession(kb, fake_provider(error=RuntimeError("caiu")))
    try:
        [_ async for _ in session.stream_events("q")]
    except RuntimeError:
        pass
    assert session.messages == []


async def test_answered_by_uses_provider_label(fake_provider, kb):
    session = ChatSession(kb, fake_provider(["a", "b"], label="Gratuito · Gemini"))
    [_ async for _ in session.stream_events("q")]
    assert session.answered_by == ("Gratuito · Gemini", 2)
