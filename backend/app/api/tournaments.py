from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select

from app.core.deps import CurrentUser, OptionalUser, SessionDep, StaffUser
from app.models import (
    AdvancementRule,
    AuditLog,
    Match,
    MatchReport,
    Stage,
    StandingsSnapshot,
    Tournament,
    TournamentPlayer,
    User,
)
from app.schemas.tournament import (
    AddPlayersIn,
    LinkSubIn,
    PlayerOut,
    RepechageOut,
    RuleOut,
    StageOut,
    StatusIn,
    TournamentCreate,
    TournamentDetail,
    TournamentSummary,
    TournamentUpdate,
)
from app.services import engine, results, templates

router = APIRouter(prefix="/tournaments", tags=["tournaments"])

# Transições de status permitidas.
TRANSITIONS = {
    "draft": {"registration", "cancelled"},
    "registration": {"draft", "running", "cancelled"},
    "running": {"finished", "cancelled"},
    "finished": set(),
    "cancelled": set(),
}
EDITABLE = ("draft", "registration")


# ---------- helpers ----------
def can_manage(user: User | None, t: Tournament) -> bool:
    return bool(user and (user.role == "admin" or (user.role == "organizer" and t.created_by == user.id)))


async def _get_or_404(session, tournament_id: int) -> Tournament:
    t = await session.get(Tournament, tournament_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Torneio não encontrado.")
    return t


def _require_manage(user: User, t: Tournament) -> None:
    if not can_manage(user, t):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Você não pode gerenciar este torneio.")


async def _counts(session, ids: list[int]) -> dict[int, int]:
    if not ids:
        return {}
    rows = await session.execute(
        select(TournamentPlayer.tournament_id, func.count())
        .where(TournamentPlayer.tournament_id.in_(ids), TournamentPlayer.status != "withdrawn")
        .group_by(TournamentPlayer.tournament_id)
    )
    return {tid: n for tid, n in rows.all()}


def _summary(t: Tournament, count: int) -> TournamentSummary:
    s = TournamentSummary.model_validate(t)
    s.players_count = count
    return s


async def _players_out(session, tournament_id: int) -> list[PlayerOut]:
    rows = await session.execute(
        select(TournamentPlayer, User.name)
        .join(User, User.id == TournamentPlayer.user_id)
        .where(TournamentPlayer.tournament_id == tournament_id)
        .order_by(TournamentPlayer.seed.is_(None), TournamentPlayer.seed, User.name)
    )
    return [
        PlayerOut(user_id=p.user_id, name=name, seed=p.seed, group_label=p.group_label, pot=p.pot, status=p.status)
        for p, name in rows.all()
    ]


async def _detail(session, t: Tournament, user: User | None) -> TournamentDetail:
    stages = (await session.scalars(select(Stage).where(Stage.tournament_id == t.id).order_by(Stage.position))).all()
    rules = (
        await session.scalars(select(AdvancementRule).where(AdvancementRule.tournament_id == t.id).order_by(AdvancementRule.id))
    ).all()
    subs = (await session.scalars(select(Tournament).where(Tournament.parent_id == t.id).order_by(Tournament.id))).all()
    parent = await session.get(Tournament, t.parent_id) if t.parent_id else None
    counts = await _counts(session, [t.id] + [s.id for s in subs] + ([parent.id] if parent else []))
    pool = (t.config or {}).get("repechage") or {}
    repechage = []
    for r in (x for x in rules if x.target == "repechage"):
        sub = await engine.rule_subtournament(session, t, r)
        enrolled = ((sub.config or {}).get("auto_enrolled") or {}).get(str(r.id)) if sub else None
        repechage.append(
            RepechageOut(
                rule_id=r.id, stage_id=r.from_stage_id, subtournament_id=sub.id if sub else None,
                user_ids=enrolled if enrolled is not None else pool.get(str(r.from_stage_id), []),
            )
        )
    return TournamentDetail(
        **_summary(t, counts.get(t.id, 0)).model_dump(),
        battle_rules=t.battle_rules,
        rules_text=t.rules_text,
        config=t.config,
        created_by=t.created_by,
        stages=[StageOut.model_validate(s) for s in stages],
        rules=[RuleOut.model_validate(r) for r in rules],
        players=await _players_out(session, t.id),
        subtournaments=[_summary(s, counts.get(s.id, 0)) for s in subs],
        repechage=repechage,
        parent=_summary(parent, counts.get(parent.id, 0)) if parent else None,
        can_manage=can_manage(user, t),
    )


async def _create_structure(session, t: Tournament, data: TournamentCreate, parent: Tournament | None) -> dict:
    """Gera fases e regras de passagem do torneio e devolve a config final."""
    to_parent: list[tuple[int, int, int]] = []
    try:
        stages_in, rules_in, cfg = templates.build(data)
        if data.template == "custom":
            to_parent = templates.validate_custom(
                stages_in, rules_in, is_subtournament=parent is not None, max_players=data.max_players
            )
    except templates.TemplateError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))

    if parent and to_parent:
        # O subtorneio só pode devolver jogadores às vagas que a fase do principal reservou (config.external_slots).
        parent_stages = {
            s.position: s for s in (await session.scalars(select(Stage).where(Stage.tournament_id == parent.id))).all()
        }
        for pos, first, last in to_parent:
            target = parent_stages.get(pos)
            if target is None:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"O torneio principal não tem a fase {pos}.")
            reserved = templates.external_slots(target.config)
            if not any(a <= first and last <= b for a, b in reserved):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"A fase {pos} ('{target.name}') do torneio principal não reserva as vagas {first} a {last} para "
                    "quem volta da repescagem (config.external_slots / repechage_slots).",
                )

    stage_ids: dict[int, int] = {}
    for i, s in enumerate(stages_in, start=1):
        stage = Stage(tournament_id=t.id, position=i, name=s.name, type=s.type, config=s.config)
        session.add(stage)
        await session.flush()
        stage_ids[i] = stage.id

    parent_stage_ids: dict[int, int] = {}
    if parent:
        rows = await session.execute(select(Stage.position, Stage.id).where(Stage.tournament_id == parent.id))
        parent_stage_ids = {pos: sid for pos, sid in rows.all()}

    for r in rules_in:
        to_stage_id = None
        if r.target == "stage":
            to_stage_id = stage_ids[r.to_stage]
        elif r.target == "parent_tournament":
            to_stage_id = parent_stage_ids.get(r.parent_stage)
            if to_stage_id is None:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, f"O torneio principal não tem a fase {r.parent_stage}."
                )
        session.add(
            AdvancementRule(
                tournament_id=t.id,
                from_stage_id=stage_ids[r.from_stage],
                source=r.source,
                pos_from=r.pos_from,
                pos_to=r.pos_to,
                target=r.target,
                to_stage_id=to_stage_id,
                to_slot_from=r.to_slot_from,
                config=r.config,
            )
        )
    return cfg


