"""Página /admin: o que estão perguntando e o que estão achando. Só com ADMIN_TOKEN configurado."""
import hmac
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from src.modules.api.rate_limit import RateLimiter, client_ip
from src.modules.observability import recorder
from src.modules.observability.store import AdminQueries
from src.modules.shared.services.courses import get_registry
from src.modules.shared.services.settings import get_settings

STATIC_DIR = Path(__file__).parent / "static"
router = APIRouter(include_in_schema=False)
# Senhas erradas por hora: 10 por IP e 50 no total (o IP pode ser forjado; o teto total não)
FAILED_LOGIN_LIMITS = (10, 50)
failed_logins = RateLimiter(*FAILED_LOGIN_LIMITS)

PERIODOS = {7, 30, 90}


def _dias(dias: int = 7) -> int:
    if dias not in PERIODOS:
        raise HTTPException(status_code=422, detail="Período deve ser 7, 30 ou 90 dias.")
    return dias


def _enabled() -> str:
    token = get_settings().admin_token
    if not token:
        raise HTTPException(status_code=404)
    return token


def require_admin(request: Request) -> None:
    token = _enabled()
    ip = client_ip(request)
    # Bloqueado continua bloqueado mesmo com a senha certa: senão o limite não impede adivinhar
    if failed_logins.blocked(ip):
        raise HTTPException(status_code=429, detail="Muitas tentativas. Tente de novo mais tarde.")
    scheme, _, given = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and hmac.compare_digest(given.encode(), token.encode()):
        return
    failed_logins.check(ip)  # registra a tentativa errada
    raise HTTPException(status_code=401, detail="Senha incorreta.")


def _store() -> AdminQueries:
    store = recorder.get_store()
    if not isinstance(store, AdminQueries):
        raise HTTPException(status_code=503, detail="Banco não configurado.")
    return store


def _curso(curso: str | None) -> str | None:
    if curso and curso not in {c.slug for c in get_registry().cursos}:
        raise HTTPException(status_code=400, detail="Curso não encontrado.")
    return curso or None


@router.get("/admin")
def admin_page() -> HTMLResponse:
    _enabled()
    html = (STATIC_DIR / "admin.html").read_text("utf-8")
    for asset in ("styles.css", "admin.css", "admin.js"):
        version = int((STATIC_DIR / asset).stat().st_mtime)
        html = html.replace(f"/static/{asset}", f"/static/{asset}?v={version}")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache", "X-Robots-Tag": "noindex"})


api = APIRouter(prefix="/admin/api", dependencies=[Depends(require_admin)], include_in_schema=False)


@api.get("/cursos")
def cursos() -> list:
    return [{"slug": c.slug, "nome": c.nome, "sigla": c.sigla} for c in get_registry().cursos]


@api.get("/resumo")
async def resumo(dias: int = Depends(_dias), curso: str | None = None) -> dict:
    return await _store().summary(dias, _curso(curso))


@api.get("/mais-feitas")
async def mais_feitas(dias: int = Depends(_dias), curso: str | None = None) -> list:
    return await _store().top_questions(dias, _curso(curso))


@api.get("/negativas")
async def negativas(dias: int = Depends(_dias), curso: str | None = None) -> list:
    return await _store().negatives(dias, _curso(curso))


@api.get("/perguntas")
async def perguntas(dias: int = Depends(_dias), curso: str | None = None, pagina: int = Query(1, ge=1, le=10_000),
                    busca: str | None = Query(None, max_length=200)) -> dict:
    return await _store().questions(dias, _curso(curso), busca or None, pagina)


router.include_router(api)
