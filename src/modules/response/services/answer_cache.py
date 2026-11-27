"""Respostas do modelo gratuito guardadas para perguntas iguais (ex.: as perguntas prontas da tela Explorar).

Só entra pergunta sem nada pessoal ou de contexto: sem dados do SUAP, sem histórico e sem disciplinas em
foco. Fica em memória: zera quando o servidor reinicia, e um PPC novo só entra com um deploy (que reinicia).
"""
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from src.modules.observability.records import normalize_question


@dataclass(frozen=True)
class CachedAnswer:
    text: str
    label: str  # quem respondeu originalmente


def cacheable(option_id: str, perfil: str | None, history: list, disciplinas: list) -> bool:
    return option_id == "gratis" and not perfil and not history and not disciplinas


class AnswerCache:
    def __init__(self, max_entries: int = 500, ttl_seconds: int = 7 * 24 * 3600,
                 clock: Callable[[], float] = time.monotonic):
        self.max_entries, self.ttl, self.clock = max_entries, ttl_seconds, clock
        self._items: OrderedDict[str, tuple[float, CachedAnswer]] = OrderedDict()

    @staticmethod
    def key(curso: str, question: str) -> str:
        return f"{curso}|{normalize_question(question)}"

    def get(self, curso: str, question: str) -> CachedAnswer | None:
        key = self.key(curso, question)
        item = self._items.get(key)
        if item is None:
            return None
        if self.clock() - item[0] > self.ttl:
            del self._items[key]
            return None
        self._items.move_to_end(key)  # usada há pouco: fica por último na fila de descarte
        return item[1]

    def put(self, curso: str, question: str, answer: CachedAnswer) -> None:
        key = self.key(curso, question)
        self._items[key] = (self.clock(), answer)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)


answer_cache = AnswerCache()
