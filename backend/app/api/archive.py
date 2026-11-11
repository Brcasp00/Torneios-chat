"""Acervo de torneios e séries. Leitura pública; cadastrar, editar e remover só admins."""
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, func, or_, select, update

from app.api.tournaments import delete_tree
from app.core.deps import AdminUser, SessionDep
from app.models import ArchiveEntry, ArchiveMatch, ArchivePlacement, AuditLog, Series, Tournament, User
from app.schemas.archive import (
    ArchiveDetail,
    ArchiveEntryIn,
    ArchiveMatchOut,
    ArchiveSummary,
    DeleteArchiveIn,
    EntryMetaIn,
    LinkIn,
    PlacementOut,
    PlayerIn,
    PlayerOutRef,
    SeriesDetail,
    SeriesIn,
    SeriesOut,
    SeriesRef,
)

router = APIRouter(prefix="/archive", tags=["archive"])
series_router = APIRouter(prefix="/series", tags=["archive"])


# ---------- leitura ----------
def _visible():
    """Torneios antigos (sem torneio ligado) e torneios da plataforma já encerrados."""
    return or_(ArchiveEntry.tournament_id.is_(None), Tournament.status == "finished")


def _base():
    return select(ArchiveEntry).outerjoin(Tournament, Tournament.id == ArchiveEntry.tournament_id).where(_visible())


async def _summaries(session, entries: list[ArchiveEntry]) -> list[ArchiveSummary]:
    ids = [e.id for e in entries]
    champs: dict[int, ArchivePlacement] = {}
    if ids:
        for p in (await session.scalars(
            select(ArchivePlacement).where(ArchivePlacement.entry_id.in_(ids), ArchivePlacement.position == 1).order_by(ArchivePlacement.id)
        )).all():
            champs.setdefault(p.entry_id, p)
    sids = {e.series_id for e in entries if e.series_id}
    series = {s.id: s for s in (await session.scalars(select(Series).where(Series.id.in_(sids)))).all()} if sids else {}
    out = []
    for e in entries:
        c, s = champs.get(e.id), series.get(e.series_id)
        out.append(ArchiveSummary(
            id=e.id, name=e.name, tournament_id=e.tournament_id, start_date=e.start_date, end_date=e.end_date,
            format=e.format, players_count=e.players_count, edition=e.edition,
            series=SeriesRef(id=s.id, name=s.name) if s else None,
            champion=PlayerOutRef(user_id=c.user_id, name=c.name) if c else None,
        ))
    return out


def _order():
    return (func.coalesce(ArchiveEntry.start_date, ArchiveEntry.end_date).desc().nulls_last(), ArchiveEntry.id.desc())


@router.get("", response_model=list[ArchiveSummary])
async def list_archive(
    session: SessionDep, q: str | None = None, series_id: int | None = None, player_id: int | None = None,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
):
    stmt = _base()
    if q:
        stmt = stmt.where(ArchiveEntry.name.ilike(f"%{q}%"))
    if series_id:
        stmt = stmt.where(ArchiveEntry.series_id == series_id)
    if player_id:
        stmt = stmt.where(ArchiveEntry.id.in_(select(ArchivePlacement.entry_id).where(ArchivePlacement.user_id == player_id)))
    entries = (await session.scalars(stmt.order_by(*_order()).limit(limit).offset(offset))).all()
    return await _summaries(session, entries)


async def _get_visible(session, entry_id: int) -> ArchiveEntry:
    e = await session.scalar(_base().where(ArchiveEntry.id == entry_id))
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Torneio não encontrado no acervo.")
    return e


async def _detail(session, e: ArchiveEntry) -> ArchiveDetail:
    summary = (await _summaries(session, [e]))[0]
    placements = (await session.scalars(
        select(ArchivePlacement).where(ArchivePlacement.entry_id == e.id).order_by(ArchivePlacement.position, ArchivePlacement.id)
    )).all()
    matches = (await session.scalars(select(ArchiveMatch).where(ArchiveMatch.entry_id == e.id).order_by(ArchiveMatch.sort))).all()
    return ArchiveDetail(
        **summary.model_dump(), organizer=e.organizer, tier=e.tier, rules_text=e.rules_text, description=e.description,
        links=[LinkIn(**x) for x in (e.links or [])], created_at=e.created_at, updated_at=e.updated_at,
        placements=[PlacementOut(position=p.position, label=p.label, user_id=p.user_id, name=p.name) for p in placements],
        matches=[
            ArchiveMatchOut(
                id=m.id, stage_label=m.stage_label, number=m.number, winner=m.winner, replay_url=m.replay_url,
                player1=PlayerOutRef(user_id=m.player1_user_id, name=m.player1_name),
                player2=PlayerOutRef(user_id=m.player2_user_id, name=m.player2_name),
            )
            for m in matches
        ],
    )


