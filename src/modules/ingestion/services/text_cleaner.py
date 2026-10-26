import re
import unicodedata

# Cabeçalho repetido em todas as páginas do PPC (inclui o número impresso da página)
PAGE_HEADER = re.compile(
    r"^\s*Projeto Pedagógico do Curso Bacharelado em Engenharia de Software\s*\n"
    r"\s*Modalidade: presencial\s*\n"
    r"\s*\d+\s*\n"
    r"\s*IFSP SÃO CARLOS\s*\n"
    r"\s*BACHARELADO EM ENGENHARIA DE SOFTWARE\s*\n",
)
DOT_LEADERS = re.compile(r"\.{4,}")
SPACES = re.compile(r"[ \t ]+")
BLANK_LINES = re.compile(r"\n{3,}")


class TextCleaner:
    @staticmethod
    def clean(text: str) -> str:
        # NFKC desfaz ligaduras mantendo acentos compostos (NFKD os separava e gastava tokens)
        text = unicodedata.normalize("NFKC", text)
        text = PAGE_HEADER.sub("", text)
        text = DOT_LEADERS.sub(" … ", text)  # pontilhado do sumário
        # Mantém quebras de linha: são elas que preservam a leitura das tabelas
        lines = (SPACES.sub(" ", line).strip() for line in text.splitlines())
        text = "\n".join(lines)
        return BLANK_LINES.sub("\n\n", text).strip()
