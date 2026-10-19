"""Página do confronto: detalhes, reporte do jogador e validação/correção pelo admin."""
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.tournaments import can_manage
from app.core.deps import CurrentUser, OptionalUser, SessionDep, StaffUser
from app.models import AuditLog, Match, MatchReport, Stage, Tournament, TournamentPlayer, User
from app.schemas.match import (
    MatchDetail,
    NoteIn,
    ReportIn,
    ReportOut,
    ResultIn,
    ValidateIn,
    WalkoverIn,
)
from app.services import results
from app.services.views import matches_out

router = APIRouter(prefix="/matches", tags=["matches"])


async def _load(session, match_id: int, lock: bool = False) -> tuple[Match, Tournament, Stage]:
    stmt = select(Match).where(Match.id == match_id)
    if lock:
        stmt = stmt.with_for_update()  # evita validações simultâneas do mesmo confronto
    m = await session.scalar(stmt)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Confronto não encontrado.")
    return m, await session.get(Tournament, m.tournament_id), await session.get(Stage, m.stage_id)


def _staff_guard(user: User, t: Tournament) -> None:
    if not can_manage(user, t):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Você não pode gerenciar este torneio.")
    if t.status not in ("running", "finished"):
        raise HTTPException(status.HTTP_409_CONFLICT, "O torneio não está em andamento.")


def _bad(e: Exception) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


async def _after(session, t, stage, m, old, reason):
    """Avança o chaveamento, resolve W.O. pendentes e salva o histórico. Cascata bloqueada => 409 (nada é gravado)."""
    try:
        await results.after_change(session, t, stage, m, old, reason)
    except results.CascadeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


def _log(session, user, action, m, data=None):
    session.add(AuditLog(actor_id=user.id, action=action, entity="match", entity_id=m.id, data=data))


async def _detail(session, m: Match, t: Tournament, stage: Stage, user: User | None) -> MatchDetail:
    base = (await matches_out(session, [m]))[0]
    reports = (
        await session.scalars(select(MatchReport).where(MatchReport.match_id == m.id).order_by(MatchReport.id.desc()))
    ).all()
    is_player = bool(user and user.id in (m.player1_id, m.player2_id))
    still_in = False
    if is_player:
        still_in = (
            await session.scalar(
                select(TournamentPlayer.status).where(
                    TournamentPlayer.tournament_id == t.id, TournamentPlayer.user_id == user.id
                )
            )
            == "active"
        )
    return MatchDetail(
        **base.model_dump(),
        tournament_name=t.name,
        tournament_status=t.status,
        stage_name=stage.name,
        battle_rules=t.battle_rules,
        reports=[ReportOut.model_validate(r) for r in reports],
        can_report=bool(
            is_player and still_in and t.status == "running" and m.player1_id and m.player2_id
            and m.status in ("scheduled", "reported")
        ),
        can_manage=can_manage(user, t),
    )


@router.get("/{match_id}", response_model=MatchDetail)
async def get_match(match_id: int, session: SessionDep, user: OptionalUser):
    m, t, stage = await _load(session, match_id)
    return await _detail(session, m, t, stage, user)


