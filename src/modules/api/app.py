import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from src.modules.api.rate_limit import RateLimiter, client_ip
from src.modules.api.suap_import import ImportStore, SuapImport
from src.modules.knowledge.services.knowledge_base import get_knowledge_base
from src.modules.response.services.chat_service import ChatSession
from src.modules.shared.services.settings import get_settings

STATIC_DIR = Path(__file__).parent / "static"
MAX_HISTORY = 30  # mensagens anteriores reenviadas pelo navegador
MAX_TEXT = 20_000  # caracteres por mensagem do histórico


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_knowledge_base()  # falha cedo se a base processada não existir
    yield


app = FastAPI(title="PPChat API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

settings = get_settings()
# O bookmarklet roda dentro do SUAP e envia os dados do aluno para cá: só essa origem é liberada
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.suap_origins,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)
rate_limiter = RateLimiter(settings.rate_limit_per_hour, settings.global_rate_limit_per_hour)
import_limiter = RateLimiter(per_ip=20, global_limit=300)
suap_imports = ImportStore()
# Respostas em andamento, para o botão "parar"; só vivem durante a requisição
running: Dict[str, asyncio.Task] = {}


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=MAX_TEXT)
    disciplinas: List[str] = Field(default_factory=list, max_length=12)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    # A API não guarda conversas: o navegador reenvia o histórico a cada pergunta
    history: List[HistoryTurn] = Field(default_factory=list, max_length=MAX_HISTORY)
    # Códigos das disciplinas selecionadas no chat; a ficha delas vai junto da pergunta
    disciplinas: List[str] = Field(default_factory=list, max_length=12)
    # Gerado pelo navegador para poder cancelar esta resposta em /chat/cancel/{request_id}
    request_id: Optional[str] = Field(default=None, max_length=64)
    # Resumo acadêmico do aluno (importado do SUAP e guardado só no navegador dele)
    perfil: Optional[str] = Field(default=None, max_length=30_000)

    @field_validator("history")
    @classmethod
    def alternating(cls, history: List[HistoryTurn]) -> List[HistoryTurn]:
        roles = [turn.role for turn in history]
        expected = ["user", "assistant"] * (len(roles) // 2)
        if roles != expected:
            raise ValueError("o histórico deve alternar user/assistant, começando por user")
        return history


class Usage(BaseModel):
    model: str
    input_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    output_tokens: int


class ChatResponse(BaseModel):
    answer: str
    usage: Optional[Usage] = None


def _check_rate_limit(http_request: Request) -> None:
    if error := rate_limiter.check(client_ip(http_request)):
        raise HTTPException(status_code=429, detail=error)


def _session(request: ChatRequest) -> ChatSession:
    return ChatSession(history=[turn.model_dump() for turn in request.history])


def _usage(session: ChatSession) -> Optional[Usage]:
    message = session.last_message
    if message is None:
        return None
    return Usage(
        model=message.model,
        input_tokens=message.usage.input_tokens,
        cache_read_input_tokens=message.usage.cache_read_input_tokens or 0,
        cache_creation_input_tokens=message.usage.cache_creation_input_tokens or 0,
        output_tokens=message.usage.output_tokens,
    )


async def _stream_answer(request: ChatRequest, http_request: Request) -> AsyncIterator[str]:
    """Emite NDJSON: {"type": "thinking"} com o resumo do raciocínio, {"type": "text"} com a
    resposta, e por fim {"type": "done"} com o uso de tokens ou {"type": "error"}.

    A resposta roda numa task separada: cancelá-la (botão "parar" ou cliente desconectado)
    fecha a conexão com a API na hora, mesmo enquanto o modelo ainda está pensando.
    """
    session = _session(request)
    events: asyncio.Queue = asyncio.Queue()

    async def produce():
        try:
            async for kind, text in session.stream_events(request.question, request.disciplinas, request.perfil):
                events.put_nowait({"type": kind, "text": text})
            usage = _usage(session)
            events.put_nowait({"type": "done", "usage": usage.model_dump() if usage else None})
        except asyncio.CancelledError:
            pass
        except Exception as error:
            events.put_nowait({"type": "error", "message": str(error)})
        finally:
            events.put_nowait(None)

    task = asyncio.create_task(produce())
    if request.request_id:
        running[request.request_id] = task
    try:
        while True:
            try:
                event = await asyncio.wait_for(events.get(), timeout=0.5)
            except asyncio.TimeoutError:
                # O Starlette não cancela este gerador quando o cliente some; checa aqui
                if await http_request.is_disconnected():
                    break
                continue
            if event is None:
                break
            yield json.dumps(event, ensure_ascii=False) + "\n"
    finally:
        if not task.done():
            task.cancel()
        if request.request_id:
            running.pop(request.request_id, None)


@app.get("/", include_in_schema=False)
def index() -> HTMLResponse:
    # Versiona os assets pela data de modificação para o navegador não usar CSS/JS antigos do cache
    html = (STATIC_DIR / "index.html").read_text("utf-8")
    for asset in ("styles.css", "app.js"):
        version = int((STATIC_DIR / asset).stat().st_mtime)
        html = html.replace(f"/static/{asset}", f"/static/{asset}?v={version}")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/pdf", include_in_schema=False)
def pdf() -> FileResponse:
    # inline para o navegador abrir no visualizador e respeitar #page=N
    return FileResponse(
        settings.pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=PPC.pdf"},
    )


@app.get("/health")
def health() -> dict:
    kb = get_knowledge_base()
    return {"status": "ok", "disciplinas": len(kb.curriculo.disciplinas)}


@app.get("/curriculum")
def curriculum() -> dict:
    """Currículo estruturado + análise do grafo, para a árvore e a grade do front."""
    kb = get_knowledge_base()
    c, graph = kb.curriculo, kb.graph
    return {
        "curso": c.curso,
        "campus": c.campus,
        "vigencia": c.vigencia,
        "duracao_semestres": c.duracao_semestres,
        "carga_horaria_total_curso": c.carga_horaria_total_curso,
        "cadeia_critica": graph.critical_path,
        "gargalos": graph.bottlenecks(),
        "requisitos_gerais": [r.model_dump() for r in c.requisitos_gerais],
        "disciplinas": [
            {**d.model_dump(), **graph.analysis[d.codigo].model_dump(exclude={"codigo"})}
            for d in sorted(c.disciplinas, key=lambda d: (d.semestre or 99, d.nome))
        ],
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request) -> ChatResponse:
    _check_rate_limit(http_request)
    session = _session(request)
    answer = await session.ask(request.question, request.disciplinas, request.perfil)
    return ChatResponse(answer=answer, usage=_usage(session))


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request) -> StreamingResponse:
    _check_rate_limit(http_request)
    return StreamingResponse(
        _stream_answer(request, http_request),
        media_type="application/x-ndjson",
        # Desliga o buffer de proxies (nginx e afins) para o streaming chegar em tempo real
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/chat/cancel/{request_id}", status_code=204)
async def chat_cancel(request_id: str) -> None:
    """Interrompe a resposta em andamento (abortar o fetch nem sempre derruba a conexão)."""
    if task := running.get(request_id):
        task.cancel()


@app.post("/aluno/importar")
async def aluno_importar(data: SuapImport, http_request: Request) -> dict:
    """Recebe os dados lidos pelo bookmarklet no SUAP e devolve um código de uso único."""
    if error := import_limiter.check(client_ip(http_request)):
        raise HTTPException(status_code=429, detail=error)
    return {"code": suap_imports.put(data)}


@app.get("/aluno/importar/{code}")
async def aluno_resgatar(code: str) -> SuapImport:
    """O PPChat troca o código pelos dados uma única vez (expira em 10 minutos)."""
    data = suap_imports.take(code)
    if data is None:
        raise HTTPException(status_code=404, detail="Código expirado ou já usado. Rode o bookmarklet de novo no SUAP.")
    return data
