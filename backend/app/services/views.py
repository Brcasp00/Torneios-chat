from sqlalchemy import select

from app.models import Match, MatchReport, User
from app.schemas.match import MatchOut, PlayerRef


async def matches_out(session, matches: list[Match]) -> list[MatchOut]:
    ids = {uid for m in matches for uid in (m.player1_id, m.player2_id) if uid}
    names = {}
    if ids:
        names = {u.id: u.name for u in (await session.scalars(select(User).where(User.id.in_(ids)))).all()}
    pending = set()
    if matches:
        pending = set(
            (
                await session.scalars(
                    select(MatchReport.match_id).where(
                        MatchReport.match_id.in_([m.id for m in matches]), MatchReport.status == "pending"
                    )
                )
            ).all()
        )

    def ref(uid):
        return PlayerRef(id=uid, name=names.get(uid, "?")) if uid else None

    return [
        MatchOut(
            id=m.id,
            tournament_id=m.tournament_id,
            stage_id=m.stage_id,
            round=m.round,
            group_label=m.group_label,
            leg=m.leg,
            best_of=m.best_of,
            status=m.status,
            player1=ref(m.player1_id),
            player2=ref(m.player2_id),
            p1_wins=m.p1_wins,
            p2_wins=m.p2_wins,
            p1_remaining=m.p1_remaining,
            p2_remaining=m.p2_remaining,
            winner_id=m.winner_id,
            is_draw=m.is_draw,
            is_walkover=m.is_walkover,
            validated_at=m.validated_at,
            has_pending_report=m.id in pending,
        )
        for m in matches
    ]