@router.post("/{match_id}/report", response_model=MatchDetail)
async def report(match_id: int, data: ReportIn, user: CurrentUser, session: SessionDep):
    """Um dos jogadores do confronto reporta o resultado; o admin valida depois."""
    m, t, stage = await _load(session, match_id, lock=True)
    if user.id not in (m.player1_id, m.player2_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Somente os jogadores deste confronto podem reportar.")
    if t.status != "running":
        raise HTTPException(status.HTTP_409_CONFLICT, "O torneio não está em andamento.")
    if not (m.player1_id and m.player2_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Aguardando a definição do adversário.")
    if m.status not in ("scheduled", "reported"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Este confronto já foi validado; peça ao admin para corrigir.")
    me = await session.scalar(
        select(TournamentPlayer.status).where(TournamentPlayer.tournament_id == t.id, TournamentPlayer.user_id == user.id)
    )
    if me != "active":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Você não está mais ativo neste torneio.")
    try:
        urls = results.check_replays(data.replay_urls, m.best_of, t.battle_rules)
        results.check_result(
            m.best_of, data.p1_wins, data.p2_wins, data.p1_remaining, data.p2_remaining,
            is_draw=data.p1_wins == data.p2_wins, allow_draw=results.allow_draw_for(t, stage),
            team=results.max_team(t.battle_rules),
        )
    except results.ResultError as e:
        raise _bad(e)

    await results.reject_pending_reports(session, m.id, None, "Substituído por um reporte mais recente.")
    session.add(
        MatchReport(
            match_id=m.id, reported_by=user.id, p1_wins=data.p1_wins, p2_wins=data.p2_wins,
            p1_remaining=data.p1_remaining, p2_remaining=data.p2_remaining, replay_urls=urls, notes=data.notes,
        )
    )
    m.status = "reported"
    _log(session, user, "match.report", m)
    await session.commit()
    return await _detail(session, m, t, stage, user)


@router.post("/{match_id}/validate", response_model=MatchDetail)
async def validate(match_id: int, data: ValidateIn, user: StaffUser, session: SessionDep):
    m, t, stage = await _load(session, match_id, lock=True)
    _staff_guard(user, t)
    stmt = select(MatchReport).where(MatchReport.match_id == m.id)
    stmt = stmt.where(MatchReport.id == data.report_id) if data.report_id else stmt.where(MatchReport.status == "pending")
    rep = await session.scalar(stmt.order_by(MatchReport.id.desc()))
    if not rep:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Não há reporte para validar. Use /result para lançar direto.")
    if rep.match_id != m.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Reporte não pertence a este confronto.")
    p1w, p2w = rep.p1_wins, rep.p2_wins
    if data.is_draw:
        p1w = p2w = 0  # empate é sempre 0x0
    try:
        results.check_result(
            m.best_of, p1w, p2w, rep.p1_remaining, rep.p2_remaining,
            is_draw=data.is_draw or p1w == p2w, allow_draw=results.allow_draw_for(t, stage),
            team=results.max_team(t.battle_rules),
        )
    except results.ResultError as e:
        raise _bad(e)
    old = results.outcome(m)
    results.set_result(m, p1w, p2w, rep.p1_remaining, rep.p2_remaining, is_draw=data.is_draw or p1w == p2w)
    await results.reject_pending_reports(session, m.id, user.id, "Outro reporte foi validado.")
    rep.status, rep.reviewed_by, rep.reviewed_at, rep.review_note = "validated", user.id, results._now(), data.note
    _log(session, user, "match.validate", m, {"report_id": rep.id, "is_draw": m.is_draw})
    await _after(session, t, stage, m, old, f"Resultado validado (confronto #{m.id})")
    await session.commit()
    return await _detail(session, m, t, stage, user)


@router.post("/{match_id}/reject", response_model=MatchDetail)
async def reject(match_id: int, data: NoteIn, user: StaffUser, session: SessionDep):
    m, t, stage = await _load(session, match_id, lock=True)
    _staff_guard(user, t)
    if m.status != "reported":
        raise HTTPException(status.HTTP_409_CONFLICT, "Não há reporte pendente neste confronto.")
    await results.reject_pending_reports(session, m.id, user.id, data.note or "Rejeitado pelo admin.")
    m.status = "scheduled"
    _log(session, user, "match.reject", m, {"note": data.note})
    await session.commit()
    return await _detail(session, m, t, stage, user)


@router.post("/{match_id}/result", response_model=MatchDetail)
async def set_result(match_id: int, data: ResultIn, user: StaffUser, session: SessionDep):
    """Admin/organizador lança ou corrige o resultado direto (também serve para corrigir um já validado)."""
    m, t, stage = await _load(session, match_id, lock=True)
    _staff_guard(user, t)
    if not (m.player1_id and m.player2_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "O confronto ainda não tem os dois jogadores.")
    if m.status == "void":
        raise HTTPException(status.HTTP_409_CONFLICT, "Confronto anulado.")
    try:
        urls = results.check_replays(data.replay_urls, m.best_of, t.battle_rules)
        results.check_result(
            m.best_of, data.p1_wins, data.p2_wins, data.p1_remaining, data.p2_remaining,
            is_draw=data.is_draw, allow_draw=results.allow_draw_for(t, stage),
            team=results.max_team(t.battle_rules),
        )
    except results.ResultError as e:
        raise _bad(e)
    await results.reject_pending_reports(session, m.id, user.id, "Resultado lançado pelo admin.")
    old = results.outcome(m)
    results.set_result(m, data.p1_wins, data.p2_wins, data.p1_remaining, data.p2_remaining, data.is_draw)
    session.add(
        MatchReport(
            match_id=m.id, reported_by=user.id, p1_wins=data.p1_wins, p2_wins=data.p2_wins,
            p1_remaining=data.p1_remaining, p2_remaining=data.p2_remaining, replay_urls=urls, notes=data.notes,
            status="validated", reviewed_by=user.id, reviewed_at=results._now(), review_note="Lançado pelo admin.",
        )
    )
    _log(session, user, "match.set_result", m)
    await _after(session, t, stage, m, old, f"Resultado lançado/corrigido pelo admin (confronto #{m.id})")
    await session.commit()
    return await _detail(session, m, t, stage, user)


@router.post("/{match_id}/walkover", response_model=MatchDetail)
async def walkover(match_id: int, data: WalkoverIn, user: StaffUser, session: SessionDep):
    m, t, stage = await _load(session, match_id, lock=True)
    _staff_guard(user, t)
    if data.winner_id not in (m.player1_id, m.player2_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "O vencedor deve ser um dos jogadores do confronto.")
    if m.status == "void":
        raise HTTPException(status.HTTP_409_CONFLICT, "Confronto anulado.")
    await results.reject_pending_reports(session, m.id, user.id, "W.O. aplicado pelo admin.")
    old = results.outcome(m)
    results.set_walkover(m, data.winner_id, (t.config or {}).get("walkover_score", 3))
    _log(session, user, "match.walkover", m, {"winner_id": data.winner_id, "note": data.note})
    await _after(session, t, stage, m, old, f"W.O. no confronto #{m.id}")
    await session.commit()
    return await _detail(session, m, t, stage, user)


@router.post("/{match_id}/invalidate", response_model=MatchDetail)
async def invalidate(match_id: int, data: NoteIn, user: StaffUser, session: SessionDep):
    """Invalida um resultado já validado: o confronto volta a 'scheduled' e a tabela é recalculada."""
    m, t, stage = await _load(session, match_id, lock=True)
    _staff_guard(user, t)
    if m.status != "validated":
        raise HTTPException(status.HTTP_409_CONFLICT, "Só é possível invalidar um resultado já validado.")
    old_outcome = results.outcome(m)
    results.clear_result(m)
    old = await session.scalars(select(MatchReport).where(MatchReport.match_id == m.id, MatchReport.status == "validated"))
    for r in old:
        r.status, r.review_note = "rejected", f"Invalidado por {user.name}: {data.note or 'sem motivo informado'}"
    _log(session, user, "match.invalidate", m, {"note": data.note})
    await _after(session, t, stage, m, old_outcome, f"Resultado invalidado (confronto #{m.id})")
    await session.commit()
    return await _detail(session, m, t, stage, user)
