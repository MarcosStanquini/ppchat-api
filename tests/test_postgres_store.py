from datetime import UTC, datetime, timedelta
from uuid import uuid4


async def test_roundtrip_and_cascade(pg, record):
    await pg.save_question(record)
    await pg.save_question(record)  # id repetido não quebra
    assert await pg.save_event(record.id, "voto", "down")
    assert (await pg.negatives(7, None))[0]["pergunta"] == record.pergunta
    await pg.purge(days=-1)
    assert (await pg.summary(7, None))["perguntas"] == 0
    assert await pg.fetch_value("select count(*) from eventos") == 0


async def test_event_for_unknown_question_is_rejected(pg):
    assert not await pg.save_event(uuid4(), "voto", "up")


async def test_last_vote_wins(pg, record):
    await pg.save_question(record)
    for value in ("up", "down", "nenhum"):
        await pg.save_event(record.id, "voto", value)
    summary = await pg.summary(7, None)
    assert summary["votadas"] == 0 and summary["positivas"] == 0


async def test_summary_counts(pg, make_record):
    up, down, stopped = make_record(), make_record(visitante="b" * 64), make_record(status="parada")
    err = make_record(status="erro", erro="RuntimeError")
    for r in (up, down, stopped, err):
        await pg.save_question(r)
    await pg.save_event(up.id, "voto", "up")
    await pg.save_event(down.id, "voto", "down")
    s = await pg.summary(7, None)
    assert (s["perguntas"], s["visitantes"], s["votadas"], s["positivas"], s["paradas"], s["erros"]) == (4, 2, 2, 1, 1, 1)


async def test_filters_by_course(pg, make_record):
    await pg.save_question(make_record(curso="a"))
    await pg.save_question(make_record(curso="b"))
    assert (await pg.summary(7, "a"))["perguntas"] == 1


async def test_reformulou(pg, make_record):
    conv = uuid4()
    await pg.save_question(make_record(conversa=conv, turno=0))
    await pg.save_question(make_record(conversa=conv, turno=1))
    assert (await pg.summary(7, None))["reformuladas"] == 1


async def test_upvoted_is_not_reformulated(pg, make_record):
    conv = uuid4()
    first = make_record(conversa=conv, turno=0)
    await pg.save_question(first)
    await pg.save_question(make_record(conversa=conv, turno=1))
    await pg.save_event(first.id, "voto", "up")
    assert (await pg.summary(7, None))["reformuladas"] == 0


async def test_late_follow_up_is_not_reformulated(pg, make_record):
    conv = uuid4()
    first = make_record(conversa=conv, turno=0)
    await pg.save_question(first)
    later = make_record(conversa=conv, turno=1)
    await pg.save_question(later)
    await pg.execute("update perguntas set criado_em = %s where id = %s",
                     (datetime.now(UTC) + timedelta(minutes=10), later.id))
    assert (await pg.summary(7, None))["reformuladas"] == 0


async def test_top_questions_group_variants(pg, make_record):
    for text in ("Como funciona o TCC?", "como funciona o tcc", "Estágio?"):
        await pg.save_question(make_record(pergunta=text))
    top = await pg.top_questions(7, None)
    assert top[0]["vezes"] == 2 and top[0]["pergunta"].lower().startswith("como funciona")


async def test_questions_list_signals_and_paging(pg, make_record):
    conv = uuid4()
    a = make_record(conversa=conv, turno=0)
    await pg.save_question(a)
    await pg.save_event(a.id, "copiou", "")
    await pg.save_event(a.id, "abriu_pagina", "3")
    await pg.save_event(a.id, "voto", "up")
    page = await pg.questions(7, None, None, 1)
    item = page["itens"][0]
    assert page["total"] == 1 and item["voto"] == "up" and item["copiou"] and item["abriu_pagina"]
    assert item["abandonou"] is False and item["reformulou"] is False


async def test_abandonou(pg, make_record):
    await pg.save_question(make_record())
    assert (await pg.questions(7, None, None, 1))["itens"][0]["abandonou"] is True


async def test_search_is_parameterized(pg, make_record):
    await pg.save_question(make_record(pergunta="100% do curso? ' drop table perguntas; --"))
    await pg.save_question(make_record(pergunta="outra coisa"))
    assert (await pg.questions(7, None, "100%", 1))["total"] == 1
    assert (await pg.questions(7, None, "' drop table", 1))["total"] == 1
    assert (await pg.questions(7, None, "_", 1))["total"] == 0
    assert await pg.fetch_value("select count(*) from perguntas") == 2



async def test_survives_dropped_connection(record):
    # Neon derruba as conexões quando suspende; a próxima gravação não pode se perder.
    # Usa o endereço direto (sem o pooler, que esconderia a queda).
    import psycopg
    import pytest

    from src.modules.observability.postgres_store import PostgresStore
    from tests.conftest import TEST_DATABASE_URL, require_test_database

    if not TEST_DATABASE_URL or "-pooler" not in TEST_DATABASE_URL:
        pytest.skip("precisa do TEST_DATABASE_URL pooled do Neon")
    direct = TEST_DATABASE_URL.replace("-pooler", "")
    store = await PostgresStore.open(direct)
    try:
        await require_test_database(store)
        await store.execute("truncate perguntas cascade")
        with psycopg.connect(direct, autocommit=True) as killer:
            killer.execute("select pg_terminate_backend(pid) from pg_stat_activity "
                           "where usename = current_user and pid <> pg_backend_pid() and datname = current_database()")
        await store.save_question(record)
        assert await store.fetch_value("select count(*) from perguntas") == 1
    finally:
        await store.close()
