"""Catálogo de Pokémon (somente leitura), gerado por `app/scripts/update_pokedex.py` a partir dos dados do Showdown.

Fica num arquivo do repositório (app/data/pokedex.json), não no banco: é igual para todos e só muda quando os tiers do
Showdown mudam. O que é de cada torneio (lote, dono, preço, posições) referencia o `id` daqui.
"""
import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data" / "pokedex.json"
REGIONS = ["Kanto", "Johto", "Hoenn", "Sinnoh", "Unova", "Kalos", "Alola", "Galar", "Hisui", "Paldea"]
# Ordem dos tiers do mais forte para o mais fraco (para ordenar e filtrar); "(OU)" etc. ficam junto do tier.
TIER_ORDER = ["AG", "Uber", "OU", "(OU)", "UUBL", "UU", "RUBL", "RU", "NUBL", "NU", "PUBL", "PU", "ZUBL", "ZU", "NFE", "LC"]


@lru_cache(maxsize=1)
def all_pokemon() -> list[dict]:
    return json.loads(DATA.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def by_id() -> dict[str, dict]:
    return {p["id"]: p for p in all_pokemon()}


def get(pid: str) -> dict | None:
    return by_id().get(pid)


def search(q: str | None = None, region: str | None = None, tier9: str | None = None, tier7: str | None = None,
           base_only: bool = False) -> list[dict]:
    q = (q or "").strip().lower()
    out = []
    for p in all_pokemon():
        if q and q not in p["name"].lower() and q != str(p["num"]):
            continue
        if region and p["region"] != region:
            continue
        if tier9 and p["tier9"] != tier9:
            continue
        if tier7 and p["tier7"] != tier7:
            continue
        if base_only and p["forme"]:
            continue
        out.append(p)
    return out
