"""Histórico estruturado: tabela de cada rodada (liga/grupos) e estado final de cada fase.

- `change`: um registro a cada alteração relevante (já existia; serve de trilha de auditoria).
- `round`: a tabela congelada quando uma rodada de pontos corridos/grupos fecha (todas as rodadas ficam consultáveis).
  Uma rodada fecha quando todos os seus confrontos estão validados/anulados ou adiados. Jogos adiados entram na tabela
  da rodada em que forem disputados; a tabela da rodada original não muda, só registra que houve adiamento.
- `final`: o estado final da fase (tabela, grupos ou chaveamento), gravado quando a fase termina e regravado se uma
  correção posterior o alterar.
"""
from sqlalchemy import select

from app.models import Match, StandingsSnapshot, Stage, Tournament, User
from app.services import engine, tables

ROUND_STAGES = ("league", "groups")  # fases com tabela de pontos e histórico por rodada


async def _names(session, matches: list[Match]) -> dict[int, str]:
    ids = {uid for m in matches for uid in (m.player1_id, m.player2_id) if uid}
    if not ids:
        return {}
    return {u.id: u.name for u in (await session.scalars(select(User).where(User.id.in_(ids)))).all()}


def _ref(uid: int | None, names: dict[int, str]):
    return {"id": uid, "name": names.get(uid, "?")} if uid else None


def _postponed_entry(m: Match, names: dict[int, str]) -> dict:
    return {
        "match_id": m.id, "round": m.round, "group_label": m.group_label,
        "player1": _ref(m.player1_id, names), "player2": _ref(m.player2_id, names), "reason": m.postponed_reason,
    }


async def snapshot_data(session, t: Tournament, stage: Stage) -> dict:
    """Conteúdo do registro: tabela (liga), tabelas por grupo (grupos) ou confrontos (demais fases)."""
    if stage.type == "league":
        return {"rows": [r.as_dict() for r in await tables.table_for_stage(session, t, stage)]}
    if stage.type == "groups":
        gt = await tables.group_tables(session, t, stage)
        return {"groups": {label: [r.as_dict() for r in rows] for label, rows in gt.items()}}
    ms = await tables.stage_matches(session, stage)
    names = await _names(session, ms)
    return {
        "players": {str(uid): name for uid, name in names.items()},
        "matches": [
            {
                "id": m.id, "round": m.round, "slot": m.slot, "group_label": m.group_label,
                "player1_id": m.player1_id, "player2_id": m.player2_id, "winner_id": m.winner_id,
                "status": m.status, "p1_wins": m.p1_wins, "p2_wins": m.p2_wins,
            }
            for m in ms
        ],
    }


def _closed(m: Match) -> bool:
    """Confronto que não impede o fechamento da rodada: decidido, anulado ou adiado (ainda sem jogo)."""
    return m.status in ("validated", "void") or (m.postponed and m.status == "scheduled")


async def _previous(session, stage: Stage) -> tuple[dict[int, StandingsSnapshot], set[int]]:
    """Último registro `round` de cada rodada e os jogos adiados que já constam de algum registro."""
    snaps = (
        await session.scalars(
            select(StandingsSnapshot)
            .where(StandingsSnapshot.stage_id == stage.id, StandingsSnapshot.kind.in_(("round", "final")))
            .order_by(StandingsSnapshot.id)
        )
    ).all()
    latest: dict[int, StandingsSnapshot] = {}
    seen: set[int] = set()
    for s in snaps:
        seen.update(p["match_id"] for p in (s.data or {}).get("played_postponed", []))
        if s.kind == "round":
            latest[s.round] = s
    return latest, seen


def _postponement_info(ms: list[Match], seen: set[int], names: dict[int, str]) -> dict:
    return {
        "postponed": [_postponed_entry(m, names) for m in ms if m.postponed and m.status != "validated"],
        "played_postponed": [
            {**_postponed_entry(m, names), "original_round": m.round}
            for m in ms
            if m.postponed and m.status == "validated" and m.id not in seen
        ],
    }


async def record_rounds(session, t: Tournament, stage: Stage) -> None:
    """Congela a tabela de cada rodada que acabou de fechar (e marca como reaberta a que deixou de estar fechada)."""
    if stage.type not in ROUND_STAGES:
        return
    ms = await tables.stage_matches(session, stage)
    if not ms:
        return
    latest, seen = await _previous(session, stage)
    names = await _names(session, ms)
    by_round: dict[int, list[Match]] = {}
    for m in ms:
        by_round.setdefault(m.round, []).append(m)
    for rnd in sorted(by_round):
        complete = all(_closed(m) for m in by_round[rnd])
        snap = latest.get(rnd)
        if complete and (snap is None or (snap.data or {}).get("reopened")):
            data = await snapshot_data(session, t, stage)
            data.update(_postponement_info(ms, seen, names))
            data["round"] = rnd
            data["rounds_total"] = len(by_round)
            session.add(
                StandingsSnapshot(
                    tournament_id=t.id, stage_id=stage.id, kind="round", round=rnd,
                    reason=f"Fim da rodada {rnd}", data=data,
                )
            )
            seen = seen | {p["match_id"] for p in data["played_postponed"]}
        elif not complete and snap is not None and not (snap.data or {}).get("reopened"):
            snap.data = {**snap.data, "reopened": True}  # a rodada voltou a ter jogo em aberto (resultado invalidado)


async def record_final(session, t: Tournament, stage: Stage) -> None:
    """Grava o estado final da fase; não repete se nada mudou desde o último registro final."""
    data = await snapshot_data(session, t, stage)
    if stage.type not in ROUND_STAGES:
        outputs = await engine.compute_outputs(session, t, stage)
        names = data.get("players", {})
        data["ranking"] = [
            {"position": i, "user_id": uid, "name": names.get(str(uid), "?")} for i, uid in enumerate(outputs["ranking"], start=1)
        ]
    ms = await tables.stage_matches(session, stage)
    last = await session.scalar(
        select(StandingsSnapshot)
        .where(StandingsSnapshot.stage_id == stage.id, StandingsSnapshot.kind == "final")
        .order_by(StandingsSnapshot.id.desc())
        .limit(1)
    )
    if last is not None and all(last.data.get(k) == v for k, v in data.items()):
        return
    _, seen = await _previous(session, stage)
    data.update(_postponement_info(ms, seen, await _names(session, ms)))
    session.add(
        StandingsSnapshot(
            tournament_id=t.id, stage_id=stage.id, kind="final", reason=f"Estado final: {stage.name}", data=data,
        )
    )


async def record(session, t: Tournament, stage: Stage) -> None:
    """Chamar depois de recalcular a fase: salva rodadas fechadas e, se a fase terminou, o estado final."""
    await record_rounds(session, t, stage)
    if stage.status == "finished":
        await record_final(session, t, stage)
