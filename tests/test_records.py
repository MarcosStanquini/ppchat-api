from datetime import date

from src.modules.observability.records import (
    normalize_question,
    valid_event,
    visitor_hash,
)
from src.modules.observability.store import MemoryStore, NullStore


def test_normalize_question():
    assert normalize_question("  Como FUNCIONA o TCC?? ") == normalize_question("como funciona o tcc") == "como funciona o tcc"
    assert normalize_question("Estágio é obrigatório?") == "estagio e obrigatorio"


def test_record_exposes_normalized_question(make_record):
    assert make_record(pergunta="Estágio  é obrigatório?").pergunta_norm == "estagio e obrigatorio"


def test_visitor_hash_changes_by_day_and_hides_ip():
    a = visitor_hash("1.2.3.4", "s", date(2026, 11, 27))
    b = visitor_hash("1.2.3.4", "s", date(2026, 11, 28))
    assert a != b and "1.2.3.4" not in a and len(a) == 64
    assert a == visitor_hash("1.2.3.4", "s", date(2026, 11, 27))
    assert a != visitor_hash("1.2.3.4", "outro", date(2026, 11, 27))


def test_valid_event():
    assert valid_event("voto", "up") and valid_event("voto", "down") and valid_event("voto", "nenhum")
    assert valid_event("abriu_pagina", "12") and valid_event("copiou", "")
    assert not valid_event("voto", "x") and not valid_event("abriu_pagina", "-1")
    assert not valid_event("abriu_pagina", "abc") and not valid_event("abriu_pagina", "2001")
    assert not valid_event("copiou", "x") and not valid_event("outro", "")


async def test_memory_store_event_needs_existing_question(record):
    store = MemoryStore()
    assert not await store.save_event(record.id, "voto", "up")
    await store.save_question(record)
    assert await store.save_event(record.id, "voto", "up")
    assert store.events == [(record.id, "voto", "up")]


async def test_memory_store_ignores_repeated_id(record, make_record):
    store = MemoryStore()
    await store.save_question(record)
    await store.save_question(make_record(id=record.id, pergunta="outra"))
    assert store.questions[record.id].pergunta == record.pergunta


async def test_null_store_accepts_everything(record):
    store = NullStore()
    await store.save_question(record)
    assert await store.save_event(record.id, "voto", "up")
