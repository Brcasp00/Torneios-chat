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


def test_jwt_secret_must_be_strong():
    for bad in ("troque-esta-chave-em-producao", "curta", ""):
        with pytest.raises(ValidationError):
            Settings(database_url="sqlite+aiosqlite://", jwt_secret=bad)
    assert Settings(database_url="sqlite+aiosqlite://", jwt_secret="x" * 32).jwt_secret == "x" * 32


async def test_negative_pagination_is_rejected(client):
    for path in ("/users?limit=-1", "/users?offset=-1", "/tournaments?limit=0", "/tournaments?offset=-5"):
        assert (await client.get(path)).status_code == 422
    assert (await client.get("/users?limit=5000")).status_code == 200  # valores grandes continuam limitados no servidor
