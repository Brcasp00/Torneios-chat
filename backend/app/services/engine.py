"""Motor das regras de passagem: quando uma fase termina, leva os jogadores para as fases seguintes.

- Cada fase de destino só é criada quando TODAS as fases de origem das suas regras terminaram.
- Se um resultado de origem muda depois, o destino é refeito, desde que nenhum confronto dele tenha sido
  reportado/validado; senão a mudança é bloqueada (CascadeError -> HTTP 409) e nada é gravado.
"""
from sqlalchemy import delete, select

from app.models import AdvancementRule, Match, MatchReport, Stage, Tournament, TournamentPlayer
from app.services import stages as stage_service
from app.services import tables
from app.services.bracket import THIRD_PLACE


class EngineError(ValueError):
    pass


# ---------- saídas de uma fase ----------
def _seed_key(seeds: dict[int, int | None]):
    return lambda uid: (seeds.get(uid) if seeds.get(uid) is not None else 10**6, uid)


async def _seeds(session, t: Tournament) -> dict[int, int | None]:
    rows = await session.execute(
        select(TournamentPlayer.user_id, TournamentPlayer.seed).where(TournamentPlayer.tournament_id == t.id)
    )
    return {uid: seed for uid, seed in rows.all()}


async def compute_outputs(session, t: Tournament, stage: Stage) -> dict:
    """{'ranking': [...], 'winners': [...], 'losers': [...], 'groups': {rótulo: [jogadores por posição]}}"""
    matches = await tables.stage_matches(session, stage)
    validated = [m for m in matches if m.status == "validated"]
    seeds = await _seeds(session, t)
    key = _seed_key(seeds)
    out: dict = {"ranking": [], "winners": [], "losers": [], "groups": {}}

    if stage.type == "league":
        out["ranking"] = [r.user_id for r in await tables.table_for_stage(session, t, stage)]

    elif stage.type == "groups":
        gt = await tables.group_tables(session, t, stage)
        out["groups"] = {label: [r.user_id for r in rows] for label, rows in gt.items()}
        flat = [(r.position, -r.points, -r.saldo, -r.wins, key(r.user_id), r.user_id) for rows in gt.values() for r in rows]
        out["ranking"] = [x[-1] for x in sorted(flat)]

    elif stage.type in ("round", "playoff"):
        winners, losers = [], []
        for m in validated:
            if m.winner_id is None:
                continue
            loser = m.player2_id if m.winner_id == m.player1_id else m.player1_id
            winners.append((-tables.pair_saldo(m, m.winner_id), key(m.winner_id), m.winner_id))
            losers.append((-tables.pair_saldo(m, loser), key(loser), loser))
        out["winners"] = [w[-1] for w in sorted(winners)]  # maior saldo primeiro
        out["losers"] = [x[-1] for x in sorted(losers)]  # menor prejuízo primeiro
        out["ranking"] = out["winners"] + out["losers"]

    elif stage.type == "knockout":
        main = [m for m in matches if m.group_label != THIRD_PLACE]
        total = max((m.round for m in main), default=0)
        final = next((m for m in validated if m.round == total and m.group_label != THIRD_PLACE), None)
        order: list[int] = []
        if final and final.winner_id:
            order += [final.winner_id, final.player2_id if final.winner_id == final.player1_id else final.player1_id]
        third = next((m for m in validated if m.group_label == THIRD_PLACE and m.winner_id), None)
        if third:
            order += [third.winner_id, third.player2_id if third.winner_id == third.player1_id else third.player1_id]
        for rnd in range(total - 1, 0, -1):  # quem caiu mais tarde fica melhor colocado
            dropped = [
                (m.player2_id if m.winner_id == m.player1_id else m.player1_id)
                for m in validated if m.round == rnd and m.group_label != THIRD_PLACE and m.winner_id
            ]
            order += sorted((u for u in dropped if u not in order), key=key)
        out["ranking"] = order
    return out


def _slots_for_rule(rule: AdvancementRule, outputs: dict) -> list[int]:
    """Jogadores que a regra envia, na ordem das vagas de destino."""
    if rule.source == "group_position":
        groups: dict[str, list[int]] = outputs["groups"]
        labels = sorted(groups)
        positions = list(range(rule.pos_from, rule.pos_to + 1))
        cfg = rule.config or {}
        if cfg.get("crossings"):
            pairs = [(str(lbl), int(pos)) for lbl, pos in cfg["crossings"]]
        elif cfg.get("fixed_crossing"):
            try:
                pairs = stage_service.crossing_order(labels, positions)
            except stage_service.StageError as e:
                raise EngineError(str(e))
        else:
            pairs = [(lbl, pos) for pos in positions for lbl in labels]
        out = []
        for lbl, pos in pairs:
            members = groups.get(lbl, [])
            if pos > len(members):
                raise EngineError(f"O grupo {lbl} não tem a posição {pos}.")
            out.append(members[pos - 1])
        return out
    pool = outputs.get(rule.source) or []
    chunk = pool[rule.pos_from - 1 : rule.pos_to]
    if len(chunk) != rule.pos_to - rule.pos_from + 1:
        raise EngineError(f"A fase não tem jogadores suficientes para as posições {rule.pos_from} a {rule.pos_to} ({rule.source}).")
    return chunk


