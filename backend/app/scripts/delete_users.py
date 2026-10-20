"""Apaga contas de vez (a interface só desativa). Pensado para limpar contas de teste.

Uso (em D:\\Projetos\\backend):
    .\\.venv\\Scripts\\python -m app.scripts.delete_users teste1 teste2            # nomes exatos (banco do .env)
    .\\.venv\\Scripts\\python -m app.scripts.delete_users --padrao "^teste([0-9]+|a)$" --prod
Opções:
    --padrao REGEX     escolhe os nomes por expressão regular (sem diferenciar maiúsculas)
    --com-torneios     apaga também os torneios de que essas contas participam (obrigatório se houver algum)
    --prod             usar o banco de produção (pede a URL)

Primeiro mostra o que será apagado e só segue se você digitar APAGAR. Admins nunca são apagados.
Faça um backup (app.scripts.backup) antes.
"""
import argparse
import asyncio
import re
import sys
from dataclasses import dataclass, field

from app.scripts._alvo import confirmar, escolher_banco


@dataclass
class Plano:
    users: list = field(default_factory=list)  # [(id, nome)]
    admins: list = field(default_factory=list)  # nomes de admins que casaram (nunca apagados)
    tournaments: list = field(default_factory=list)  # [(id, nome, status, total, de_fora)]


async def planejar(session, nomes: list[str], padrao: str | None) -> Plano:
    from sqlalchemy import func, or_, select

    from app.models import Match, Tournament, TournamentPlayer, User

    rx = re.compile(padrao, re.IGNORECASE) if padrao else None
    wanted = {n.lower() for n in nomes}
    plano = Plano()
    for u in (await session.scalars(select(User).order_by(User.id))).all():
        if u.name.lower() in wanted or (rx and rx.search(u.name)):
            (plano.admins.append(u.name) if u.role == "admin" else plano.users.append((u.id, u.name)))
    ids = [uid for uid, _ in plano.users]
    if not ids:
        return plano
    tids = set((await session.scalars(select(TournamentPlayer.tournament_id).where(TournamentPlayer.user_id.in_(ids)))).all())
    tids |= set((await session.scalars(select(Match.tournament_id).where(or_(Match.player1_id.in_(ids), Match.player2_id.in_(ids))))).all())
    # Subtorneio de um torneio afetado vai junto com o principal; o principal de um subtorneio afetado também é listado.
    for t in (await session.scalars(select(Tournament).where(Tournament.id.in_(tids)))).all():
        if t.parent_id:
            tids.add(t.parent_id)
    roots = (await session.scalars(select(Tournament).where(Tournament.id.in_(tids), Tournament.parent_id.is_(None)))).all()
    for t in roots:
        family = [t.id] + list((await session.scalars(select(Tournament.id).where(Tournament.parent_id == t.id))).all())
        members = set((await session.scalars(select(TournamentPlayer.user_id).where(TournamentPlayer.tournament_id.in_(family)))).all())
        total = (await session.scalar(select(func.count()).select_from(TournamentPlayer).where(TournamentPlayer.tournament_id == t.id))) or 0
        plano.tournaments.append((t.id, t.name, t.status, total, len(members - set(ids))))
    return plano


async def executar(session, plano: Plano) -> None:
    from sqlalchemy import delete

    from app.api.tournaments import delete_tree
    from app.models import AuditLog, Tournament, User

    for tid, nome, *_ in plano.tournaments:
        t = await session.get(Tournament, tid)
        if t:
            await delete_tree(session, t)
            session.add(AuditLog(actor_id=None, action="tournament.delete", entity="tournament", entity_id=tid, data={"name": nome, "via": "script"}))
    for uid, nome in plano.users:
        await session.execute(delete(User).where(User.id == uid))
        session.add(AuditLog(actor_id=None, action="user.delete", entity="user", entity_id=uid, data={"name": nome, "via": "script"}))
    await session.commit()


async def main(nomes: list[str], padrao: str | None, com_torneios: bool, prod: bool) -> None:
    if not nomes and not padrao:
        sys.exit("Informe os nomes ou --padrao.")
    alvo = escolher_banco(prod)
    from app.db.session import SessionLocal, engine

    try:
        async with SessionLocal() as session:
            plano = await planejar(session, nomes, padrao)
            print(f"Banco: {alvo}")
            if plano.admins:
                print(f"Admins nunca são apagados (ignorados): {', '.join(plano.admins)}")
            if not plano.users:
                sys.exit("Nenhuma conta encontrada. Nada foi feito.")
            print(f"\nContas que serão apagadas ({len(plano.users)}): {', '.join(n for _, n in plano.users)}")
            if plano.tournaments:
                print(f"\nTorneios com essas contas ({len(plano.tournaments)}):")
                for tid, nome, status, total, de_fora in plano.tournaments:
                    extra = f" — ATENÇÃO: {de_fora} participante(s) que NÃO estão na lista" if de_fora else ""
                    print(f"  #{tid} {nome} [{status}], {total} inscrito(s){extra}")
                if not com_torneios:
                    sys.exit("\nEssas contas participam de torneios. Rode de novo com --com-torneios para apagar os torneios também "
                             "(apagar só as contas deixaria confrontos sem jogador). Nada foi feito.")
            confirmar("APAGAR", "\nIsso não pode ser desfeito (só restaurando um backup).")
            await executar(session, plano)
            print(f"Pronto: {len(plano.users)} conta(s) e {len(plano.tournaments)} torneio(s) apagados.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Apaga contas de vez (ex.: contas de teste).")
    p.add_argument("nomes", nargs="*")
    p.add_argument("--padrao", help="expressão regular para os nomes")
    p.add_argument("--com-torneios", action="store_true", help="apaga também os torneios dessas contas")
    p.add_argument("--prod", action="store_true", help="usar o banco de produção (pede a URL)")
    a = p.parse_args()
    asyncio.run(main(a.nomes, a.padrao, a.com_torneios, a.prod))