@router.get("/{entry_id}", response_model=ArchiveDetail)
async def get_entry(entry_id: int, session: SessionDep):
    return await _detail(session, await _get_visible(session, entry_id))


@router.get("/by-tournament/{tournament_id}", response_model=ArchiveSummary)
async def entry_of_tournament(tournament_id: int, session: SessionDep):
    """Entrada do acervo de um torneio da plataforma (para a página do torneio apontar para o acervo)."""
    e = await session.scalar(_base().where(ArchiveEntry.tournament_id == tournament_id))
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este torneio não está no acervo.")
    return (await _summaries(session, [e]))[0]


# ---------- escrita (admin) ----------
async def _resolve(session, players: list[PlayerIn]) -> dict[int, str]:
    """Contas citadas -> nome atual (o nome fica copiado, para continuar aparecendo se a conta sumir)."""
    ids = {p.user_id for p in players if p.user_id is not None}
    if not ids:
        return {}
    found = {u.id: u.name for u in (await session.scalars(select(User).where(User.id.in_(ids)))).all()}
    missing = ids - set(found)
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Contas não encontradas: {sorted(missing)}")
    return found


async def _check_series(session, series_id: int | None) -> None:
    if series_id is not None and not await session.get(Series, series_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Série não encontrada.")


def _apply_meta(e: ArchiveEntry, data: EntryMetaIn) -> None:
    e.description = (data.description or "").strip() or None
    e.links = [link.model_dump() for link in data.links]
    e.series_id = data.series_id
    e.edition = data.edition


async def _write_manual(session, e: ArchiveEntry, data: ArchiveEntryIn) -> None:
    await _check_series(session, data.series_id)
    names = await _resolve(session, [*data.placements, *(p for m in data.matches for p in (m.player1, m.player2))])

    def who(p: PlayerIn) -> tuple[int | None, str]:
        return (p.user_id, names[p.user_id]) if p.user_id is not None else (None, p.name or "?")

    for field in ("name", "start_date", "end_date", "format", "players_count", "organizer", "tier"):
        setattr(e, field, getattr(data, field))
    e.rules_text = (data.rules_text or "").strip() or None
    _apply_meta(e, data)
    await session.flush()
    await session.execute(delete(ArchivePlacement).where(ArchivePlacement.entry_id == e.id))
    await session.execute(delete(ArchiveMatch).where(ArchiveMatch.entry_id == e.id))
    for p in data.placements:
        uid, name = who(p)
        session.add(ArchivePlacement(entry_id=e.id, position=p.position, label=p.label, user_id=uid, name=name))
    for k, m in enumerate(data.matches):
        (u1, n1), (u2, n2) = who(m.player1), who(m.player2)
        session.add(ArchiveMatch(
            entry_id=e.id, sort=k, stage_label=m.stage_label, number=m.number, winner=m.winner, replay_url=m.replay_url,
            player1_user_id=u1, player1_name=n1, player2_user_id=u2, player2_name=n2,
        ))


@router.post("", response_model=ArchiveDetail, status_code=status.HTTP_201_CREATED)
async def create_entry(data: ArchiveEntryIn, admin: AdminUser, session: SessionDep):
    """Cadastra um torneio antigo (jogado fora da plataforma)."""
    e = ArchiveEntry(name=data.name, created_by=admin.id)
    session.add(e)
    await _write_manual(session, e, data)
    session.add(AuditLog(actor_id=admin.id, action="archive.create", entity="archive", entity_id=e.id, data={"name": e.name}))
    await session.commit()
    await session.refresh(e)
    return await _detail(session, e)


@router.put("/{entry_id}", response_model=ArchiveDetail)
async def update_entry(entry_id: int, data: ArchiveEntryIn, admin: AdminUser, session: SessionDep):
    """Edita um torneio antigo por inteiro. Para torneios da plataforma use PUT /archive/{id}/meta."""
    e = await _get_visible(session, entry_id)
    if e.tournament_id is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Este torneio foi jogado na plataforma: a classificação e as partidas vêm dele. Só a descrição, os links e a série podem ser editados.",
        )
    await _write_manual(session, e, data)
    session.add(AuditLog(actor_id=admin.id, action="archive.update", entity="archive", entity_id=e.id, data={"name": e.name}))
    await session.commit()
    await session.refresh(e)
    return await _detail(session, e)


