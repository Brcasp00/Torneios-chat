"""Consulta do log de auditoria (admin) e linha do tempo pública de um confronto."""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.deps import AdminUser, SessionDep
from app.models import AuditLog, Match, MatchReport, User
from app.schemas.audit import AuditOut, AuditPage, TimelineEvent

router = APIRouter(tags=["audit"])


async def _names(session, ids: set[int | None]) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.name for u in (await session.scalars(select(User).where(User.id.in_(ids)))).all()}


@router.get("/audit", response_model=AuditPage)
async def list_audit(
    _: AdminUser,
    session: SessionDep,
    actor_id: int | None = None,
    action: str | None = Query(None, description="Ação exata ou prefixo terminado em ponto, ex.: match."),
    entity: str | None = None,
    entity_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Log de auditoria (somente admin), mais recentes primeiro, com filtros e paginação."""
    conds = []
    if actor_id is not None:
        conds.append(AuditLog.actor_id == actor_id)
    if action:
        conds.append(AuditLog.action.startswith(action) if action.endswith(".") else AuditLog.action == action)
    if entity:
        conds.append(AuditLog.entity == entity)
    if entity_id is not None:
        conds.append(AuditLog.entity_id == entity_id)
    if since:
        conds.append(AuditLog.created_at >= since)
    if until:
        conds.append(AuditLog.created_at <= until)
    total = await session.scalar(select(func.count()).select_from(AuditLog).where(*conds))
    rows = (
        await session.scalars(select(AuditLog).where(*conds).order_by(AuditLog.id.desc()).limit(limit).offset(offset))
    ).all()
    names = await _names(session, {r.actor_id for r in rows})
    return AuditPage(
        total=total or 0,
        items=[
            AuditOut(
                id=r.id, created_at=r.created_at, actor_id=r.actor_id, actor_name=names.get(r.actor_id), action=r.action,
                entity=r.entity, entity_id=r.entity_id, data=r.data,
            )
            for r in rows
        ],
    )


@router.get("/matches/{match_id}/timeline", response_model=list[TimelineEvent])
async def match_timeline(match_id: int, session: SessionDep):
    """História do confronto: reportes, revisões do admin e ações (validar, corrigir, invalidar, W.O., adiar...)."""
    if not await session.get(Match, match_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Confronto não encontrado.")
    reports = (await session.scalars(select(MatchReport).where(MatchReport.match_id == match_id))).all()
    logs = (
        await session.scalars(select(AuditLog).where(AuditLog.entity == "match", AuditLog.entity_id == match_id))
    ).all()
    names = await _names(session, {r.reported_by for r in reports} | {r.reviewed_by for r in reports} | {a.actor_id for a in logs})
    events: list[TimelineEvent] = []
    for r in reports:
        events.append(
            TimelineEvent(
                at=r.created_at, kind="report", actor_id=r.reported_by, actor_name=names.get(r.reported_by), action="match.report",
                data={"report_id": r.id, "p1_wins": r.p1_wins, "p2_wins": r.p2_wins, "p1_remaining": r.p1_remaining,
                      "p2_remaining": r.p2_remaining, "replay_urls": r.replay_urls, "notes": r.notes},
            )
        )
        if r.reviewed_at:
            events.append(
                TimelineEvent(
                    at=r.reviewed_at, kind="review", actor_id=r.reviewed_by, actor_name=names.get(r.reviewed_by),
                    action=f"report.{r.status}", data={"report_id": r.id, "note": r.review_note},
                )
            )
    for a in logs:
        events.append(
            TimelineEvent(at=a.created_at, kind="action", actor_id=a.actor_id, actor_name=names.get(a.actor_id),
                          action=a.action, data=a.data)
        )
    return sorted(events, key=lambda e: e.at.replace(tzinfo=None))
