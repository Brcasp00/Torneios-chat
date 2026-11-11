"""Acervo de torneios: torneios encerrados da plataforma e torneios antigos cadastrados à mão, agrupáveis em séries."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK, JsonType, TimestampMixin


class Series(Base, TimestampMixin):
    """Série de torneios recorrentes (ex.: "Copa X"), com edições."""

    __tablename__ = "series"
    __table_args__ = (Index("uq_series_name_lower", text("lower(name)"), unique=True),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)


class ArchiveEntry(Base, TimestampMixin):
    """Um torneio no acervo. Com `tournament_id`, é um torneio jogado na plataforma (aparece quando ele encerra);
    sem, é um torneio antigo cadastrado à mão por um admin."""

    __tablename__ = "archive_entries"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int | None] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"), unique=True
    )
    name: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    format: Mapped[str | None] = mapped_column(String(200))  # texto livre: "Grupos + mata-mata", "Suíço"...
    players_count: Mapped[int | None] = mapped_column(Integer)
    organizer: Mapped[str | None] = mapped_column(String(80))
    tier: Mapped[str | None] = mapped_column(String(60))
    rules_text: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    links: Mapped[list | None] = mapped_column(JsonType)  # [{"label": "...", "url": "https://..."}]
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id", ondelete="SET NULL"), index=True)
    edition: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ArchivePlacement(Base):
    """Classificação final: posição, rótulo opcional ("Campeão", "Semifinal") e jogador (conta ou só nome)."""

    __tablename__ = "archive_placements"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("archive_entries.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    label: Mapped[str | None] = mapped_column(String(40))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(60))  # nome mostrado (cópia do nome da conta, ou texto livre)


class ArchiveMatch(Base):
    """Partida de um torneio antigo: "Rodada 4 · Partida 3 — A × B — vencedor — link do replay"."""

    __tablename__ = "archive_matches"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("archive_entries.id", ondelete="CASCADE"), index=True)
    sort: Mapped[int] = mapped_column(Integer)  # ordem de exibição
    stage_label: Mapped[str] = mapped_column(String(60))  # "Rodada 4", "Semifinal"...
    number: Mapped[int | None] = mapped_column(SmallInteger)
    player1_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    player1_name: Mapped[str] = mapped_column(String(60))
    player2_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    player2_name: Mapped[str] = mapped_column(String(60))
    winner: Mapped[int | None] = mapped_column(SmallInteger)  # 1, 2 ou vazio
    replay_url: Mapped[str | None] = mapped_column(String(500))
