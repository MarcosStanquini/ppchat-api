import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from fastapi import Request

WINDOW_SECONDS = 3600


class RateLimiter:
    """Janela deslizante de 1 hora, em memória.

    Basta para uma instância única (como o plano grátis do Render); se o processo reiniciar,
    as contagens zeram, o que é aceitável aqui. O limite de gastos no console da Anthropic
    continua sendo a rede de segurança final.
    """

    def __init__(self, per_ip: int, global_limit: int):
        self.per_ip = per_ip
        self.global_limit = global_limit
        self.hits: Dict[str, Deque[float]] = defaultdict(deque)
        self.global_hits: Deque[float] = deque()

    @staticmethod
    def _prune(hits: Deque[float], now: float) -> None:
        while hits and now - hits[0] > WINDOW_SECONDS:
            hits.popleft()

    def check(self, ip: str) -> Optional[str]:
        """Registra a pergunta e devolve uma mensagem de erro se algum limite estourou."""
        now = time.monotonic()
        hits = self.hits[ip]
        self._prune(hits, now)
        self._prune(self.global_hits, now)

        if self.global_limit and len(self.global_hits) >= self.global_limit:
            return "O PPChat atingiu o limite de perguntas desta hora. Tente de novo mais tarde."
        if self.per_ip and len(hits) >= self.per_ip:
            minutes = max(1, int((WINDOW_SECONDS - (now - hits[0])) / 60))
            return f"Você atingiu o limite de {self.per_ip} perguntas por hora. Tente de novo em {minutes} min."

        hits.append(now)
        self.global_hits.append(now)
        if len(self.hits) > 10_000:  # evita crescer sem limite com IPs que não voltam
            for key in [k for k, v in self.hits.items() if not v]:
                del self.hits[key]
        return None


def client_ip(request: Request) -> str:
    # Atrás do proxy do Render o IP real vem no X-Forwarded-For (o primeiro da lista)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"