async def _new_tournament(session, data: TournamentCreate, user: User, parent: Tournament | None) -> Tournament:
    t = Tournament(
        name=data.name,
        template=data.template,
        max_players=data.max_players,
        status="draft",
        battle_rules=data.battle_rules.model_dump(),
        rules_text=data.rules_text,
        config={},
        parent_id=parent.id if parent else None,
        created_by=user.id,
    )
    session.add(t)
    await session.flush()
    t.config = await _create_structure(session, t, data, parent)
    session.add(
        AuditLog(
            actor_id=user.id,
            action="tournament.create_sub" if parent else "tournament.create",
            entity="tournament",
            entity_id=t.id,
            data={"name": t.name, "template": t.template},
        )
    )
    if parent:
        await session.flush()
        try:  # se a fase de origem da repescagem já terminou, os candidatos entram agora
            await engine.refresh_repechage(session, parent)
        except results.CascadeError as e:
            raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    await session.commit()
    await session.refresh(t)
    return t


# ---------- leitura (pública) ----------
@router.get("", response_model=list[TournamentSummary])
async def list_tournaments(
    session: SessionDep,
    status_: str | None = None,
    q: str | None = None,
    include_sub: bool = False,
    limit: int = 50,
    offset: int = 0,
):
    stmt = select(Tournament).order_by(Tournament.id.desc())
    if not include_sub:
        stmt = stmt.where(Tournament.parent_id.is_(None))
    if status_:
        stmt = stmt.where(Tournament.status == status_)
    if q:
        stmt = stmt.where(Tournament.name.ilike(f"%{q}%"))
    items = (await session.scalars(stmt.limit(min(limit, 100)).offset(offset))).all()
    counts = await _counts(session, [t.id for t in items])
    return [_summary(t, counts.get(t.id, 0)) for t in items]


