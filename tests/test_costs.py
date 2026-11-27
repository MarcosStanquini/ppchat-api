from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.modules.observability.costs import CostService, windows

NOW = datetime(2026, 11, 27, 15, 40, tzinfo=UTC)
REFRESHED = datetime(2026, 11, 27, 6, 0, tzinfo=UTC)


def item(day: int, model: str | None, cents: str):
    start = datetime(2026, 11, day, tzinfo=UTC)
    return SimpleNamespace(cost=SimpleNamespace(amount=cents), group=SimpleNamespace(model=model),
                           starting_at=start, ending_at=start + timedelta(days=1))


class Page:
    def __init__(self, data, nxt=None):
        self.data, self._next, self.data_refreshed_at = data, nxt, REFRESHED

    def has_next_page(self):
        return self._next is not None

    async def get_next_page(self):
        return self._next


class FakeList:
    """Faz o papel de client.beta.organization.analytics.cost.list."""

    def __init__(self, pages=None, error=None):
        self.calls, self.pages, self.error = [], pages or [], error

    async def __call__(self, **params):
        self.calls.append(params)
        if self.error:
            raise self.error
        return self.pages.pop(0) if self.pages else Page([])


def test_windows_split_long_range_without_overlap():
    start = datetime(2026, 8, 29, tzinfo=UTC)
    parts = windows(start, start + timedelta(days=90))
    assert len(parts) == 3
    assert parts[0][0] == start and parts[-1][1] == start + timedelta(days=90)
    assert all(a[1] == b[0] for a, b in zip(parts, parts[1:]))
    assert all(e - s <= timedelta(days=31) for s, e in parts)


def test_windows_empty_when_start_is_not_before_end():
    assert windows(NOW, NOW) == []


async def test_report_sums_by_day_and_model_in_dollars():
    fake = FakeList([Page([item(26, "claude-opus-5-5", "150.5"), item(26, "claude-haiku-5-5", "49.5"),
                           item(27, "claude-opus-5-5", "100")])])
    report = await CostService(fake, now=lambda: NOW).report(7)
    assert report["total_usd"] == 3.0
    assert report["por_dia"] == [{"dia": "2026-11-26", "usd": 2.0}, {"dia": "2026-11-27", "usd": 1.0}]
    assert report["por_modelo"][0] == {"modelo": "claude-opus-5-5", "usd": 2.505}
    assert report["dados_ate"] == REFRESHED.isoformat()
    params = fake.calls[0]
    assert params["time_bucket_width"] == "1d" and params["group_by"] == ["model"]
    assert params["ending_at"] - params["starting_at"] <= timedelta(days=31)


async def test_report_follows_every_page_and_window():
    second = Page([item(27, "claude-opus-5-5", "100")])
    fake = FakeList([Page([item(26, "claude-opus-5-5", "100")], nxt=second)])
    report = await CostService(fake, now=lambda: NOW).report(90)
    assert report["total_usd"] == 2.0
    assert len(fake.calls) == 3  # 90 dias = 3 janelas


async def test_report_is_cached_but_errors_are_not():
    clock = [NOW]
    fake = FakeList(error=RuntimeError("caiu"))
    service = CostService(fake, now=lambda: clock[0])
    with pytest.raises(RuntimeError):
        await service.report(7)
    fake.error = None
    await service.report(7)
    await service.report(7)
    assert len(fake.calls) == 2  # a falha não ficou guardada; a segunda chamada veio do cache
    clock[0] = NOW + timedelta(minutes=31)
    await service.report(7)
    assert len(fake.calls) == 3


async def test_spent_since_sums_from_reference_hour():
    fake = FakeList([Page([item(27, None, "250")])])
    spent, refreshed = await CostService(fake, now=lambda: NOW).spent_since(NOW - timedelta(hours=5, minutes=10))
    assert spent == Decimal("2.5") and refreshed == REFRESHED
    assert fake.calls[0]["starting_at"] == datetime(2026, 11, 27, 10, tzinfo=UTC)
    assert "time_bucket_width" not in fake.calls[0]


async def test_spent_since_in_the_current_hour_is_zero_without_calling():
    fake = FakeList()
    spent, _ = await CostService(fake, now=lambda: NOW).spent_since(NOW - timedelta(minutes=5))
    assert spent == 0 and fake.calls == []
