import re
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_JWT_SECRET = "troque-esta-chave-em-producao"

def _asyncpg_url(url: str) -> str:
    url = url.strip().strip("\"'")
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+asyncpg://", url)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8-sig", extra="ignore")

    database_url: str
    # Opcional: se vazio, deriva de database_url trocando a porta 6543 (transaction pooler) por 5432 (session pooler).
    database_url_migrations: str = ""
    jwt_secret: str = _DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    # Cadastro público (/auth/register). Fechado por padrão: só o admin cria contas.
    allow_registration: bool = False
    # Cloudflare Turnstile (verificação anti-robô no cadastro). Com as duas chaves, o cadastro exige a verificação.
    turnstile_site_key: str = ""  # pública: o site a usa para mostrar a caixinha
    turnstile_secret: str = ""  # secreta: só a API a usa para conferir o comprovante

    @property
    def turnstile_enabled(self) -> bool:
        return bool(self.turnstile_site_key.strip() and self.turnstile_secret.strip())

    @field_validator("jwt_secret")
    @classmethod
    def _strong_secret(cls, v: str) -> str:
        # Com a chave padrão (ou curta) qualquer um poderia fabricar um token de admin: a API se recusa a iniciar.
        v = v.strip()
        if v == _DEFAULT_JWT_SECRET or len(v) < 32:
            raise ValueError(
                "JWT_SECRET ausente, padrão ou curta demais (mínimo 32 caracteres). Gere uma com: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return v

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
