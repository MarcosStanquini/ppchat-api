"""Gasto real com a Anthropic, pelo relatório de custos da API de administração.

Precisa de uma chave de administração (ANTHROPIC_ADMIN_KEY), usada só aqui e só para ler custos.
O relatório chega com algumas horas de atraso e aceita no máximo 31 dias por consulta.
"""
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from src.modules.shared.services.settings import get_settings

MAX_WINDOW = timedelta(days=31)
CACHE_SECONDS = 30 * 60
TIMEOUT_SECONDS = 10.0

ListCosts = Callable[..., Awaitable[Any]]


def windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Corta [start, end) em pedaços de até 31 dias, sem sobreposição."""
    parts = []
    while start < end:
        stop = min(start + MAX_WINDOW, end)
        parts.append((start, stop))
        start = stop
    return parts


def _hour(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def _usd(cents: Decimal) -> float:
    return float(round(cents / 100, 4))


class CostService:
    def __init__(self, list_costs: ListCosts, now: Callable[[], datetime] = lambda: datetime.now(UTC),
                 ttl: float = CACHE_SECONDS) -> None:
        self._list = list_costs
        self._now = now
        self._ttl = ttl
        self._cache: dict[tuple, tuple[datetime, Any]] = {}

    async def _rows(self, start: datetime, end: datetime, **params) -> tuple[list, datetime | None]:
        rows, refreshed = [], None
        for win_start, win_end in windows(start, end):
            page = await self._list(starting_at=win_start, ending_at=win_end, limit=1000, **params)
            while True:
                rows.extend(page.data)
                refreshed = page.data_refreshed_at or refreshed
                if not page.has_next_page():
                    break
                page = await page.get_next_page()
        return rows, refreshed

    async def _cached(self, key: tuple, load: Callable[[], Awaitable[Any]]) -> Any:
        now = self._now()
        hit = self._cache.get(key)
        if hit and (now - hit[0]).total_seconds() < self._ttl:
            return hit[1]
        value = await load()  # se falhar, nada é guardado
        self._cache[key] = (now, value)
        return value

    async def report(self, dias: int) -> dict:
        """Gasto dos últimos `dias` dias (contando hoje), por dia e por modelo, em US$."""
        async def load() -> dict:
            now = self._now()
            start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=dias - 1)
            rows, refreshed = await self._rows(start, _hour(now), time_bucket_width="1d", group_by=["model"])
            per_day: dict[str, Decimal] = defaultdict(Decimal)
            per_model: dict[str, Decimal] = defaultdict(Decimal)
            for row in rows:
                cents = Decimal(row.cost.amount)
                per_day[row.starting_at.date().isoformat()] += cents
                per_model[row.group.model or "outros"] += cents
            return {
                "total_usd": _usd(sum(per_day.values(), Decimal())),
                "por_dia": [{"dia": day, "usd": _usd(v)} for day, v in sorted(per_day.items())],
                "por_modelo": [{"modelo": m, "usd": _usd(v)}
                               for m, v in sorted(per_model.items(), key=lambda kv: -kv[1])],
                "dados_ate": refreshed.isoformat() if refreshed else None,
            }

        return await self._cached(("report", dias), load)

    async def spent_since(self, when: datetime) -> tuple[Decimal, datetime | None]:
        """Gasto em US$ desde a hora cheia de `when` (o relatório trabalha com horas inteiras)."""
        start = _hour(when)

        async def load() -> tuple[Decimal, datetime | None]:
            rows, refreshed = await self._rows(start, _hour(self._now()))
            return sum((Decimal(r.cost.amount) for r in rows), Decimal()) / 100, refreshed

        return await self._cached(("since", start), load)


_service: CostService | None = None


def get_service() -> CostService | None:
    """None sem ANTHROPIC_ADMIN_KEY: o cartão de custos mostra "não configurado"."""
    global _service
    key = get_settings().anthropic_admin_key
    if not key:
        return None
    if _service is None:
        from anthropic import AsyncAnthropic

        # Cliente separado do chat, só com a chave de administração
        client = AsyncAnthropic(api_key=key, timeout=TIMEOUT_SECONDS, max_retries=1)
        _service = CostService(client.beta.organization.analytics.cost.list)
    return _service


def set_service(service: CostService | None) -> None:
    global _service
    _service = service
