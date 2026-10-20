"""Backup completo do banco (todas as tabelas) num arquivo JSON, fora do repositório.

Uso (em D:\\Projetos\\backend):
    .\\.venv\\Scripts\\python -m app.scripts.backup           # banco do .env (testes)
    .\\.venv\\Scripts\\python -m app.scripts.backup --prod    # produção (a URL é pedida sem aparecer na tela)
    ... --pasta D:\\MeusBackups                               # onde salvar (padrão: <sua pasta de usuário>\\Backups-torneios)

Só LÊ o banco. O arquivo contém dados pessoais e as impressões (hashes) das senhas: guarde-o num lugar seguro e
nunca o coloque no repositório. Para devolver um backup a um banco vazio, use app.scripts.restore.
"""
import argparse
import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path

from app.scripts._alvo import escolher_banco

FORMAT = 1
REPO = Path(__file__).resolve().parents[3]


def _json_default(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    raise TypeError(f"Valor não suportado no backup: {type(v).__name__}")


async def dump(conn) -> dict:
    """Lê todas as tabelas do modelo (em ordem de dependência) e a versão das migrations."""
    from sqlalchemy import text

    from app.db.base import Base
    import app.models  # noqa: F401  (registra as tabelas)

    try:
        version = (await conn.execute(text("select version_num from alembic_version"))).scalar()
    except Exception:  # noqa: BLE001  (banco de teste sem alembic)
        version = None
    tables = {}
    for table in Base.metadata.sorted_tables:
        pk = list(table.primary_key.columns)
        rows = (await conn.execute(table.select().order_by(*pk))).mappings().all()
        tables[table.name] = [dict(r) for r in rows]
    return {"format": FORMAT, "alembic_version": version, "created_at": datetime.now().isoformat(timespec="seconds"), "tables": tables}


async def main(prod: bool, pasta: Path) -> None:
    alvo = escolher_banco(prod)
    pasta = pasta.expanduser().resolve()
    if pasta == REPO or REPO in pasta.parents:
        sys.exit(f"A pasta {pasta} fica dentro do repositório; o backup não pode ir para o Git. Escolha outra.")
    from app.db.session import engine

    print(f"Lendo {alvo}...")
    async with engine.connect() as conn:
        data = await dump(conn)
    await engine.dispose()
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f"torneios-{'producao' if prod else 'testes'}-{datetime.now():%Y%m%d-%H%M%S}.json"
    arquivo = pasta / nome
    arquivo.write_text(json.dumps(data, ensure_ascii=False, default=_json_default, indent=1), encoding="utf-8")
    print(f"Backup salvo em: {arquivo}")
    print(f"Versão das migrations: {data['alembic_version']}")
    for tabela, linhas in data["tables"].items():
        print(f"  {tabela}: {len(linhas)} linha(s)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Backup do banco em JSON.")
    p.add_argument("--prod", action="store_true", help="usar o banco de produção (pede a URL)")
    p.add_argument("--pasta", type=Path, default=Path.home() / "Backups-torneios", help="pasta de destino")
    a = p.parse_args()
    asyncio.run(main(a.prod, a.pasta))
