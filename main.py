import argparse
import asyncio
import sys

from src.modules.ingestion.services.ingestion_pipeline import IngestionPipeline
from src.modules.shared.services.courses import LEGACY_COURSE, get_course, get_registry


def ingest(curso: str, force: bool, extract: bool) -> None:
    courses = get_registry().cursos if curso == "all" else [get_course(curso)]
    for course in courses:
        IngestionPipeline(course).run(force=force, extract=extract)


def _session(curso: str):
    from src.modules.knowledge.services.knowledge_base import get_knowledge_base
    from src.modules.response.services.chat_service import ChatSession

    return ChatSession(get_knowledge_base(curso))


async def chat(curso: str) -> None:
    session = _session(curso)
    print(f"PPChat — pergunte sobre o PPC de {get_course(curso).nome} (Ctrl+C ou 'sair' para encerrar)\n")
    while True:
        try:
            # input() roda numa thread para não travar o loop do asyncio
            question = (await asyncio.to_thread(input, "Você: ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in {"sair", "exit", "quit"}:
            break
        if not question:
            continue
        print("\nPPChat: ", end="", flush=True)
        async for chunk in session.stream(question):
            print(chunk, end="", flush=True)
        usage = session.last_message.usage if session.last_message else None
        if usage:
            print(
                f"\n\n  [tokens — cache lido: {usage.cache_read_input_tokens or 0:,} · "
                f"cache gravado: {usage.cache_creation_input_tokens or 0:,} · "
                f"entrada: {usage.input_tokens:,} · saída: {usage.output_tokens:,}]"
            )
        print()


async def ask(curso: str, question: str) -> None:
    async for chunk in _session(curso).stream(question):
        print(chunk, end="", flush=True)
    print()


def serve(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run("src.modules.api.app:app", host=host, port=port)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="PPChat — chat sobre o PPC do curso")
    commands = parser.add_subparsers(dest="command", required=True)

    slugs = [c.slug for c in get_registry().cursos]
    ingest_parser = commands.add_parser("ingest", help="Processa o PDF e extrai o currículo estruturado")
    ingest_parser.add_argument("--curso", choices=[*slugs, "all"], default="all")
    ingest_parser.add_argument("--force", action="store_true", help="Refaz mesmo se o PDF não mudou")
    ingest_parser.add_argument("--sem-extracao", action="store_true", help="Gera só o texto (ppc.md), sem chamar a API")
    chat_parser = commands.add_parser("chat", help="Chat interativo no terminal")
    chat_parser.add_argument("--curso", choices=slugs, default=LEGACY_COURSE)
    ask_parser = commands.add_parser("ask", help="Faz uma única pergunta")
    ask_parser.add_argument("--curso", choices=slugs, default=LEGACY_COURSE)
    ask_parser.add_argument("question")
    serve_parser = commands.add_parser("serve", help="Sobe a API HTTP (FastAPI)")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    if args.command == "ingest":
        ingest(args.curso, args.force, not args.sem_extracao)
    elif args.command == "chat":
        try:
            asyncio.run(chat(args.curso))
        except KeyboardInterrupt:
            pass
    elif args.command == "ask":
        asyncio.run(ask(args.curso, args.question))
    elif args.command == "serve":
        serve(args.host, args.port)


if __name__ == "__main__":
    main()
