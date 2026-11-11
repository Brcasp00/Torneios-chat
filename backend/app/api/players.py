"""Perfil público do jogador: números, títulos, pódios e torneios disputados."""
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.api.archive import _base as archive_visible
from app.core.deps import SessionDep
from app.models import ArchiveEntry, ArchiveMatch, ArchivePlacement, Match, Tournament, TournamentPlayer, User
from app.services import standings

router = APIRouter(prefix="/players", tags=["players"])


class Stats(BaseModel):
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    saldo: int = 0  # Pokémon vivos (só em melhor de 1)


class Finish(BaseModel):
    """Colocação num torneio do acervo."""

    archive_id: int
    tournament_id: int | None
    name: str
    date: date | None
    position: int
    label: str | None


class Participation(BaseModel):
    """Torneio da área de torneios (ainda não encerrado) de que o jogador participa."""

    tournament_id: int
    name: str
    status: str
    player_status: str  # active | eliminated | withdrawn


class Profile(BaseModel):
    id: int
    name: str
    role: str
    member_since: datetime
    stats: Stats
    titles: list[Finish]  # 1º lugar
    podiums: list[Finish]  # 2º e 3º lugar
    archive: list[Finish]  # todos os torneios do acervo em que aparece (mais recentes primeiro)
    current: list[Participation]  # torneios em andamento/inscrições


@router.get("/{user_id}", response_model=Profile)
async def profile(user_id: int, session: SessionDep):
    u = await session.get(User, user_id)
    if not u or not u.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Jogador não encontrado.")

    # números: todos os confrontos validados (torneios e subtorneios da plataforma)
    st = Stats()
    ms = (await session.scalars(
        select(Match).where(Match.status == "validated", or_(Match.player1_id == u.id, Match.player2_id == u.id))
    )).all()
    cfgs = {}
    if ms:
        cfgs = dict((await session.execute(
            select(Tournament.id, Tournament.config).where(Tournament.id.in_({m.tournament_id for m in ms}))
        )).all())
    for m in ms:
        if not (m.player1_id and m.player2_id):
            continue
        st.played += 1
        st.saldo += standings._side_saldo(m, 1 if m.player1_id == u.id else 2, cfgs.get(m.tournament_id))
        if m.is_draw:
            st.draws += 1
        elif m.winner_id == u.id:
            st.wins += 1
        else:
            st.losses += 1

    # acervo: colocação final em cada torneio (da plataforma ou antigo) em que o jogador aparece
    entries = {e.id: e for e in (await session.scalars(
        archive_visible().where(or_(
            ArchiveEntry.id.in_(select(ArchivePlacement.entry_id).where(ArchivePlacement.user_id == u.id)),
            ArchiveEntry.id.in_(select(ArchiveMatch.entry_id).where(
                or_(ArchiveMatch.player1_user_id == u.id, ArchiveMatch.player2_user_id == u.id)
            )),
        ))
    )).all()}
    places = {p.entry_id: p for p in (await session.scalars(
        select(ArchivePlacement).where(ArchivePlacement.user_id == u.id, ArchivePlacement.entry_id.in_(list(entries)))
        .order_by(ArchivePlacement.position.desc())
    )).all()}  # se aparecer mais de uma vez, fica a melhor colocação
    archive: list[Finish] = []
    for e in entries.values():
        p = places.get(e.id)
        if p is None:
            continue  # só jogou partidas, sem colocação final cadastrada
        archive.append(Finish(archive_id=e.id, tournament_id=e.tournament_id, name=e.name,
                              date=e.end_date or e.start_date, position=p.position, label=p.label))
    archive.sort(key=lambda f: (f.date or date.min, f.archive_id), reverse=True)

    # torneios ainda não encerrados (área de torneios)
    rows = (await session.execute(
        select(Tournament, TournamentPlayer.status)
        .join(TournamentPlayer, TournamentPlayer.tournament_id == Tournament.id)
        .where(TournamentPlayer.user_id == u.id, Tournament.parent_id.is_(None),
               Tournament.status.in_(("draft", "registration", "running")))
        .order_by(Tournament.id.desc())
    )).all()
    current = [Participation(tournament_id=t.id, name=t.name, status=t.status, player_status=ps) for t, ps in rows]

    return Profile(
        id=u.id, name=u.name, role=u.role, member_since=u.created_at, stats=st,
        titles=[f for f in archive if f.position == 1],
        podiums=[f for f in archive if f.position in (2, 3)],
        archive=archive, current=current,
    )
