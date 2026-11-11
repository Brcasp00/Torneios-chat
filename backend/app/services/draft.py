"""Regras do Draft que mais de uma rota usa: configuração, caixa e montagem das respostas."""
from sqlalchemy import func, select

from app.models import DraftClub, DraftPokemon, DraftTransaction, Tournament, TournamentPlayer, User
from app.schemas.calculator import EconomyConfig
from app.schemas.draft import ClubOut, DraftPokemonOut, TransactionOut
from app.schemas.match import PlayerRef
from app.services import draft_config, pokedex

POSITIONS = ["defensor", "meio", "atacante"]
KIND_LABEL = {"purchase": "Compra", "correction": "Correção", "adjustment": "Ajuste manual"}


def settings(t: Tournament) -> dict | None:
    return (t.config or {}).get("draft")


def economy(t: Tournament) -> EconomyConfig:
    eco = (settings(t) or {}).get("economy") or draft_config.PRESETS[draft_config.DEFAULT_PRESET]
    return EconomyConfig(**eco)


def salary(price: int | None, eco: EconomyConfig) -> int | None:
    return None if price is None else price * eco.salary_rate_bp // 10_000


async def cash_by_user(session, t: Tournament) -> dict[int, int]:
    """Caixa de cada clube = orçamento inicial + soma das movimentações."""
    eco = economy(t)
    rows = await session.execute(
        select(DraftTransaction.user_id, func.coalesce(func.sum(DraftTransaction.amount), 0))
        .where(DraftTransaction.tournament_id == t.id).group_by(DraftTransaction.user_id)
    )
    sums = {uid: int(total) for uid, total in rows.all()}
    players = (await session.scalars(select(TournamentPlayer.user_id).where(TournamentPlayer.tournament_id == t.id))).all()
    return {uid: eco.initial_budget + sums.get(uid, 0) for uid in players}


async def names(session, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {u.id: u.name for u in (await session.scalars(select(User).where(User.id.in_(ids)))).all()}


def ref(uid: int | None, nm: dict[int, str]) -> PlayerRef | None:
    return PlayerRef(id=uid, name=nm.get(uid, "?")) if uid else None


def pokemon_out(p: DraftPokemon, eco: EconomyConfig, nm: dict[int, str]) -> DraftPokemonOut:
    cat = pokedex.get(p.species_id) or {}
    return DraftPokemonOut(
        id=p.id, species_id=p.species_id, name=p.name, num=cat.get("num"), types=cat.get("types", []),
        region=cat.get("region"), tier9=cat.get("tier9"), tier7=cat.get("tier7"), draft_tier=p.draft_tier, price=p.price,
        positions=list(p.positions or []), costs=dict(p.costs or {}), owner=ref(p.owner_id, nm),
        contract_price=p.contract_price, salary=salary(p.contract_price, eco) if p.owner_id else None,
        acquired_via=p.acquired_via, acquired_at=p.acquired_at, registered=bool(p.registered),
    )


async def transactions_out(session, rows: list[DraftTransaction]) -> list[TransactionOut]:
    nm = await names(session, {r.user_id for r in rows} | {r.created_by for r in rows})
    pids = {r.pokemon_id for r in rows if r.pokemon_id}
    pnames = {}
    if pids:
        pnames = {p.id: p.name for p in (await session.scalars(select(DraftPokemon).where(DraftPokemon.id.in_(pids)))).all()}
    return [
        TransactionOut(id=r.id, user=ref(r.user_id, nm), kind=r.kind, amount=r.amount, pokemon_id=r.pokemon_id,
                       pokemon_name=pnames.get(r.pokemon_id), round=r.round, note=r.note, created_by=ref(r.created_by, nm),
                       created_at=r.created_at)
        for r in rows
    ]


async def clubs(session, t: Tournament) -> list[ClubOut]:
    eco = economy(t)
    cash = await cash_by_user(session, t)
    nm = await names(session, cash.keys())
    owned = (await session.scalars(select(DraftPokemon).where(DraftPokemon.tournament_id == t.id, DraftPokemon.owner_id.is_not(None)))).all()
    extra = {c.user_id: c for c in (await session.scalars(select(DraftClub).where(DraftClub.tournament_id == t.id))).all()}
    out = []
    for uid, c in cash.items():
        mine = [p for p in owned if p.owner_id == uid]
        value = sum(p.contract_price or 0 for p in mine)
        club = extra.get(uid)
        out.append(ClubOut(
            user=PlayerRef(id=uid, name=nm.get(uid, "?")), cash=c, transferban=c < 0, squad_count=len(mine),
            registered_count=sum(1 for p in mine if p.registered), squad_value=value,
            salary_per_round=value * eco.salary_rate_bp // 10_000,
            sponsors=list(club.sponsors or []) if club else [], ct_level=club.ct_level if club else 0,
        ))
    return sorted(out, key=lambda x: x.user.name.lower())
