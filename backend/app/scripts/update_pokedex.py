"""Gera o catálogo de Pokémon (app/data/pokedex.json) a partir dos dados públicos do Pokémon Showdown.

Uso (em backend/):  .venv\\Scripts\\python -m app.scripts.update_pokedex
Opcional: --dir PASTA  (usa arquivos já baixados: pokedex.json, gen9-formats-data.ts, gen7-formats-data.ts)

Cada forma (regional, Mega, Rotom-Wash...) é um Pokémon separado. Tiers lado a lado: Geração 9 National Dex e
Geração 7. Ficam de fora: CAP/Pokestar (fan-made), formas só de batalha (Aegislash-Blade, Mimikyu-Busted...),
Gigantamax, formas Totem e Megas ainda não lançadas no Showdown. Rode de novo quando o Showdown atualizar os tiers e faça o deploy.
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

URLS = {
    "pokedex.json": "https://play.pokemonshowdown.com/data/pokedex.json",
    "gen9-formats-data.ts": "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/formats-data.ts",
    "gen7-formats-data.ts": "https://raw.githubusercontent.com/smogon/pokemon-showdown/master/data/mods/gen7/formats-data.ts",
}
OUT = Path(__file__).resolve().parents[1] / "data" / "pokedex.json"

# Região pelo número da Pokédex nacional; formas regionais contam na região da forma.
REGIONS = [(151, "Kanto"), (251, "Johto"), (386, "Hoenn"), (493, "Sinnoh"), (649, "Unova"), (721, "Kalos"),
           (809, "Alola"), (898, "Galar"), (905, "Hisui"), (1025, "Paldea")]
REGIONAL_FORMS = ["Alola", "Galar", "Hisui", "Paldea"]
SKIP_NONSTANDARD = {"CAP", "Custom", "Future", "LGPE"}


def region_of(num: int, forme: str | None) -> str:
    for r in REGIONAL_FORMS:
        if forme and forme.split("-")[0] == r:
            return r
    for top, name in REGIONS:
        if num <= top:
            return name
    return "Outra"


def parse_formats(ts: str) -> dict[str, dict[str, str]]:
    """Lê o objeto do formats-data (TypeScript) sem executar nada: chave -> {campo: valor}."""
    out: dict[str, dict[str, str]] = {}
    for key, body in re.findall(r"^\t(\w+): \{([^{}]*)\}", ts, flags=re.M):
        out[key] = dict(re.findall(r'(\w+): "([^"]*)"', body))
    return out


def load(folder: Path | None) -> dict[str, str]:
    texts = {}
    for name, url in URLS.items():
        if folder:
            texts[name] = (folder / name).read_text(encoding="utf-8")
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "torneios-pokedex-import"})
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 (URLs fixas do Showdown)
                texts[name] = r.read().decode("utf-8")
    return texts


def build(texts: dict[str, str]) -> list[dict]:
    dex = json.loads(texts["pokedex.json"])
    gen9 = parse_formats(texts["gen9-formats-data.ts"])
    gen7 = parse_formats(texts["gen7-formats-data.ts"])
    out = []
    for key, s in dex.items():
        num, forme = s.get("num", 0), s.get("forme")
        if num < 1 or s.get("isNonstandard") in SKIP_NONSTANDARD or s.get("battleOnly") or forme in ("Gmax", "Eternamax") or (forme or "").endswith("Totem"):
            continue
        f9 = gen9.get(key, {})
        t9 = f9.get("natDexTier") or f9.get("tier")
        t7 = gen7.get(key, {}).get("tier") if num <= 809 or (forme or "").startswith("Alola") else None
        if forme and forme.startswith(("Galar", "Hisui", "Paldea")):
            t7 = None  # formas criadas depois da Geração 7
        t9 = None if t9 == "Illegal" else t9
        t7 = None if t7 == "Illegal" else t7
        if not t9 and not t7:
            continue
        out.append({
            "id": key, "name": s["name"], "num": num, "base": s.get("baseSpecies") or s["name"], "forme": forme,
            "region": region_of(num, forme), "types": s.get("types", []), "tier9": t9, "tier7": t7,
        })
    out.sort(key=lambda p: (p["num"], p["forme"] is not None, p["name"]))
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", type=Path, help="pasta com os arquivos já baixados")
    args = ap.parse_args(argv)
    data = build(load(args.dir))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(data)} Pokémon gravados em {OUT}")


if __name__ == "__main__":
    sys.exit(main())
