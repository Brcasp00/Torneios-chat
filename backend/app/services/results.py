"""Regras de resultado de confrontos: validação, aplicação, W.O., invalidação, avanço no chaveamento
e recálculo da tabela."""
import re
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models import Match, MatchReport, Stage, StandingsSnapshot, Tournament, TournamentPlayer, User
from app.services import standings
from app.services.bracket import THIRD_PLACE

REPLAY_RE = re.compile(r"^https://replay\.pokemonshowdown\.com/[A-Za-z0-9._\-/]+$")
KNOCKOUT = ("knockout",)  # tipos de fase com chaveamento (vencedor avança)
LEAGUE_LIKE = ("league", "groups")  # tipos de fase com tabela de pontos


class ResultError(ValueError):
    pass


class CascadeError(ResultError):
    """A mudança afetaria um confronto seguinte que já foi reportado/validado."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def max_team(battle_rules: dict | None) -> int:
    br = battle_rules or {}
    return br.get("bring") or br.get("team_size") or 6


def allow_draw_for(t: Tournament, stage: Stage) -> bool:
    """Empate só existe em pontos corridos/grupos, e se o torneio permitir. Mata-mata nunca."""
    return stage.type in LEAGUE_LIKE and bool((t.config or {}).get("allow_draw"))


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
            raise ResultError("Esta fase não permite empates.")
        if p1_wins != 0 or p2_wins != 0:
            raise ResultError("Empate só pode ser registrado com o placar 0x0.")
        return
    if p1_wins == p2_wins:
        raise ResultError("Placar igual só é aceito como empate (0x0), e apenas onde há empate.")
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


# ---------- chaveamento ----------
def outcome(m: Match) -> tuple[int | None, int | None]:
    """(vencedor, perdedor) do confronto; (None, None) se não houver resultado decisivo."""
    if m.status != "validated" or m.winner_id is None:
        return (None, None)
    return (m.winner_id, m.player2_id if m.winner_id == m.player1_id else m.player1_id)


def _place(nxt: Match, slot: int, player_id: int | None) -> None:
    if nxt.status != "scheduled":
        raise CascadeError(
            f"O confronto seguinte (#{nxt.id}) já tem reporte ou resultado. Invalide-o primeiro e depois altere este."
        )
    if slot == 1:
        nxt.player1_id = player_id
    else:
        nxt.player2_id = player_id


async def propagate(session, stage: Stage, m: Match, old: tuple[int | None, int | None]) -> None:
    """Leva o vencedor (e, nas semifinais, o perdedor) para o confronto seguinte. Bloqueia se o seguinte já foi jogado."""
    if stage.type not in KNOCKOUT or m.group_label == THIRD_PLACE:
        return
    new = outcome(m)
    if new == old:
        return
    if m.next_match_id and new[0] != old[0]:
        nxt = await session.get(Match, m.next_match_id)
        _place(nxt, m.next_slot, new[0])
    if new[1] != old[1]:
        third = await session.scalar(
            select(Match).where(Match.stage_id == stage.id, Match.group_label == THIRD_PLACE)
        )
        if third and m.round == third.round - 1:  # semifinal
            _place(third, m.slot, new[1])


async def settle_withdrawn(session, t: Tournament, stage: Stage) -> None:
    """No mata-mata, confrontos com um desistente e um adversário ativo viram W.O. (encadeando as próximas rodadas)."""
    wo_score = (t.config or {}).get("walkover_score", 3)
    withdrawn = set(
        (
            await session.scalars(
                select(TournamentPlayer.user_id).where(
                    TournamentPlayer.tournament_id == t.id, TournamentPlayer.status == "withdrawn"
                )
            )
        ).all()
    )
    if not withdrawn:
        return
    changed = True
    while changed:
        changed = False
        ms = (
            await session.scalars(
                select(Match)
                .where(Match.stage_id == stage.id, Match.status == "scheduled")
                .order_by(Match.round, Match.slot)
            )
        ).all()
        for m in ms:
            if not (m.player1_id and m.player2_id):
                continue
            out1, out2 = m.player1_id in withdrawn, m.player2_id in withdrawn
            if out1 == out2:  # ninguém desistiu, ou os dois (fica para o admin decidir)
                continue
            old = outcome(m)
            await reject_pending_reports(session, m.id, None, "Substituído por W.O. (desistência).")
            set_walkover(m, m.player2_id if out1 else m.player1_id, wo_score)
            await propagate(session, stage, m, old)
            changed = True
        await session.flush()


# ---------- tabela / histórico ----------
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


async def _snapshot_data(session, t: Tournament, stage: Stage) -> dict:
    if stage.type in KNOCKOUT:
        ms = (
            await session.scalars(select(Match).where(Match.stage_id == stage.id).order_by(Match.round, Match.slot))
        ).all()
        return {
            "matches": [
                {
                    "id": m.id, "round": m.round, "slot": m.slot, "group_label": m.group_label,
                    "player1_id": m.player1_id, "player2_id": m.player2_id, "winner_id": m.winner_id,
                    "status": m.status, "p1_wins": m.p1_wins, "p2_wins": m.p2_wins,
                }
                for m in ms
            ]
        }
    rows = await table_for_stage(session, t, stage)
    return {"rows": [r.as_dict() for r in rows]}


async def recalc(session, t: Tournament, stage: Stage, reason: str, match_id: int | None = None) -> None:
    """Salva um snapshot (tabela ou chaveamento) e atualiza o estado da fase/torneio."""
    await session.flush()
    session.add(
        StandingsSnapshot(
            tournament_id=t.id,
            stage_id=stage.id,
            reason=reason,
            triggered_by_match_id=match_id,
            data=await _snapshot_data(session, t, stage),
        )
    )
    open_matches = await session.scalar(
        select(func.count()).select_from(Match).where(Match.stage_id == stage.id, Match.status.in_(("scheduled", "reported")))
    )
    if t.status in ("running", "finished"):
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


async def after_change(session, t: Tournament, stage: Stage, m: Match, old: tuple[int | None, int | None], reason: str) -> None:
    """Chamar depois de alterar o resultado de `m`: avança o chaveamento, resolve W.O. pendentes e salva o histórico."""
    await propagate(session, stage, m, old)
    await session.flush()
    if stage.type in KNOCKOUT:
        await settle_withdrawn(session, t, stage)
    await recalc(session, t, stage, reason, m.id)


async def apply_withdrawal(session, t: Tournament, user_id: int) -> None:
    """Jogador desistiu com o torneio em andamento.

    Pontos corridos: adversários dos jogos ainda sem reporte vencem por W.O. Mata-mata: o adversário avança
    (agora, ou quando chegar ao confronto). Reportes pendentes antes da desistência permanecem.
    """
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
        stage = stages.get(m.stage_id) or await session.get(Stage, m.stage_id)
        stages[m.stage_id] = stage
        if stage.type in KNOCKOUT:
            continue  # tratado por settle_withdrawn
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
    # Mata-mata: mesmo sem confronto pendente "agora", a fase precisa ser avaliada (o adversário pode chegar depois).
    for stage in (await session.scalars(select(Stage).where(Stage.tournament_id == t.id, Stage.type.in_(KNOCKOUT)))).all():
        stages.setdefault(stage.id, stage)
    for stage in stages.values():
        if stage.type in KNOCKOUT:
            await settle_withdrawn(session, t, stage)
        await recalc(session, t, stage, "Desistência de jogador (W.O. nos jogos pendentes)")
