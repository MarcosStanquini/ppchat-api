from functools import lru_cache
from pathlib import Path
from typing import List, Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[4]

Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # Se vazia, o SDK procura ANTHROPIC_API_KEY no ambiente ou um login do `ant auth login`
    anthropic_api_key: Optional[str] = None

    llm_model: str = "claude-opus-5-5"
    # A extração roda uma vez por PDF; vale usar um modelo mais forte que o do chat
    extraction_model: Optional[str] = None  # vazio = mesmo modelo do chat
    # Usado só se o modelo principal recusar a requisição (middleware de fallback do SDK)
    fallback_model: str = "claude-opus-4-8"

    # Esforço de raciocínio: chat pode ser "medium"; extração estruturada merece mais
    chat_effort: Effort = "medium"
    extraction_effort: Effort = "high"
    max_output_tokens: int = 64000

    # Proteção dos créditos da API quando o site é público (0 desliga)
    rate_limit_per_hour: int = 30  # perguntas por IP
    global_rate_limit_per_hour: int = 400  # teto para o site inteiro, vale mesmo se alguém forjar o IP

    # Origens do SUAP de onde o bookmarklet pode enviar os dados do aluno (CORS)
    suap_origins: List[str] = ["https://suap.ifsp.edu.br"]

    # Arquivos
    pdf_path: Path = ROOT_DIR / "src" / "data" / "documents" / "PPCENGSOFTWARE.pdf"
    processed_dir: Path = ROOT_DIR / "src" / "data" / "processed"


@lru_cache
def get_settings() -> Settings:
    return Settings()
