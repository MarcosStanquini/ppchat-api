import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.modules.knowledge.services.knowledge_base import get_knowledge_base
from src.modules.response.services.chat_service import ChatSession
from src.modules.shared.services.settings import get_settings

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_knowledge_base()  # falha cedo se a ingestão não foi feita
    yield


app = FastAPI(title="PPChat API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@dataclass
class SessionState:
    chat: ChatSession
    # Duas perguntas simultâneas na mesma sessão embaralhariam o histórico
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    task: Optional[asyncio.Task] = None  # resposta em andamento, para o /cancel


# Sessões em memória: suficiente para um processo único; troque por Redis/DB se escalar
sessions: Dict[str, SessionState] = {}


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class Usage(BaseModel):
    model: str
    input_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    output_tokens: int


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    usage: Optional[Usage] = None


async def _acquire_session(session_id: Optional[str]) -> tuple[str, SessionState]:
    if session_id is None:
        session_id = str(uuid.uuid4())
        sessions[session_id] = SessionState(chat=ChatSession())
    elif session_id not in sessions:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    state = sessions[session_id]
    if state.lock.locked():
        raise HTTPException(status_code=409, detail="Esta sessão ainda está respondendo")
    await state.lock.acquire()  # livre: retorna na hora, sem ceder o loop
    return session_id, state


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


async def _stream_answer(state: SessionState, question: str, http_request: Request) -> AsyncIterator[str]:
    """Emite NDJSON: {"type": "thinking"} com o resumo do raciocínio, {"type": "text"} com a
    resposta, e por fim {"type": "done"} com o uso de tokens ou {"type": "error"}.

    A resposta roda numa task separada: cancelá-la (botão "parar" ou cliente desconectado)
    fecha a conexão com a API na hora, mesmo enquanto o modelo ainda está pensando.
    """
    events: asyncio.Queue = asyncio.Queue()

    async def produce():
        try:
            async for kind, text in state.chat.stream_events(question):
                events.put_nowait({"type": kind, "text": text})
            usage = _usage(state.chat)
            events.put_nowait({"type": "done", "usage": usage.model_dump() if usage else None})
        except asyncio.CancelledError:
            pass  # a sessão já descartou a pergunta
        except Exception as error:
            events.put_nowait({"type": "error", "message": str(error)})
        finally:
            state.task = None
            state.lock.release()
            events.put_nowait(None)

    task = state.task = asyncio.create_task(produce())
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
        get_settings().pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=PPC.pdf"},
    )


@app.get("/health")
def health() -> dict:
    kb = get_knowledge_base()
    return {"status": "ok", "disciplinas": len(kb.curriculo.disciplinas)}


@app.get("/curriculum")
def curriculum() -> dict:
    """Currículo estruturado + análise do grafo, para o mapa curricular do front."""
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
async def chat(request: ChatRequest) -> ChatResponse:
    session_id, state = await _acquire_session(request.session_id)
    try:
        answer = await state.chat.ask(request.question)
    finally:
        state.lock.release()
    return ChatResponse(session_id=session_id, answer=answer, usage=_usage(state.chat))


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request) -> StreamingResponse:
    session_id, state = await _acquire_session(request.session_id)
    return StreamingResponse(
        _stream_answer(state, request.question, http_request),
        media_type="application/x-ndjson",
        headers={"X-Session-Id": session_id},
    )


@app.post("/chat/{session_id}/cancel", status_code=204)
async def chat_cancel(session_id: str) -> None:
    """Interrompe a resposta em andamento; a pergunta é descartada do histórico."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    task = sessions[session_id].task
    if task and not task.done():
        task.cancel()
