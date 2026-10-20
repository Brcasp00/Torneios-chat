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
    slot: int | None = None
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
    postponed: bool = False
    postponed_reason: str | None = None
    deadline: datetime | None = None  # fim do prazo da rodada deste confronto, se definido
    overdue: bool = False  # prazo vencido e ainda sem resultado/reporte (aviso para o admin)
    auto_result: bool = False  # empate marcado automaticamente por vencimento do prazo
    deadline_waived: bool = False  # admin liberou a entrega atrasada


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


class GroupTable(BaseModel):
    label: str
    rows: list[StandingRow]


class StageStandings(BaseModel):
    stage_id: int
    stage_name: str
    stage_type: str
    rows: list[StandingRow]  # pontos corridos
    groups: list[GroupTable] = []  # fase de grupos


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage_id: int | None
    reason: str | None
    triggered_by_match_id: int | None
    kind: str = "change"
    round: int | None = None
    created_at: datetime


class SnapshotDetail(SnapshotOut):
    tournament_id: int
    data: dict


class RoundHistory(BaseModel):
    """Tabela congelada ao fim de uma rodada (liga/grupos)."""

    snapshot_id: int
    tournament_id: int
    stage_id: int
    stage_name: str
    round: int
    created_at: datetime
    reopened: bool = False  # a rodada voltou a ter jogo em aberto depois de registrada
    postponed: list[dict] = []  # jogos adiados ainda pendentes quando a tabela foi gravada
    played_postponed: list[dict] = []  # jogos adiados que foram disputados e entram nesta tabela
    data: dict


class StageHistory(BaseModel):
    """Estado final de uma fase (do torneio ou de um subtorneio): tabela, grupos ou chaveamento."""

    snapshot_id: int
    tournament_id: int
    tournament_name: str
    stage_id: int
    stage_name: str
    stage_type: str
    created_at: datetime
    versions: int  # 1 = nunca corrigida depois de encerrar
    data: dict


class PostponeIn(BaseModel):
    reason: str | None = Field(None, max_length=300)


class RoundPostponeIn(PostponeIn):
    stage_id: int
    round: int = Field(ge=1)
    group_label: str | None = Field(None, max_length=8, description="Em fase de grupos: só este grupo (padrão: todos)")


class Arrangement(BaseModel):
    """Arranjo manual da 1ª fase (use somente o campo que se aplica ao tipo da fase)."""

    slots: list[int] | None = Field(None, description="Mata-mata: jogadores na ordem do chaveamento (pares adjacentes se enfrentam)")
    groups: dict[str, list[int]] | None = Field(None, description="Grupos: {'A': [ids], 'B': [ids]}")
    pairs: list[list[int]] | None = Field(None, description="Rodada única/playoff: [[id, id], ...]")


class DrawIn(BaseModel):
    seed: int | None = Field(None, ge=1, lt=2**31, description="Semente do sorteio (omita para sortear uma nova)")
    use_pots: bool = Field(True, description="Usar os potes definidos (se houver)")
    arrangement: Arrangement | None = Field(None, description="Sorteio manual: substitui o sorteio aleatório")


class DrawMatch(BaseModel):
    player1: PlayerRef
    player2: PlayerRef
    leg: int
    group_label: str | None = None


class DrawRound(BaseModel):
    round: int
    matches: list[DrawMatch]


class DrawOut(BaseModel):
    seed: int
    mode: str = "random"
    rounds: list[DrawRound]
    arrangement: Arrangement | None = None  # reenvie (após ajustar) em /start para sortear manualmente


class PotAssignment(BaseModel):
    user_id: int
    pot: int | None = Field(None, ge=1, le=8, description="1 = pote mais forte; null remove o pote")


class PotsIn(BaseModel):
    assignments: list[PotAssignment] = Field(min_length=1, max_length=256)


class DrawRecord(BaseModel):
    seed: int
    mode: str
    drawn_at: datetime | None = None
    drawn_by: int | None = None
    pots: dict[str, int] = {}
    arrangement: Arrangement | None = None
    players: list[PlayerRef] = []


class BracketRound(BaseModel):
    round: int
    name: str
    matches: list[MatchOut]


class BracketStage(BaseModel):
    stage_id: int
    stage_name: str
    status: str
    rounds: list[BracketRound]
    third_place: MatchOut | None = None
    champion: PlayerRef | None = None


class DeadlinesIn(BaseModel):
    """Prazos por rodada: {"1": "2026-11-01T21:00:00-03:00", "2": null}. null remove o prazo da rodada."""

    deadlines: dict[int, datetime | None]
