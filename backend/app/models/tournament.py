from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK, JsonType, TimestampMixin


class Tournament(Base, TimestampMixin):
    """Torneio. Subtorneio (repescagem) é um torneio com parent_id preenchido (1 nível apenas)."""

    __tablename__ = "tournaments"
    __table_args__ = (
        CheckConstraint("status in ('draft','registration','running','finished','cancelled')", name="status_valid"),
        CheckConstraint("max_players >= 2", name="max_players_min"),
        Index("ix_tournaments_parent_id", "parent_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    template: Mapped[str] = mapped_column(String(24))  # league | knockout | groups_knockout | custom
    max_players: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft", server_default="draft")
    battle_rules: Mapped[dict | None] = mapped_column(JsonType)  # campos estruturados (formato, tier, clausulas...)
    rules_text: Mapped[str | None] = mapped_column(Text)  # texto livre
    config: Mapped[dict | None] = mapped_column(JsonType)  # pontuação, turno/returno, desempates...
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)


class Stage(Base):
    """Fase de um torneio (rodada única, pontos corridos, grupos ou mata-mata), em ordem de `position`."""

    __tablename__ = "stages"
    __table_args__ = (
        UniqueConstraint("tournament_id", "position", name="uq_stages_tournament_position"),
        CheckConstraint("type in ('round','league','groups','knockout','playoff')", name="type_valid"),
        CheckConstraint("status in ('pending','running','finished')", name="status_valid"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str] = mapped_column(String(80))
    type: Mapped[str] = mapped_column(String(16))
    config: Mapped[dict | None] = mapped_column(JsonType)  # best_of, turno/returno, n. de grupos, 3º lugar...
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")


class AdvancementRule(Base):
    """Regra de passagem: 'da fase X, posições A..B (pelo critério) vão para a fase Y a partir da vaga N'."""

    __tablename__ = "advancement_rules"
    __table_args__ = (
        CheckConstraint("pos_to >= pos_from", name="pos_range"),
        CheckConstraint("target in ('stage','eliminated','repechage','parent_tournament')", name="target_valid"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"), index=True)
    from_stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(16), default="ranking")  # ranking | winners | losers | group_position
    pos_from: Mapped[int] = mapped_column(SmallInteger)
    pos_to: Mapped[int] = mapped_column(SmallInteger)
    target: Mapped[str] = mapped_column(String(20))
    to_stage_id: Mapped[int | None] = mapped_column(ForeignKey("stages.id", ondelete="SET NULL"))
    to_slot_from: Mapped[int | None] = mapped_column(SmallInteger)  # primeira vaga de destino
    config: Mapped[dict | None] = mapped_column(JsonType)  # ex.: critério de ranking, grupo específico


class TournamentPlayer(Base, TimestampMixin):
    __tablename__ = "tournament_players"
    __table_args__ = (
        UniqueConstraint("tournament_id", "user_id", name="uq_tournament_players_tournament_user"),
        CheckConstraint("status in ('active','eliminated','withdrawn')", name="status_valid"),
        CheckConstraint("pot is null or (pot >= 1 and pot <= 8)", name="pot_valid"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    seed: Mapped[int | None] = mapped_column(SmallInteger)
    group_label: Mapped[str | None] = mapped_column(String(8))
    pot: Mapped[int | None] = mapped_column(SmallInteger)  # pote/cabeça de chave para o sorteio (1 = mais forte)
    status: Mapped[str] = mapped_column(String(12), default="active", server_default="active")


class Match(Base, TimestampMixin):
    __tablename__ = "matches"
    __table_args__ = (
        CheckConstraint("status in ('scheduled','reported','validated','void')", name="status_valid"),
        CheckConstraint("best_of in (1,3,5,7)", name="best_of_valid"),
        Index("ix_matches_tournament_stage", "tournament_id", "stage_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"), index=True)
    round: Mapped[int] = mapped_column(SmallInteger, default=1)
    group_label: Mapped[str | None] = mapped_column(String(8))
    slot: Mapped[int | None] = mapped_column(SmallInteger)  # posição no chaveamento
    leg: Mapped[int] = mapped_column(SmallInteger, default=1)  # 1 = turno, 2 = returno
    player1_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    player2_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    best_of: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(12), default="scheduled", server_default="scheduled")
    # Resultado validado
    p1_wins: Mapped[int | None] = mapped_column(SmallInteger)
    p2_wins: Mapped[int | None] = mapped_column(SmallInteger)
    p1_remaining: Mapped[int | None] = mapped_column(SmallInteger)  # Pokémon vivos (saldo)
    p2_remaining: Mapped[int | None] = mapped_column(SmallInteger)
    winner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_draw: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_walkover: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Encadeamento do chaveamento: vencedor segue para next_match_id na posição next_slot (1 ou 2)
    next_match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id", ondelete="SET NULL"))
    next_slot: Mapped[int | None] = mapped_column(SmallInteger)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchReport(Base, TimestampMixin):
    """Reporte feito por um jogador; o admin valida, rejeita ou marca empate."""

    __tablename__ = "match_reports"
    __table_args__ = (CheckConstraint("status in ('pending','validated','rejected')", name="status_valid"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)
    reported_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    p1_wins: Mapped[int] = mapped_column(SmallInteger)
    p2_wins: Mapped[int] = mapped_column(SmallInteger)
    p1_remaining: Mapped[int] = mapped_column(SmallInteger)
    p2_remaining: Mapped[int] = mapped_column(SmallInteger)
    replay_urls: Mapped[list | None] = mapped_column(JsonType)  # links de replay do Showdown (um por jogo)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="pending", server_default="pending")
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)


class StandingsSnapshot(Base, TimestampMixin):
    """Histórico: tabela/chaveamento congelado a cada alteração relevante."""

    __tablename__ = "standings_snapshots"
    __table_args__ = (Index("ix_standings_snapshots_tournament", "tournament_id", "stage_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id", ondelete="CASCADE"))
    stage_id: Mapped[int | None] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"))
    group_label: Mapped[str | None] = mapped_column(String(8))
    reason: Mapped[str | None] = mapped_column(String(120))
    triggered_by_match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id", ondelete="SET NULL"))
    data: Mapped[dict] = mapped_column(JsonType)
