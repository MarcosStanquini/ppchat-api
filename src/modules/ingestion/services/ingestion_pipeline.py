import hashlib
import json
from pathlib import Path
from typing import List

from src.modules.ingestion.models.curriculum import Curriculo, PageText
from src.modules.ingestion.services.curriculum_extractor import CurriculumExtractor
from src.modules.ingestion.services.pdf_loader import PdfLoader
from src.modules.ingestion.services.text_cleaner import TextCleaner
from src.modules.shared.services.courses import Course
from src.modules.shared.services.settings import get_settings


def build_document_text(pages: List[PageText], min_length: int = 20) -> str:
    """Junta as páginas limpas com marcadores [Página N] para o modelo poder citar a fonte."""
    cleaner = TextCleaner([(page.page_number, page.text) for page in pages])
    parts = []
    for page in pages:
        text = cleaner.clean(page.text, page.page_number)
        if len(text) >= min_length:
            parts.append(f"[Página {page.page_number}]\n{text}")
    return "\n\n".join(parts)


def validate_curriculum(curriculo: Curriculo) -> List[str]:
    """Checagens de consistência baratas; problemas viram avisos, não erros."""
    warnings = []
    by_code = {d.codigo: d for d in curriculo.disciplinas}
    for disciplina in curriculo.disciplinas:
        unknown = [c for c in disciplina.pre_requisitos if c not in by_code]
        if unknown:
            warnings.append(f"{disciplina.codigo}: pré-requisitos desconhecidos removidos {unknown}")
            disciplina.pre_requisitos = [c for c in disciplina.pre_requisitos if c in by_code]
        for code in disciplina.pre_requisitos:
            required = by_code[code]
            if disciplina.semestre and required.semestre and required.semestre >= disciplina.semestre:
                warnings.append(
                    f"{disciplina.codigo} (sem {disciplina.semestre}) exige {code} (sem {required.semestre})"
                )
    return warnings


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IngestionPipeline:
    """Processa o PPC de um curso para a pasta dele (src/data/courses/<slug>/)."""

    def __init__(self, course: Course):
        self.settings = get_settings()
        self.course = course
        self.output_dir = course.dir

    def is_up_to_date(self) -> bool:
        manifest = self.course.manifest_path
        if not manifest.exists() or not self.course.curriculum_path.exists():
            return False
        return json.loads(manifest.read_text("utf-8")).get("pdf_sha256") == _sha256(self.course.pdf_path)

    def write_document(self) -> str:
        """Só o texto (PyMuPDF, local e sem custo de API)."""
        pages = PdfLoader.load(self.course.pdf_path)
        document_text = build_document_text(pages)
        self.course.document_path.write_text(document_text, "utf-8")
        print(f"[{self.course.slug}] {len(pages)} páginas, {len(document_text):,} caracteres.")
        return document_text

    def run(self, force: bool = False, extract: bool = True) -> None:
        if extract and not force and self.is_up_to_date():
            print(f"[{self.course.slug}] Base já processada para este PDF (use --force para refazer).")
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        document_text = self.write_document()
        if not extract:
            return

        model = self.settings.extraction_model or self.settings.llm_model
        print(f"[{self.course.slug}] Extraindo currículo estruturado com {model}...")
        curriculo = CurriculumExtractor().extract(document_text)
        save_curriculum(self.course, curriculo, model)


def save_curriculum(course: Course, curriculo: Curriculo, source: str) -> list[str]:
    """Valida, grava o currículo e o manifest; devolve os avisos de consistência."""
    warnings = validate_curriculum(curriculo)
    for warning in warnings:
        print(f"  aviso: {warning}")
    course.curriculum_path.write_text(curriculo.model_dump_json(indent=2), "utf-8")
    course.manifest_path.write_text(
        json.dumps({"pdf_sha256": _sha256(course.pdf_path), "extraido_por": source}, indent=2), "utf-8"
    )
    print(f"[{course.slug}] {len(curriculo.disciplinas)} disciplinas salvas em {course.dir}.")
    return warnings
