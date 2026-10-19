"""Chaveamento de eliminação simples (sem byes)."""
import math

from app.models import Match

THIRD_PLACE = "3rd"  # group_label do confronto de 3º lugar


def is_power_of_two(n: int) -> bool:
    return n >= 2 and (n & (n - 1)) == 0


def rounds_count(n_players: int) -> int:
    return int(math.log2(n_players))


def round_name(rnd: int, total_rounds: int) -> str:
    remaining = 2 ** (total_rounds - rnd + 1)  # jogadores ainda vivos no início da rodada
    return {2: "Final", 4: "Semifinal", 8: "Quartas de final", 16: "Oitavas de final"}.get(remaining, f"Rodada de {remaining}")


def first_round_pairs(slots: list[int]) -> list[tuple[int, int]]:
    return [(slots[i], slots[i + 1]) for i in range(0, len(slots), 2)]


async def generate(session, tournament_id: int, stage_id: int, slots: list[int], best_of: int, third_place: bool) -> list[Match]:
    """Cria todos os confrontos do chaveamento. `slots` são os jogadores na ordem do chaveamento
    (posições 2k e 2k+1 se enfrentam na 1ª rodada). Retorna os confrontos criados (já com ids)."""
    n = len(slots)
    if not is_power_of_two(n):
        raise ValueError("O mata-mata sem byes exige número de jogadores potência de 2.")
    total = rounds_count(n)

    grid: dict[tuple[int, int], Match] = {}
    for rnd in range(1, total + 1):
        for slot in range(1, n // 2 ** rnd + 1):
            m = Match(tournament_id=tournament_id, stage_id=stage_id, round=rnd, slot=slot, best_of=best_of, status="scheduled")
            if rnd == 1:
                m.player1_id, m.player2_id = slots[2 * slot - 2], slots[2 * slot - 1]
            grid[(rnd, slot)] = m
            session.add(m)

    third = None
    if third_place and total >= 2:
        third = Match(
            tournament_id=tournament_id, stage_id=stage_id, round=total, slot=2, group_label=THIRD_PLACE,
            best_of=best_of, status="scheduled",
        )
        session.add(third)

    await session.flush()
    for (rnd, slot), m in grid.items():
        if rnd < total:
            m.next_match_id = grid[(rnd + 1, (slot + 1) // 2)].id
            m.next_slot = 1 if slot % 2 == 1 else 2
    await session.flush()
    return list(grid.values()) + ([third] if third else [])
