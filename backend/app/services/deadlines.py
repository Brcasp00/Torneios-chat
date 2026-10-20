"""Prazo das rodadas.

O admin/organizador define a data-limite de cada rodada (`stage.config["deadlines"] = {"1": "<ISO com fuso>"}`).
Vencido o prazo:
- liga e grupos, em torneio que permite empate: os jogos ainda `scheduled` (sem reporte, não adiados e não liberados)
  viram empate 0x0 automático (`auto_result`). Invalidar esse resultado "libera" o jogo (`deadline_waived`): os
  jogadores podem entregar atrasado e o prazo não age mais sobre ele;
- demais casos (mata-mata, rodada única, playoff, ou torneio sem empate): nada é decidido; o confronto só aparece
  com o aviso de prazo vencido (`overdue`) para o admin resolver (W.O., adiamento, resultado direto...).

A verificação roda de tempos em tempos (tarefa em segundo plano) e também na leitura do torneio, porque o servidor
gratuito dorme e a tarefa não roda enquanto isso.
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import AuditLog, Match, Stage, Tournament
from app.services import results

log = logging.getLogger("deadlines")
MAX_ROUND = 500


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_deadlines(config: dict | None) -> dict[int, datetime]:
    """{rodada: datetime com fuso} a partir do config da fase (valores inválidos são ignorados)."""
    out: dict[int, datetime] = {}
    for key, value in ((config or {}).get("deadlines") or {}).items():
        try:
            out[int(key)] = _aware(datetime.fromisoformat(str(value)))
        except (TypeError, ValueError):
            continue
    return out


def set_deadlines(stage: Stage, changes: dict[int, datetime | None]) -> None:
    """Aplica as mudanças (None remove o prazo da rodada)."""
    current = {str(r): d.isoformat() for r, d in parse_deadlines(stage.config).items()}
    for rnd, when in changes.items():
        if when is None:
            current.pop(str(rnd), None)
        else:
            current[str(rnd)] = _aware(when).astimezone(timezone.utc).isoformat()
    cfg = dict(stage.config or {})
    if current:
        cfg["deadlines"] = current
    else:
        cfg.pop("deadlines", None)
    stage.config = cfg


def is_overdue(m: Match, deadlines: dict[int, datetime], at: datetime | None = None) -> bool:
    d = deadlines.get(m.round)
    return bool(d and d <= (at or now()) and m.status == "scheduled" and not m.postponed and not m.deadline_waived)


def waive_if_overdue(stage: Stage, m: Match) -> None:
    """Jogo retomado depois do prazo: o admin quer que seja disputado, então o prazo não deve empatá-lo na hora."""
    d = parse_deadlines(stage.config).get(m.round)
    if d and d <= now():
        m.deadline_waived = True


async def sweep_tournament(session, t: Tournament) -> int:
    """Marca como empate os jogos vencidos de `t`. Retorna quantos foram marcados."""
    if t.status != "running":
        return 0
    stages = (
        await session.scalars(select(Stage).where(Stage.tournament_id == t.id, Stage.status == "running", Stage.type.in_(results.LEAGUE_LIKE)))
    ).all()
    total = 0
    at = now()
    for stage in stages:
        due = {r for r, d in parse_deadlines(stage.config).items() if d <= at}
        if not due or not results.allow_draw_for(t, stage):
            continue
        ms = (
            await session.scalars(
                select(Match)
                .where(Match.stage_id == stage.id, Match.status == "scheduled", Match.round.in_(due))
                .order_by(Match.round, Match.slot, Match.id)
                .with_for_update()
            )
        ).all()
        todo = [m for m in ms if m.player1_id and m.player2_id and not m.postponed and not m.deadline_waived]
        if not todo:
            continue
        for m in todo:
            results.set_result(m, 0, 0, 0, 0, is_draw=True)
            m.auto_result = True
            session.add(AuditLog(actor_id=None, action="match.auto_draw", entity="match", entity_id=m.id, data={"round": m.round}))
        rounds = ", ".join(str(r) for r in sorted({m.round for m in todo}))
        await results.recalc(session, t, stage, f"Prazo vencido (rodada {rounds}): {len(todo)} jogo(s) sem resultado marcados como empate")
        total += len(todo)
    if total:
        await session.commit()
    return total


async def safe_sweep(session, t: Tournament) -> None:
    """Versão para chamar na leitura: qualquer falha desfaz a tentativa e não atrapalha a resposta."""
    try:
        await sweep_tournament(session, t)
    except Exception:  # noqa: BLE001  (CascadeError, bloqueio de banco...: tenta de novo na próxima leitura)
        await session.rollback()
        log.exception("Falha ao aplicar prazos do torneio %s", t.id)


async def sweep_all(maker) -> int:
    """Percorre todos os torneios em andamento (tarefa em segundo plano)."""
    total = 0
    async with maker() as session:
        ids = (await session.scalars(select(Tournament.id).where(Tournament.status == "running"))).all()
    for tid in ids:
        async with maker() as session:
            t = await session.get(Tournament, tid)
            if t is None:
                continue
            try:
                total += await sweep_tournament(session, t)
            except Exception:  # noqa: BLE001
                await session.rollback()
                log.exception("Falha ao aplicar prazos do torneio %s", tid)
    return total


async def run_forever(maker, every_seconds: int = 60) -> None:
    while True:
        try:
            await sweep_all(maker)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Falha na verificação de prazos")
        await asyncio.sleep(every_seconds)
