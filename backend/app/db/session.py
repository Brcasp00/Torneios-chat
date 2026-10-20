from collections.abc import AsyncIterator
from uuid import uuid4

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_url = get_settings().async_database_url

_kwargs: dict = {"pool_pre_ping": True}
if _url.startswith("postgresql"):
    # Supabase pooler (pgbouncer em modo transaction) não suporta prepared statements: cada comando pode cair em
    # outra conexão real. Além do cache do asyncpg, o dialeto do SQLAlchemy tem um cache próprio que também precisa
    # ser desligado, senão aparece "prepared statement ... does not exist" de forma intermitente.
    _url = make_url(_url).update_query_pairs([("prepared_statement_cache_size", "0")]).render_as_string(hide_password=False)
    _kwargs["connect_args"] = {
        "ssl": "require",  # conexão sempre criptografada (o padrão "prefer" aceitaria cair para texto puro)
        "statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    }
    _kwargs.update(pool_size=5, max_overflow=5)

engine = create_async_engine(_url, **_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
