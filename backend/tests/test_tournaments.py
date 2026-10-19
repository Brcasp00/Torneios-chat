import pytest

pytestmark = pytest.mark.asyncio


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def make_user(client, name, password="senha123"):
    r = await client.post("/auth/register", json={"name": name, "password": password})
    return r.json()["user"]["id"], r.json()["access_token"]


async def admin_token(client):
    r = await client.post("/auth/login", json={"name": "Admin", "password": "admin123"})
    return r.json()["access_token"]


async def make_organizer(client, name="Org"):
    uid, _ = await make_user(client, name)
    adm = await admin_token(client)
    await client.patch(f"/users/{uid}/role", json={"role": "organizer"}, headers=auth(adm))
    r = await client.post("/auth/login", json={"name": name, "password": "senha123"})
    return uid, r.json()["access_token"]


async def create(client, token, **over):
    body = {"name": "Copa Teste", "template": "league", "max_players": 4, **over}
    return await client.post("/tournaments", json=body, headers=auth(token))


async def test_player_cannot_create(client):
    _, tok = await make_user(client, "Jogador")
    assert (await create(client, tok)).status_code == 403
    assert (await client.post("/tournaments", json={})).status_code == 401


async def test_league_template(client):
    adm = await admin_token(client)
    r = await create(client, adm, config={"double_round": True})
    assert r.status_code == 201
    t = r.json()
    assert t["status"] == "draft" and t["can_manage"] is True
    assert [s["type"] for s in t["stages"]] == ["league"]
    assert t["stages"][0]["config"]["double_round"] is True
    assert t["config"]["allow_draw"] is True and t["config"]["points_win"] == 3


async def test_knockout_requires_power_of_two(client):
    adm = await admin_token(client)
    assert (await create(client, adm, template="knockout", max_players=6)).status_code == 422
    r = await create(client, adm, template="knockout", max_players=8, config={"third_place": True})
    assert r.status_code == 201
    assert r.json()["config"]["allow_draw"] is False
    assert r.json()["stages"][0]["config"]["third_place"] is True


async def test_groups_knockout_with_repechage_rule(client):
    adm = await admin_token(client)
    r = await create(
        client, adm, template="groups_knockout", max_players=16,
        config={"groups_count": 4, "qualifiers_per_group": 2, "repechage_position": 3},
    )
    assert r.status_code == 201, r.text
    t = r.json()
    assert [s["type"] for s in t["stages"]] == ["groups", "knockout"]
    targets = sorted((x["target"], x["pos_from"], x["pos_to"]) for x in t["rules"])
    assert targets == [("eliminated", 4, 4), ("repechage", 3, 3), ("stage", 1, 2)]


async def test_groups_knockout_validations(client):
    adm = await admin_token(client)
    # 3 grupos x 2 = 6 vagas: não é potência de 2
    r = await create(client, adm, template="groups_knockout", max_players=12, config={"groups_count": 3})
    assert r.status_code == 422
    # classificados >= tamanho do grupo
    r = await create(client, adm, template="groups_knockout", max_players=8, config={"groups_count": 4, "qualifiers_per_group": 2})
    assert r.status_code == 422


async def test_custom_20_players_example(client):
    """20 jogadores: 10 confrontos; 6 melhores vencedores direto, 4 piores jogam playoff; 8 no mata-mata."""
    adm = await admin_token(client)
    body = {
        "name": "Torneio 20", "template": "custom", "max_players": 20,
        "stages": [
            {"name": "Rodada inicial", "type": "round", "config": {"best_of": 1}},
            {"name": "Playoff", "type": "playoff", "config": {"best_of": 1}},
            {"name": "Mata-mata", "type": "knockout", "config": {"best_of": 3}},
        ],
        "rules": [
            {"from_stage": 1, "source": "losers", "pos_from": 1, "pos_to": 10, "target": "eliminated"},
            {"from_stage": 1, "source": "winners", "pos_from": 1, "pos_to": 6, "target": "stage", "to_stage": 3, "to_slot_from": 1},
            {"from_stage": 1, "source": "winners", "pos_from": 7, "pos_to": 10, "target": "stage", "to_stage": 2, "to_slot_from": 1},
            {"from_stage": 2, "source": "winners", "pos_from": 1, "pos_to": 2, "target": "stage", "to_stage": 3, "to_slot_from": 7},
        ],
    }
    r = await client.post("/tournaments", json=body, headers=auth(adm))
    assert r.status_code == 201, r.text
    t = r.json()
    assert len(t["stages"]) == 3 and len(t["rules"]) == 4
    ids = {s["position"]: s["id"] for s in t["stages"]}
    stage_rules = [x for x in t["rules"] if x["target"] == "stage"]
    assert {x["to_stage_id"] for x in stage_rules} == {ids[2], ids[3]}


