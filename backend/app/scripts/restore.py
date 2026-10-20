"""Devolve um backup (feito por app.scripts.backup) a um banco.

Uso (em D:\\Projetos\\backend):
    .\\.venv\\Scripts\\python -m app.scripts.restore ARQUIVO.json              # banco do .env (testes)
    .\\.venv\\Scripts\\python -m app.scripts.restore ARQUIVO.json --prod       # produção (pede a URL)
Opções:
    --simular     faz tudo e desfaz no final (confere se o backup é restaurável, sem mudar nada)
    --substituir  apaga os dados atuais antes (sem isso, o banco precisa estar vazio)

O banco precisa estar com as mesmas migrations do backup (rode `alembic upgrade head` antes num banco novo).
Tudo acontece numa única transação: se algo falhar no meio, nada muda.
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from app.scripts._alvo import confirmar, escolher_banco


class Simulacao(Exception):
    """Usada para desfazer a transação no modo --simular."""


def _converter(table, row: dict) -> dict:
    from sqlalchemy import DateTime

    out = {}
    for col in table.columns:
        if col.name not in row:
            continue
        v = row[col.name]
        if v is not None and isinstance(col.type, DateTime) and isinstance(v, str):
            v = datetime.fromisoformat(v)
        out[col.name] = v
    return out


async def load(conn, data: dict, replace: bool) -> dict[str, int]:
    """Insere o backup em `conn` (dentro da transação do chamador). Devolve linhas inseridas por tabela."""
    from sqlalchemy import func, select, text

    from app.db.base import Base
    import app.models  # noqa: F401

    tables = Base.metadata.sorted_tables
    if replace:
        for table in reversed(tables):
            await conn.execute(table.delete())
    else:
        cheias = [t.name for t in tables if (await conn.execute(select(func.count()).select_from(t))).scalar()]
        if cheias:
            raise SystemExit(f"O banco não está vazio ({', '.join(cheias)}). Use --substituir para apagar os dados atuais antes.")

    counts: dict[str, int] = {}
    for table in tables:
        rows = [_converter(table, r) for r in data["tables"].get(table.name, [])]
        counts[table.name] = len(rows)
        if not rows:
            continue
        # Colunas que apontam para a própria tabela (torneio pai, próximo confronto) entram vazias e são
        # preenchidas depois, para não depender da ordem das linhas.
        self_fks = [c.name for c in table.columns if any(fk.column.table is table for fk in c.foreign_keys)]
        later = []
        for r in rows:
            if any(r.get(c) is not None for c in self_fks):
                later.append(({k: r[k] for k in self_fks}, r["id"]))
                r = {**r, **{c: None for c in self_fks}}
            await conn.execute(table.insert().values(**r))
        for values, rid in later:
            await conn.execute(table.update().where(table.c.id == rid).values(**values))
    if conn.dialect.name == "postgresql":
        # As próximas inserções continuam a numeração depois dos IDs restaurados.
        for table in tables:
            if "id" in table.c:
                await conn.execute(text(
                    f"select setval(pg_get_serial_sequence('{table.name}', 'id'), coalesce((select max(id) from {table.name}), 0) + 1, false)"
                ))
    return counts


async def main(arquivo: Path, prod: bool, simular: bool, substituir: bool) -> None:
    data = json.loads(arquivo.read_text(encoding="utf-8"))
    if data.get("format") != 1:
        sys.exit("Arquivo não reconhecido como backup desta plataforma.")
    alvo = escolher_banco(prod)
    from sqlalchemy import text

    from app.db.session import engine

    async with engine.connect() as conn:
        version = (await conn.execute(text("select version_num from alembic_version"))).scalar()
    if version != data["alembic_version"]:
        sys.exit(
            f"O banco está na migration {version} e o backup é da {data['alembic_version']}. "
            "Deixe os dois na mesma versão (alembic upgrade) antes de restaurar."
        )
    total = sum(len(v) for v in data["tables"].values())
    print(f"Backup de {data['created_at']} com {total} linha(s) -> {alvo}")
    if not simular:
        aviso = "ATENÇÃO: os dados atuais serão APAGADOS e trocados pelos do backup." if substituir else "Os dados do backup serão inseridos."
        confirmar("RESTAURAR", aviso)
    try:
        async with engine.begin() as conn:
            counts = await load(conn, data, substituir)
            if simular:
                raise Simulacao
    except Simulacao:
        print("Simulação concluída: o backup é restaurável. Nada foi alterado.")
    else:
        print("Restauração concluída.")
    finally:
        await engine.dispose()
    for tabela, n in counts.items():
        print(f"  {tabela}: {n} linha(s)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Restaura um backup JSON.")
    p.add_argument("arquivo", type=Path)
    p.add_argument("--prod", action="store_true", help="usar o banco de produção (pede a URL)")
    p.add_argument("--simular", action="store_true", help="faz tudo e desfaz no final")
    p.add_argument("--substituir", action="store_true", help="apaga os dados atuais antes")
    a = p.parse_args()
    asyncio.run(main(a.arquivo, a.prod, a.simular, a.substituir))
