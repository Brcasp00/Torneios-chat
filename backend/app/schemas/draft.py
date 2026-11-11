"""Draft Pokémon (Modo Carreira): lote, clubes e movimentações. Dinheiro em euros inteiros."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.calculator import MAXM, EconomyConfig
from app.schemas.match import PlayerRef

Position = Literal["defensor", "meio", "atacante"]


class DraftSetupIn(BaseModel):
    regions: list[str] = Field(min_length=1, max_length=12, description="Regiões do lote (ex.: ['Kanto', 'Johto'])")
    economy: EconomyConfig | None = Field(None, description="Valores econômicos (padrão: os do arquivo de configuração)")


class AddPokemonIn(BaseModel):
    species_ids: list[str] = Field(min_length=1, max_length=600)


class UpdatePokemonIn(BaseModel):
    draft_tier: str | None = Field(None, max_length=10)
    price: int | None = Field(None, ge=0, le=MAXM)
    positions: list[Position] = Field(default_factory=list, max_length=3)
    costs: dict[Position, int] = Field(default_factory=dict)

    @field_validator("costs")
    @classmethod
    def _costs(cls, v: dict) -> dict:
        if any(not 0 <= x <= 100 for x in v.values()):
            raise ValueError("O custo em pontos de cada posição deve ficar entre 0 e 100.")
        return v

    @field_validator("positions")
    @classmethod
    def _unique(cls, v: list) -> list:
        return list(dict.fromkeys(v))


class AssignIn(BaseModel):
    user_id: int
    price: int = Field(ge=0, le=MAXM, description="Valor pago (euros)")
    via: Literal["auction", "market"] = "auction"
    allow_negative: bool = Field(False, description="Registrar mesmo que o caixa fique negativo")
    note: str | None = Field(None, max_length=300)


class NoteIn(BaseModel):
    note: str | None = Field(None, max_length=300)


class AdjustIn(BaseModel):
    user_id: int
    amount: int = Field(ge=-MAXM, le=MAXM, description="Positivo entra no caixa; negativo sai")
    note: str = Field(min_length=3, max_length=300)


class SponsorsIn(BaseModel):
    sponsors: list[str] = Field(default_factory=list, max_length=20)


class DraftPokemonOut(BaseModel):
    id: int
    species_id: str
    name: str
    num: int | None = None
    types: list[str] = []
    region: str | None = None
    tier9: str | None = None  # referência Smogon: Gen 9 National Dex
    tier7: str | None = None  # referência Smogon: Gen 7
    draft_tier: str | None
    price: int | None
    positions: list[str]
    costs: dict[str, int]
    owner: PlayerRef | None
    contract_price: int | None
    salary: int | None  # por rodada jogada
    acquired_via: str | None
    acquired_at: datetime | None
    registered: bool


class TransactionOut(BaseModel):
    id: int
    user: PlayerRef | None
    kind: str
    amount: int
    pokemon_id: int | None
    pokemon_name: str | None
    round: int | None
    note: str | None
    created_by: PlayerRef | None
    created_at: datetime


class ClubOut(BaseModel):
    user: PlayerRef
    cash: int
    transferban: bool
    squad_count: int
    registered_count: int
    squad_value: int
    salary_per_round: int
    sponsors: list[str]
    ct_level: int


class DraftOverview(BaseModel):
    enabled: bool
    regions: list[str] = []
    economy: EconomyConfig | None = None
    clubs: list[ClubOut] = []
    lote_count: int = 0
    free_count: int = 0
    can_manage: bool = False


class PokemonDetail(DraftPokemonOut):
    transactions: list[TransactionOut]


class ClubDetail(ClubOut):
    squad: list[DraftPokemonOut]
    transactions: list[TransactionOut]
    can_edit: bool = False
