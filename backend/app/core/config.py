import re
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _asyncpg_url(url: str) -> str:
    url = url.strip().strip("\"'")
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+asyncpg://", url)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")

    database_url: str
    # Opcional: se vazio, deriva de database_url trocando a porta 6543 (transaction pooler) por 5432 (session pooler).
    database_url_migrations: str = ""
    jwt_secret: str = "troque-esta-chave-em-producao"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def async_database_url(self) -> str:
        return _asyncpg_url(self.database_url)

    @property
    def migrations_database_url(self) -> str:
        url = self.database_url_migrations or self.database_url.replace(":6543/", ":5432/")
        return _asyncpg_url(url)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
