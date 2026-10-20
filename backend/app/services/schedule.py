"""Sorteio e geração de confrontos."""
import random


def new_seed() -> int:
    return random.SystemRandom().randrange(1, 2**31)


def shuffled(ids: list[int], seed: int) -> list[int]:
    out = list(ids)
    random.Random(seed).shuffle(out)
    return out


def round_robin(ids: list[int], double_round: bool = False) -> list[list[tuple[int, int, int]]]:
    """Todos contra todos (método do círculo).

    Retorna uma lista de rodadas; cada rodada é uma lista de (jogador1, jogador2, perna).
    Com número ímpar de jogadores, um descansa em cada rodada. Com `double_round`, as rodadas do
    returno (perna 2) vêm depois do turno, com os mandos invertidos.
    """
    players: list[int | None] = list(ids)
    if len(players) % 2:
        players.append(None)
    n = len(players)
    first_leg: list[list[tuple[int, int, int]]] = []
    for r in range(n - 1):
        rnd = []
        for i in range(n // 2):
            a, b = players[i], players[n - 1 - i]
            if a is None or b is None:
                continue
            if (r + i) % 2 == 1:
                a, b = b, a
            rnd.append((a, b, 1))
        first_leg.append(rnd)
        players = [players[0], players[-1], *players[1:-1]]
    if not double_round:
        return first_leg
    second_leg = [[(b, a, 2) for a, b, _ in rnd] for rnd in first_leg]
    return first_leg + second_leg
