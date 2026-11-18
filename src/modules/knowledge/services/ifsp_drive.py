"""Sincroniza e indexa os documentos oficiais da secretaria/DDGA do Drive IFSP."""

import base64
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Dict, List
from urllib.parse import unquote
from urllib.request import Request, urlopen

import fitz

SHARE_TOKEN = "Telw2fiYl0dDG9n"
SHARE_URL = f"https://drive.ifsp.edu.br/s/{SHARE_TOKEN}"
WEBDAV_URL = "https://drive.ifsp.edu.br/public.php/webdav"
IFSP_DOCS_FILE = "ifsp_docs.json"


def _norm(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def _extract_xml_text(raw: bytes, entry_path: str) -> str:
    with zipfile.ZipFile(BytesIO(raw)) as z:
        if entry_path not in z.namelist():
            return ""
        root = ET.fromstring(z.read(entry_path))
        parts = [el.text.strip() for el in root.iter() if el.text and el.text.strip()]
        return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _extract_text(filename: str, raw: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        with fitz.open(stream=raw, filetype="pdf") as doc:
            return "\n\n".join(page.get_text("text").strip() for page in doc if page.get_text("text").strip())
    if ext == ".docx":
        return _extract_xml_text(raw, "word/document.xml")
    if ext == ".odt":
        return _extract_xml_text(raw, "content.xml")
    return ""


def sync_ifsp_drive(processed_dir: Path) -> List[Dict]:
    """Baixa e extrai os documentos públicos do link do Drive IFSP para `ifsp_docs.json`."""
    auth = base64.b64encode(f"{SHARE_TOKEN}:".encode()).decode()
    req = Request(
        f"{WEBDAV_URL}/",
        method="PROPFIND",
        headers={"Authorization": f"Basic {auth}", "Depth": "1", "User-Agent": "PPChat/1.0"},
    )
    with urlopen(req, timeout=20) as resp:
        xml = resp.read().decode("utf-8", errors="ignore")

    hrefs = re.findall(r"<d:href>(.*?)</d:href>", xml, re.I)
    docs: List[Dict] = []
    for href in hrefs:
        rel = href.split("/public.php/webdav/")[-1].strip("/")
        if not rel:
            continue
        name = unquote(rel)
        dl_url = f"https://drive.ifsp.edu.br/s/{SHARE_TOKEN}/download?path=%2F&files={rel}"
        text = ""
        try:
            f_req = Request(
                f"{WEBDAV_URL}/{rel}",
                headers={"Authorization": f"Basic {auth}", "User-Agent": "PPChat/1.0"},
            )
            with urlopen(f_req, timeout=20) as fr:
                raw = fr.read()
            text = _extract_text(name, raw)[:8000]
        except Exception:
            text = ""

        docs.append({
            "name": name,
            "url": dl_url,
            "share_url": SHARE_URL,
            "text": text,
        })

    processed_dir.mkdir(parents=True, exist_ok=True)
    (processed_dir / IFSP_DOCS_FILE).write_text(
        json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return docs


def load_ifsp_docs(processed_dir: Path) -> List[Dict]:
    path = processed_dir / IFSP_DOCS_FILE
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def search_ifsp_docs(docs: List[Dict], question: str, limit: int = 3) -> List[Dict]:
    """Retorna apenas os documentos relevantes para a pergunta (TokenOps)."""
    if not docs:
        return []
    q_norm = _norm(question)
    tokens = [t for t in re.findall(r"[a-z0-9]{3,}", q_norm) if t not in {"como", "para", "qual", "quais", "sobre", "fazer", "posso", "onde", "ifsp", "suap"}]
    if not tokens:
        return []

    scored = []
    for d in docs:
        hay_name = _norm(d.get("name", ""))
        hay_text = _norm(d.get("text", "")[:2500])
        score = sum(3 for t in tokens if t in hay_name) + sum(1 for t in tokens if t in hay_text)
        if score > 0:
            scored.append((score, d))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored[:limit]]
