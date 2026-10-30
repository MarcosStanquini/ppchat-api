"""Ponte entre o bookmarklet (rodando no SUAP) e o PPChat.

O SUAP usa Cross-Origin-Opener-Policy: same-origin, então a aba do SUAP não consegue
passar dados para uma janela do PPChat via postMessage. Em vez disso o bookmarklet envia
os dados para cá, recebe um código de uso único e abre o PPChat com `#suap=<código>`;
o front troca o código pelos dados uma única vez. Nada vai para disco: os dados ficam
na memória por no máximo 1 hora.
"""

import secrets
import time
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

TTL_SECONDS = 3600  # o plano grátis do Render dorme após 15 min sem uso e perde a memória de qualquer forma
MAX_PENDING = 500


class Tabela(BaseModel):
    titulo: str = Field(default="", max_length=300)
    linhas: List[List[str]] = Field(default_factory=list, max_length=400)


class Aba(BaseModel):
    titulo: str = Field(max_length=120)
    tabelas: List[Tabela] = Field(default_factory=list, max_length=40)


class SuapImport(BaseModel):
    versao: int = 1  # 2: colunas mescladas expandidas (permite ler notas pelo cabeçalho)
    matricula: str = Field(max_length=30)
    coletado_em: str = Field(max_length=40)
    abas: List[Aba] = Field(default_factory=list, max_length=12)


class ImportStore:
    def __init__(self):
        self._pending: Dict[str, Tuple[float, SuapImport]] = {}

    def _prune(self) -> None:
        now = time.monotonic()
        for code in [c for c, (expires, _) in self._pending.items() if expires < now]:
            del self._pending[code]

    def put(self, data: SuapImport) -> str:
        self._prune()
        if len(self._pending) >= MAX_PENDING:
            oldest = min(self._pending, key=lambda c: self._pending[c][0])
            del self._pending[oldest]
        code = secrets.token_urlsafe(24)
        self._pending[code] = (time.monotonic() + TTL_SECONDS, data)
        return code

    def take(self, code: str) -> Optional[SuapImport]:
        """Uso único: devolve e apaga."""
        self._prune()
        entry = self._pending.pop(code, None)
        return entry[1] if entry else None