# ---------- sincronização ----------
async def _rules(session, **filters) -> list[AdvancementRule]:
    stmt = select(AdvancementRule).order_by(AdvancementRule.id)
    for col, val in filters.items():
        stmt = stmt.where(getattr(AdvancementRule, col) == val)
    return list((await session.scalars(stmt)).all())


async def _clear_stage_matches(session, stage: Stage) -> None:
    """Apaga os confrontos de uma fase de destino, se nenhum foi reportado/validado."""
    ms = await tables.stage_matches(session, stage)
    if not ms:
        return
    if any(m.status != "scheduled" for m in ms):
        from app.services.results import CascadeError

        raise CascadeError(
            f"A fase '{stage.name}' já tem confrontos reportados ou validados. "
            "Invalide-os primeiro (de trás para frente) e depois altere este resultado."
        )
    ids = [m.id for m in ms]
    await session.execute(delete(MatchReport).where(MatchReport.match_id.in_(ids)))
    await session.execute(delete(Match).where(Match.id.in_(ids)))
    await session.flush()


async def _statuses(session, t: Tournament, stage: Stage, outputs: dict, rules: list[AdvancementRule]) -> None:
    """Atualiza quem segue ativo e quem foi eliminado (ou vai à repescagem) quando a fase termina."""
    members = tables.participants(await tables.stage_matches(session, stage))
    forwarded: set[int] = set()
    out_of_main: set[int] = set()
    repechage: list[int] = []
    for r in rules:
        if r.target == "stage":
            forwarded.update(_slots_for_rule(r, outputs))
        elif r.target in ("eliminated", "repechage"):
            ids = _slots_for_rule(r, outputs)
            out_of_main.update(ids)
            if r.target == "repechage":
                repechage += ids
    has_forward = any(r.target == "stage" for r in rules)
    tps = (
        await session.scalars(
            select(TournamentPlayer).where(TournamentPlayer.tournament_id == t.id, TournamentPlayer.user_id.in_(list(members)))
        )
    ).all()
    for tp in tps:
        if tp.status == "withdrawn":
            continue
        if tp.user_id in forwarded:
            tp.status = "active"
        elif tp.user_id in out_of_main or (has_forward and tp.user_id not in forwarded):
            tp.status = "eliminated"
    cfg = dict(t.config or {})
    pool = dict(cfg.get("repechage") or {})
    if repechage:
        pool[str(stage.id)] = repechage
    else:
        pool.pop(str(stage.id), None)
    cfg["repechage"] = pool
    t.config = cfg


async def sync(session, t: Tournament, stage: Stage) -> None:
    """Chamar depois de recalcular o estado de `stage`: libera, refaz ou desfaz as fases de destino."""
    from app.services.results import CascadeError  # noqa: F401  (import tardio: evita ciclo)

    rules = await _rules(session, from_stage_id=stage.id)
    if not rules:
        return
    if stage.status == "finished":
        try:
            outputs = await compute_outputs(session, t, stage)
            await _statuses(session, t, stage, outputs, rules)
        except EngineError as e:
            raise CascadeError(str(e))
    dest_ids = {r.to_stage_id for r in rules if r.target == "stage" and r.to_stage_id}
    for dest_id in sorted(dest_ids):
        await _sync_dest(session, t, await session.get(Stage, dest_id))


async def _sync_dest(session, t: Tournament, dest: Stage) -> None:
    from app.services import results

    incoming = [r for r in await _rules(session, to_stage_id=dest.id) if r.target == "stage"]
    sources = {r.from_stage_id: await session.get(Stage, r.from_stage_id) for r in incoming}
    ready = all(s.status == "finished" for s in sources.values())
    cfg = dict(dest.config or {})

    if not ready:
        if await tables.stage_matches(session, dest):
            await _clear_stage_matches(session, dest)
            dest.status = "pending"
            cfg.pop("seated", None)
            dest.config = cfg
        return

    placements: dict[int, int] = {}
    try:
        for r in incoming:
            outputs = await compute_outputs(session, t, sources[r.from_stage_id])
            for i, uid in enumerate(_slots_for_rule(r, outputs)):
                slot = (r.to_slot_from or 1) + i
                if slot in placements:
                    raise EngineError(f"A vaga {slot} da fase '{dest.name}' foi preenchida por mais de uma regra.")
                placements[slot] = uid
        n = len(placements)
        if sorted(placements) != list(range(1, n + 1)):
            raise EngineError(f"As vagas da fase '{dest.name}' não são contínuas (1 a {n}).")
    except EngineError as e:
        raise results.CascadeError(str(e))

    seated = {str(slot): uid for slot, uid in placements.items()}
    existing = await tables.stage_matches(session, dest)
    if existing and cfg.get("seated") == seated:
        return  # nada mudou
    await _clear_stage_matches(session, dest)

    ordered = [placements[i] for i in range(1, n + 1)]
    base_seed = (t.config or {}).get("draw_seed", 1)
    try:
        plan = stage_service.plan_stage(dest, ordered, base_seed, fed=True)
    except stage_service.StageError as e:
        raise results.CascadeError(str(e))
    await stage_service.materialize(session, t.id, dest, plan)
    cfg["seated"] = seated
    dest.config = cfg
    dest.status = "running"
    if await results.settle_withdrawn(session, t, dest):
        await results.recalc(session, t, dest, "Desistências já existentes aplicadas como W.O.")
    else:
        await results.recalc(session, t, dest, f"Fase '{dest.name}' iniciada com os classificados")
