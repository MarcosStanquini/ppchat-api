"""O que fica guardado de cada pergunta ao chat (sem dados do SUAP, histórico ou IP)."""
import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID

Status = Literal["ok", "parada", "erro"]
EventType = Literal["voto", "copiou", "abriu_pagina"]
VOTOS = {"up", "down", "nenhum"}
MAX_PAGINA = 2000


def normalize_question(text: str) -> str:
    """Agrupa variações da mesma pergunta: minúsculas, sem acentos, espaços únicos, sem ?!. no fim."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().rstrip("?!. ").strip()


def visitor_hash(ip: str, secret: str, day: date) -> str:
    """Conta visitantes do dia sem guardar o IP: o código muda a cada dia e não volta ao IP."""
    return hmac.new(secret.encode(), f"{ip}|{day.isoformat()}".encode(), hashlib.sha256).hexdigest()


def valid_event(tipo: str, valor: str) -> bool:
    if tipo == "voto":
        return valor in VOTOS
    if tipo == "abriu_pagina":
        return valor.isdigit() and 1 <= int(valor) <= MAX_PAGINA
    if tipo == "copiou":
        return valor == ""
    return False


@dataclass(frozen=True)
class QuestionRecord:
    id: UUID
    curso: str
    conversa: UUID | None
    turno: int
    pergunta: str
    resposta: str
    modelo: str
    status: Status
    erro: str | None
    duracao_ms: int
    primeiro_texto_ms: int | None
    tokens_saida: int | None
    tinha_suap: bool
    disciplinas: int
    visitante: str

    @property
    def pergunta_norm(self) -> str:
        return normalize_question(self.pergunta)
