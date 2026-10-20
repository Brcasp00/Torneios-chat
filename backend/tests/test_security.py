"""Bloqueio de login por tentativas erradas, exigência de JWT_SECRET forte e limites de paginação."""
import pytest
from pydantic import ValidationError

from app.core import login_guard
from app.core.config import Settings
from tests.test_auth_users import auth, login, register


async def test_three_wrong_passwords_lock_the_account(client, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(login_guard, "_clock", lambda: clock[0])
    await register(client)
    for _ in range(3):
        assert (await login(client, "Ash", "errada")).status_code == 401
    # bloqueado: nem a senha certa entra (o nome não diferencia maiúsculas/espaços)
    r = await login(client, "  ash ", "pikachu1")
    assert r.status_code == 429 and "10 minuto" in r.json()["detail"] and r.headers["Retry-After"] == "600"
    clock[0] += 9 * 60
    assert (await login(client, "Ash", "pikachu1")).status_code == 429
    clock[0] += 61
    assert (await login(client, "Ash", "pikachu1")).status_code == 200


async def test_success_resets_and_old_failures_expire(client, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(login_guard, "_clock", lambda: clock[0])
    await register(client)
    for _ in range(2):
        await login(client, "Ash", "errada")
    assert (await login(client, "Ash", "pikachu1")).status_code == 200  # zera a contagem
    for _ in range(2):
        await login(client, "Ash", "errada")
    clock[0] += 11 * 60  # falhas de mais de 10 min atrás não contam
    await login(client, "Ash", "errada")
    assert (await login(client, "Ash", "pikachu1")).status_code == 200


async def test_unknown_names_are_locked_too_and_admin_reset_unlocks(client):
    for _ in range(3):
        assert (await login(client, "Ninguem", "x")).status_code == 401
    assert (await login(client, "Ninguem", "x")).status_code == 429  # não revela se a conta existe

    uid = (await register(client)).json()["user"]["id"]
    for _ in range(3):
        await login(client, "Ash", "errada")
    assert (await login(client, "Ash", "pikachu1")).status_code == 429
    adm = (await login(client, "Admin", "admin123")).json()["access_token"]  # outras contas não são afetadas
    r = await client.post(f"/users/{uid}/reset-password", json={"new_password": "nova12345"}, headers=auth(adm))
    assert r.status_code == 200
    assert (await login(client, "Ash", "nova12345")).status_code == 200


async def _with_db(fn):
    """Roda `fn(session)` numa sessão própria do banco de teste, fechada logo em seguida."""
    from app.db.session import get_session
    from app.main import app

    async for s in app.dependency_overrides[get_session]():
        return await fn(s)


async def test_old_short_password_must_be_changed_and_hash_is_upgraded(client):
    from argon2 import PasswordHasher
    from sqlalchemy import select

    from app.core.security import needs_rehash
    from app.models import User

    old_hash = PasswordHasher().hash("123456")  # parâmetros antigos (64 MiB) e senha abaixo do mínimo atual
    assert needs_rehash(old_hash)

    async def insert(s):
        s.add(User(name="Antigo", password_hash=old_hash, role="player"))
        await s.commit()

    async def stored_hash(s):
        return (await s.scalars(select(User).where(User.name == "Antigo"))).one().password_hash

    await _with_db(insert)

    r = await login(client, "Antigo", "123456")
    assert r.status_code == 200 and r.json()["user"]["must_change_password"] is True
    tok = r.json()["access_token"]
    r = await client.post("/tournaments/1/withdraw", headers=auth(tok))
    assert r.status_code == 403 and "8 caracteres" in r.json()["detail"]
    stored = await _with_db(stored_hash)
    assert stored != old_hash and not needs_rehash(stored)

    # a senha nova também precisa ter 8+; depois disso a conta volta ao normal
    body = {"current_password": "123456", "new_password": "1234567"}
    assert (await client.post("/auth/change-password", json=body, headers=auth(tok))).status_code == 422
    body["new_password"] = "senhaforte1"
    assert (await client.post("/auth/change-password", json=body, headers=auth(tok))).status_code == 204
    assert (await login(client, "Antigo", "senhaforte1")).json()["user"]["must_change_password"] is False


async def test_new_passwords_need_eight_characters(client):
    assert (await register(client, "Curta", "1234567")).status_code == 422
    assert (await register(client, "Longa", "12345678")).status_code == 201


def test_jwt_secret_must_be_strong():
    for bad in ("troque-esta-chave-em-producao", "curta", ""):
        with pytest.raises(ValidationError):
            Settings(database_url="sqlite+aiosqlite://", jwt_secret=bad)
    assert Settings(database_url="sqlite+aiosqlite://", jwt_secret="x" * 32).jwt_secret == "x" * 32


async def test_negative_pagination_is_rejected(client):
    for path in ("/users?limit=-1", "/users?offset=-1", "/tournaments?limit=0", "/tournaments?offset=-5"):
        assert (await client.get(path)).status_code == 422
    assert (await client.get("/users?limit=5000")).status_code == 200  # valores grandes continuam limitados no servidor
