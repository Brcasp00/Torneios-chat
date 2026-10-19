"""Rotas por torneio: sorteio, início, confrontos, tabela e histórico."""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.tournaments import _counts, _get_or_404, _require_manage, can_manage  # noqa: F401
from app.core.deps import SessionDep, StaffUser
from app.models import AuditLog, Match, Stage, StandingsSnapshot, Tournament, TournamentPlayer, User
from app.schemas.match import (
    DrawIn,
    DrawMatch,
    DrawOut,
    DrawRound,
    MatchOut,
    PlayerRef,
    SnapshotDetail,
    SnapshotOut,
    StageStandings,
    StandingRow,
)
from app.services import results, schedule
from app.services.views import matches_out

router = APIRouter(prefix="/tournaments", tags=["play"])

SUPPORTED_TEMPLATES = ("league",)  # mata-mata, grupos e custom chegam nas próximas fases


def _check_supported(t: Tournament) -> None:
    if t.template not in SUPPORTED_TEMPLATES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"O formato '{t.template}' ainda não tem sorteio/partidas implementados.")


async def _active_players(session, t: Tournament) -> list[tuple[int, str]]:
    rows = await session.execute(
        select(User.id, User.name)
        .join(TournamentPlayer, TournamentPlayer.user_id == User.id)
        .where(TournamentPlayer.tournament_id == t.id, TournamentPlayer.status == "active")
        .order_by(User.id)
    )
    return [(uid, name) for uid, name in rows.all()]


def _plan(t: Tournament, stage: Stage, players: list[tuple[int, str]], seed: int):
    ids = schedule.shuffled([uid for uid, _ in players], seed)
    return schedule.round_robin(ids, bool((stage.config or {}).get("double_round")))


@router.post("/{tournament_id}/draw", response_model=DrawOut)
async def preview_draw(tournament_id: int, data: DrawIn, user: StaffUser, session: SessionDep):
    """Sorteador: mostra os confrontos que seriam gerados, sem salvar. Use a mesma `seed` em /start."""
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    _check_supported(t)
    if t.status not in ("draft", "registration"):
        raise HTTPException(status.HTTP_409_CONFLICT, "O sorteio já foi realizado.")
    players = await _active_players(session, t)
    if len(players) < 2:
        raise HTTPException(status.HTTP_409_CONFLICT, "São necessários ao menos 2 jogadores inscritos.")
    stage = await session.scalar(select(Stage).where(Stage.tournament_id == t.id, Stage.position == 1))
    seed = data.seed or schedule.new_seed()
    names = dict(players)
    rounds = [
        DrawRound(
            round=i,
            matches=[
                DrawMatch(player1=PlayerRef(id=a, name=names[a]), player2=PlayerRef(id=b, name=names[b]), leg=leg)
                for a, b, leg in rnd
            ],
        )
        for i, rnd in enumerate(_plan(t, stage, players, seed), start=1)
    ]
    return DrawOut(seed=seed, rounds=rounds)


@router.post("/{tournament_id}/start", response_model=list[MatchOut])
async def start_tournament(tournament_id: int, data: DrawIn, user: StaffUser, session: SessionDep):
    """Realiza o sorteio, gera os confrontos da primeira fase e coloca o torneio em andamento."""
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    _check_supported(t)
    if t.status not in ("draft", "registration"):
        raise HTTPException(status.HTTP_409_CONFLICT, "O torneio já foi iniciado.")
    players = await _active_players(session, t)
    if len(players) != t.max_players:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Para iniciar, o torneio precisa de exatamente {t.max_players} jogadores (há {len(players)}).",
        )
    stage = await session.scalar(select(Stage).where(Stage.tournament_id == t.id, Stage.position == 1))
    seed = data.seed or schedule.new_seed()
    best_of = (stage.config or {}).get("best_of", 1)

    created: list[Match] = []
    for rnd_no, rnd in enumerate(_plan(t, stage, players, seed), start=1):
        for slot, (a, b, leg) in enumerate(rnd, start=1):
            m = Match(
                tournament_id=t.id, stage_id=stage.id, round=rnd_no, slot=slot, leg=leg,
                player1_id=a, player2_id=b, best_of=best_of, status="scheduled",
            )
            session.add(m)
            created.append(m)
    t.status = "running"
    stage.status = "running"
    t.config = {**(t.config or {}), "draw_seed": seed}
    session.add(
        AuditLog(actor_id=user.id, action="tournament.start", entity="tournament", entity_id=t.id,
                 data={"seed": seed, "matches": len(created)})
    )
    await session.flush()
    await results.recalc(session, t, stage, "Início do torneio")
    await session.commit()
    return await matches_out(session, created)


@router.get("/{tournament_id}/matches", response_model=list[MatchOut])
async def list_matches(
    tournament_id: int,
    session: SessionDep,
    stage_id: int | None = None,
    round: int | None = None,
    player_id: int | None = None,
    status_: str | None = None,
):
    await _get_or_404(session, tournament_id)
    stmt = select(Match).where(Match.tournament_id == tournament_id).order_by(Match.stage_id, Match.round, Match.slot, Match.id)
    if stage_id:
        stmt = stmt.where(Match.stage_id == stage_id)
    if round:
        stmt = stmt.where(Match.round == round)
    if player_id:
        stmt = stmt.where((Match.player1_id == player_id) | (Match.player2_id == player_id))
    if status_:
        stmt = stmt.where(Match.status == status_)
    return await matches_out(session, (await session.scalars(stmt)).all())


@router.get("/{tournament_id}/standings", response_model=list[StageStandings])
async def standings_view(tournament_id: int, session: SessionDep):
    """Tabela de classificação de cada fase de pontos corridos."""
    t = await _get_or_404(session, tournament_id)
    stages = (
        await session.scalars(
            select(Stage).where(Stage.tournament_id == t.id, Stage.type.in_(("league", "groups"))).order_by(Stage.position)
        )
    ).all()
    out = []
    for s in stages:
        rows = await results.table_for_stage(session, t, s)
        out.append(
            StageStandings(
                stage_id=s.id, stage_name=s.name, stage_type=s.type,
                rows=[StandingRow(**r.as_dict()) for r in rows],
            )
        )
    return out


@router.get("/{tournament_id}/history", response_model=list[SnapshotOut])
async def history(tournament_id: int, session: SessionDep, stage_id: int | None = None, limit: int = 100):
    await _get_or_404(session, tournament_id)
    stmt = select(StandingsSnapshot).where(StandingsSnapshot.tournament_id == tournament_id)
    if stage_id:
        stmt = stmt.where(StandingsSnapshot.stage_id == stage_id)
    stmt = stmt.order_by(StandingsSnapshot.id.desc()).limit(min(limit, 500))
    return (await session.scalars(stmt)).all()


@router.get("/{tournament_id}/history/{snapshot_id}", response_model=SnapshotDetail)
async def history_detail(tournament_id: int, snapshot_id: int, session: SessionDep):
    snap = await session.get(StandingsSnapshot, snapshot_id)
    if not snap or snap.tournament_id != tournament_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro de histórico não encontrado.")
    return snap
