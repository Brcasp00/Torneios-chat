"""Rotas por torneio: sorteio, início, confrontos, tabelas, chaveamento e histórico."""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.tournaments import _counts, _get_or_404, _require_manage, can_manage  # noqa: F401
from app.core.deps import SessionDep, StaffUser
from app.models import AuditLog, Match, Stage, StandingsSnapshot, Tournament, TournamentPlayer, User
from app.schemas.match import (
    BracketRound,
    BracketStage,
    DrawIn,
    DrawMatch,
    DrawOut,
    DrawRound,
    GroupTable,
    MatchOut,
    PlayerRef,
    SnapshotDetail,
    SnapshotOut,
    StageStandings,
    StandingRow,
)
from app.services import bracket, results, schedule, tables
from app.services import stages as stage_service
from app.services.views import matches_out

router = APIRouter(prefix="/tournaments", tags=["play"])


async def _active_players(session, t: Tournament) -> list[tuple[int, str]]:
    rows = await session.execute(
        select(User.id, User.name)
        .join(TournamentPlayer, TournamentPlayer.user_id == User.id)
        .where(TournamentPlayer.tournament_id == t.id, TournamentPlayer.status == "active")
        .order_by(User.id)
    )
    return [(uid, name) for uid, name in rows.all()]


async def _first_stage(session, t: Tournament) -> Stage:
    stage = await session.scalar(select(Stage).where(Stage.tournament_id == t.id, Stage.position == 1))
    if not stage:
        raise HTTPException(status.HTTP_409_CONFLICT, "O torneio não tem fases configuradas.")
    return stage


def _plan_or_409(stage: Stage, ids: list[int], seed: int) -> stage_service.Plan:
    try:
        return stage_service.plan_stage(stage, ids, seed, fed=False)
    except stage_service.StageError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.post("/{tournament_id}/draw", response_model=DrawOut)
async def preview_draw(tournament_id: int, data: DrawIn, user: StaffUser, session: SessionDep):
    """Sorteador: mostra os confrontos da primeira fase que seriam gerados, sem salvar. Use a mesma `seed` em /start."""
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    if t.status not in ("draft", "registration"):
        raise HTTPException(status.HTTP_409_CONFLICT, "O sorteio já foi realizado.")
    players = await _active_players(session, t)
    if len(players) < 2:
        raise HTTPException(status.HTTP_409_CONFLICT, "São necessários ao menos 2 jogadores inscritos.")
    stage = await _first_stage(session, t)
    seed = data.seed or schedule.new_seed()
    names = dict(players)
    plan = _plan_or_409(stage, [uid for uid, _ in players], seed)

    def dm(a, b, leg=1, label=None):
        return DrawMatch(player1=PlayerRef(id=a, name=names[a]), player2=PlayerRef(id=b, name=names[b]), leg=leg, group_label=label)

    if plan.bracket_slots is not None:
        pairs = bracket.first_round_pairs(plan.bracket_slots)
        return DrawOut(seed=seed, rounds=[DrawRound(round=1, matches=[dm(a, b) for a, b in pairs])])
    by_round: dict[int, list[DrawMatch]] = {}
    for sp in plan.specs:
        by_round.setdefault(sp.round, []).append(dm(sp.p1, sp.p2, sp.leg, sp.group_label))
    return DrawOut(seed=seed, rounds=[DrawRound(round=r, matches=ms) for r, ms in sorted(by_round.items())])


@router.post("/{tournament_id}/start", response_model=list[MatchOut])
async def start_tournament(tournament_id: int, data: DrawIn, user: StaffUser, session: SessionDep):
    """Realiza o sorteio, gera os confrontos da primeira fase e coloca o torneio em andamento."""
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    if t.status not in ("draft", "registration"):
        raise HTTPException(status.HTTP_409_CONFLICT, "O torneio já foi iniciado.")
    players = await _active_players(session, t)
    if len(players) != t.max_players:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Para iniciar, o torneio precisa de exatamente {t.max_players} jogadores (há {len(players)}).",
        )
    stage = await _first_stage(session, t)
    seed = data.seed or schedule.new_seed()
    plan = _plan_or_409(stage, [uid for uid, _ in players], seed)
    created = await stage_service.materialize(session, t.id, stage, plan)
    if plan.bracket_slots is not None:
        for pos, uid in enumerate(plan.bracket_slots, start=1):  # posição no chaveamento vira o seed do jogador
            tp = await session.scalar(
                select(TournamentPlayer).where(TournamentPlayer.tournament_id == t.id, TournamentPlayer.user_id == uid)
            )
            tp.seed = pos
    t.status = "running"
    stage.status = "running"
    t.config = {**(t.config or {}), "draw_seed": seed}
    session.add(
        AuditLog(actor_id=user.id, action="tournament.start", entity="tournament", entity_id=t.id,
                 data={"seed": seed, "matches": len(created)})
    )
    await session.flush()
    try:
        await results.recalc(session, t, stage, "Início do torneio")
    except results.CascadeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
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
    """Tabelas de classificação: uma por fase de pontos corridos, ou uma por grupo nas fases de grupos."""
    t = await _get_or_404(session, tournament_id)
    stages = (
        await session.scalars(
            select(Stage).where(Stage.tournament_id == t.id, Stage.type.in_(("league", "groups"))).order_by(Stage.position)
        )
    ).all()
    out = []
    for s in stages:
        if s.type == "groups":
            gt = await tables.group_tables(session, t, s)
            groups = [GroupTable(label=lbl, rows=[StandingRow(**r.as_dict()) for r in rows]) for lbl, rows in gt.items()]
            out.append(StageStandings(stage_id=s.id, stage_name=s.name, stage_type=s.type, rows=[], groups=groups))
        else:
            rows = await tables.table_for_stage(session, t, s)
            out.append(
                StageStandings(stage_id=s.id, stage_name=s.name, stage_type=s.type, rows=[StandingRow(**r.as_dict()) for r in rows])
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


@router.get("/{tournament_id}/bracket", response_model=list[BracketStage])
async def bracket_view(tournament_id: int, session: SessionDep):
    """Chaveamento de cada fase de mata-mata, por rodada (público)."""
    await _get_or_404(session, tournament_id)
    stages = (
        await session.scalars(
            select(Stage).where(Stage.tournament_id == tournament_id, Stage.type == "knockout").order_by(Stage.position)
        )
    ).all()
    out = []
    for s in stages:
        ms = (await session.scalars(select(Match).where(Match.stage_id == s.id).order_by(Match.round, Match.slot))).all()
        views = {v.id: v for v in await matches_out(session, ms)}
        main = [m for m in ms if m.group_label != bracket.THIRD_PLACE]
        total = max((m.round for m in main), default=0)
        rounds = [
            BracketRound(
                round=r, name=bracket.round_name(r, total),
                matches=[views[m.id] for m in main if m.round == r],
            )
            for r in range(1, total + 1)
        ]
        third = next((views[m.id] for m in ms if m.group_label == bracket.THIRD_PLACE), None)
        final = next((m for m in main if m.round == total), None)
        champion = None
        if final and final.status == "validated" and final.winner_id:
            champion = views[final.id].player1 if final.winner_id == final.player1_id else views[final.id].player2
        out.append(BracketStage(stage_id=s.id, stage_name=s.name, status=s.status, rounds=rounds, third_place=third, champion=champion))
    return out