@router.put("/{entry_id}/meta", response_model=ArchiveDetail)
async def update_meta(entry_id: int, data: EntryMetaIn, admin: AdminUser, session: SessionDep):
    """Descrição, links e série/edição (vale para qualquer torneio do acervo)."""
    e = await _get_visible(session, entry_id)
    await _check_series(session, data.series_id)
    _apply_meta(e, data)
    session.add(AuditLog(actor_id=admin.id, action="archive.update", entity="archive", entity_id=e.id, data={"name": e.name, "meta": True}))
    await session.commit()
    await session.refresh(e)
    return await _detail(session, e)


@router.post("/{entry_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(entry_id: int, data: DeleteArchiveIn, admin: AdminUser, session: SessionDep):
    """Remove do acervo. Se o torneio foi jogado na plataforma, ele é APAGADO de vez (confrontos, histórico...)."""
    e = await _get_visible(session, entry_id)
    if " ".join(data.confirm_name.split()).lower() != e.name.lower():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Para confirmar, digite exatamente o nome do torneio.")
    tid, name = e.tournament_id, e.name
    await session.execute(delete(ArchivePlacement).where(ArchivePlacement.entry_id == e.id))
    await session.execute(delete(ArchiveMatch).where(ArchiveMatch.entry_id == e.id))
    await session.execute(delete(ArchiveEntry).where(ArchiveEntry.id == e.id))
    if tid is not None:
        t = await session.get(Tournament, tid)
        if t:
            await delete_tree(session, t)
    session.add(AuditLog(actor_id=admin.id, action="archive.delete", entity="archive", entity_id=entry_id,
                         data={"name": name, "tournament_id": tid}))
    await session.commit()


# ---------- séries ----------
@series_router.get("", response_model=list[SeriesOut])
async def list_series(session: SessionDep):
    return (await session.scalars(select(Series).order_by(func.lower(Series.name)))).all()


@series_router.get("/{series_id}", response_model=SeriesDetail)
async def get_series(series_id: int, session: SessionDep):
    s = await session.get(Series, series_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Série não encontrada.")
    entries = (await session.scalars(
        _base().where(ArchiveEntry.series_id == s.id).order_by(ArchiveEntry.edition.desc().nulls_last(), *_order())
    )).all()
    return SeriesDetail(id=s.id, name=s.name, description=s.description, editions=await _summaries(session, entries))


async def _unique_series_name(session, name: str, skip_id: int | None = None) -> None:
    stmt = select(Series.id).where(func.lower(Series.name) == name.lower())
    if skip_id:
        stmt = stmt.where(Series.id != skip_id)
    if await session.scalar(stmt):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma série com esse nome.")


@series_router.post("", response_model=SeriesOut, status_code=status.HTTP_201_CREATED)
async def create_series(data: SeriesIn, admin: AdminUser, session: SessionDep):
    await _unique_series_name(session, data.name)
    s = Series(name=data.name, description=(data.description or "").strip() or None)
    session.add(s)
    await session.flush()
    session.add(AuditLog(actor_id=admin.id, action="series.create", entity="series", entity_id=s.id, data={"name": s.name}))
    await session.commit()
    return s


@series_router.put("/{series_id}", response_model=SeriesOut)
async def update_series(series_id: int, data: SeriesIn, admin: AdminUser, session: SessionDep):
    s = await session.get(Series, series_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Série não encontrada.")
    await _unique_series_name(session, data.name, skip_id=s.id)
    s.name, s.description = data.name, (data.description or "").strip() or None
    session.add(AuditLog(actor_id=admin.id, action="series.update", entity="series", entity_id=s.id, data={"name": s.name}))
    await session.commit()
    return s


@series_router.delete("/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_series(series_id: int, admin: AdminUser, session: SessionDep):
    """Apaga a série; os torneios dela continuam no acervo, só sem série."""
    s = await session.get(Series, series_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Série não encontrada.")
    await session.execute(update(ArchiveEntry).where(ArchiveEntry.series_id == s.id).values(series_id=None, edition=None))
    session.add(AuditLog(actor_id=admin.id, action="series.delete", entity="series", entity_id=s.id, data={"name": s.name}))
    await session.delete(s)
    await session.commit()
