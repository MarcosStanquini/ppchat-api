import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from src.modules.api import admin
from src.modules.api.rate_limit import RateLimiter, client_ip
from src.modules.api.suap_import import ImportStore, SuapImport
from src.modules.knowledge.services.knowledge_base import (
    KnowledgeBase,
    get_knowledge_base,
)
from src.modules.observability import recorder
from src.modules.observability.records import valid_event
from src.modules.response.services.chat_service import ChatSession
from src.modules.response.services.providers import claude_provider
from src.modules.shared.services.courses import (
    LEGACY_COURSE,
    Course,
    get_course,
    get_registry,
)
from src.modules.shared.services.settings import get_settings

STATIC_DIR = Path(__file__).parent / "static"
MAX_HISTORY = 30  # mensagens anteriores reenviadas pelo navegador
MAX_TEXT = 20_000  # caracteres por mensagem do histórico


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Carrega a base de todos os cursos agora: um curso quebrado falha o deploy, não a visita de um aluno
    for course in get_registry().cursos:
        get_knowledge_base(course.slug)
    purge_task = await _open_store()
    yield
    if purge_task:
        purge_task.cancel()
    await recorder.get_store().close()


async def _open_store() -> asyncio.Task | None:
    """Abre o banco das perguntas, se configurado. Se o banco não responder, o site sobe sem gravar."""
    current = get_settings()
    if not current.database_url:
        return None
    if not current.log_secret:
        raise RuntimeError("LOG_SECRET é obrigatória quando DATABASE_URL está definida.")
    from src.modules.observability.postgres_store import PostgresStore

    try:
        store = await PostgresStore.open(current.database_url)
    except Exception as error:  # noqa: BLE001
        recorder.logger.warning("banco das perguntas indisponível, seguindo sem gravar: %s", type(error).__name__)
        return None
    recorder.set_store(store)

    async def purge_daily():
        while True:
            try:
                await store.purge(current.log_retention_days)
            except Exception as error:  # noqa: BLE001
                recorder.logger.warning("limpeza dos registros antigos falhou: %s", type(error).__name__)
            await asyncio.sleep(24 * 3600)

    return asyncio.create_task(purge_daily())


app = FastAPI(title="PPChat API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(admin.router)  # antes do link direto de curso (/{slug}), que é a última rota

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
event_limiter = RateLimiter(per_ip=120, global_limit=5000)
suap_imports = ImportStore()
# Respostas em andamento, para o botão "parar"; só vivem durante a requisição
running: Dict[str, asyncio.Task] = {}


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=MAX_TEXT)
    disciplinas: List[str] = Field(default_factory=list, max_length=12)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    # Slug do curso aberto no navegador; clientes antigos não mandam e caem em Engenharia de Software
    curso: str = Field(default=LEGACY_COURSE, max_length=64)
    # A API não guarda conversas: o navegador reenvia o histórico a cada pergunta
    history: List[HistoryTurn] = Field(default_factory=list, max_length=MAX_HISTORY)
    # Códigos das disciplinas selecionadas no chat; a ficha delas vai junto da pergunta
    disciplinas: List[str] = Field(default_factory=list, max_length=12)
    # Gerado pelo navegador para poder cancelar esta resposta em /chat/cancel/{request_id}
    request_id: Optional[str] = Field(default=None, max_length=64)
    # Resumo acadêmico do aluno (importado do SUAP e guardado só no navegador dele)
    perfil: Optional[str] = Field(default=None, max_length=30_000)
    # Id aleatório da conversa no navegador: liga as perguntas de uma conversa nos registros
    conversa: UUID | None = None

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


def _course(slug: str) -> Course:
    """Só slugs do registro chegam ao disco; qualquer outro é 404."""
    try:
        return get_course(slug)
    except KeyError:
        raise HTTPException(status_code=404, detail="Curso não encontrado.") from None


def _knowledge_base(slug: str) -> KnowledgeBase:
    return get_knowledge_base(_course(slug).slug)


def _session(request: ChatRequest) -> ChatSession:
    return ChatSession(_knowledge_base(request.curso), claude_provider(),
                       history=[turn.model_dump() for turn in request.history])


def _usage(session: ChatSession) -> Optional[Usage]:
    usage = session.provider.usage
    if usage is None:
        return None
    return Usage(
        model=usage.model,
        input_tokens=usage.input_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens or 0,
        cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
        output_tokens=usage.output_tokens,
    )


def _tracker(request: ChatRequest, http_request: Request) -> recorder.AnswerTracker:
    current = get_settings()
    return recorder.AnswerTracker(
        request_id=request.request_id, curso=request.curso, conversa=request.conversa,
        turno=len(request.history) // 2, pergunta=request.question, modelo=current.llm_model,
        tinha_suap=bool(request.perfil), disciplinas=len(request.disciplinas),
        ip=client_ip(http_request), secret=current.log_secret or "",
    )


