import re
import unicodedata
from collections import Counter

DOT_LEADERS = re.compile(r"\.{4,}")
SPACES = re.compile("[ \t\u00a0\u200b]+")  # espaço, tab, espaço rígido e de largura zero
BLANK_LINES = re.compile(r"\n{3,}")
PAGE_NUMBER = re.compile(r"^\d{1,3}$")

# Cabeçalho e rodapé ficam nas pontas da página; só essas linhas são candidatas a repetição
EDGE_LINES = 6
# Uma linha que se repete em pelo menos esta fração das páginas é cabeçalho/rodapé, não conteúdo
REPEAT_RATIO = 0.3


def _norm(line: str) -> str:
    return SPACES.sub(" ", unicodedata.normalize("NFKC", line)).strip()


def _lines(text: str) -> list[str]:
    """Linhas normalizadas; as vazias saem para não ocuparem as posições de cabeçalho e rodapé."""
    return [line for line in (_norm(raw) for raw in text.splitlines()) if line]


def _edges(lines: list[str]) -> list[str]:
    return lines[:EDGE_LINES] + lines[-EDGE_LINES:]


class TextCleaner:
    """Limpa o texto das páginas de qualquer PPC.

    Os PPCs de cada curso têm cabeçalhos diferentes, então em vez de um regex por curso a limpeza
    descobre as linhas que se repetem no topo ou no pé de muitas páginas e as remove. O número
    impresso da página só sai quando bate com o deslocamento que o documento usa (página do PDF
    menos número impresso); um número solto qualquer pode ser célula de tabela e fica.
    """

    def __init__(self, pages: list[tuple[int, str]]):
        counts: Counter = Counter()
        offsets: Counter = Counter()
        for page_number, text in pages:
            edges = _edges(_lines(text))
            counts.update(set(edges))
            offsets.update({page_number - int(line) for line in edges if PAGE_NUMBER.match(line)})
        threshold = max(3, int(len(pages) * REPEAT_RATIO))
        # Números soltos ficam de fora da repetição: quem decide se saem é o deslocamento da página
        self.repeated: set[str] = {
            line for line, n in counts.items() if n >= threshold and not PAGE_NUMBER.match(line)
        }
        offset, hits = offsets.most_common(1)[0] if offsets else (None, 0)
        self.page_offset: int | None = offset if hits >= threshold else None

    def _is_page_number(self, line: str, page_number: int) -> bool:
        return (
            self.page_offset is not None
            and PAGE_NUMBER.match(line) is not None
            and page_number - int(line) == self.page_offset
        )

    def clean(self, text: str, page_number: int) -> str:
        lines = _lines(text)
        edge = set(range(EDGE_LINES)) | set(range(max(0, len(lines) - EDGE_LINES), len(lines)))
        kept = [
            line for i, line in enumerate(lines)
            if not (i in edge and (line in self.repeated or self._is_page_number(line, page_number)))
        ]
        text = DOT_LEADERS.sub(" … ", "\n".join(kept))  # pontilhado do sumário
        # Mantém quebras de linha: são elas que preservam a leitura das tabelas
        return BLANK_LINES.sub("\n\n", text).strip()
