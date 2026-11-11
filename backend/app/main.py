import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import archive, audit, auth, calculator, matches, play, players, tournaments, users
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services import archive as archive_service
from app.services import deadlines


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Torneios encerrados antes do acervo existir (ou sem entrada por algum motivo) entram no acervo agora.
    try:
        await archive_service.backfill(SessionLocal)
    except Exception:  # noqa: BLE001  (não impede a API de subir)
        logging.getLogger("archive").exception("Falha ao preencher o acervo")
    # Verifica os prazos das rodadas a cada minuto (a leitura do torneio também verifica, caso o servidor tenha dormido).
    task = asyncio.create_task(deadlines.run_forever(SessionLocal, every_seconds=60))
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Plataforma de Torneios Pokémon", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tournaments.router)
app.include_router(play.router)
app.include_router(matches.router)
app.include_router(audit.router)
app.include_router(archive.router)
app.include_router(archive.series_router)
app.include_router(players.router)
app.include_router(calculator.router)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}