async def test_custom_rule_validation(client):
    adm = await admin_token(client)
    base = {"name": "Custom X", "template": "custom", "max_players": 8, "stages": [{"name": "A", "type": "round"}]}
    bad = dict(base, rules=[{"from_stage": 1, "target": "stage", "pos_from": 1, "pos_to": 2, "to_stage": 1, "to_slot_from": 1}])
    assert (await client.post("/tournaments", json=bad, headers=auth(adm))).status_code == 422
    bad = dict(base, rules=[{"from_stage": 1, "target": "parent_tournament", "pos_from": 1, "pos_to": 1, "parent_stage": 1, "to_slot_from": 1}])
    assert (await client.post("/tournaments", json=bad, headers=auth(adm))).status_code == 422
    mixed = {"name": "Liga Y", "template": "league", "max_players": 8, "stages": [{"name": "A", "type": "round"}]}
    assert (await client.post("/tournaments", json=mixed, headers=auth(adm))).status_code == 422


async def test_organizer_manages_only_own(client):
    _, org1 = await make_organizer(client, "Org1")
    _, org2 = await make_organizer(client, "Org2")
    tid = (await create(client, org1)).json()["id"]
    r = await client.patch(f"/tournaments/{tid}", json={"name": "Novo Nome"}, headers=auth(org2))
    assert r.status_code == 403
    r = await client.patch(f"/tournaments/{tid}", json={"name": "Novo Nome"}, headers=auth(org1))
    assert r.status_code == 200 and r.json()["name"] == "Novo Nome"
    adm = await admin_token(client)
    assert (await client.patch(f"/tournaments/{tid}", json={"name": "Admin Mudou"}, headers=auth(adm))).status_code == 200


async def test_public_read(client):
    adm = await admin_token(client)
    tid = (await create(client, adm)).json()["id"]
    r = await client.get(f"/tournaments/{tid}")
    assert r.status_code == 200 and r.json()["can_manage"] is False
    lst = await client.get("/tournaments")
    assert [x["id"] for x in lst.json()] == [tid]
    assert (await client.get("/tournaments/9999")).status_code == 404


async def test_players_lifecycle(client):
    adm = await admin_token(client)
    tid = (await create(client, adm, max_players=2)).json()["id"]
    u1, tok1 = await make_user(client, "Jog1")
    u2, _ = await make_user(client, "Jog2")
    u3, _ = await make_user(client, "Jog3")

    r = await client.post(f"/tournaments/{tid}/players", json={"user_ids": [u1]}, headers=auth(tok1))
    assert r.status_code == 403  # jogador não se inscreve sozinho
    r = await client.post(f"/tournaments/{tid}/players", json={"user_ids": [u1, u2]}, headers=auth(adm))
    assert r.status_code == 201 and len(r.json()) == 2
    assert (await client.post(f"/tournaments/{tid}/players", json={"user_ids": [u1]}, headers=auth(adm))).status_code == 409
    assert (await client.post(f"/tournaments/{tid}/players", json={"user_ids": [u3]}, headers=auth(adm))).status_code == 409  # lotado
    assert (await client.post(f"/tournaments/{tid}/players", json={"user_ids": [99999]}, headers=auth(adm))).status_code == 404

    # desistir antes do início remove da lista
    assert (await client.post(f"/tournaments/{tid}/withdraw", headers=auth(tok1))).status_code == 204
    assert len((await client.get(f"/tournaments/{tid}/players")).json()) == 1
    assert (await client.post(f"/tournaments/{tid}/withdraw", headers=auth(tok1))).status_code == 404


