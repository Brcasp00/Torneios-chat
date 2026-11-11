"""Acervo: um torneio da plataforma entra no acervo quando encerra (e some da área de torneios).

A entrada guarda um resumo (nome, datas, formato, tier...) e a classificação final; o histórico completo (tabelas,
chave, confrontos, replays) continua no próprio torneio. Se o torneio reabrir (resultado invalidado), a entrada some do
acervo até ele encerrar de novo — e o que o admin editou nela (descrição, links, série) é mantido.
"""
from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select

from app.models import ArchiveEntry, ArchivePlacement, Stage, Tournament, TournamentPlayer, User
from app.services import bracket, engine, tables

TEMPLATE_LABEL = {"league": "Pontos corridos", "knockout": "Mata-mata", "groups_knockout": "Grupos + mata-mata"}


async def final_placements(session, t: Tournament) -> list[tuple[int, int, str | None]]:
    """Classificação final do torneio: [(posição, jogador, rótulo)].

    Começa pela última fase e volta: quem caiu numa fase anterior fica atrás de quem chegou mais longe. No mata-mata
    (e em rodada única/playoff) quem cai na mesma rodada divide a posição ("5º — Quartas de final").
    """
    stages = (await session.scalars(select(Stage).where(Stage.tournament_id == t.id).order_by(Stage.position.desc()))).all()
    placed: dict[int, tuple[int, str | None]] = {}
    nxt = 1

    def put(group: list[int], label: str | None, shared: bool):
        nonlocal nxt
        group = [u for u in group if u not in placed]
        for k, uid in enumerate(group):
            placed[uid] = (nxt if shared else nxt + k, label)
        nxt += len(group)

    for i, stage in enumerate(stages):
        if stage.status == "pending":
            continue
        out = await engine.compute_outputs(session, t, stage)
        matches = await tables.stage_matches(session, stage)
        last = i == 0
        if stage.type == "knockout":
            main = [m for m in matches if m.group_label != bracket.THIRD_PLACE]
            total = max((m.round for m in main), default=0)
            ranking = out["ranking"]
            has_third = any(m.group_label == bracket.THIRD_PLACE and m.winner_id for m in matches)
            if last and len(ranking) >= 2:
                put(ranking[:1], "Campeão", False)
                put(ranking[1:2], "Vice", False)
                if has_third:
                    put(ranking[2:3], "3º lugar", False)
                    put(ranking[3:4], "4º lugar", False)
            for rnd in range(total - 1, 0, -1):
                losers = [
                    m.player2_id if m.winner_id == m.player1_id else m.player1_id
                    for m in matches if m.round == rnd and m.group_label != bracket.THIRD_PLACE and m.winner_id
                ]
                put([u for u in ranking if u in losers], bracket.round_name(rnd, total) if last else stage.name, True)
            put(ranking, stage.name, True)  # quem sobrar (ex.: final ainda sem resultado)
        elif stage.type in ("round", "playoff"):
            if last:
                put(out["winners"], stage.name, False)
            put(out["losers"], stage.name, True)
        else:  # pontos corridos e grupos: a tabela define a ordem
            put(out["ranking"], None if last else stage.name, False)
        rest = [u for u in tables.participants(matches) if u not in placed]
        put(rest, stage.name, True)
    return sorted(((pos, uid, label) for uid, (pos, label) in placed.items()), key=lambda x: (x[0], x[1]))


def _format(t: Tournament, stages: list[Stage]) -> str:
    return TEMPLATE_LABEL.get(t.template) or " → ".join(s.name for s in stages) or "Personalizado"


async def sync_entry(session, t: Tournament) -> ArchiveEntry | None:
    """Cria (ou atualiza) a entrada do acervo de um torneio da plataforma que acabou de encerrar."""
    if t.parent_id is not None or t.status != "finished":
        return None  # subtorneios aparecem dentro do torneio principal
    stages = (await session.scalars(select(Stage).where(Stage.tournament_id == t.id).order_by(Stage.position))).all()
    entry = await session.scalar(select(ArchiveEntry).where(ArchiveEntry.tournament_id == t.id))
    players = await session.scalar(select(func.count()).select_from(TournamentPlayer).where(TournamentPlayer.tournament_id == t.id))
    today = datetime.now(timezone.utc).date()
    if entry is None:
        drawn = ((t.config or {}).get("draw") or {}).get("drawn_at")
        start = _date(drawn) or (t.created_at.date() if t.created_at else today)
        organizer = await session.scalar(select(User.name).where(User.id == t.created_by)) if t.created_by else None
        entry = ArchiveEntry(
            tournament_id=t.id, name=t.name, start_date=start, format=_format(t, stages),
            organizer=organizer, tier=(t.battle_rules or {}).get("tier"), rules_text=t.rules_text, created_by=t.created_by,
        )
        session.add(entry)
    entry.name = t.name
    entry.end_date = today
    entry.players_count = players
    await session.flush()
    await session.execute(delete(ArchivePlacement).where(ArchivePlacement.entry_id == entry.id))
    rows = await final_placements(session, t)
    names = {u.id: u.name for u in (await session.scalars(select(User).where(User.id.in_([uid for _, uid, _ in rows])))).all()}
    for pos, uid, label in rows:
        session.add(ArchivePlacement(entry_id=entry.id, position=pos, label=label, user_id=uid, name=names.get(uid, "?")))
    await session.flush()
    return entry


def _date(iso: str | None) -> date | None:
    try:
        return datetime.fromisoformat(iso).date() if iso else None
    except ValueError:
        return None
