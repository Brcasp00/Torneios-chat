from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Template = Literal["league", "knockout", "groups_knockout", "custom"]
Status = Literal["draft", "registration", "running", "finished", "cancelled"]
StageType = Literal["round", "league", "groups", "knockout", "playoff"]
RuleSource = Literal["ranking", "winners", "losers", "group_position"]
RuleTarget = Literal["stage", "eliminated", "repechage", "parent_tournament"]


class BattleRules(BaseModel):
    """Regras estruturadas de batalha (o texto livre fica em rules_text)."""

    format: str | None = Field(None, max_length=40, description="Ex.: singles, doubles")
    game: str | None = Field(None, max_length=60, description="Ex.: Gen 9, Scarlet/Violet")
    tier: str | None = Field(None, max_length=40, description="Ex.: OU, VGC Reg G")
    team_size: int | None = Field(None, ge=1, le=6)
    bring: int | None = Field(None, ge=1, le=6, description="Quantos Pokémon levar para a batalha")
    level_cap: int | None = Field(None, ge=1, le=100)
    timer: bool | None = None
    clauses: list[str] = Field(default_factory=list, max_length=30)
    showdown_required: bool = True  # replay do Showdown obrigatório no reporte


class TournamentConfig(BaseModel):
    points_win: int = Field(3, ge=0, le=10)
    points_draw: int = Field(1, ge=0, le=10)
    points_loss: int = Field(0, ge=0, le=10)
    walkover_score: int = Field(3, ge=1, le=6, description="W.O. conta como vitória por N a 0")
    allow_draw: bool | None = None  # padrão: True em pontos corridos/grupos, False em mata-mata
    best_of: Literal[1, 3, 5, 7] = 1
    double_round: bool = False  # turno e returno
    third_place: bool = False  # disputa de 3º lugar (mata-mata)
    groups_count: int | None = Field(None, ge=2, le=32)
    qualifiers_per_group: int = Field(2, ge=1, le=16)
    repechage_position: int | None = Field(None, ge=1, le=16, description="Ex.: 3 = o 3º de cada grupo vai à repescagem")
    repechage_slots: int = Field(0, ge=0, le=64, description="Vagas do mata-mata reservadas a quem volta de um subtorneio")
    tiebreakers: list[Literal["saldo", "vitorias", "confronto_direto"]] = ["saldo", "vitorias", "confronto_direto"]


class StageIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: StageType
    config: dict = Field(default_factory=dict)


class RuleIn(BaseModel):
    """Regra de passagem. As fases são referenciadas pela posição (1 = primeira fase)."""

    from_stage: int = Field(ge=1)
    source: RuleSource = "ranking"
    pos_from: int = Field(ge=1)
    pos_to: int = Field(ge=1)
    target: RuleTarget
    to_stage: int | None = Field(None, ge=1)
    to_slot_from: int | None = Field(None, ge=1)
    parent_stage: int | None = Field(None, ge=1, description="Posição da fase no torneio principal (subtorneios)")
    config: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self):
        if self.pos_to < self.pos_from:
            raise ValueError("pos_to deve ser maior ou igual a pos_from.")
        if self.target == "stage" and (self.to_stage is None or self.to_slot_from is None):
            raise ValueError("Destino 'stage' exige to_stage e to_slot_from.")
        if self.target == "parent_tournament" and (self.parent_stage is None or self.to_slot_from is None):
            raise ValueError("Destino 'parent_tournament' exige parent_stage e to_slot_from.")
        return self


class TournamentCreate(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    template: Template
    max_players: int = Field(ge=2, le=256)
    battle_rules: BattleRules = Field(default_factory=BattleRules)
    rules_text: str | None = Field(None, max_length=5000)
    config: TournamentConfig = Field(default_factory=TournamentConfig)
    # Somente para template "custom":
    stages: list[StageIn] = Field(default_factory=list, max_length=12)
    rules: list[RuleIn] = Field(default_factory=list, max_length=60)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return " ".join(v.split())

    @model_validator(mode="after")
    def _custom(self):
        if self.template == "custom" and not self.stages:
            raise ValueError("Template 'custom' exige ao menos uma fase em 'stages'.")
        if self.template != "custom" and (self.stages or self.rules):
            raise ValueError("'stages' e 'rules' só podem ser usados com template 'custom'.")
        return self


class TournamentUpdate(BaseModel):
    name: str | None = Field(None, min_length=3, max_length=120)
    max_players: int | None = Field(None, ge=2, le=256)
    battle_rules: BattleRules | None = None
    rules_text: str | None = Field(None, max_length=5000)
    config: TournamentConfig | None = None


class StatusIn(BaseModel):
    status: Status


class AddPlayersIn(BaseModel):
    user_ids: list[int] = Field(min_length=1, max_length=256)


class StageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    position: int
    name: str
    type: str
    config: dict | None
    status: str


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_stage_id: int
    source: str
    pos_from: int
    pos_to: int
    target: str
    to_stage_id: int | None
    to_slot_from: int | None
    config: dict | None


class PlayerOut(BaseModel):
    user_id: int
    name: str
    seed: int | None
    group_label: str | None
    pot: int | None = None
    status: str


class TournamentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    template: str
    max_players: int
    status: str
    parent_id: int | None
    created_at: datetime
    players_count: int = 0


class LinkSubIn(BaseModel):
    subtournament_id: int | None = None  # None desfaz a ligação explícita (volta ao "único subtorneio", se houver)


class RepechageOut(BaseModel):
    """Regra de repescagem: de qual fase vêm os candidatos e para qual subtorneio vão."""

    rule_id: int
    stage_id: int
    subtournament_id: int | None
    user_ids: list[int]  # candidatos já definidos (vazio enquanto a fase de origem não terminou)


class TournamentDetail(TournamentSummary):
    battle_rules: dict | None
    rules_text: str | None
    config: dict | None
    created_by: int | None
    stages: list[StageOut]
    rules: list[RuleOut]
    players: list[PlayerOut]
    subtournaments: list[TournamentSummary]
    repechage: list[RepechageOut] = []
    parent: TournamentSummary | None = None
    can_manage: bool = False