async def test_status_flow_and_start_requires_full(client):
    adm = await admin_token(client)
    tid = (await create(client, adm, max_players=2)).json()["id"]
    u1, tok1 = await make_user(client, "Ana1")
    u2, _ = await make_user(client, "Ana2")
    st = lambda s: client.patch(f"/tournaments/{tid}/status", json={"status": s}, headers=auth(adm))  # noqa: E731
    assert (await st("finished")).status_code == 409  # transição inválida
    assert (await st("registration")).status_code == 200
    assert (await st("running")).status_code == 409  # início só pelo /start
    start = lambda: client.post(f"/tournaments/{tid}/start", json={}, headers=auth(adm))  # noqa: E731
    assert (await start()).status_code == 409  # faltam jogadores
    await client.post(f"/tournaments/{tid}/players", json={"user_ids": [u1, u2]}, headers=auth(adm))
    assert (await start()).status_code == 200

    # depois do início: não inscreve/edita, desistência vira 'withdrawn'
    assert (await client.post(f"/tournaments/{tid}/players", json={"user_ids": [u1]}, headers=auth(adm))).status_code == 409
    assert (await client.patch(f"/tournaments/{tid}", json={"name": "Outro"}, headers=auth(adm))).status_code == 409
    assert (await client.post(f"/tournaments/{tid}/withdraw", headers=auth(tok1))).status_code == 204
    players = (await client.get(f"/tournaments/{tid}/players")).json()
    assert {p["name"]: p["status"] for p in players} == {"Ana1": "withdrawn", "Ana2": "active"}
    assert (await client.get(f"/tournaments/{tid}")).json()["players_count"] == 1


async def test_update_rebuilds_template(client):
    adm = await admin_token(client)
    tid = (await create(client, adm, template="knockout", max_players=8)).json()["id"]
    r = await client.patch(f"/tournaments/{tid}", json={"max_players": 16}, headers=auth(adm))
    assert r.status_code == 200 and r.json()["max_players"] == 16 and len(r.json()["stages"]) == 1
    r = await client.patch(f"/tournaments/{tid}", json={"config": {"best_of": 3, "third_place": True}}, headers=auth(adm))
    assert r.json()["stages"][0]["config"] == {"best_of": 3, "third_place": True}


async def test_subtournament(client):
    adm = await admin_token(client)
    parent = (await create(
        client, adm, template="groups_knockout", max_players=16,
        config={"groups_count": 4, "qualifiers_per_group": 2, "repechage_position": 3},
    )).json()
    sub_body = {
        "name": "Repescagem", "template": "custom", "max_players": 4,
        "stages": [{"name": "Mata-mata", "type": "knockout"}],
        "rules": [{
            "from_stage": 1, "source": "winners", "pos_from": 1, "pos_to": 2,
            "target": "parent_tournament", "parent_stage": 2, "to_slot_from": 5,
        }],
    }
    r = await client.post(f"/tournaments/{parent['id']}/subtournaments", json=sub_body, headers=auth(adm))
    assert r.status_code == 201, r.text
    sub = r.json()
    parent_ko = next(s for s in parent["stages"] if s["position"] == 2)
    assert sub["parent_id"] == parent["id"] and sub["rules"][0]["to_stage_id"] == parent_ko["id"]

    # página do principal mostra o botão (lista de subtorneios); a listagem geral esconde subtorneios
    assert [s["id"] for s in (await client.get(f"/tournaments/{parent['id']}")).json()["subtournaments"]] == [sub["id"]]
    assert (await client.get(f"/tournaments/{sub['id']}")).json()["parent"]["id"] == parent["id"]
    assert [t["id"] for t in (await client.get("/tournaments")).json()] == [parent["id"]]

    # sem aninhamento
    r = await client.post(f"/tournaments/{sub['id']}/subtournaments", json=sub_body, headers=auth(adm))
    assert r.status_code == 400
    # subtorneio não pode ter repescagem própria
    bad = dict(sub_body, rules=[{"from_stage": 1, "target": "repechage", "pos_from": 3, "pos_to": 3}])
    assert (await client.post(f"/tournaments/{parent['id']}/subtournaments", json=bad, headers=auth(adm))).status_code == 422


async def test_delete_tournament(client):
    _, org = await make_organizer(client)
    tid = (await create(client, org)).json()["id"]
    assert (await client.delete(f"/tournaments/{tid}", headers=auth(org))).status_code == 204
    assert (await client.get(f"/tournaments/{tid}")).status_code == 404
