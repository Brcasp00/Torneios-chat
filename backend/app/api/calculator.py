"""Calculadora de custos da temporada (Draft). Pública: simulação livre, não lê nem grava no banco."""
from fastapi import APIRouter

from app.schemas.calculator import CalcIn, CalcOut, EconomyConfig
from app.services import calculator, draft_config

router = APIRouter(prefix="/calculator", tags=["calculator"])


@router.get("/presets")
async def presets() -> dict:
    """Modelos de configuração (valores do arquivo `services/draft_config.py`)."""
    return {
        "default": draft_config.DEFAULT_PRESET,
        "presets": {k: EconomyConfig(**v).model_dump() for k, v in draft_config.PRESETS.items()},
    }


@router.post("", response_model=CalcOut)
async def calculate(data: CalcIn) -> CalcOut:
    return calculator.compute(data)
