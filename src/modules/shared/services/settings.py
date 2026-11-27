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

    # Limite do modelo gratuito (0 desliga); o Claude (teste) e a chave do aluno têm limites próprios
    rate_limit_per_hour: int = 30  # perguntas por IP
    global_rate_limit_per_hour: int = 400  # teto para o site inteiro, vale mesmo se alguém forjar o IP

    # Multi-IA. Gratuito: chaves do dono no nível grátis, tentadas em ordem (cada modelo do Gemini tem cota própria)
    gemini_api_key: str | None = None
    gemini_models: list[str] = ["gemini-flash-latest", "gemini-3.5-flash-lite"]
    openrouter_api_key: str | None = None
    openrouter_model: str = "openrouter/free"  # roteador que escolhe um modelo grátis
    claude_teste_model: str | None = None  # vazio = llm_model
    # Modelos usados com a chave do aluno (precisam aceitar o PPC inteiro, ~140 mil tokens)
    openai_model: str = "gpt-6-luna"
    gemini_byok_model: str = "gemini-flash-latest"
    groq_model: str = "minimaxai/minimax-m2.7"  # os modelos estáveis do Groq param em 131 mil tokens

    # Origens do SUAP de onde o bookmarklet pode enviar os dados do aluno (CORS)
    suap_origins: List[str] = ["https://suap.ifsp.edu.br"]

    # Observabilidade: sem DATABASE_URL nada é gravado; sem ADMIN_TOKEN o /admin não existe
    database_url: str | None = None
    admin_token: str | None = None
    log_secret: str | None = None  # chave do código diário de visitante (obrigatória com DATABASE_URL)
    log_retention_days: int = 180
    # Chave de administração da Anthropic (sk-ant-admin...): só para ler os custos no /admin
    anthropic_admin_key: str | None = None

    # Uma pasta por curso (ppc.pdf, ppc.md, curriculo.json...) e o registro courses.json
    courses_dir: Path = ROOT_DIR / "src" / "data" / "courses"


@lru_cache
def get_settings() -> Settings:
    return Settings()
