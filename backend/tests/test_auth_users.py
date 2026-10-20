import pytest

pytestmark = pytest.mark.asyncio


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def register(client, name="Ash", password="pikachu1"):
    r = await client.post("/auth/register", json={"name": name, "password": password})
    return r


async def login(client, name, password):
    return await client.post("/auth/login", json={"name": name, "password": password})


async def test_register_and_login(client):
    r = await register(client)
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "player"
    r = await login(client, "ash", "pikachu1")  # nome sem diferenciar maiúsculas
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = await client.get("/auth/me", headers=auth(token))
    assert me.json()["name"] == "Ash"
    assert "password_hash" not in me.json()


async def test_duplicate_name_case_insensitive(client):
    await register(client, "Misty")
    r = await register(client, "MISTY")
    assert r.status_code == 409


async def test_invalid_inputs(client):
    assert (await register(client, "ab")).status_code == 422
    assert (await register(client, "Brock", "123")).status_code == 422


async def test_wrong_password_and_unknown_user(client):
    await register(client)
    assert (await login(client, "Ash", "errada")).status_code == 401
    assert (await login(client, "Ninguem", "x")).status_code == 401


async def test_me_requires_auth(client):
    assert (await client.get("/auth/me")).status_code == 401
    assert (await client.get("/auth/me", headers=auth("lixo"))).status_code == 401


async def test_player_cannot_use_admin_endpoints(client):
    tok = (await register(client)).json()["access_token"]
    assert (await client.get("/users/admin", headers=auth(tok))).status_code == 403
    assert (await client.post("/users/1/reset-password", json={}, headers=auth(tok))).status_code == 403
    assert (await client.patch("/users/2/role", json={"role": "admin"}, headers=auth(tok))).status_code == 403


async def test_admin_reset_password(client):
    reg = (await register(client)).json()
    admin_tok = (await login(client, "Admin", "admin123")).json()["access_token"]
    r = await client.post(f"/users/{reg['user']['id']}/reset-password", json={}, headers=auth(admin_tok))
    assert r.status_code == 200
    temp = r.json()["temporary_password"]
    assert temp
    assert (await login(client, "Ash", "pikachu1")).status_code == 401
    assert (await login(client, "Ash", temp)).status_code == 200


async def test_admin_set_role_and_deactivate(client):
    reg = (await register(client)).json()
    uid = reg["user"]["id"]
    admin_tok = (await login(client, "Admin", "admin123")).json()["access_token"]
    r = await client.patch(f"/users/{uid}/role", json={"role": "organizer"}, headers=auth(admin_tok))
    assert r.json()["role"] == "organizer"
    r = await client.patch(f"/users/{uid}/active", json={"is_active": False}, headers=auth(admin_tok))
    assert r.json()["is_active"] is False
    assert (await login(client, "Ash", "pikachu1")).status_code == 401
    # token antigo também deixa de valer
    assert (await client.get("/auth/me", headers=auth(reg["access_token"]))).status_code == 401


async def test_admin_cannot_demote_self(client):
    admin_tok = (await login(client, "Admin", "admin123")).json()["access_token"]
    r = await client.patch("/users/1/role", json={"role": "player"}, headers=auth(admin_tok))
    assert r.status_code == 400


async def test_public_user_list_hides_sensitive_data(client):
    await register(client, "Gary")
    r = await client.get("/users", params={"q": "gar"})
    assert r.status_code == 200
    assert r.json() == [{"id": r.json()[0]["id"], "name": "Gary"}]


async def test_change_password(client):
    tok = (await register(client)).json()["access_token"]
    r = await client.post("/auth/change-password", json={"current_password": "x", "new_password": "novasenha"}, headers=auth(tok))
    assert r.status_code == 400
    r = await client.post("/auth/change-password", json={"current_password": "pikachu1", "new_password": "novasenha"}, headers=auth(tok))
    assert r.status_code == 204
    assert (await login(client, "Ash", "novasenha")).status_code == 200


