"""Catálogo público de Pokémon (tiers da Geração 9 National Dex e da Geração 7, lado a lado)."""
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.services import pokedex

router = APIRouter(prefix="/pokedex", tags=["pokedex"])


class PokemonOut(BaseModel):
    id: str
    name: str
    num: int
    base: str
    forme: str | None
    region: str
    types: list[str]
    tier9: str | None  # Geração 9 National Dex
    tier7: str | None  # Geração 7 (None = não existia na Geração 7)


class PokedexMeta(BaseModel):
    total: int
    regions: list[str]
    tiers9: list[str]
    tiers7: list[str]


def _tiers(field: str) -> list[str]:
    present = {p[field] for p in pokedex.all_pokemon() if p[field]}
    order = {t: i for i, t in enumerate(pokedex.TIER_ORDER)}
    return sorted(present, key=lambda t: (order.get(t, len(order)), t))


@router.get("/meta", response_model=PokedexMeta)
async def meta():
    return PokedexMeta(total=len(pokedex.all_pokemon()), regions=pokedex.REGIONS, tiers9=_tiers("tier9"), tiers7=_tiers("tier7"))


@router.get("", response_model=list[PokemonOut])
async def list_pokemon(
    q: str | None = Query(None, max_length=40), region: str | None = Query(None, max_length=20),
    tier9: str | None = Query(None, max_length=10), tier7: str | None = Query(None, max_length=10), base_only: bool = False,
):
    return pokedex.search(q, region, tier9, tier7, base_only)


@router.get("/{pid}", response_model=PokemonOut)
async def get_pokemon(pid: str):
    p = pokedex.get(pid)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pokémon não encontrado.")
    return p
