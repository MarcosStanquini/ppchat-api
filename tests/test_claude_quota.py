from datetime import date

from src.modules.response.services.claude_quota import ClaudeQuota


def test_two_per_person_per_day_then_free_model():
    quota = ClaudeQuota(per_day=2, global_per_hour=100, today=lambda: date(2026, 11, 27))
    assert [quota.take("1.1.1.1") for _ in range(3)] == [True, True, False]
    assert quota.take("2.2.2.2")  # outra pessoa tem as dela


def test_resets_next_day():
    day = [date(2026, 11, 27)]
    quota = ClaudeQuota(per_day=1, global_per_hour=100, today=lambda: day[0])
    assert quota.take("ip") and not quota.take("ip")
    day[0] = date(2026, 11, 28)
    assert quota.take("ip")


def test_global_hourly_cap_protects_the_bill():
    quota = ClaudeQuota(per_day=5, global_per_hour=3, today=lambda: date(2026, 11, 27))
    assert [quota.take(f"ip{i}") for i in range(4)] == [True, True, True, False]


def test_zero_turns_claude_off():
    assert not ClaudeQuota(per_day=0, global_per_hour=100).take("ip")