async def _stream_answer(request: ChatRequest, http_request: Request) -> AsyncIterator[str]:
    """Emite NDJSON: {"type": "thinking"} com o resumo do raciocínio, {"type": "text"} com a
    resposta, e por fim {"type": "done"} com o uso de tokens ou {"type": "error"}.

    A resposta roda numa task separada: cancelá-la (botão "parar" ou cliente desconectado)
    fecha a conexão com a API na hora, mesmo enquanto o modelo ainda está pensando.
    """
    session = _session(request)
    tracker = _tracker(request, http_request)
    events: asyncio.Queue = asyncio.Queue()

    async def produce():
        # O tracker grava ao sair do bloco: parada e cliente desconectado também ficam registrados
        try:
            async with tracker.track(lambda: session.answered_by):
                async for kind, text in session.stream_events(request.question, request.disciplinas, request.perfil):
                    if kind == "text":
                        tracker.add_text(text)
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
def pdf(curso: str = LEGACY_COURSE) -> FileResponse:
    # inline para o navegador abrir no visualizador e respeitar #page=N
    return FileResponse(
        _course(curso).pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=PPC.pdf"},
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "cursos": len(get_registry().cursos)}


@app.get("/courses")
def courses() -> dict:
    """Cursos atendidos, com os números e as perguntas prontas da prévia na tela Explorar."""
    items = []
    for course in get_registry().cursos:
        c = get_knowledge_base(course.slug).curriculo
        items.append({
            **course.model_dump(exclude={"fonte"}),
            "duracao_semestres": c.duracao_semestres,
            "carga_horaria_total_curso": c.carga_horaria_total_curso,
            "disciplinas": len(c.disciplinas),
            "vigencia": c.vigencia,
        })
    return {"campus": get_registry().campus, "cursos": items}


@app.get("/curriculum")
def curriculum(curso: str = LEGACY_COURSE) -> dict:
    """Currículo estruturado + análise do grafo, para a árvore e a grade do front."""
    kb = _knowledge_base(curso)
    c, graph = kb.curriculo, kb.graph
    return {
        "slug": kb.course.slug,
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
    tracker = _tracker(request, http_request)
    parts = []
    async with tracker.track(lambda: session.answered_by):
        async for text in session.stream(request.question, request.disciplinas, request.perfil):
            parts.append(text)
            tracker.add_text(text)
    return ChatResponse(answer="".join(parts), usage=_usage(session))


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


class EventRequest(BaseModel):
    pergunta_id: UUID
    tipo: str = Field(max_length=20)
    valor: str = Field(default="", max_length=10)


@app.post("/eventos", status_code=204)
async def eventos(event: EventRequest, http_request: Request) -> Response:
    """Sinais de uma resposta: 👍/👎, cópia, página do PPC aberta."""
    if error := event_limiter.check(client_ip(http_request)):
        raise HTTPException(status_code=429, detail=error)
    if not valid_event(event.tipo, event.valor):
        raise HTTPException(status_code=400, detail="Evento inválido.")
    try:
        saved = await asyncio.wait_for(
            recorder.get_store().save_event(event.pergunta_id, event.tipo, event.valor), recorder.SAVE_TIMEOUT
        )
    except Exception:  # noqa: BLE001 - banco lento ou fora do ar: o sinal se perde, o site não
        raise HTTPException(status_code=503, detail="Não foi possível registrar agora.") from None
    if not saved:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada.")
    return Response(status_code=204)


@app.post("/aluno/importar")
async def aluno_importar(data: SuapImport, http_request: Request) -> dict:
    """Recebe os dados lidos pelo bookmarklet no SUAP e devolve um código de uso único."""
    if error := import_limiter.check(client_ip(http_request)):
        raise HTTPException(status_code=429, detail=error)
    return {"code": suap_imports.put(data)}


@app.get("/aluno/importar/{code}")
async def aluno_resgatar(code: str) -> SuapImport:
    """O PPChat troca o código pelos dados uma única vez (expira em 1 hora)."""
    data = suap_imports.take(code)
    if data is None:
        raise HTTPException(status_code=404, detail="Código expirado ou já usado. Rode o bookmarklet de novo no SUAP.")
    return data


# Por último: rotas fixas (/pdf, /health, /courses...) têm prioridade sobre o link direto de um curso
@app.get("/{slug}", include_in_schema=False)
def course_page(slug: str) -> HTMLResponse:
    _course(slug)
    return index()
