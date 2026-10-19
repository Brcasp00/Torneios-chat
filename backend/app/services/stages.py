"""Planejamento e criação dos confrontos de cada tipo de fase."""
from dataclasses import dataclass, field

from sqlalchemy import select

from app.models import Match, Stage, TournamentPlayer
from app.services import bracket, schedule


class StageError(ValueError):
    pass


@dataclass
class MatchSpec:
    round: int
    slot: int
    p1: int | None
    p2: int | None
    group_label: str | None = None
    leg: int = 1


@dataclass
class Plan:
    specs: list[MatchSpec] = field(default_factory=list)
    groups: dict[int, str] = field(default_factory=dict)  # jogador -> grupo
    bracket_slots: list[int] | None = None  # mata-mata: jogadores na ordem do chaveamento
    third_place: bool = False


def group_label(i: int) -> str:
    return chr(65 + i) if i < 26 else f"G{i + 1}"


def standard_order(n: int) -> list[int]:
    """Ordem padrão de seeds numa chave de n posições: n=8 -> [1,8,4,5,2,7,3,6] (1x8, 4x5, 3x6, 2x7)."""
    order = [1]
    size = 1
    while size < n:
        size *= 2
        order = [x for s in order for x in (s, size + 1 - s)]
    return order


def crossing_order(labels: list[str], positions: list[int]) -> list[tuple[str, int]]:
    """Cruzamento fixo grupos -> mata-mata (na ordem das vagas do chaveamento).

    Os grupos são pareados (A-B, C-D...). Em cada par, a posição i de um grupo enfrenta a posição inversa do outro
    (ex.: 1ºA x 2ºB e 1ºB x 2ºA). As chaves de pares diferentes são intercaladas para que companheiros de grupo só
    se reencontrem o mais tarde possível.
    """
    if len(labels) < 2 or len(labels) % 2:
        raise StageError("Cruzamento fixo exige número par de grupos.")
    k = len(positions)
    pairs = [(labels[i], labels[i + 1]) for i in range(0, len(labels), 2)]
    out: list[tuple[str, int]] = []
    is_pow2 = k > 1 and (k & (k - 1)) == 0
    for i in [s - 1 for s in standard_order(k)] if is_pow2 else list(range(k)):
        for x, y in pairs:
            out.append((x, positions[i]))
            out.append((y, positions[k - 1 - i]))
    return out


def _derived(seed: int, stage: Stage) -> int:
    return seed + stage.position * 7919


def plan_stage(stage: Stage, ordered_ids: list[int], seed: int, fed: bool) -> Plan:
    """Monta o plano de confrontos. `ordered_ids` vem ordenado por vaga quando a fase é alimentada por regras (fed)."""
    cfg = stage.config or {}
    n = len(ordered_ids)
    s = _derived(seed, stage)
    t = stage.type

    if t == "league":
        ids = schedule.shuffled(ordered_ids, s)
        specs = []
        for r, rnd in enumerate(schedule.round_robin(ids, bool(cfg.get("double_round"))), start=1):
            for i, (a, b, leg) in enumerate(rnd, start=1):
                specs.append(MatchSpec(r, i, a, b, leg=leg))
        return Plan(specs)

    if t == "groups":
        from app.services.templates import default_groups_count

        g = cfg.get("groups_count") or default_groups_count(n)
        if n < 2 * g:
            raise StageError(f"{n} jogadores não formam {g} grupos de pelo menos 2.")
        ids = schedule.shuffled(ordered_ids, s)
        plan = Plan()
        for gi in range(g):
            label = group_label(gi)
            members = ids[gi::g]
            for uid in members:
                plan.groups[uid] = label
            for r, rnd in enumerate(schedule.round_robin(members, bool(cfg.get("double_round"))), start=1):
                for i, (a, b, leg) in enumerate(rnd, start=1):
                    plan.specs.append(MatchSpec(r, i, a, b, group_label=label, leg=leg))
        return plan

    if t == "knockout":
        if not bracket.is_power_of_two(n):
            raise StageError(f"O mata-mata sem byes exige potência de 2 jogadores (recebeu {n}).")
        if not fed:
            slots = schedule.shuffled(ordered_ids, s)
        elif cfg.get("seeding") == "standard":
            slots = [ordered_ids[seed_no - 1] for seed_no in standard_order(n)]  # vaga = seed (1 = melhor)
        else:
            slots = list(ordered_ids)  # vaga = posição no chaveamento (pares adjacentes se enfrentam)
        return Plan(bracket_slots=slots, third_place=bool(cfg.get("third_place")))

    if t in ("round", "playoff"):
        if n < 2 or n % 2:
            raise StageError(f"Fase '{stage.name}' exige número par de jogadores (recebeu {n}).")
        if fed and cfg.get("pairing") == "seeded":
            ids = list(ordered_ids)
            pairs = [(ids[i], ids[n - 1 - i]) for i in range(n // 2)]  # melhor x pior
        else:
            ids = schedule.shuffled(ordered_ids, s)
            pairs = [(ids[i], ids[i + 1]) for i in range(0, n, 2)]
        return Plan([MatchSpec(1, i, a, b) for i, (a, b) in enumerate(pairs, start=1)])

    raise StageError(f"Tipo de fase desconhecido: {t}")


async def materialize(session, tournament_id: int, stage: Stage, plan: Plan) -> list[Match]:
    best_of = (stage.config or {}).get("best_of", 1)
    if plan.bracket_slots is not None:
        created = await bracket.generate(session, tournament_id, stage.id, plan.bracket_slots, best_of, plan.third_place)
    else:
        created = []
        for sp in plan.specs:
            m = Match(
                tournament_id=tournament_id, stage_id=stage.id, round=sp.round, slot=sp.slot, leg=sp.leg,
                group_label=sp.group_label, player1_id=sp.p1, player2_id=sp.p2, best_of=best_of, status="scheduled",
            )
            session.add(m)
            created.append(m)
        await session.flush()
    for uid, label in plan.groups.items():
        tp = await session.scalar(
            select(TournamentPlayer).where(TournamentPlayer.tournament_id == tournament_id, TournamentPlayer.user_id == uid)
        )
        if tp:
            tp.group_label = label
    return created
