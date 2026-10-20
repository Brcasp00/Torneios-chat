"""Rotas por torneio: sorteio, início, confrontos, tabelas, chaveamento e histórico."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.tournaments import _counts, _get_or_404, _players_out, _require_manage, can_manage  # noqa: F401
from app.core.deps import SessionDep, StaffUser
from app.models import AuditLog, Match, Stage, StandingsSnapshot, Tournament, TournamentPlayer, User
from app.schemas.match import (
    Arrangement,
    BracketRound,
    BracketStage,
    DeadlinesIn,
    DrawIn,
    DrawMatch,
    DrawOut,
    DrawRecord,
    DrawRound,
    GroupTable,
    MatchOut,
    PlayerRef,
    PotsIn,
    RoundHistory,
    RoundPostponeIn,
    SnapshotDetail,
    SnapshotOut,
    StageHistory,
    StageStandings,
    StandingRow,
)
from app.services import bracket, deadlines, results, schedule, tables
from app.services import stages as stage_service
from app.schemas.tournament import PlayerOut, StageOut
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


async def _pots(session, t: Tournament) -> dict[int, int]:
    rows = await session.execute(
        select(TournamentPlayer.user_id, TournamentPlayer.pot).where(
            TournamentPlayer.tournament_id == t.id, TournamentPlayer.pot.is_not(None)
        )
    )
    return {uid: pot for uid, pot in rows.all()}


def _plan_or_409(stage: Stage, ids: list[int], seed: int, data: DrawIn, pots: dict[int, int]) -> stage_service.Plan:
    arrangement = data.arrangement.model_dump(exclude_none=True) if data.arrangement else None
    try:
        return stage_service.plan_stage(
            stage, ids, seed, fed=False, pots=(pots if data.use_pots and not arrangement else None), arrangement=arrangement
        )
    except stage_service.StageError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.put("/{tournament_id}/pots", response_model=list[PlayerOut])
async def set_pots(tournament_id: int, data: PotsIn, user: StaffUser, session: SessionDep):
    """Define (ou remove) o pote de cada jogador antes do sorteio. Pote 1 = mais forte / cabeças de chave."""
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    if t.status not in ("draft", "registration"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Os potes só podem ser alterados antes do sorteio.")
    tps = {
        tp.user_id: tp
        for tp in (await session.scalars(select(TournamentPlayer).where(TournamentPlayer.tournament_id == t.id))).all()
    }
    missing = [a.user_id for a in data.assignments if a.user_id not in tps]
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Jogadores não inscritos neste torneio: {sorted(set(missing))}")
    for a in data.assignments:
        tps[a.user_id].pot = a.pot
    session.add(
        AuditLog(actor_id=user.id, action="tournament.set_pots", entity="tournament", entity_id=t.id,
                 data={str(a.user_id): a.pot for a in data.assignments})
    )
    await session.commit()
    return await _players_out(session, t.id)


@router.post("/{tournament_id}/draw", response_model=DrawOut)
async def preview_draw(tournament_id: int, data: DrawIn, user: StaffUser, session: SessionDep):
    """Sorteador: mostra os confrontos da primeira fase que seriam gerados, sem salvar.

    Aleatório por padrão; usa os potes definidos (`use_pots`); ou valida um arranjo manual (`arrangement`).
    O `arrangement` devolvido pode ser ajustado e reenviado em /start. Use a mesma `seed` em /start.
    """
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
    plan = _plan_or_409(stage, [uid for uid, _ in players], seed, data, await _pots(session, t))

    def dm(a, b, leg=1, label=None):
        return DrawMatch(player1=PlayerRef(id=a, name=names[a]), player2=PlayerRef(id=b, name=names[b]), leg=leg, group_label=label)

    arr = plan.arrangement()
    arrangement = Arrangement(**arr) if arr else None
    if plan.bracket_slots is not None:
        pairs = bracket.first_round_pairs(plan.bracket_slots)
        rounds = [DrawRound(round=1, matches=[dm(a, b) for a, b in pairs])]
    else:
        by_round: dict[int, list[DrawMatch]] = {}
        for sp in plan.specs:
            by_round.setdefault(sp.round, []).append(dm(sp.p1, sp.p2, sp.leg, sp.group_label))
        rounds = [DrawRound(round=r, matches=ms) for r, ms in sorted(by_round.items())]
    return DrawOut(seed=seed, mode=plan.mode, rounds=rounds, arrangement=arrangement)


@router.post("/{tournament_id}/start", response_model=list[MatchOut])
async def start_tournament(tournament_id: int, data: DrawIn, user: StaffUser, session: SessionDep):
    """Realiza o sorteio (aleatório, por potes ou manual), gera os confrontos da 1ª fase e inicia o torneio."""
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    if t.status not in ("draft", "registration"):
        raise HTTPException(status.HTTP_409_CONFLICT, "O torneio já foi iniciado.")
    if t.parent_id:
        parent = await session.get(Tournament, t.parent_id)
        if parent.status != "running":
            raise HTTPException(status.HTTP_409_CONFLICT, "O subtorneio só pode começar com o torneio principal em andamento.")
    players = await _active_players(session, t)
    if len(players) != t.max_players:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Para iniciar, o torneio precisa de exatamente {t.max_players} jogadores (há {len(players)}).",
        )
    stage = await _first_stage(session, t)
    seed = data.seed or schedule.new_seed()
    pots = await _pots(session, t)
    plan = _plan_or_409(stage, [uid for uid, _ in players], seed, data, pots)
    created = await stage_service.materialize(session, t.id, stage, plan)
    if plan.seeds or plan.bracket_slots is not None:
        seeds = plan.seeds or {uid: pos for pos, uid in enumerate(plan.bracket_slots, start=1)}
        for uid, sd in seeds.items():  # seed do jogador = posição na chave (ou ranking dos potes)
            tp = await session.scalar(
                select(TournamentPlayer).where(TournamentPlayer.tournament_id == t.id, TournamentPlayer.user_id == uid)
            )
            tp.seed = sd
    t.status = "running"
    stage.status = "running"
    record = {
        "seed": seed,
        "mode": plan.mode,
        "drawn_at": datetime.now(timezone.utc).isoformat(),
        "drawn_by": user.id,
        "pots": {str(uid): pot for uid, pot in pots.items()} if plan.mode == "pots" else {},
        "arrangement": plan.arrangement(),
    }
    t.config = {**(t.config or {}), "draw_seed": seed, "draw": record}
    session.add(
        AuditLog(actor_id=user.id, action="tournament.start", entity="tournament", entity_id=t.id,
                 data={"seed": seed, "mode": plan.mode, "matches": len(created)})
    )
    await session.flush()
    try:
        await results.recalc(session, t, stage, f"Início do torneio (sorteio: {plan.mode})")
    except results.CascadeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    await session.commit()
    return await matches_out(session, created)


@router.get("/{tournament_id}/draw", response_model=DrawRecord)
async def draw_record(tournament_id: int, session: SessionDep):
    """Registro público do sorteio realizado (seed, modo, potes e arranjo), para transparência."""
    t = await _get_or_404(session, tournament_id)
    rec = (t.config or {}).get("draw")
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "O sorteio ainda não foi realizado.")
    players = await _players_out(session, t.id)
    return DrawRecord(**rec, players=[PlayerRef(id=p.user_id, name=p.name) for p in players])


@router.get("/{tournament_id}/matches", response_model=list[MatchOut])
async def list_matches(
    tournament_id: int,
    session: SessionDep,
    stage_id: int | None = None,
    round: int | None = None,
    player_id: int | None = None,
    status_: str | None = None,
    postponed: bool | None = None,
):
    t = await _get_or_404(session, tournament_id)
    await deadlines.safe_sweep(session, t)
    stmt = select(Match).where(Match.tournament_id == tournament_id).order_by(Match.stage_id, Match.round, Match.slot, Match.id)
    if stage_id:
        stmt = stmt.where(Match.stage_id == stage_id)
    if round:
        stmt = stmt.where(Match.round == round)
    if player_id:
        stmt = stmt.where((Match.player1_id == player_id) | (Match.player2_id == player_id))
    if status_:
        stmt = stmt.where(Match.status == status_)
    if postponed is not None:
        stmt = stmt.where(Match.postponed.is_(postponed))
    return await matches_out(session, (await session.scalars(stmt)).all())


@router.get("/{tournament_id}/standings", response_model=list[StageStandings])
async def standings_view(tournament_id: int, session: SessionDep):
    """Tabelas de classificação: uma por fase de pontos corridos, ou uma por grupo nas fases de grupos."""
    t = await _get_or_404(session, tournament_id)
    await deadlines.safe_sweep(session, t)
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
async def history(
    tournament_id: int, session: SessionDep, stage_id: int | None = None, kind: str | None = None,
    limit: int = Query(100, ge=1),
):
    """Todos os registros do torneio (mais recentes primeiro). `kind`: change | round | final."""
    await _get_or_404(session, tournament_id)
    stmt = select(StandingsSnapshot).where(StandingsSnapshot.tournament_id == tournament_id)
    if stage_id:
        stmt = stmt.where(StandingsSnapshot.stage_id == stage_id)
    if kind:
        stmt = stmt.where(StandingsSnapshot.kind == kind)
    stmt = stmt.order_by(StandingsSnapshot.id.desc()).limit(min(limit, 500))
    return (await session.scalars(stmt)).all()


async def _family_ids(session, t: Tournament) -> list[int]:
    """O torneio e os seus subtorneios: o histórico do principal mostra também a repescagem."""
    kids = (await session.scalars(select(Tournament.id).where(Tournament.parent_id == t.id).order_by(Tournament.id))).all()
    return [t.id, *kids]


@router.get("/{tournament_id}/history/stages", response_model=list[StageHistory])
async def history_stages(tournament_id: int, session: SessionDep):
    """Estado final de cada fase já encerrada (fase de grupos, pontos corridos, mata-mata, repescagem...).

    Inclui as fases dos subtorneios. Se uma correção posterior alterou o resultado, vale a versão mais recente.
    """
    t = await _get_or_404(session, tournament_id)
    ids = await _family_ids(session, t)
    snaps = (
        await session.scalars(
            select(StandingsSnapshot)
            .where(StandingsSnapshot.tournament_id.in_(ids), StandingsSnapshot.kind == "final")
            .order_by(StandingsSnapshot.id)
        )
    ).all()
    latest: dict[int, StandingsSnapshot] = {}
    versions: dict[int, int] = {}
    for s in snaps:
        latest[s.stage_id] = s
        versions[s.stage_id] = versions.get(s.stage_id, 0) + 1
    rows = await session.execute(select(Tournament.id, Tournament.name).where(Tournament.id.in_(ids)))
    names = {tid: name for tid, name in rows.all()}
    stages = (await session.scalars(select(Stage).where(Stage.tournament_id.in_(ids)))).all()
    out = []
    for st in sorted(stages, key=lambda s: (ids.index(s.tournament_id), s.position)):
        snap = latest.get(st.id)
        if snap is None or st.status != "finished":
            continue
        out.append(
            StageHistory(
                snapshot_id=snap.id, tournament_id=st.tournament_id, tournament_name=names[st.tournament_id],
                stage_id=st.id, stage_name=st.name, stage_type=st.type, created_at=snap.created_at,
                versions=versions[st.id], data=snap.data,
            )
        )
    return out


@router.get("/{tournament_id}/history/rounds", response_model=list[RoundHistory])
async def history_rounds(tournament_id: int, session: SessionDep, stage_id: int | None = None):
    """Tabela ao fim de cada rodada de pontos corridos/grupos, da primeira em diante (uma por rodada)."""
    t = await _get_or_404(session, tournament_id)
    ids = await _family_ids(session, t)
    stmt = select(StandingsSnapshot).where(StandingsSnapshot.tournament_id.in_(ids), StandingsSnapshot.kind == "round")
    if stage_id:
        stmt = stmt.where(StandingsSnapshot.stage_id == stage_id)
    latest: dict[tuple[int, int], StandingsSnapshot] = {}
    for s in (await session.scalars(stmt.order_by(StandingsSnapshot.id))).all():
        latest[(s.stage_id, s.round)] = s  # se a rodada foi refeita depois de reaberta, vale a mais recente
    stage_by_id = {st.id: st for st in (await session.scalars(select(Stage).where(Stage.tournament_id.in_(ids)))).all()}

    def order(item):
        (sid, rnd), _ = item
        st = stage_by_id[sid]
        return (ids.index(st.tournament_id), st.position, rnd)

    out = []
    for (sid, rnd), s in sorted(latest.items(), key=order):
        d = s.data or {}
        out.append(
            RoundHistory(
                snapshot_id=s.id, tournament_id=s.tournament_id, stage_id=sid, stage_name=stage_by_id[sid].name, round=rnd,
                created_at=s.created_at, reopened=bool(d.get("reopened")), postponed=d.get("postponed", []),
                played_postponed=d.get("played_postponed", []), data=d,
            )
        )
    return out


@router.get("/{tournament_id}/history/{snapshot_id}", response_model=SnapshotDetail)
async def history_detail(tournament_id: int, snapshot_id: int, session: SessionDep):
    t = await _get_or_404(session, tournament_id)
    snap = await session.get(StandingsSnapshot, snapshot_id)
    if not snap or snap.tournament_id not in await _family_ids(session, t):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro de histórico não encontrado.")
    return snap


# ---------- adiamento de rodadas (pontos corridos / grupos) ----------
async def _round_action(session, tournament_id: int, data: RoundPostponeIn, user, postpone: bool) -> list:
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    stage = await session.get(Stage, data.stage_id)
    if not stage or stage.tournament_id != t.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fase não encontrada neste torneio.")
    try:
        results.check_postponable(t, stage)
    except results.ResultError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    ms = [
        m for m in await tables.stage_matches(session, stage)
        if m.round == data.round and (data.group_label is None or m.group_label == data.group_label)
    ]
    if not ms:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rodada não encontrada nesta fase.")
    changed = [m for m in ms if (results.postpone(m, user.id, data.reason) if postpone else results.resume(m))]
    if not postpone:
        for m in changed:
            deadlines.waive_if_overdue(stage, m)
    if not changed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Nenhum confronto pendente nesta rodada para adiar." if postpone else "Nenhum confronto adiado nesta rodada.",
        )
    where = f" (grupo {data.group_label})" if data.group_label else ""
    session.add(
        AuditLog(
            actor_id=user.id, action="round.postpone" if postpone else "round.resume", entity="tournament", entity_id=t.id,
            data={"stage_id": stage.id, "round": data.round, "group_label": data.group_label, "reason": data.reason,
                  "matches": [m.id for m in changed]},
        )
    )
    verb = "adiada" if postpone else "retomada"
    await results.recalc(session, t, stage, f"Rodada {data.round}{where} {verb}")
    await session.commit()
    return await matches_out(session, changed)


@router.post("/{tournament_id}/rounds/postpone", response_model=list[MatchOut])
async def postpone_round(tournament_id: int, data: RoundPostponeIn, user: StaffUser, session: SessionDep):
    """Adia os confrontos ainda pendentes de uma rodada (só admin ou organizador do torneio).

    Os jogos adiados continuam podendo ser reportados, mas a fase não encerra enquanto houver algum pendente.
    """
    return await _round_action(session, tournament_id, data, user, postpone=True)


@router.post("/{tournament_id}/rounds/resume", response_model=list[MatchOut])
async def resume_round(tournament_id: int, data: RoundPostponeIn, user: StaffUser, session: SessionDep):
    """Remove o adiamento dos confrontos de uma rodada que ainda não foram disputados."""
    return await _round_action(session, tournament_id, data, user, postpone=False)


@router.get("/{tournament_id}/bracket", response_model=list[BracketStage])
async def bracket_view(tournament_id: int, session: SessionDep):
    """Chaveamento de cada fase de mata-mata, por rodada (público)."""
    t = await _get_or_404(session, tournament_id)
    await deadlines.safe_sweep(session, t)
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


# ---------- prazo das rodadas ----------
@router.put("/{tournament_id}/stages/{stage_id}/deadlines", response_model=StageOut)
async def set_stage_deadlines(tournament_id: int, stage_id: int, data: DeadlinesIn, user: StaffUser, session: SessionDep):
    """Define (ou remove, com null) a data-limite de cada rodada de uma fase.

    Vencido o prazo, em liga/grupos (se o torneio permitir empate) os jogos sem resultado viram empate automático;
    nas demais fases o confronto só ganha o aviso de prazo vencido. Datas passadas só são aceitas se não mudarem.
    """
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    stage = await session.get(Stage, stage_id)
    if not stage or stage.tournament_id != t.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fase não encontrada neste torneio.")
    if t.status in ("finished", "cancelled"):
        raise HTTPException(status.HTTP_409_CONFLICT, "O torneio já foi encerrado.")
    current = deadlines.parse_deadlines(stage.config)
    at = deadlines.now()
    for rnd, when in data.deadlines.items():
        if not 1 <= rnd <= deadlines.MAX_ROUND:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Rodada inválida: {rnd}.")
        if when is not None:
            when = when if when.tzinfo else when.replace(tzinfo=timezone.utc)
            if when <= at and current.get(rnd) != when:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"O prazo da rodada {rnd} precisa estar no futuro (uma data já passada marcaria os jogos como empate na hora).",
                )
    deadlines.set_deadlines(stage, data.deadlines)
    session.add(
        AuditLog(
            actor_id=user.id, action="stage.set_deadlines", entity="tournament", entity_id=t.id,
            data={"stage_id": stage.id, "deadlines": {str(r): (w.isoformat() if w else None) for r, w in data.deadlines.items()}},
        )
    )
    await session.commit()
    return stage