async def test_admin_creates_user(client):
    adm = (await client.post("/auth/login", json={"name": "Admin", "password": "admin123"})).json()["access_token"]
    h = {"Authorization": f"Bearer {adm}"}
    # com senha informada
    r = await client.post("/users", json={"name": "Novo Treinador", "password": "senha123", "role": "organizer"}, headers=h)
    assert r.status_code == 201 and r.json()["user"]["role"] == "organizer" and r.json()["temporary_password"] is None
    assert (await client.post("/auth/login", json={"name": "Novo Treinador", "password": "senha123"})).status_code == 200
    # sem senha: devolve uma temporária que funciona
    r = await client.post("/users", json={"name": "Sem Senha"}, headers=h)
    temp = r.json()["temporary_password"]
    assert r.status_code == 201 and r.json()["user"]["role"] == "player" and temp
    assert (await client.post("/auth/login", json={"name": "Sem Senha", "password": temp})).status_code == 200
    # nome repetido (sem diferenciar maiúsculas), nome/senha inválidos
    assert (await client.post("/users", json={"name": "novo treinador"}, headers=h)).status_code == 409
    assert (await client.post("/users", json={"name": "ab"}, headers=h)).status_code == 422
    assert (await client.post("/users", json={"name": "Outro Nome", "password": "123"}, headers=h)).status_code == 422
    # só admin
    tok = (await client.post("/auth/login", json={"name": "Novo Treinador", "password": "senha123"})).json()["access_token"]
    assert (await client.post("/users", json={"name": "Fulano"}, headers={"Authorization": f"Bearer {tok}"})).status_code == 403
    assert (await client.post("/users", json={"name": "Fulano"})).status_code == 401


async def test_temporary_password_forces_change(client):
    h = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731
    adm = (await client.post("/auth/login", json={"name": "Admin", "password": "admin123"})).json()["access_token"]
    r = await client.post("/users", json={"name": "Temporario"}, headers=h(adm))
    temp = r.json()["temporary_password"]
    assert r.json()["user"]["must_change_password"] is True

    login = (await client.post("/auth/login", json={"name": "Temporario", "password": temp})).json()
    assert login["user"]["must_change_password"] is True
    tok = login["access_token"]
    # /auth/me continua funcionando e informa a pendência; o resto fica bloqueado com mensagem clara
    assert (await client.get("/auth/me", headers=h(tok))).json()["must_change_password"] is True
    r = await client.post("/tournaments/1/withdraw", headers=h(tok))
    assert r.status_code == 403 and "senha temporária" in r.json()["detail"]
    r = await client.post("/tournaments", json={"name": "Teste", "template": "league", "max_players": 4}, headers=h(tok))
    assert r.status_code == 403

    # trocar: a nova precisa ser diferente; depois libera tudo
    r = await client.post("/auth/change-password", json={"current_password": temp, "new_password": temp}, headers=h(tok))
    assert r.status_code == 400
    r = await client.post("/auth/change-password", json={"current_password": temp, "new_password": "minhasenha1"}, headers=h(tok))
    assert r.status_code == 204
    assert (await client.get("/auth/me", headers=h(tok))).json()["must_change_password"] is False
    assert (await client.post("/tournaments/1/withdraw", headers=h(tok))).status_code != 403

    # senha definida pelo admin não é temporária; reset sem senha volta a exigir a troca
    r = await client.post("/users", json={"name": "Definida", "password": "senha123"}, headers=h(adm))
    assert r.json()["user"]["must_change_password"] is False
    uid = r.json()["user"]["id"]
    assert (await client.post(f"/users/{uid}/reset-password", json={}, headers=h(adm))).status_code == 200
    users = (await client.get("/users/admin", headers=h(adm))).json()
    assert next(u for u in users if u["id"] == uid)["must_change_password"] is True
    assert (await client.post(f"/users/{uid}/reset-password", json={"new_password": "outra123"}, headers=h(adm))).status_code == 200
    users = (await client.get("/users/admin", headers=h(adm))).json()
    assert next(u for u in users if u["id"] == uid)["must_change_password"] is False
