from pathlib import Path
from typing import List

import fitz  # PyMuPDF

from src.modules.ingestion.models.curriculum import PageText


class PdfLoader:
    @staticmethod
    def load(pdf_path: Path) -> List[PageText]:
        with fitz.open(pdf_path) as document:
            return [
                PageText(page_number=index, text=page.get_text())
                for index, page in enumerate(document, start=1)
            ]