@router.get("/{tournament_id}", response_model=TournamentDetail)
async def get_tournament(tournament_id: int, session: SessionDep, user: OptionalUser):
    return await _detail(session, await _get_or_404(session, tournament_id), user)


@router.get("/{tournament_id}/players", response_model=list[PlayerOut])
async def list_players(tournament_id: int, session: SessionDep):
    await _get_or_404(session, tournament_id)
    return await _players_out(session, tournament_id)


# ---------- criação / edição ----------
@router.post("", response_model=TournamentDetail, status_code=status.HTTP_201_CREATED)
async def create_tournament(data: TournamentCreate, user: StaffUser, session: SessionDep):
    t = await _new_tournament(session, data, user, parent=None)
    return await _detail(session, t, user)


@router.post("/{tournament_id}/subtournaments", response_model=TournamentDetail, status_code=status.HTTP_201_CREATED)
async def create_subtournament(tournament_id: int, data: TournamentCreate, user: StaffUser, session: SessionDep):
    parent = await _get_or_404(session, tournament_id)
    _require_manage(user, parent)
    if parent.parent_id is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Subtorneios não podem ter subtorneios.")
    if parent.status in ("finished", "cancelled"):
        raise HTTPException(status.HTTP_409_CONFLICT, "O torneio principal já foi encerrado.")
    t = await _new_tournament(session, data, user, parent=parent)
    return await _detail(session, t, user)


@router.patch("/{tournament_id}", response_model=TournamentDetail)
async def update_tournament(tournament_id: int, data: TournamentUpdate, user: StaffUser, session: SessionDep):
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    if t.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "O torneio só pode ser editado antes de começar.")

    if data.name is not None:
        t.name = " ".join(data.name.split())
    if data.rules_text is not None:
        t.rules_text = data.rules_text
    if data.battle_rules is not None:
        t.battle_rules = data.battle_rules.model_dump()

    structure_changed = data.max_players is not None or data.config is not None
    if data.max_players is not None:
        current = (await _counts(session, [t.id])).get(t.id, 0)
        if data.max_players < current:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Já há {current} jogadores inscritos.")
        t.max_players = data.max_players
        if data.config is None and t.template == "groups_knockout":
            t.config = {**(t.config or {}), "groups_count": None}  # recalcula pelo novo número de jogadores
    if data.config is not None:
        t.config = data.config.model_dump()

    if structure_changed and t.template != "custom":
        # Modelos prontos: refaz fases e regras a partir da nova configuração.
        parent = await session.get(Tournament, t.parent_id) if t.parent_id else None
        await session.execute(delete(AdvancementRule).where(AdvancementRule.tournament_id == t.id))
        await session.execute(delete(Stage).where(Stage.tournament_id == t.id))
        rebuilt = TournamentCreate(
            name=t.name,
            template=t.template,
            max_players=t.max_players,
            config=t.config,
        )
        t.config = await _create_structure(session, t, rebuilt, parent)

    session.add(AuditLog(actor_id=user.id, action="tournament.update", entity="tournament", entity_id=t.id))
    await session.commit()
    await session.refresh(t)
    return await _detail(session, t, user)


