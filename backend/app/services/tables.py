"""Leitura de participantes e tabelas por fase (liga, grupos)."""
from sqlalchemy import select

from app.models import Match, Stage, Tournament, TournamentPlayer, User
from app.services import standings


async def stage_matches(session, stage: Stage, validated_only: bool = False) -> list[Match]:
    stmt = select(Match).where(Match.stage_id == stage.id).order_by(Match.round, Match.slot, Match.id)
    if validated_only:
        stmt = stmt.where(Match.status == "validated")
    return list((await session.scalars(stmt)).all())


async def player_info(session, t: Tournament) -> dict[int, tuple[str, bool]]:
    rows = await session.execute(
        select(TournamentPlayer.user_id, User.name, TournamentPlayer.status)
        .join(User, User.id == TournamentPlayer.user_id)
        .where(TournamentPlayer.tournament_id == t.id)
    )
    return {uid: (name, st == "withdrawn") for uid, name, st in rows.all()}


def participants(matches: list[Match]) -> dict[int, str | None]:
    """Jogadores que aparecem nos confrontos da fase -> grupo (ou None)."""
    out: dict[int, str | None] = {}
    for m in matches:
        for uid in (m.player1_id, m.player2_id):
            if uid is not None:
                out[uid] = m.group_label
    return out


def group_labels(matches: list[Match]) -> list[str]:
    return sorted({m.group_label for m in matches if m.group_label})


async def group_tables(session, t: Tournament, stage: Stage) -> dict[str, list[standings.Row]]:
    """Tabela de cada grupo (chave = rótulo do grupo)."""
    matches = await stage_matches(session, stage)
    info = await player_info(session, t)
    members = participants(matches)
    validated = [m for m in matches if m.status == "validated"]
    out: dict[str, list[standings.Row]] = {}
    for label in group_labels(matches):
        players = {uid: info[uid] for uid, g in members.items() if g == label and uid in info}
        out[label] = standings.compute(players, [m for m in validated if m.group_label == label], t.config or {})
    return out


async def table_for_stage(session, t: Tournament, stage: Stage) -> list[standings.Row]:
    """Tabela única (pontos corridos). Para fases de grupos, use `group_tables`."""
    matches = await stage_matches(session, stage)
    info = await player_info(session, t)
    players = {uid: info[uid] for uid in participants(matches) if uid in info}
    return standings.compute(players, [m for m in matches if m.status == "validated"], t.config or {})


def pair_saldo(m: Match, uid: int) -> int:
    if m.best_of != 1:
        return 0
    mine, theirs = (m.p1_remaining, m.p2_remaining) if uid == m.player1_id else (m.p2_remaining, m.p1_remaining)
    return (mine or 0) - (theirs or 0)
