from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PlayerRef(BaseModel):
    id: int
    name: str


class ReportIn(BaseModel):
    p1_wins: int = Field(ge=0, le=4, description="Vitórias do jogador 1 (jogos ganhos na série)")
    p2_wins: int = Field(ge=0, le=4)
    p1_remaining: int = Field(0, ge=0, le=6, description="Pokémon vivos do jogador 1 ao fim do jogo")
    p2_remaining: int = Field(0, ge=0, le=6)
    replay_urls: list[str] = Field(default_factory=list, max_length=7)
    notes: str | None = Field(None, max_length=1000)


class ResultIn(ReportIn):
    """Resultado lançado direto por admin/organizador (sem reporte de jogador)."""

    is_draw: bool = False


class ValidateIn(BaseModel):
    report_id: int | None = None  # padrão: o reporte pendente mais recente
    is_draw: bool = False  # admin marca como empate
    note: str | None = Field(None, max_length=500)


class NoteIn(BaseModel):
    note: str | None = Field(None, max_length=500)


class WalkoverIn(BaseModel):
    winner_id: int
    note: str | None = Field(None, max_length=500)


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reported_by: int | None
    p1_wins: int
    p2_wins: int
    p1_remaining: int
    p2_remaining: int
    replay_urls: list | None
    notes: str | None
    status: str
    created_at: datetime
    reviewed_by: int | None
    reviewed_at: datetime | None
    review_note: str | None


class MatchOut(BaseModel):
    id: int
    tournament_id: int
    stage_id: int
    round: int
    group_label: str | None
    leg: int
    best_of: int
    status: str
    player1: PlayerRef | None
    player2: PlayerRef | None
    p1_wins: int | None
    p2_wins: int | None
    p1_remaining: int | None
    p2_remaining: int | None
    winner_id: int | None
    is_draw: bool
    is_walkover: bool
    validated_at: datetime | None
    has_pending_report: bool = False


class MatchDetail(MatchOut):
    tournament_name: str
    tournament_status: str
    stage_name: str
    battle_rules: dict | None
    reports: list[ReportOut]
    can_report: bool = False
    can_manage: bool = False


class StandingRow(BaseModel):
    position: int
    user_id: int
    name: str
    withdrawn: bool
    played: int
    wins: int
    draws: int
    losses: int
    points: int
    saldo: int


class StageStandings(BaseModel):
    stage_id: int
    stage_name: str
    stage_type: str
    rows: list[StandingRow]


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage_id: int | None
    reason: str | None
    triggered_by_match_id: int | None
    created_at: datetime


class SnapshotDetail(SnapshotOut):
    data: dict


class DrawIn(BaseModel):
    seed: int | None = Field(None, ge=1, lt=2**31, description="Semente do sorteio (omita para sortear uma nova)")


class DrawMatch(BaseModel):
    player1: PlayerRef
    player2: PlayerRef
    leg: int


class DrawRound(BaseModel):
    round: int
    matches: list[DrawMatch]


class DrawOut(BaseModel):
    seed: int
    rounds: list[DrawRound]
