"""Quantas perguntas do gratuito cada pessoa ainda pode fazer ao Claude do dono hoje.

Por IP e por dia (horário de Brasília), em memória: zera num deploy novo, o que é aceitável. Um teto por
hora para o site inteiro protege a conta mesmo se alguém trocar de IP para ganhar mais perguntas.
"""
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from src.modules.api.rate_limit import RateLimiter

BRASILIA = timezone(timedelta(hours=-3))


def _today() -> date:
    return datetime.now(BRASILIA).date()


class ClaudeQuota:
    def __init__(self, per_day: int, global_per_hour: int, today: Callable[[], date] = _today):
        self.per_day, self.today = per_day, today
        self.global_limiter = RateLimiter(per_ip=0, global_limit=global_per_hour)
        self.day: date | None = None
        self.used: dict[str, int] = {}

    def take(self, ip: str) -> bool:
        """Gasta uma pergunta do Claude desta pessoa, se ainda houver; senão a pergunta vai ao modelo gratuito."""
        if self.per_day <= 0:
            return False
        if self.day != self.today():
            self.day, self.used = self.today(), {}
        if self.used.get(ip, 0) >= self.per_day or self.global_limiter.blocked(ip):
            return False
        self.global_limiter.check(ip)
        self.used[ip] = self.used.get(ip, 0) + 1
        return True
