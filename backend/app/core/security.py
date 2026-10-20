from datetime import datetime, timedelta, timezone

import anyio
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

# Parâmetros mínimos recomendados pela OWASP para argon2id (19 MiB, 2 passadas, 1 via). O padrão da biblioteca
# (64 MiB por cálculo) pesa demais no plano gratuito do Render. Hashes antigos continuam válidos (cada hash guarda os
# próprios parâmetros) e são refeitos no próximo login (`needs_rehash`).
MIN_PASSWORD_LENGTH = 8
_hasher = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)

# No máximo 2 cálculos de senha ao mesmo tempo; os demais esperam na fila (protege a memória do servidor).
_limiter = anyio.CapacityLimiter(2)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return False


# Versões para as rotas: o cálculo (lento de propósito) roda numa thread separada, sem travar a API para os outros.
async def hash_password_async(password: str) -> str:
    return await anyio.to_thread.run_sync(hash_password, password, limiter=_limiter)


async def verify_password_async(password: str, password_hash: str) -> bool:
    return await anyio.to_thread.run_sync(verify_password, password, password_hash, limiter=_limiter)


def create_access_token(user_id: int, role: str) -> str:
    s = get_settings()
    now = now_utc()
    exp = now + timedelta(minutes=s.access_token_minutes)
    payload = {"sub": str(user_id), "role": role, "iat": int(now.timestamp()), "exp": exp}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def issued_before_password_change(payload: dict, password_changed_at: datetime | None) -> bool:
    """O crachá foi emitido antes da última troca de senha? Então não vale mais (quem tinha a senha antiga sai).

    Compara em segundos inteiros (precisão do `iat`): o crachá novo devolvido na própria troca continua valendo.
    Crachás antigos, sem `iat`, deixam de valer assim que a senha é trocada.
    """
    if password_changed_at is None:
        return False
    if password_changed_at.tzinfo is None:  # SQLite (testes) devolve sem fuso
        password_changed_at = password_changed_at.replace(tzinfo=timezone.utc)
    iat = payload.get("iat")
    return not isinstance(iat, int) or iat < int(password_changed_at.timestamp())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def decode_access_token(token: str) -> dict | None:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError:
        return None
