"""Regras de resultado de confrontos: validação, aplicação, W.O., invalidação e recálculo da tabela."""
import re
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models import Match, MatchReport, Stage, StandingsSnapshot, Tournament, TournamentPlayer, User
from app.services import standings

REPLAY_RE = re.compile(r"^https://replay\.pokemonshowdown\.com/[A-Za-z0-9._\-/]+$")


class ResultError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def max_team(battle_rules: dict | None) -> int:
    br = battle_rules or {}
    return br.get("bring") or br.get("team_size") or 6


def check_replays(urls: list[str], best_of: int, battle_rules: dict | None) -> list[str]:
    urls = [u.strip() for u in urls if u and u.strip()]
    if (battle_rules or {}).get("showdown_required", True) and not urls:
        raise ResultError("Este torneio exige o link do replay do Showdown.")
    if len(urls) > best_of:
        raise ResultError(f"No máximo {best_of} link(s) de replay para uma série melhor de {best_of}.")
    for u in urls:
        if not REPLAY_RE.match(u):
            raise ResultError(f"Link de replay inválido: {u} (use https://replay.pokemonshowdown.com/...).")
    return urls


def check_result(best_of: int, p1_wins: int, p2_wins: int, p1_rem: int, p2_rem: int, is_draw: bool,
                 allow_draw: bool, team: int) -> None:
    need = best_of // 2 + 1
    if p1_rem > team or p2_rem > team:
        raise ResultError(f"Pokémon restantes não pode passar de {team}.")
    if is_draw:
        if not allow_draw:
            raise ResultError("Este torneio não permite empates.")
        if p1_wins != 0 or p2_wins != 0:
            raise ResultError("Empate só pode ser registrado com o placar 0x0.")
        return
    if p1_wins == p2_wins:
        raise ResultError("Placar igual só é aceito como empate (0x0).")
    winner_wins, loser_wins = max(p1_wins, p2_wins), min(p1_wins, p2_wins)
    if winner_wins != need or loser_wins >= need:
        raise ResultError(f"Em melhor de {best_of}, o vencedor precisa de exatamente {need} vitória(s).")
    if best_of == 1:
        w_rem, l_rem = (p1_rem, p2_rem) if p1_wins > p2_wins else (p2_rem, p1_rem)
        if l_rem != 0 or w_rem < 1:
            raise ResultError("Em melhor de 1, o vencedor deve ter ao menos 1 Pokémon vivo e o perdedor 0.")


def set_result(m: Match, p1_wins: int, p2_wins: int, p1_rem: int, p2_rem: int, is_draw: bool, walkover: bool = False) -> None:
    m.p1_wins, m.p2_wins, m.p1_remaining, m.p2_remaining = p1_wins, p2_wins, p1_rem, p2_rem
    m.is_draw = is_draw
    m.is_walkover = walkover
    m.winner_id = None if is_draw else (m.player1_id if p1_wins > p2_wins else m.player2_id)
    m.status = "validated"
    m.validated_at = _now()


def clear_result(m: Match) -> None:
    m.p1_wins = m.p2_wins = m.p1_remaining = m.p2_remaining = None
    m.winner_id = None
    m.is_draw = False
    m.is_walkover = False
    m.status = "scheduled"
    m.validated_at = None


def set_walkover(m: Match, winner_id: int, walkover_score: int) -> None:
    need = m.best_of // 2 + 1
    p1_wins = need if winner_id == m.player1_id else 0
    p2_wins = need if winner_id == m.player2_id else 0
    # W.O. vale 3 a 0 em Pokémon restantes (o saldo só conta em melhor de 1).
    p1_rem = walkover_score if winner_id == m.player1_id else 0
    p2_rem = walkover_score if winner_id == m.player2_id else 0
    set_result(m, p1_wins, p2_wins, p1_rem, p2_rem, is_draw=False, walkover=True)


async def reject_pending_reports(session, match_id: int, by: int | None, note: str) -> None:
    reports = await session.scalars(
        select(MatchReport).where(MatchReport.match_id == match_id, MatchReport.status == "pending")
    )
    for r in reports:
        r.status, r.reviewed_by, r.reviewed_at, r.review_note = "rejected", by, _now(), note


async def table_for_stage(session, t: Tournament, stage: Stage) -> list[standings.Row]:
    prows = await session.execute(
        select(TournamentPlayer.user_id, User.name, TournamentPlayer.status)
        .join(User, User.id == TournamentPlayer.user_id)
        .where(TournamentPlayer.tournament_id == t.id)
    )
    players = {uid: (name, st == "withdrawn") for uid, name, st in prows.all()}
    matches = (
        await session.scalars(select(Match).where(Match.stage_id == stage.id, Match.status == "validated"))
    ).all()
    return standings.compute(players, matches, t.config or {})


async def recalc(session, t: Tournament, stage: Stage, reason: str, match_id: int | None = None) -> None:
    """Salva um snapshot da tabela e atualiza o estado da fase/torneio (pontos corridos)."""
    await session.flush()
    rows = await table_for_stage(session, t, stage)
    session.add(
        StandingsSnapshot(
            tournament_id=t.id,
            stage_id=stage.id,
            reason=reason,
            triggered_by_match_id=match_id,
            data={"rows": [r.as_dict() for r in rows]},
        )
    )
    open_matches = await session.scalar(
        select(func.count()).select_from(Match).where(Match.stage_id == stage.id, Match.status.in_(("scheduled", "reported")))
    )
    if stage.type == "league" and t.status in ("running", "finished"):
        if open_matches == 0:
            stage.status = "finished"
            later = await session.scalar(
                select(func.count()).select_from(Stage).where(Stage.tournament_id == t.id, Stage.position > stage.position)
            )
            if not later:
                t.status = "finished"
        else:
            stage.status = "running"
            if t.status == "finished":
                t.status = "running"


async def apply_withdrawal(session, t: Tournament, user_id: int) -> None:
    """Jogador desistiu com o torneio em andamento: adversários dos jogos em aberto vencem por W.O."""
    # Só os jogos ainda sem reporte viram W.O. Se já havia um reporte pendente, o resultado reportado permanece
    # (o admin o valida normalmente), independentemente da desistência.
    matches = (
        await session.scalars(
            select(Match).where(
                Match.tournament_id == t.id,
                Match.status == "scheduled",
                (Match.player1_id == user_id) | (Match.player2_id == user_id),
            )
        )
    ).all()
    wo_score = (t.config or {}).get("walkover_score", 3)
    stages: dict[int, Stage] = {}
    for m in matches:
        opp = m.player2_id if m.player1_id == user_id else m.player1_id
        opp_out = False
        if opp is not None:
            opp_out = (
                await session.scalar(
                    select(TournamentPlayer.status).where(
                        TournamentPlayer.tournament_id == t.id, TournamentPlayer.user_id == opp
                    )
                )
                == "withdrawn"
            )
        if opp is None or opp_out:
            m.status = "void"
        else:
            set_walkover(m, opp, wo_score)
        stages[m.stage_id] = stages.get(m.stage_id) or await session.get(Stage, m.stage_id)
    for stage in stages.values():
        await recalc(session, t, stage, "Desistência de jogador (W.O. nos jogos pendentes)")
