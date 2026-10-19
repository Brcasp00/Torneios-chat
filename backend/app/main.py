from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, matches, play, tournaments, users
from app.core.config import get_settings

app = FastAPI(title="Plataforma de Torneios Pokémon", version="0.1.0")

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


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}
