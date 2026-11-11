"""Draft Pokémon (Modo Carreira): configuração, lote de Pokémon do torneio, registro do leilão e clubes.

Leitura pública (tudo é público no Draft). Escrita: admin/organizador do torneio, exceto os patrocinadores, que o
próprio jogador também informa. O leilão acontece fora da plataforma (Discord); aqui só se registra quem levou e quanto pagou.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.tournaments import can_manage
from app.core.deps import CurrentUser, OptionalUser, SessionDep, StaffUser
from app.models import AuditLog, DraftClub, DraftPokemon, DraftTransaction, Tournament, TournamentPlayer, User
from app.schemas.draft import (
    AddPokemonIn,
    AdjustIn,
    AssignIn,
    ClubDetail,
    DraftOverview,
    DraftPokemonOut,
    DraftSetupIn,
    NoteIn,
    PokemonDetail,
    SponsorsIn,
    UpdatePokemonIn,
)
from app.services import draft, draft_config, pokedex

router = APIRouter(prefix="/tournaments/{tournament_id}/draft", tags=["draft"])


def _fmt(n: int) -> str:
    return f"€ {n / 1_000_000:,.2f} mi".replace(",", "X").replace(".", ",").replace("X", ".")


async def _tournament(session, tournament_id: int, lock: bool = False) -> Tournament:
    stmt = select(Tournament).where(Tournament.id == tournament_id)
    if lock:
        stmt = stmt.with_for_update()
    t = await session.scalar(stmt)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Torneio não encontrado.")
    return t


def _need_draft(t: Tournament) -> None:
    if not draft.settings(t):
        raise HTTPException(status.HTTP_409_CONFLICT, "Este torneio não usa o modo Draft.")


def _manage(user: User, t: Tournament) -> None:
    if not can_manage(user, t):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Você não pode gerenciar este torneio.")
    if t.status in ("finished", "cancelled"):
        raise HTTPException(status.HTTP_409_CONFLICT, "O torneio já terminou.")


def _log(session, user, action, t, data=None):
    session.add(AuditLog(actor_id=user.id, action=action, entity="tournament", entity_id=t.id, data=data))


async def _pokemon(session, t: Tournament, pid: int, lock: bool = False) -> DraftPokemon:
    stmt = select(DraftPokemon).where(DraftPokemon.id == pid, DraftPokemon.tournament_id == t.id)
    if lock:
        stmt = stmt.with_for_update()
    p = await session.scalar(stmt)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pokémon não está no lote deste torneio.")
    return p


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- configuração ----------
@router.get("", response_model=DraftOverview)
async def overview(tournament_id: int, session: SessionDep, user: OptionalUser):
    t = await _tournament(session, tournament_id)
    cfg = draft.settings(t)
    if not cfg:
        return DraftOverview(enabled=False, can_manage=can_manage(user, t))
    lote = (await session.scalars(select(DraftPokemon).where(DraftPokemon.tournament_id == t.id))).all()
    return DraftOverview(
        enabled=True, regions=cfg.get("regions", []), economy=draft.economy(t), clubs=await draft.clubs(session, t),
        lote_count=len(lote), free_count=sum(1 for p in lote if p.owner_id is None), can_manage=can_manage(user, t),
    )


@router.put("", response_model=DraftOverview)
async def setup(tournament_id: int, data: DraftSetupIn, user: StaffUser, session: SessionDep):
    """Liga o modo Draft no torneio (ou muda as regiões do lote e os valores econômicos)."""
    t = await _tournament(session, tournament_id, lock=True)
    _manage(user, t)
    bad = [r for r in data.regions if r not in pokedex.REGIONS]
    if bad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Região desconhecida: {', '.join(bad)}.")
    old = draft.settings(t) or {}
    eco = data.economy.model_dump() if data.economy else old.get("economy") or draft_config.PRESETS[draft_config.DEFAULT_PRESET]
    t.config = {**(t.config or {}), "draft": {"regions": list(dict.fromkeys(data.regions)), "economy": eco}}
    _log(session, user, "draft.setup", t, {"regions": data.regions, "economy_changed": data.economy is not None})
    await session.commit()
    return await overview(tournament_id, session, user)


# ---------- lote ----------
@router.get("/pokemon", response_model=list[DraftPokemonOut])
async def list_pokemon(tournament_id: int, session: SessionDep):
    t = await _tournament(session, tournament_id)
    _need_draft(t)
    rows = (await session.scalars(select(DraftPokemon).where(DraftPokemon.tournament_id == t.id))).all()
    nm = await draft.names(session, {p.owner_id for p in rows})
    eco = draft.economy(t)
    out = [draft.pokemon_out(p, eco, nm) for p in rows]
    return sorted(out, key=lambda p: (p.num or 0, p.name))


@router.post("/pokemon", response_model=dict)
async def add_pokemon(tournament_id: int, data: AddPokemonIn, user: StaffUser, session: SessionDep):
    """Adiciona Pokémon do catálogo ao lote (só das regiões do lote). Os que já estão no lote são ignorados."""
    t = await _tournament(session, tournament_id, lock=True)
    _manage(user, t)
    _need_draft(t)
    regions = set(draft.settings(t).get("regions", []))
    existing = set((await session.scalars(select(DraftPokemon.species_id).where(DraftPokemon.tournament_id == t.id))).all())
    unknown, outside, added = [], [], []
    for sid in dict.fromkeys(data.species_ids):
        cat = pokedex.get(sid)
        if not cat:
            unknown.append(sid)
        elif cat["region"] not in regions:
            outside.append(cat["name"])
        elif sid not in existing:
            session.add(DraftPokemon(tournament_id=t.id, species_id=sid, name=cat["name"], positions=[], costs={}))
            added.append(cat["name"])
    if unknown or outside:
        parts = []
        if outside:
            parts.append(f"fora das regiões do lote ({', '.join(sorted(regions))}): {', '.join(outside[:10])}")
        if unknown:
            parts.append(f"não encontrados no catálogo: {', '.join(unknown[:10])}")
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Nada foi adicionado. Pokémon " + "; ".join(parts) + ".")
    if added:
        _log(session, user, "draft.add_pokemon", t, {"count": len(added)})
    await session.commit()
    return {"added": len(added), "skipped": len(data.species_ids) - len(added)}


@router.get("/pokemon/{pokemon_id}", response_model=PokemonDetail)
async def get_pokemon(tournament_id: int, pokemon_id: int, session: SessionDep):
    t = await _tournament(session, tournament_id)
    _need_draft(t)
    p = await _pokemon(session, t, pokemon_id)
    nm = await draft.names(session, {p.owner_id})
    tx = (await session.scalars(select(DraftTransaction).where(DraftTransaction.pokemon_id == p.id).order_by(DraftTransaction.id.desc()))).all()
    return PokemonDetail(**draft.pokemon_out(p, draft.economy(t), nm).model_dump(), transactions=await draft.transactions_out(session, list(tx)))


@router.put("/pokemon/{pokemon_id}", response_model=DraftPokemonOut)
async def update_pokemon(tournament_id: int, pokemon_id: int, data: UpdatePokemonIn, user: StaffUser, session: SessionDep):
    """Tier do Draft, preço de referência, posições próprias e custo em pontos por posição (definidos pelo organizador)."""
    t = await _tournament(session, tournament_id)
    _manage(user, t)
    _need_draft(t)
    p = await _pokemon(session, t, pokemon_id, lock=True)
    p.draft_tier = (data.draft_tier or "").strip() or None
    p.price = data.price
    p.positions = data.positions
    p.costs = dict(data.costs)
    _log(session, user, "draft.update_pokemon", t, {"pokemon_id": p.id, "name": p.name})
    await session.commit()
    nm = await draft.names(session, {p.owner_id})
    return draft.pokemon_out(p, draft.economy(t), nm)


@router.delete("/pokemon/{pokemon_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_pokemon(tournament_id: int, pokemon_id: int, user: StaffUser, session: SessionDep):
    t = await _tournament(session, tournament_id)
    _manage(user, t)
    p = await _pokemon(session, t, pokemon_id, lock=True)
    if p.owner_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este Pokémon tem dono. Desfaça o registro antes de tirá-lo do lote.")
    _log(session, user, "draft.remove_pokemon", t, {"name": p.name})
    await session.delete(p)
    await session.commit()


# ---------- leilão / mercado ----------
@router.post("/pokemon/{pokemon_id}/assign", response_model=DraftPokemonOut)
async def assign(tournament_id: int, pokemon_id: int, data: AssignIn, user: StaffUser, session: SessionDep):
    """Registra quem levou o Pokémon (leilão no Discord ou compra no mercado) e quanto pagou; o valor sai do caixa."""
    t = await _tournament(session, tournament_id, lock=True)  # trava o torneio: compras uma de cada vez (caixa e limite)
    _manage(user, t)
    _need_draft(t)
    p = await _pokemon(session, t, pokemon_id, lock=True)
    eco = draft.economy(t)
    if p.owner_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este Pokémon já tem dono.")
    tp = await session.scalar(select(TournamentPlayer).where(TournamentPlayer.tournament_id == t.id, TournamentPlayer.user_id == data.user_id))
    if not tp or tp.status == "withdrawn":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "O comprador precisa ser um jogador ativo deste torneio.")
    owned = len((await session.scalars(select(DraftPokemon.id).where(DraftPokemon.tournament_id == t.id, DraftPokemon.owner_id == data.user_id))).all())
    if owned >= eco.max_squad:
        raise HTTPException(status.HTTP_409_CONFLICT, f"O elenco já tem {owned} Pokémon (máximo {eco.max_squad}). É preciso vender ou dispensar antes.")
    cash = (await draft.cash_by_user(session, t)).get(data.user_id, eco.initial_budget)
    if cash < 0:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Transferban: o caixa do clube está negativo ({_fmt(cash)}); compras estão proibidas.")
    if data.price > cash and not data.allow_negative:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Caixa insuficiente: o clube tem {_fmt(cash)} e o valor é {_fmt(data.price)}. "
            "Para registrar mesmo assim (o clube entra em transferban), marque a opção de permitir caixa negativo.",
        )
    p.owner_id, p.contract_price, p.acquired_via, p.acquired_at, p.registered = data.user_id, data.price, data.via, _now(), False
    via = "leilão" if data.via == "auction" else "mercado"
    session.add(DraftTransaction(tournament_id=t.id, user_id=data.user_id, kind="purchase", amount=-data.price, pokemon_id=p.id,
                                 note=data.note or f"Compra no {via}", created_by=user.id))
    _log(session, user, "draft.assign", t, {"pokemon_id": p.id, "name": p.name, "user_id": data.user_id, "price": data.price, "via": data.via})
    await session.commit()
    nm = await draft.names(session, {p.owner_id})
    return draft.pokemon_out(p, eco, nm)


@router.post("/pokemon/{pokemon_id}/unassign", response_model=DraftPokemonOut)
async def unassign(tournament_id: int, pokemon_id: int, data: NoteIn, user: StaffUser, session: SessionDep):
    """Desfaz um registro errado: o Pokémon volta a ficar livre e o valor pago volta ao caixa (movimentação de correção)."""
    t = await _tournament(session, tournament_id, lock=True)
    _manage(user, t)
    p = await _pokemon(session, t, pokemon_id, lock=True)
    if p.owner_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este Pokémon não tem dono.")
    session.add(DraftTransaction(tournament_id=t.id, user_id=p.owner_id, kind="correction", amount=p.contract_price or 0,
                                 pokemon_id=p.id, note=data.note or "Registro desfeito", created_by=user.id))
    _log(session, user, "draft.unassign", t, {"pokemon_id": p.id, "name": p.name, "user_id": p.owner_id})
    p.owner_id = p.contract_price = p.acquired_via = p.acquired_at = None
    p.registered = False
    await session.commit()
    return draft.pokemon_out(p, draft.economy(t), {})


# ---------- clubes ----------
@router.get("/clubs/{user_id}", response_model=ClubDetail)
async def club(tournament_id: int, user_id: int, session: SessionDep, user: OptionalUser):
    t = await _tournament(session, tournament_id)
    _need_draft(t)
    base = next((c for c in await draft.clubs(session, t) if c.user.id == user_id), None)
    if not base:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este jogador não está no torneio.")
    eco = draft.economy(t)
    squad = (await session.scalars(select(DraftPokemon).where(DraftPokemon.tournament_id == t.id, DraftPokemon.owner_id == user_id))).all()
    nm = {user_id: base.user.name}
    tx = (await session.scalars(
        select(DraftTransaction).where(DraftTransaction.tournament_id == t.id, DraftTransaction.user_id == user_id).order_by(DraftTransaction.id.desc())
    )).all()
    return ClubDetail(
        **base.model_dump(), squad=sorted((draft.pokemon_out(p, eco, nm) for p in squad), key=lambda x: (x.num or 0, x.name)),
        transactions=await draft.transactions_out(session, list(tx)),
        can_edit=bool(user and (user.id == user_id or can_manage(user, t))),
    )


@router.put("/clubs/{user_id}/sponsors", response_model=ClubDetail)
async def set_sponsors(tournament_id: int, user_id: int, data: SponsorsIn, user: CurrentUser, session: SessionDep):
    """Patrocinadores (nomes das empresas, texto livre). O próprio jogador ou a organização informa."""
    t = await _tournament(session, tournament_id)
    _need_draft(t)
    if user.id != user_id and not can_manage(user, t):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Só o dono do clube ou a organização informa os patrocinadores.")
    eco = draft.economy(t)
    names = [" ".join(s.split())[:60] for s in data.sponsors if s and s.strip()]
    if len(names) > eco.sponsors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"No máximo {eco.sponsors} patrocinadores.")
    if not await session.scalar(select(TournamentPlayer.id).where(TournamentPlayer.tournament_id == t.id, TournamentPlayer.user_id == user_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este jogador não está no torneio.")
    c = await session.scalar(select(DraftClub).where(DraftClub.tournament_id == t.id, DraftClub.user_id == user_id))
    if not c:
        c = DraftClub(tournament_id=t.id, user_id=user_id)
        session.add(c)
    c.sponsors = names
    _log(session, user, "draft.sponsors", t, {"user_id": user_id, "sponsors": names})
    await session.commit()
    return await club(tournament_id, user_id, session, user)


@router.post("/adjust", response_model=ClubDetail)
async def adjust(tournament_id: int, data: AdjustIn, user: StaffUser, session: SessionDep):
    """Ajuste manual no caixa (enquanto as cobranças e rendas automáticas não existem, ou para corrigir algo)."""
    t = await _tournament(session, tournament_id, lock=True)
    _manage(user, t)
    _need_draft(t)
    if data.amount == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Informe um valor diferente de zero.")
    if not await session.scalar(select(TournamentPlayer.id).where(TournamentPlayer.tournament_id == t.id, TournamentPlayer.user_id == data.user_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este jogador não está no torneio.")
    session.add(DraftTransaction(tournament_id=t.id, user_id=data.user_id, kind="adjustment", amount=data.amount, note=data.note, created_by=user.id))
    _log(session, user, "draft.adjust", t, {"user_id": data.user_id, "amount": data.amount, "note": data.note})
    await session.commit()
    return await club(tournament_id, data.user_id, session, user)
