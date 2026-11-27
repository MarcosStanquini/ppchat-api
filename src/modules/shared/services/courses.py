"""Registro dos cursos atendidos pelo PPChat (src/data/courses/courses.json)."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.modules.shared.services.settings import get_settings

# Antes do multi-curso o PPChat era só de Engenharia de Software: clientes antigos não mandam `curso`
LEGACY_COURSE = "engenharia-de-software"


class Course(BaseModel):
    slug: str
    nome: str
    sigla: str
    nome_curto: str  # rótulo da aba na tela Explorar
    tipo: Literal["bacharelado", "tecnologia"]
    status: Literal["ativo", "em_extincao"]
    fonte: str
    nomes_suap: list[str]  # trechos normalizados do nome do curso como aparece no SUAP
    # Perguntas prontas da prévia do curso na tela Explorar (todas respondidas pelo PPC do curso)
    perguntas: list[str] = Field(min_length=1, max_length=4)

    @property
    def dir(self) -> Path:
        return get_settings().courses_dir / self.slug

    @property
    def pdf_path(self) -> Path:
        return self.dir / "ppc.pdf"

    @property
    def document_path(self) -> Path:
        return self.dir / "ppc.md"  # texto limpo com marcadores [Página N]

    @property
    def curriculum_path(self) -> Path:
        return self.dir / "curriculo.json"

    @property
    def manifest_path(self) -> Path:
        return self.dir / "manifest.json"  # hash do PDF processado

    @property
    def notes_path(self) -> Path:
        return self.dir / "notas.md"  # instruções específicas do curso para o prompt (opcional)


class CourseRegistry(BaseModel):
    campus: str
    cursos: list[Course]

    @property
    def by_slug(self) -> dict[str, Course]:
        return {c.slug: c for c in self.cursos}


@lru_cache
def get_registry() -> CourseRegistry:
    path = get_settings().courses_dir / "courses.json"
    return CourseRegistry.model_validate(json.loads(path.read_text("utf-8")))


def get_course(slug: str) -> Course:
    """Só slugs do registro chegam ao sistema de arquivos; o resto é KeyError."""
    return get_registry().by_slug[slug]
