"""Calculadora de custos da temporada (Draft). Dinheiro em euros inteiros; percentuais em pontos-base (500 = 5%)."""
from typing import Literal

from pydantic import BaseModel, Field

Money = int
MAXM = 10**12  # teto para qualquer valor em euros (evita números absurdos)


class EconomyConfig(BaseModel):
    label: str = Field("", max_length=120)
    initial_budget: int = Field(ge=0, le=MAXM)
    sponsors: int = Field(ge=0, le=20)
    win_per_sponsor: int = Field(ge=0, le=MAXM)
    draw_per_sponsor: int = Field(ge=0, le=MAXM)
    loss_per_sponsor: int = Field(ge=0, le=MAXM)
    wo_fine: int = Field(ge=0, le=MAXM)
    salary_rate_bp: int = Field(ge=0, le=10_000)
    registration_step: int = Field(ge=0, le=MAXM)
    registration_free_slots: int = Field(ge=0, le=30)
    registration_charge: Literal["season", "round"]
    max_squad: int = Field(ge=1, le=60)
    max_registered: int = Field(ge=1, le=60)
    ct_build: list[int] = Field(min_length=4, max_length=4)
    ct_maintenance: list[int] = Field(min_length=4, max_length=4)
    ct_parallel: list[int] = Field(min_length=4, max_length=4)
    ct_min_level: dict[str, int] = Field(default_factory=lambda: {"extra": 1, "opt": 2})
    training_extra_bp: int = Field(ge=0, le=10_000)
    training_opt_bp: int = Field(ge=0, le=10_000)
    tier_order: list[str] = Field(max_length=20)
    tier_prices: dict[str, int | None]
    market_premium: int = Field(ge=0, le=MAXM)
    league_rounds: int = Field(ge=0, le=100)
    knockout_rounds: int = Field(ge=0, le=10)
    league_label: str = Field("Liga", max_length=40)
    knockout_label: str = Field("Mata-mata", max_length=40)
    prizes: list[int] = Field(default_factory=list, max_length=64)


class SquadItem(BaseModel):
    name: str = Field("", max_length=60)
    price: int = Field(ge=0, le=MAXM)
    tier: str | None = Field(None, max_length=10)
    registered: bool = False


class CTIn(BaseModel):
    current_level: int = Field(0, ge=0, le=3)
    target_level: int | None = Field(None, ge=1, le=3)  # vazio = não vai construir/melhorar
    build_round: int | None = Field(None, ge=1, le=200)


class TrainingIn(BaseModel):
    pokemon: int = Field(ge=0, le=99, description="Índice do Pokémon no elenco")
    kind: Literal["extra", "opt"]  # posição extra | otimização
    round: int = Field(ge=1, le=200)


Result = Literal["W", "D", "L", "WO", "-"]  # vitória, empate, derrota, W.O. perdido, ainda não jogada


class ResultsIn(BaseModel):
    mode: Literal["simple", "detailed"] = "simple"
    wins: int = Field(0, ge=0, le=200)
    draws: int = Field(0, ge=0, le=200)
    wo: int = Field(0, ge=0, le=200)
    per_round: list[Result] = Field(default_factory=list, max_length=200)


class CalcIn(BaseModel):
    config: EconomyConfig
    squad: list[SquadItem] = Field(default_factory=list, max_length=60)
    ct: CTIn = Field(default_factory=CTIn)
    trainings: list[TrainingIn] = Field(default_factory=list, max_length=60)
    results: ResultsIn = Field(default_factory=ResultsIn)
    knockout_played: int = Field(0, ge=0, le=10, description="Rodadas do mata-mata que o jogador disputa")
    placement: int | None = Field(None, ge=1, le=64, description="Colocação final (para o prêmio)")


class RoundRow(BaseModel):
    round: int
    phase: str
    played: bool
    result: str | None = None
    salaries: Money = 0
    registration: Money = 0
    ct_maintenance: Money = 0
    ct_build: Money = 0
    trainings: Money = 0
    fine: Money = 0
    cost: Money = 0
    income: Money = 0
    prize: Money = 0
    balance: Money = 0
    cash: Money = 0


class Totals(BaseModel):
    salaries: Money = 0
    registration: Money = 0
    ct_maintenance: Money = 0
    ct_build: Money = 0
    trainings: Money = 0
    fine: Money = 0
    cost: Money = 0
    income: Money = 0
    income_wins: Money = 0
    income_draws: Money = 0
    income_losses: Money = 0
    prize: Money = 0
    balance: Money = 0


class CalcOut(BaseModel):
    rounds_total: int
    rounds_played: int
    squad_count: int
    registered_count: int
    squad_value: Money
    start_cash: Money
    final_cash: Money
    totals: Totals
    rows: list[RoundRow]
    first_negative_round: int | None
    breakeven_exact: float | None  # vitórias necessárias (sem arredondar), em cenário sem empates e sem W.O.
    breakeven_wins: int | None  # arredondado para cima
    breakeven_impossible: bool = False
    win_value: Money
    draw_value: Money
    loss_value: Money
    errors: list[str]
    warnings: list[str]
    notes: list[str]
