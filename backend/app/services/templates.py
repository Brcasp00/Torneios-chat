"""Converte um modelo de torneio (liga, mata-mata, grupos + mata-mata) em fases e regras de passagem.

Tudo vira o mesmo formato (fases + regras), que é o que o modo "custom" também usa.
"""
import math

from app.schemas.tournament import RuleIn, StageIn, TournamentCreate


class TemplateError(ValueError):
    pass


def is_power_of_two(n: int) -> bool:
    return n >= 2 and (n & (n - 1)) == 0


def default_groups_count(max_players: int) -> int:
    return max(2, round(max_players / 4))


def build(data: TournamentCreate) -> tuple[list[StageIn], list[RuleIn], dict]:
    """Retorna (fases, regras, config final do torneio)."""
    cfg = data.config.model_dump()
    t = data.template

    if cfg["allow_draw"] is None:
        cfg["allow_draw"] = t in ("league", "groups_knockout")

    if t == "custom":
        return data.stages, data.rules, cfg

    if t == "league":
        stage = StageIn(
            name="Pontos corridos",
            type="league",
            config={"best_of": cfg["best_of"], "double_round": cfg["double_round"]},
        )
        return [stage], [], cfg

    if t == "knockout":
        if not is_power_of_two(data.max_players):
            raise TemplateError(
                "Mata-mata sem byes exige número de jogadores potência de 2 (2, 4, 8, 16...). "
                "Para outros números, use o modo 'custom' com uma fase preliminar."
            )
        stage = StageIn(
            name="Mata-mata",
            type="knockout",
            config={"best_of": cfg["best_of"], "third_place": cfg["third_place"]},
        )
        return [stage], [], cfg

    # groups_knockout
    groups = cfg["groups_count"] or default_groups_count(data.max_players)
    cfg["groups_count"] = groups
    per_group = math.ceil(data.max_players / groups)
    q = cfg["qualifiers_per_group"]
    if groups > data.max_players // 2:
        raise TemplateError("Há grupos demais para essa quantidade de jogadores (mínimo 2 por grupo).")
    if q >= per_group:
        raise TemplateError("Classificados por grupo deve ser menor que o tamanho do grupo.")
    if not is_power_of_two(groups * q):
        raise TemplateError(
            f"{groups} grupos x {q} classificados = {groups * q} vagas no mata-mata; "
            "o total precisa ser potência de 2 (sem byes)."
        )
    rep = cfg["repechage_position"]
    if rep is not None and not (q < rep <= per_group):
        raise TemplateError("A posição de repescagem deve ser maior que os classificados e caber no grupo.")

    stages = [
        StageIn(
            name="Fase de grupos",
            type="groups",
            config={
                "best_of": cfg["best_of"],
                "double_round": cfg["double_round"],
                "groups_count": groups,
                "qualifiers_per_group": q,
            },
        ),
        StageIn(name="Mata-mata", type="knockout", config={"best_of": cfg["best_of"], "third_place": cfg["third_place"]}),
    ]
    rules = [
        RuleIn(
            from_stage=1,
            source="group_position",
            pos_from=1,
            pos_to=q,
            target="stage",
            to_stage=2,
            to_slot_from=1,
            config={"fixed_crossing": True},
        )
    ]
    if rep is not None:
        rules.append(RuleIn(from_stage=1, source="group_position", pos_from=rep, pos_to=rep, target="repechage"))
    # Demais posições (acima de q, exceto repescagem) são eliminadas.
    first_out = q + 1
    if rep is None:
        rules.append(RuleIn(from_stage=1, source="group_position", pos_from=first_out, pos_to=per_group, target="eliminated"))
    else:
        if rep > first_out:
            rules.append(RuleIn(from_stage=1, source="group_position", pos_from=first_out, pos_to=rep - 1, target="eliminated"))
        if rep < per_group:
            rules.append(RuleIn(from_stage=1, source="group_position", pos_from=rep + 1, pos_to=per_group, target="eliminated"))
    return stages, rules, cfg


def validate_custom(stages: list[StageIn], rules: list[RuleIn], is_subtournament: bool) -> None:
    n = len(stages)
    for r in rules:
        if r.from_stage > n:
            raise TemplateError(f"Regra referencia a fase {r.from_stage}, mas existem só {n} fases.")
        if r.target == "stage":
            if r.to_stage > n:
                raise TemplateError(f"Regra aponta para a fase {r.to_stage}, que não existe.")
            if r.to_stage <= r.from_stage:
                raise TemplateError("A fase de destino deve vir depois da fase de origem.")
        if r.target == "parent_tournament" and not is_subtournament:
            raise TemplateError("Destino 'parent_tournament' só pode ser usado em subtorneios.")
        if r.target == "repechage" and is_subtournament:
            raise TemplateError("Subtorneios não podem ter repescagem (sem subtorneios aninhados).")
