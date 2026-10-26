import hashlib
import json
from pathlib import Path
from typing import List

from src.modules.ingestion.models.curriculum import Curriculo, PageText
from src.modules.ingestion.services.curriculum_extractor import CurriculumExtractor
from src.modules.ingestion.services.pdf_loader import PdfLoader
from src.modules.ingestion.services.text_cleaner import TextCleaner
from src.modules.shared.services.settings import get_settings

DOCUMENT_FILE = "ppc.md"
CURRICULUM_FILE = "curriculo.json"
MANIFEST_FILE = "manifest.json"


def build_document_text(pages: List[PageText], min_length: int = 20) -> str:
    """Junta as páginas limpas com marcadores [Página N] para o modelo poder citar a fonte."""
    parts = []
    for page in pages:
        text = TextCleaner.clean(page.text)
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
    def __init__(self):
        self.settings = get_settings()
        self.output_dir = self.settings.processed_dir

    def is_up_to_date(self) -> bool:
        manifest = self.output_dir / MANIFEST_FILE
        if not manifest.exists() or not (self.output_dir / CURRICULUM_FILE).exists():
            return False
        return json.loads(manifest.read_text("utf-8")).get("pdf_sha256") == _sha256(self.settings.pdf_path)

    def run(self, force: bool = False) -> None:
        if not force and self.is_up_to_date():
            print("Base já processada para este PDF (use --force para refazer).")
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)

        print("Extraindo texto do PDF...")
        pages = PdfLoader.load(self.settings.pdf_path)
        document_text = build_document_text(pages)
        (self.output_dir / DOCUMENT_FILE).write_text(document_text, "utf-8")
        print(f"{len(pages)} páginas, {len(document_text):,} caracteres.")

        print(f"Extraindo currículo estruturado com {self.settings.extraction_model or self.settings.llm_model}...")
        curriculo = CurriculumExtractor().extract(document_text)
        for warning in validate_curriculum(curriculo):
            print(f"  aviso: {warning}")

        (self.output_dir / CURRICULUM_FILE).write_text(
            curriculo.model_dump_json(indent=2), "utf-8"
        )
        (self.output_dir / MANIFEST_FILE).write_text(
            json.dumps({"pdf_sha256": _sha256(self.settings.pdf_path), "model": self.settings.extraction_model or self.settings.llm_model}, indent=2),
            "utf-8",
        )
        print(f"{len(curriculo.disciplinas)} disciplinas salvas em {self.output_dir}.")
