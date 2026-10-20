from datetime import datetime

from pydantic import BaseModel


class AuditOut(BaseModel):
    id: int
    created_at: datetime
    actor_id: int | None
    actor_name: str | None
    action: str
    entity: str
    entity_id: int | None
    data: dict | None


class AuditPage(BaseModel):
    total: int
    items: list[AuditOut]


class TimelineEvent(BaseModel):
    """Evento da história de um confronto (reporte, revisão ou ação do admin), em ordem cronológica."""

    at: datetime
    kind: str  # report | review | action
    actor_id: int | None
    actor_name: str | None
    action: str
    data: dict | None = None
