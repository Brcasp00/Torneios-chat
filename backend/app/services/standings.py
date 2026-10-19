"""Cálculo da tabela de classificação a partir dos confrontos validados."""
from dataclasses import dataclass, field

DEFAULT_TIEBREAKERS = ["saldo", "vitorias", "confronto_direto"]


@dataclass
class Row:
    user_id: int
    name: str
    withdrawn: bool = False
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    points: int = 0
    saldo: int = 0
    position: int = 0
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "position": self.position,
            "user_id": self.user_id,
            "name": self.name,
            "withdrawn": self.withdrawn,
            "played": self.played,
            "wins": self.wins,
            "draws": self.draws,
            "losses": self.losses,
            "points": self.points,
            "saldo": self.saldo,
        }


def _side_saldo(m, side: int) -> int:
    """Saldo = Pokémon restantes do jogador - do adversário. Só conta em melhor de 1."""
    if m.best_of != 1:
        return 0
    mine, theirs = (m.p1_remaining, m.p2_remaining) if side == 1 else (m.p2_remaining, m.p1_remaining)
    return (mine or 0) - (theirs or 0)


def compute(players: dict[int, tuple[str, bool]], matches, cfg: dict) -> list[Row]:
    """players: user_id -> (nome, desistiu). matches: confrontos já validados (objetos com os campos do Match)."""
    pw, pd, pl = cfg.get("points_win", 3), cfg.get("points_draw", 1), cfg.get("points_loss", 0)
    rows = {uid: Row(uid, name, withdrawn) for uid, (name, withdrawn) in players.items()}

    for m in matches:
        if m.status != "validated" or m.player1_id not in rows or m.player2_id not in rows:
            continue
        for side, uid in ((1, m.player1_id), (2, m.player2_id)):
            r = rows[uid]
            r.played += 1
            r.saldo += _side_saldo(m, side)
            if m.is_draw:
                r.draws += 1
                r.points += pd
            elif m.winner_id == uid:
                r.wins += 1
                r.points += pw
            else:
                r.losses += 1
                r.points += pl

    ordered = _rank(list(rows.values()), ["pontos", *cfg.get("tiebreakers", DEFAULT_TIEBREAKERS)], matches, cfg)
    for i, r in enumerate(ordered, start=1):
        r.position = i
    return ordered


def _head_to_head_points(group_ids: set[int], matches, cfg: dict) -> dict[int, int]:
    pw, pd, pl = cfg.get("points_win", 3), cfg.get("points_draw", 1), cfg.get("points_loss", 0)
    pts = {uid: 0 for uid in group_ids}
    for m in matches:
        if m.status != "validated" or m.player1_id not in group_ids or m.player2_id not in group_ids:
            continue
        for uid in (m.player1_id, m.player2_id):
            pts[uid] += pd if m.is_draw else (pw if m.winner_id == uid else pl)
    return pts


def _rank(group: list[Row], criteria: list[str], matches, cfg: dict) -> list[Row]:
    """Ordena aplicando um critério por vez; empates seguem para o próximo critério."""
    if len(group) <= 1:
        return group
    if not criteria:
        return sorted(group, key=lambda r: (r.name.lower(), r.user_id))  # desempate final estável
    crit, rest = criteria[0], criteria[1:]
    if crit == "pontos":
        value = {r.user_id: r.points for r in group}
    elif crit == "saldo":
        value = {r.user_id: r.saldo for r in group}
    elif crit == "vitorias":
        value = {r.user_id: r.wins for r in group}
    elif crit == "confronto_direto":
        value = _head_to_head_points({r.user_id for r in group}, matches, cfg)
    else:
        return _rank(group, rest, matches, cfg)

    out: list[Row] = []
    for v in sorted({value[r.user_id] for r in group}, reverse=True):
        tied = [r for r in group if value[r.user_id] == v]
        out.extend(_rank(tied, rest, matches, cfg))
    return out
