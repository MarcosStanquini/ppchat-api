from src.modules.response.services.answer_cache import AnswerCache, CachedAnswer, cacheable


def test_normalized_key_matches_variants():
    assert AnswerCache.key("ads", "Como funciona o TCC?") == AnswerCache.key("ads", "  como funciona o tcc ")
    assert AnswerCache.key("ads", "TCC?") != AnswerCache.key("bes", "TCC?")


def test_not_cacheable_with_personal_or_context_data():
    assert not cacheable("gratis", "perfil", [], []) and not cacheable("gratis", None, [{"role": "user"}], [])
    assert not cacheable("gratis", None, [], ["SCLAPR1"]) and not cacheable("claude-teste", None, [], [])
    assert not cacheable("openai", None, [], [])
    assert cacheable("gratis", None, [], [])


def test_get_put_roundtrip():
    c = AnswerCache()
    c.put("a", "Q?", CachedAnswer("r", "Gratuito · Gemini"))
    assert c.get("a", "q") == CachedAnswer("r", "Gratuito · Gemini")


def test_expires_and_evicts():
    c = AnswerCache(max_entries=1, ttl_seconds=10)
    c.put("a", "q1", CachedAnswer("r", "l"))
    c.put("a", "q2", CachedAnswer("r", "l"))
    assert c.get("a", "q1") is None and c.get("a", "q2") is not None
    clock = [0.0]
    c = AnswerCache(ttl_seconds=10, clock=lambda: clock[0])
    c.put("a", "q", CachedAnswer("r", "l"))
    clock[0] = 11
    assert c.get("a", "q") is None
