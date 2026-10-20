from datetime import datetime

from sqlalchemy import DateTime, JSON, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Nomes determinísticos para constraints (necessário para migrations estáveis).
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# JSONB no Postgres, JSON genérico em outros bancos (testes com SQLite).
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

# bigint no Postgres; INTEGER no SQLite (necessário para autoincrement nos testes).
from sqlalchemy import BigInteger, Integer  # noqa: E402

BigIntPK = BigInteger().with_variant(Integer(), "sqlite")
