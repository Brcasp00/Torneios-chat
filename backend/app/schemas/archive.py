from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = " ".join(v.split())
    return v or None


def _url(v: str | None) -> str | None:
    """Só links http(s): um link "javascript:..." no acervo viraria código rodando no navegador de quem clicar."""
    v = (v or "").strip()
    if not v:
        return None
    if not v.lower().startswith(("https://", "http://")):
        raise ValueError("O link precisa começar com https:// (ou http://).")
    return v


class LinkIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    url: str = Field(max_length=500)

    _u = field_validator("url")(_url)


class PlayerIn(BaseModel):
    """Jogador numa classificação/partida: uma conta (`user_id`) ou só um nome (quem não tem conta)."""

    user_id: int | None = None
    name: str | None = Field(None, max_length=60)

    _n = field_validator("name")(_clean)

    @model_validator(mode="after")
    def _one(self):
        if self.user_id is None and not self.name:
            raise ValueError("Informe a conta do jogador ou o nome dele.")
        return self


class PlacementIn(PlayerIn):
    position: int = Field(ge=1, le=1024)
    label: str | None = Field(None, max_length=40)

    _l = field_validator("label")(_clean)


class ArchiveMatchIn(BaseModel):
    stage_label: str = Field(min_length=1, max_length=60)
    number: int | None = Field(None, ge=1, le=10000)
    player1: PlayerIn
    player2: PlayerIn
    winner: int | None = Field(None, ge=1, le=2)
    replay_url: str | None = Field(None, max_length=500)

    _s = field_validator("stage_label")(_clean)
    _u = field_validator("replay_url")(_url)


class EntryMetaIn(BaseModel):
    """Campos que o admin pode editar também nos torneios jogados na plataforma."""

    description: str | None = Field(None, max_length=20000)
    links: list[LinkIn] = Field(default_factory=list, max_length=50)
    series_id: int | None = None
    edition: int | None = Field(None, ge=1, le=10000)


class ArchiveEntryIn(EntryMetaIn):
    """Torneio antigo, cadastrado à mão."""

    name: str = Field(min_length=3, max_length=120)
    start_date: date | None = None
    end_date: date | None = None
    format: str | None = Field(None, max_length=200)
    players_count: int | None = Field(None, ge=2, le=1024)
    organizer: str | None = Field(None, max_length=80)
    tier: str | None = Field(None, max_length=60)
    rules_text: str | None = Field(None, max_length=5000)
    placements: list[PlacementIn] = Field(default_factory=list, max_length=1024)
    matches: list[ArchiveMatchIn] = Field(default_factory=list, max_length=2000)

    _n = field_validator("name", "format", "organizer", "tier")(_clean)

    @model_validator(mode="after")
    def _dates(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("A data de término não pode ser antes da de início.")
        return self


class PlayerOutRef(BaseModel):
    user_id: int | None
    name: str


class PlacementOut(PlayerOutRef):
    position: int
    label: str | None


class ArchiveMatchOut(BaseModel):
    id: int
    stage_label: str
    number: int | None
    player1: PlayerOutRef
    player2: PlayerOutRef
    winner: int | None
    replay_url: str | None


class SeriesRef(BaseModel):
    id: int
    name: str


class ArchiveSummary(BaseModel):
    id: int
    name: str
    tournament_id: int | None  # preenchido = jogado na plataforma
    start_date: date | None
    end_date: date | None
    format: str | None
    players_count: int | None
    series: SeriesRef | None
    edition: int | None
    champion: PlayerOutRef | None


class ArchiveDetail(ArchiveSummary):
    organizer: str | None
    tier: str | None
    rules_text: str | None
    description: str | None
    links: list[LinkIn]
    placements: list[PlacementOut]
    matches: list[ArchiveMatchOut]
    created_at: datetime
    updated_at: datetime


class SeriesIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(None, max_length=5000)

    _n = field_validator("name")(_clean)


class SeriesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None


class SeriesDetail(SeriesOut):
    editions: list[ArchiveSummary]  # da mais recente para a mais antiga


class DeleteArchiveIn(BaseModel):
    """Remover do acervo apaga o torneio de vez: o admin confirma digitando o nome."""

    confirm_name: str
