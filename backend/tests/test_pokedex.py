"""Catálogo de Pokémon (dados do Showdown) e o gerador do arquivo."""
import json

from app.scripts import update_pokedex
from app.services import pokedex


def test_catalog_file_contents():
    data = pokedex.all_pokemon()
    assert len(data) > 1000 and len({p["id"] for p in data}) == len(data)
    names = {p["name"]: p for p in data}
    # formas são Pokémon separados; tiers da Gen 9 National Dex e da Gen 7 lado a lado
    assert names["Charizard-Mega-X"]["base"] == "Charizard" and names["Charizard-Mega-X"]["region"] == "Kanto"
    assert names["Raichu-Alola"]["region"] == "Alola" and names["Weezing-Galar"]["tier7"] is None
    assert names["Kingambit"]["region"] == "Paldea" and names["Kingambit"]["tier7"] is None and names["Kingambit"]["tier9"]
    assert names["Rotom-Wash"]["tier9"] and names["Rotom-Wash"]["tier7"]
    # de fora: fan-made, formas só de batalha, Gigantamax e Totem
    assert not {"Syclant", "Aegislash-Blade", "Mimikyu-Busted", "Charizard-Gmax", "Mimikyu-Totem"} & names.keys()
    assert set(p["region"] for p in data) == set(pokedex.REGIONS)


def test_region_and_parser():
    assert update_pokedex.region_of(151, None) == "Kanto" and update_pokedex.region_of(152, None) == "Johto"
    assert update_pokedex.region_of(26, "Alola") == "Alola" and update_pokedex.region_of(128, "Paldea-Combat") == "Paldea"
    assert update_pokedex.region_of(6, "Mega-X") == "Kanto" and update_pokedex.region_of(1025, None) == "Paldea"
    ts = 'export const FormatsData = {\n\tbulbasaur: {\n\t\ttier: "LC",\n\t},\n\tvenusaur: {\n\t\ttier: "ZU",\n\t\tnatDexTier: "RU",\n\t},\n};\n'
    assert update_pokedex.parse_formats(ts) == {"bulbasaur": {"tier": "LC"}, "venusaur": {"tier": "ZU", "natDexTier": "RU"}}
    dex = {"venusaur": {"num": 3, "name": "Venusaur", "types": ["Grass", "Poison"]},
           "syclant": {"num": -2, "name": "Syclant", "isNonstandard": "CAP"}}
    out = update_pokedex.build({"pokedex.json": json.dumps(dex), "gen9-formats-data.ts": ts, "gen7-formats-data.ts": ts})
    assert out == [{"id": "venusaur", "name": "Venusaur", "num": 3, "base": "Venusaur", "forme": None, "region": "Kanto",
                    "types": ["Grass", "Poison"], "tier9": "RU", "tier7": "ZU"}]


async def test_pokedex_api(client):
    meta = (await client.get("/pokedex/meta")).json()
    assert meta["total"] > 1000 and meta["regions"][0] == "Kanto" and "OU" in meta["tiers9"] and "ZU" in meta["tiers7"]
    r = (await client.get("/pokedex", params={"q": "charizard"})).json()
    assert [p["name"] for p in r][:3] == ["Charizard", "Charizard-Mega-X", "Charizard-Mega-Y"]
    alola = (await client.get("/pokedex", params={"region": "Alola", "base_only": True})).json()
    assert alola and all(p["region"] == "Alola" and p["forme"] is None for p in alola)
    assert (await client.get("/pokedex/kingambit")).json()["tier9"]
    assert (await client.get("/pokedex/naoexiste")).status_code == 404
