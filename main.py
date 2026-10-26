import argparse
import asyncio
import sys

from src.modules.ingestion.services.ingestion_pipeline import IngestionPipeline


def ingest(force: bool) -> None:
    IngestionPipeline().run(force=force)


async def chat() -> None:
    from src.modules.response.services.chat_service import ChatSession

    session = ChatSession()
    print("PPChat — pergunte sobre o PPC de Engenharia de Software (Ctrl+C ou 'sair' para encerrar)\n")
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


async def ask(question: str) -> None:
    from src.modules.response.services.chat_service import ChatSession

    async for chunk in ChatSession().stream(question):
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

    ingest_parser = commands.add_parser("ingest", help="Processa o PDF e extrai o currículo estruturado")
    ingest_parser.add_argument("--force", action="store_true", help="Refaz mesmo se o PDF não mudou")
    commands.add_parser("chat", help="Chat interativo no terminal")
    ask_parser = commands.add_parser("ask", help="Faz uma única pergunta")
    ask_parser.add_argument("question")
    serve_parser = commands.add_parser("serve", help="Sobe a API HTTP (FastAPI)")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()
    if args.command == "ingest":
        ingest(args.force)
    elif args.command == "chat":
        try:
            asyncio.run(chat())
        except KeyboardInterrupt:
            pass
    elif args.command == "ask":
        asyncio.run(ask(args.question))
    elif args.command == "serve":
        serve(args.host, args.port)


if __name__ == "__main__":
    main()