@router.patch("/{tournament_id}/status", response_model=TournamentDetail)
async def set_status(tournament_id: int, data: StatusIn, user: StaffUser, session: SessionDep):
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    if data.status not in TRANSITIONS[t.status]:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Não é possível ir de '{t.status}' para '{data.status}'.")
    if data.status == "running":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Para iniciar o torneio use POST /tournaments/{id}/start (faz o sorteio e gera os confrontos)."
        )
    if data.status == "finished":
        pending = await session.scalar(
            select(func.count()).select_from(Match).where(
                Match.tournament_id == t.id, Match.postponed.is_(True), Match.status.in_(("scheduled", "reported"))
            )
        )
        if pending:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Há {pending} confronto(s) adiado(s) pendente(s); o torneio só encerra depois de eles serem disputados."
            )
    old = t.status
    t.status = data.status
    session.add(
        AuditLog(
            actor_id=user.id, action="tournament.set_status", entity="tournament", entity_id=t.id, data={"from": old, "to": data.status}
        )
    )
    await session.commit()
    return await _detail(session, t, user)


@router.put("/{tournament_id}/rules/{rule_id}/subtournament", response_model=TournamentDetail)
async def link_subtournament(tournament_id: int, rule_id: int, data: LinkSubIn, user: StaffUser, session: SessionDep):
    """Escolhe o subtorneio que recebe os candidatos de uma regra de repescagem.

    Só é necessário quando há mais de um subtorneio (com um só, a ligação é automática). Os candidatos já definidos
    são inscritos no novo subtorneio e retirados do antigo (se este ainda não começou).
    """
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    rule = await session.get(AdvancementRule, rule_id)
    if not rule or rule.tournament_id != t.id or rule.target != "repechage":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regra de repescagem não encontrada neste torneio.")
    new_sub = None
    if data.subtournament_id is not None:
        new_sub = await session.get(Tournament, data.subtournament_id)
        if not new_sub or new_sub.parent_id != t.id or new_sub.status == "cancelled":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Subtorneio inválido para este torneio.")
    try:
        old = await engine.rule_subtournament(session, t, rule)
        if old and (new_sub is None or old.id != new_sub.id):
            await engine.set_enrolled(session, old, rule.id, [], set())
        cfg = dict(rule.config or {})
        if new_sub:
            cfg["subtournament_id"] = new_sub.id
        else:
            cfg.pop("subtournament_id", None)
        rule.config = cfg
        await session.flush()
        await engine.refresh_repechage(session, t)
    except results.CascadeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    session.add(
        AuditLog(actor_id=user.id, action="tournament.link_subtournament", entity="tournament", entity_id=t.id,
                 data={"rule_id": rule.id, "subtournament_id": data.subtournament_id})
    )
    await session.commit()
    return await _detail(session, t, user)


