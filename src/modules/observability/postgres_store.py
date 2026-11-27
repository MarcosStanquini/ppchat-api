"""Perguntas e sinais no Postgres (Neon).

Usa o driver síncrono em threads próprias: o modo assíncrono do psycopg não roda no loop padrão do
Windows (onde o dono desenvolve), e o volume aqui é pequeno. Valores sempre vão como parâmetros.
"""
import asyncio
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from src.modules.observability.records import EventType, QuestionRecord

SCHEMA = (Path(__file__).parent / "schema.sql").read_text("utf-8")

# Perguntas do período (e do curso) com os sinais derivados de cada uma
_SIGNALS = """
with base as (
  select * from perguntas
  where criado_em >= now() - make_interval(days => %(dias)s)
    and (%(curso)s::text is null or curso = %(curso)s)
),
votos as (
  select distinct on (pergunta_id) pergunta_id, valor
  from eventos where tipo = 'voto'
  order by pergunta_id, criado_em desc, id desc
),
sinais as (
  select b.*,
    case when v.valor in ('up', 'down') then v.valor end as voto,
    exists (select 1 from eventos e where e.pergunta_id = b.id and e.tipo = 'copiou') as copiou,
    exists (select 1 from eventos e where e.pergunta_id = b.id and e.tipo = 'abriu_pagina') as abriu_pagina,
    exists (select 1 from perguntas n where n.conversa = b.conversa and n.turno = b.turno + 1) as tem_proxima,
    exists (
      select 1 from perguntas n
      where n.conversa = b.conversa and n.turno = b.turno + 1
        and n.criado_em - make_interval(secs => n.duracao_ms / 1000.0) <= b.criado_em + interval '2 minutes'
    ) as proxima_rapida
  from base b left join votos v on v.pergunta_id = b.id
),
final as (
  select s.*,
    (s.proxima_rapida and coalesce(s.voto, '') <> 'up') as reformulou,
    (s.conversa is not null and not s.tem_proxima and s.voto is null and not s.copiou) as abandonou
  from sinais s
)
"""
# proxima_rapida: a próxima pergunta da conversa começou até 2 min depois do fim desta
# (criado_em é gravado quando a resposta termina; o começo é criado_em - duracao_ms)

_ITEM_FIELDS = (
    "id, criado_em, curso, pergunta, resposta, modelo, status, erro, duracao_ms, tinha_suap, "
    "voto, copiou, abriu_pagina, reformulou, abandonou"
)


def _plain(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if isinstance(value, UUID):
            value = str(value)
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        out[key] = value
    return out


def _like(text: str) -> str:
    """Busca literal: %, _ e \\ digitados pelo dono não viram curingas."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class PostgresStore:
    def __init__(self, pool: ConnectionPool, executor: ThreadPoolExecutor):
        self.pool = pool
        # Threads só do banco: um banco lento não ocupa as threads que o resto do servidor usa (DNS da API etc.)
        self.executor = executor

    @classmethod
    async def open(cls, url: str) -> "PostgresStore":
        def connect() -> ConnectionPool:
            pool = ConnectionPool(
                url, min_size=1, max_size=4, open=True, timeout=5,
                # O Neon derruba as conexões quando suspende: confere cada uma antes de usar e troca as mortas
                check=ConnectionPool.check_connection,
                kwargs={"autocommit": True, "connect_timeout": 10, "row_factory": dict_row},
            )
            with pool.connection() as conn:
                conn.execute(SCHEMA)
            return pool

        executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ppchat-db")
        pool = await asyncio.get_running_loop().run_in_executor(executor, connect)
        return cls(pool, executor)

    async def _run(self, sql: str, params: Any = None, fetch: str = "none"):
        def work():
            with self.pool.connection() as conn:
                cur = conn.execute(sql, params)
                if fetch == "all":
                    return cur.fetchall()
                if fetch == "one":
                    return cur.fetchone()
                return cur.rowcount

        return await asyncio.get_running_loop().run_in_executor(self.executor, work)

    async def execute(self, sql: str, params: Sequence | None = None) -> int:
        return await self._run(sql, params)

    async def fetch_value(self, sql: str, params: Sequence | None = None) -> Any:
        row = await self._run(sql, params, "one")
        return next(iter(row.values())) if row else None

    async def save_question(self, record: QuestionRecord) -> None:
        fields = {**asdict(record), "pergunta_norm": record.pergunta_norm}
        # Nomes de coluna vêm do dataclass (fixos no código); os valores vão como parâmetros
        columns = ", ".join(fields)
        values = ", ".join(f"%({name})s" for name in fields)
        await self._run(f"insert into perguntas ({columns}) values ({values}) on conflict (id) do nothing", fields)

    async def save_event(self, pergunta_id: UUID, tipo: EventType, valor: str) -> bool:
        count = await self._run(
            "insert into eventos (pergunta_id, tipo, valor) "
            "select %s, %s, %s where exists (select 1 from perguntas where id = %s)",
            (pergunta_id, tipo, valor, pergunta_id),
        )
        return count == 1

    async def purge(self, days: int = 180) -> None:
        await self._run("delete from perguntas where criado_em < now() - make_interval(days => %s)", (days,))

    async def close(self) -> None:
        await asyncio.get_running_loop().run_in_executor(self.executor, self.pool.close)
        self.executor.shutdown(wait=False)

    # ── Consultas do /admin ──
    async def summary(self, dias: int, curso: str | None) -> dict:
        row = await self._run(_SIGNALS + """
            select count(*) as perguntas,
              count(distinct visitante) as visitantes,
              count(*) filter (where voto is not null) as votadas,
              count(*) filter (where voto = 'up') as positivas,
              count(*) filter (where status = 'parada') as paradas,
              count(*) filter (where reformulou) as reformuladas,
              count(*) filter (where status = 'erro') as erros
            from final""", {"dias": dias, "curso": curso}, "one")
        return dict(row)

    async def top_questions(self, dias: int, curso: str | None, limit: int = 20) -> list:
        rows = await self._run(_SIGNALS + """
            select (array_agg(pergunta order by criado_em desc))[1] as pergunta, count(*) as vezes
            from final group by pergunta_norm
            order by vezes desc, max(criado_em) desc limit %(limit)s""",
            {"dias": dias, "curso": curso, "limit": limit}, "all")
        return [_plain(r) for r in rows]

    async def negatives(self, dias: int, curso: str | None, limit: int = 50) -> list:
        rows = await self._run(_SIGNALS + f"""
            select {_ITEM_FIELDS} from final where voto = 'down'
            order by criado_em desc limit %(limit)s""",
            {"dias": dias, "curso": curso, "limit": limit}, "all")
        return [_plain(r) for r in rows]

    async def questions(self, dias: int, curso: str | None, busca: str | None, pagina: int,
                        por_pagina: int = 30) -> dict:
        rows = await self._run(_SIGNALS + f"""
            select {_ITEM_FIELDS}, count(*) over () as total from final
            where %(busca)s::text is null or pergunta ilike %(busca)s escape '\\'
            order by criado_em desc limit %(limit)s offset %(offset)s""",
            {"dias": dias, "curso": curso, "busca": _like(busca) if busca else None,
             "limit": por_pagina, "offset": (max(pagina, 1) - 1) * por_pagina}, "all")
        total = rows[0]["total"] if rows else 0
        return {"itens": [_plain({k: v for k, v in r.items() if k != "total"}) for r in rows], "total": total}
