"""Planejamento e criação dos confrontos de cada tipo de fase (sorteio aleatório, por potes ou manual)."""
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
    seeds: dict[int, int] = field(default_factory=dict)  # jogador -> seed (1 = melhor), quando houver
    mode: str = "random"  # random | pots | manual

    def arrangement(self) -> dict | None:
        """O arranjo em formato editável (para o front reenviar após ajustes manuais)."""
        if self.bracket_slots is not None:
            return {"slots": list(self.bracket_slots)}
        if self.groups:
            out: dict[str, list[int]] = {}
            for uid, label in self.groups.items():
                out.setdefault(label, []).append(uid)
            return {"groups": dict(sorted(out.items()))}
        if self.specs and all(s.group_label is None and s.leg == 1 and s.round == 1 for s in self.specs) and len(self.specs) >= 1:
            return {"pairs": [[s.p1, s.p2] for s in self.specs]}
        return None


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


def _check_same_players(provided: list[int], expected: list[int]) -> None:
    if len(provided) != len(set(provided)):
        raise StageError("Há jogadores repetidos no arranjo manual.")
    missing, extra = set(expected) - set(provided), set(provided) - set(expected)
    if missing or extra:
        raise StageError(
            f"O arranjo manual deve conter exatamente os jogadores inscritos (faltam {sorted(missing)}, sobram {sorted(extra)})."
        )


def _groups_plan(stage: Stage, members_by_label: dict[str, list[int]], mode: str) -> Plan:
    cfg = stage.config or {}
    plan = Plan(mode=mode)
    for label in sorted(members_by_label):
        members = members_by_label[label]
        if len(members) < 2:
            raise StageError(f"O grupo {label} precisa de ao menos 2 jogadores.")
        for uid in members:
            plan.groups[uid] = label
        for r, rnd in enumerate(schedule.round_robin(members, bool(cfg.get("double_round"))), start=1):
            for i, (a, b, leg) in enumerate(rnd, start=1):
                plan.specs.append(MatchSpec(r, i, a, b, group_label=label, leg=leg))
    return plan


def _pots_groups(ids_by_pot: dict[int, list[int]], g: int, seed: int) -> dict[str, list[int]]:
    """Distribui pote a pote: com potes do tamanho do nº de grupos, cada grupo recebe um jogador de cada pote."""
    members: dict[str, list[int]] = {group_label(i): [] for i in range(g)}
    pointer = 0
    for pot in sorted(ids_by_pot):
        for uid in schedule.shuffled(ids_by_pot[pot], seed + pot * 104729):
            members[group_label(pointer % g)].append(uid)
            pointer += 1
    return members


def plan_stage(
    stage: Stage,
    ordered_ids: list[int],
    seed: int,
    fed: bool,
    pots: dict[int, int] | None = None,
    arrangement: dict | None = None,
    default_seeding: str = "standard",
) -> Plan:
    """Monta o plano de confrontos.

    - `fed`: a fase recebe jogadores de regras de passagem (`ordered_ids` vem ordenado por vaga).
    - `pots`: jogador -> pote (somente 1ª fase). Grupos recebem um jogador de cada pote; no mata-mata os potes
      viram seeds (pote 1 = cabeças de chave) e a chave segue o seeding padrão.
    - `arrangement`: arranjo manual (`slots`, `groups` ou `pairs`), que substitui o sorteio.
    """
    cfg = stage.config or {}
    n = len(ordered_ids)
    s = _derived(seed, stage)
    t = stage.type

    if arrangement:
        return _manual_plan(stage, ordered_ids, arrangement)

    if pots:
        if fed:
            pots = None
        else:
            missing = [u for u in ordered_ids if u not in pots]
            if missing:
                raise StageError(f"Jogadores sem pote definido: {sorted(missing)}.")

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
        if pots:
            by_pot: dict[int, list[int]] = {}
            for uid in ordered_ids:
                by_pot.setdefault(pots[uid], []).append(uid)
            return _groups_plan(stage, _pots_groups(by_pot, g, s), "pots")
        ids = schedule.shuffled(ordered_ids, s)
        return _groups_plan(stage, {group_label(i): ids[i::g] for i in range(g)}, "random")

    if t == "knockout":
        if not bracket.is_power_of_two(n):
            raise StageError(f"O mata-mata sem byes exige potência de 2 jogadores (recebeu {n}).")
        third = bool(cfg.get("third_place"))
        if pots:
            seed_list: list[int] = []
            for pot in sorted(set(pots[u] for u in ordered_ids)):
                seed_list += schedule.shuffled([u for u in ordered_ids if pots[u] == pot], s + pot * 104729)
            slots = [seed_list[k - 1] for k in standard_order(n)]
            return Plan(bracket_slots=slots, third_place=third, seeds={u: i for i, u in enumerate(seed_list, 1)}, mode="pots")
        if not fed:
            return Plan(bracket_slots=schedule.shuffled(ordered_ids, s), third_place=third)
        seeding = cfg.get("seeding") or default_seeding
        if seeding == "random":
            slots = schedule.shuffled(ordered_ids, s)  # chave sorteada (reproduzível: semente do torneio + fase)
        elif seeding == "standard":
            slots = [ordered_ids[seed_no - 1] for seed_no in standard_order(n)]  # vaga = seed (1 = melhor)
        else:
            slots = list(ordered_ids)  # vaga = posição no chaveamento (pares adjacentes se enfrentam)
        return Plan(bracket_slots=slots, third_place=third)

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


def _manual_plan(stage: Stage, ordered_ids: list[int], arr: dict) -> Plan:
    t = stage.type
    if t == "league":
        raise StageError("Arranjo manual não se aplica a pontos corridos (todos jogam contra todos).")
    if t == "groups":
        groups = arr.get("groups")
        if not groups:
            raise StageError("Para fase de grupos, informe o arranjo em 'groups' ({'A': [ids], 'B': [ids]}).")
        flat = [u for members in groups.values() for u in members]
        _check_same_players(flat, ordered_ids)
        wanted = (stage.config or {}).get("groups_count")
        if wanted and len(groups) != wanted:
            raise StageError(f"A fase tem {wanted} grupos; o arranjo tem {len(groups)}.")
        return _groups_plan(stage, {str(k): list(v) for k, v in groups.items()}, "manual")
    if t == "knockout":
        slots = arr.get("slots")
        if not slots:
            raise StageError("Para mata-mata, informe o arranjo em 'slots' (jogadores na ordem do chaveamento).")
        _check_same_players(slots, ordered_ids)
        if not bracket.is_power_of_two(len(slots)):
            raise StageError("O mata-mata sem byes exige potência de 2 jogadores.")
        return Plan(
            bracket_slots=list(slots), third_place=bool((stage.config or {}).get("third_place")),
            seeds={u: i for i, u in enumerate(slots, 1)}, mode="manual",
        )
    if t in ("round", "playoff"):
        pairs = arr.get("pairs")
        if not pairs:
            raise StageError("Para esta fase, informe o arranjo em 'pairs' ([[id, id], ...]).")
        if any(len(p) != 2 for p in pairs):
            raise StageError("Cada par deve ter exatamente 2 jogadores.")
        _check_same_players([u for p in pairs for u in p], ordered_ids)
        return Plan([MatchSpec(1, i, a, b) for i, (a, b) in enumerate(pairs, start=1)], mode="manual")
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