@router.delete("/{tournament_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tournament(tournament_id: int, user: StaffUser, session: SessionDep):
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    if user.role != "admin" and t.status != "draft":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só admins podem apagar torneios que já saíram do rascunho.")
    ids = [t.id] + list((await session.scalars(select(Tournament.id).where(Tournament.parent_id == t.id))).all())
    for tid in ids:
        match_ids = select(Match.id).where(Match.tournament_id == tid)
        await session.execute(delete(MatchReport).where(MatchReport.match_id.in_(match_ids)))
        await session.execute(delete(StandingsSnapshot).where(StandingsSnapshot.tournament_id == tid))
        await session.execute(delete(Match).where(Match.tournament_id == tid))
        await session.execute(delete(AdvancementRule).where(AdvancementRule.tournament_id == tid))
        await session.execute(delete(TournamentPlayer).where(TournamentPlayer.tournament_id == tid))
        await session.execute(delete(Stage).where(Stage.tournament_id == tid))
    await session.execute(delete(Tournament).where(Tournament.parent_id == t.id))
    await session.execute(delete(Tournament).where(Tournament.id == t.id))
    session.add(AuditLog(actor_id=user.id, action="tournament.delete", entity="tournament", entity_id=t.id, data={"name": t.name}))
    await session.commit()


# ---------- jogadores ----------
@router.post("/{tournament_id}/players", response_model=list[PlayerOut], status_code=status.HTTP_201_CREATED)
async def add_players(tournament_id: int, data: AddPlayersIn, user: StaffUser, session: SessionDep):
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    if t.status not in EDITABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "Só é possível inscrever jogadores antes do início.")

    wanted = list(dict.fromkeys(data.user_ids))
    found = (await session.scalars(select(User).where(User.id.in_(wanted), User.is_active.is_(True)))).all()
    missing = set(wanted) - {u.id for u in found}
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Usuários não encontrados ou inativos: {sorted(missing)}")

    if t.parent_id:  # subtorneio (repescagem): só entram jogadores do torneio principal
        in_parent = set(
            (
                await session.scalars(
                    select(TournamentPlayer.user_id).where(
                        TournamentPlayer.tournament_id == t.parent_id, TournamentPlayer.status != "withdrawn"
                    )
                )
            ).all()
        )
        outside = set(wanted) - in_parent
        if outside:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Só jogadores do torneio principal podem entrar no subtorneio: {sorted(outside)}"
            )

    existing = set(
        (await session.scalars(select(TournamentPlayer.user_id).where(TournamentPlayer.tournament_id == t.id))).all()
    )
    dup = existing & set(wanted)
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Já inscritos neste torneio: {sorted(dup)}")
    if len(existing) + len(wanted) > t.max_players:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Limite de {t.max_players} jogadores excedido (há {len(existing)} inscritos)."
        )

    for uid in wanted:
        session.add(TournamentPlayer(tournament_id=t.id, user_id=uid))
    session.add(
        AuditLog(actor_id=user.id, action="tournament.add_players", entity="tournament", entity_id=t.id, data={"user_ids": wanted})
    )
    await session.commit()
    return await _players_out(session, t.id)


async def _remove_player(session, t: Tournament, user_id: int, actor: User, action: str) -> None:
    if t.status in ("finished", "cancelled"):
        raise HTTPException(status.HTTP_409_CONFLICT, "O torneio já foi encerrado.")
    tp = await session.scalar(
        select(TournamentPlayer).where(TournamentPlayer.tournament_id == t.id, TournamentPlayer.user_id == user_id)
    )
    if not tp or tp.status == "withdrawn":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Jogador não está inscrito neste torneio.")
    try:
        await _drop_player(session, t, tp)
        # Quem sai do principal também sai dos subtorneios em que estava (repescagem ainda não encerrada).
        for sub in (await session.scalars(select(Tournament).where(Tournament.parent_id == t.id))).all():
            if sub.status in ("finished", "cancelled"):
                continue
            sub_tp = await session.scalar(
                select(TournamentPlayer).where(TournamentPlayer.tournament_id == sub.id, TournamentPlayer.user_id == user_id)
            )
            if sub_tp and sub_tp.status != "withdrawn":
                await _drop_player(session, sub, sub_tp)
    except results.CascadeError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    session.add(AuditLog(actor_id=actor.id, action=action, entity="tournament", entity_id=t.id, data={"user_id": user_id}))
    await session.commit()


async def _drop_player(session, t: Tournament, tp: TournamentPlayer) -> None:
    if t.status in EDITABLE:
        await session.delete(tp)  # antes do início: simplesmente sai da lista
    else:
        tp.status = "withdrawn"  # em andamento: fica registrado e os jogos em aberto viram W.O. para os adversários
        await session.flush()
        await results.apply_withdrawal(session, t, tp.user_id)


@router.delete("/{tournament_id}/players/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_player(tournament_id: int, user_id: int, user: StaffUser, session: SessionDep):
    t = await _get_or_404(session, tournament_id)
    _require_manage(user, t)
    await _remove_player(session, t, user_id, user, "tournament.remove_player")


@router.post("/{tournament_id}/withdraw", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw(tournament_id: int, user: CurrentUser, session: SessionDep):
    """O próprio jogador desiste do torneio."""
    t = await _get_or_404(session, tournament_id)
    await _remove_player(session, t, user.id, user, "tournament.withdraw")
