"""Registro dos cursos atendidos pelo PPChat (src/data/courses/courses.json)."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator

from src.modules.shared.services.settings import get_settings

# Antes do multi-curso o PPChat era só de Engenharia de Software: clientes antigos não mandam `curso`
LEGACY_COURSE = "engenharia-de-software"


class Course(BaseModel):
    slug: str
    nome: str
    sigla: str
    tipo: Literal["bacharelado", "tecnologia"]
    status: Literal["ativo", "em_extincao"]
    fonte: str
    nomes_suap: list[str]  # trechos normalizados do nome do curso como aparece no SUAP
    area: str  # slug de uma das `areas` do registro; agrupa os cursos na tela Explorar
    pergunta: str  # pergunta pronta do card na tela Explorar (o PPC do curso responde)

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


class Area(BaseModel):
    slug: str
    nome: str


class CourseRegistry(BaseModel):
    campus: str
    areas: list[Area]
    cursos: list[Course]

    @model_validator(mode="after")
    def _known_areas(self) -> "CourseRegistry":
        known = {a.slug for a in self.areas}
        if len(known) != len(self.areas):
            raise ValueError("áreas com slug repetido no registro")
        unknown = sorted({c.area for c in self.cursos} - known)
        if unknown:
            raise ValueError(f"cursos com área fora do registro: {unknown}")
        return self

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
