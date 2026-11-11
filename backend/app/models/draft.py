"""Draft Pokémon (Modo Carreira): lote de Pokémon do torneio, clubes e movimentações de dinheiro.

O caixa de um clube nunca é guardado pronto: é o orçamento inicial do torneio + a soma das movimentações dele
(compras, vendas, salários, rendas, multas, ajustes...). Assim tudo fica auditável e uma correção é só outra movimentação.
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK, JsonType, TimestampMixin


class DraftPokemon(Base, TimestampMixin):
    """Pokémon do lote de um torneio de Draft (referencia o catálogo pelo `species_id`)."""

    __tablename__ = "draft_pokemon"
    __table_args__ = (UniqueConstraint("tournament_id", "species_id", name="uq_draft_pokemon_tournament_species"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    species_id: Mapped[str] = mapped_column(String(40))  # id do catálogo (app/data/pokedex.json)
    name: Mapped[str] = mapped_column(String(60))
    draft_tier: Mapped[str | None] = mapped_column(String(10))  # tier do Draft, definido pelo organizador
    price: Mapped[int | None] = mapped_column(BigInteger)  # preço de referência definido pelo organizador (euros)
    positions: Mapped[list | None] = mapped_column(JsonType)  # posições próprias: ["defensor", ...]
    costs: Mapped[dict | None] = mapped_column(JsonType)  # custo em pontos por posição: {"defensor": 15, ...}
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    contract_price: Mapped[int | None] = mapped_column(BigInteger)  # quanto o dono atual pagou (base do salário)
    acquired_via: Mapped[str | None] = mapped_column(String(16))  # auction | market | transfer
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registered: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")  # inscrito no torneio


class DraftClub(Base, TimestampMixin):
    """Clube de um jogador num torneio de Draft (patrocinadores e nível do CT)."""

    __tablename__ = "draft_clubs"
    __table_args__ = (UniqueConstraint("tournament_id", "user_id", name="uq_draft_clubs_tournament_user"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sponsors: Mapped[list | None] = mapped_column(JsonType)  # nomes das empresas (texto livre)
    ct_level: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")


class DraftTransaction(Base, TimestampMixin):
    """Movimentação de dinheiro de um clube. amount > 0 entra no caixa; < 0 sai."""

    __tablename__ = "draft_transactions"
    __table_args__ = (Index("ix_draft_transactions_tournament_user", "tournament_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(20))  # purchase | correction | adjustment | ... (ver services/draft.py)
    amount: Mapped[int] = mapped_column(BigInteger)
    pokemon_id: Mapped[int | None] = mapped_column(ForeignKey("draft_pokemon.id", ondelete="SET NULL"), index=True)
    round: Mapped[int | None] = mapped_column(SmallInteger)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
