"""Fase 7: repescagem em subtorneio (entrada automática, retorno ao principal, cascata e desistência)."""
from tests.test_groups import REPLAY, admin, auth, create, detail, make_players, matches_of, play, play_stage  # noqa: F401

SUB_BODY = {
    "name": "Repescagem", "template": "custom", "max_players": 4,
    "stages": [{"name": "Mata-mata da repescagem", "type": "knockout"}],
    "rules": [{
        "from_stage": 1, "source": "ranking", "pos_from": 1, "pos_to": 2,
        "target": "parent_tournament", "parent_stage": 2, "to_slot_from": 3,
    }],
}


async def scenario(client, adm, finish_groups=True):
    """8 jogadores, 2 grupos de 4, 1º de cada grupo direto, 3º de cada grupo à repescagem (vagas 3-4 do mata-mata)."""
    parent = await create(client, adm, {
        "name": "Copa Repescagem", "template": "groups_knockout", "max_players": 8,
        "config": {"groups_count": 2, "qualifiers_per_group": 1, "repechage_position": 3, "repechage_slots": 2},
    })
    pid = parent["id"]
    g_stage, ko_stage = parent["stages"]
    r = await client.post(f"/tournaments/{pid}/subtournaments", json=SUB_BODY, headers=auth(adm))
    assert r.status_code == 201, r.text
    sub = r.json()
    users = await make_players(client, adm, pid, 8)
    assert (await client.post(f"/tournaments/{pid}/start", json={"seed": 3}, headers=auth(adm))).status_code == 200
    if finish_groups:
        await play_stage(client, adm, pid, g_stage["id"])
    return parent, sub, g_stage, ko_stage, users


async def make_players_named(client, adm, tid, n, prefix):
    """Como make_players, mas com outro prefixo de nome (para um segundo torneio no mesmo teste)."""
    users = []
    for i in range(n):
        r = await client.post("/auth/register", json={"name": f"{prefix}{i + 1:02d}", "password": "senha123"})
        users.append((r.json()["user"]["id"], r.json()["access_token"]))
    r = await client.post(f"/tournaments/{tid}/players", json={"user_ids": [u for u, _ in users]}, headers=auth(adm))
    assert r.status_code == 201, r.text
    return users


async def positions(client, pid):
    st = (await client.get(f"/tournaments/{pid}/standings")).json()[0]
    return {g["label"]: [r["user_id"] for r in g["rows"]] for g in st["groups"]}


async def sub_player_ids(client, sid):
    return {p["user_id"] for p in (await client.get(f"/tournaments/{sid}/players")).json()}


async def test_template_validates_repechage_slots(client):
    adm = await admin(client)
    base = {"name": "Copa X", "template": "groups_knockout", "max_players": 8}

    async def post(**cfg):
        return await client.post("/tournaments", json={**base, "config": cfg}, headers=auth(adm))

    ok = await post(groups_count=2, qualifiers_per_group=1, repechage_position=3, repechage_slots=2)
    assert ok.status_code == 201
    ko = ok.json()["stages"][1]["config"]
    assert ko["external_slots"] == [[3, 4]] and ko["seeding"] == "standard"
    # 2 + 1 vagas não é potência de 2; e vagas de repescagem exigem de onde vêm os candidatos
    assert (await post(groups_count=2, qualifiers_per_group=1, repechage_position=3, repechage_slots=1)).status_code == 422
    assert (await post(groups_count=2, qualifiers_per_group=1, repechage_slots=2)).status_code == 422


async def test_repechage_end_to_end(client):
    adm = await admin(client)
    parent, sub, g_stage, ko_stage, users = await scenario(client, adm, finish_groups=False)
    pid, sid = parent["id"], sub["id"]

    # o subtorneio só começa com o principal em andamento... e antes da hora o principal ainda não o liberou
    assert await sub_player_ids(client, sid) == set()
    await play_stage(client, adm, pid, g_stage["id"])
    pos = await positions(client, pid)
    thirds = {pos["A"][2], pos["B"][2]}

    # entrada automática: os 3ºs dos grupos estão no subtorneio; o mata-mata principal espera o subtorneio
    assert await sub_player_ids(client, sid) == thirds
    td = await detail(client, pid)
    assert td["repechage"] == [{
        "rule_id": td["repechage"][0]["rule_id"], "stage_id": g_stage["id"],
        "subtournament_id": sid, "user_ids": td["repechage"][0]["user_ids"],
    }] and set(td["repechage"][0]["user_ids"]) == thirds
    assert await matches_of(client, pid, stage_id=ko_stage["id"]) == []
    status_of = {p["user_id"]: p["status"] for p in td["players"]}
    assert all(status_of[u] == "eliminated" for u in thirds)
    assert td["status"] == "running"

    # jogadores de fora do principal não entram no subtorneio; os demais (entrada manual) sim
    outsider = (await client.post("/auth/register", json={"name": "Forasteiro", "password": "senha123"})).json()["user"]["id"]
    r = await client.post(f"/tournaments/{sid}/players", json={"user_ids": [outsider]}, headers=auth(adm))
    assert r.status_code == 409
    manual = [pos["A"][1], pos["B"][1]]
    r = await client.post(f"/tournaments/{sid}/players", json={"user_ids": manual}, headers=auth(adm))
    assert r.status_code == 201, r.text

    # inicia o subtorneio e joga até o fim
    r = await client.post(f"/tournaments/{sid}/start", json={"seed": 5}, headers=auth(adm))
    assert r.status_code == 200 and len(r.json()) == 3
    await play_stage(client, adm, sid, sub["stages"][0]["id"])
    await play_stage(client, adm, sid, sub["stages"][0]["id"])
    sd = await detail(client, sid)
    assert sd["status"] == "finished"
    sub_matches = await matches_of(client, sid)
    final = max(sub_matches, key=lambda m: m["round"])
    returnees = {final["player1"]["id"], final["player2"]["id"]}

    # retorno ao principal: mata-mata com os 2 primeiros dos grupos + os 2 que voltaram, cada primeiro contra um repescado
    ko = await matches_of(client, pid, stage_id=ko_stage["id"])
    r1 = [m for m in ko if m["round"] == 1]
    assert len(r1) == 2
    entrants = {p["id"] for m in r1 for p in (m["player1"], m["player2"])}
    assert entrants == {pos["A"][0], pos["B"][0]} | returnees
    for m in r1:
        ids = {m["player1"]["id"], m["player2"]["id"]}
        assert len(ids & returnees) == 1
    td = await detail(client, pid)
    status_of = {p["user_id"]: p["status"] for p in td["players"]}
    assert all(status_of[u] == "active" for u in returnees)
    assert all(status_of[u] == "eliminated" for u in (thirds | set(manual)) - returnees)

    # o torneio principal termina junto com o mata-mata
    await play_stage(client, adm, pid, ko_stage["id"])
    await play_stage(client, adm, pid, ko_stage["id"])
    assert (await detail(client, pid))["status"] == "finished"


async def test_subtournament_cascade(client):
    adm = await admin(client)
    parent, sub, g_stage, ko_stage, users = await scenario(client, adm)
    pid, sid = parent["id"], sub["id"]
    sub_stage = sub["stages"][0]
    pos = await positions(client, pid)
    manual = [pos["A"][1], pos["B"][1]]
    await client.post(f"/tournaments/{sid}/players", json={"user_ids": manual}, headers=auth(adm))
    await client.post(f"/tournaments/{sid}/start", json={"seed": 5}, headers=auth(adm))
    await play_stage(client, adm, sid, sub_stage["id"])
    await play_stage(client, adm, sid, sub_stage["id"])
    assert len(await matches_of(client, pid, stage_id=ko_stage["id"])) == 3

    # corrigir o subtorneio sem que o principal tenha jogado: o mata-mata principal é desfeito e refeito depois
    final = max(await matches_of(client, sid), key=lambda m: m["round"])
    r = await client.post(f"/matches/{final['id']}/invalidate", json={"note": "irregular"}, headers=auth(adm))
    assert r.status_code == 200, r.text
    assert await matches_of(client, pid, stage_id=ko_stage["id"]) == []
    td = await detail(client, pid)
    assert {s["id"]: s["status"] for s in td["stages"]}[ko_stage["id"]] == "pending"
    assert all(p["status"] == "eliminated" for p in td["players"] if p["user_id"] in {pos["A"][2], pos["B"][2], *manual})
    await play(client, adm, final)
    ko = await matches_of(client, pid, stage_id=ko_stage["id"])
    assert len(ko) == 3

    # com um jogo do principal já validado, mexer no subtorneio é bloqueado (409) e nada muda
    await play(client, adm, next(m for m in ko if m["round"] == 1))
    r = await client.post(f"/matches/{final['id']}/invalidate", json={}, headers=auth(adm))
    assert r.status_code == 409 and "Invalide" in r.json()["detail"]
    assert (await client.get(f"/matches/{final['id']}")).json()["status"] == "validated"
    assert len(await matches_of(client, pid, stage_id=ko_stage["id"])) == 3

    # mudar o grupo de origem também é bloqueado: o subtorneio já começou
    gm = (await matches_of(client, pid, stage_id=g_stage["id"]))[0]
    r = await client.post(f"/matches/{gm['id']}/invalidate", json={}, headers=auth(adm))
    assert r.status_code == 409


async def test_subtournament_before_start_follows_group_changes(client):
    adm = await admin(client)
    parent, sub, g_stage, ko_stage, users = await scenario(client, adm)
    pid, sid = parent["id"], sub["id"]
    thirds = {p for p in await sub_player_ids(client, sid)}
    assert len(thirds) == 2
    # reabrir o grupo antes de o subtorneio começar tira os candidatos; refazer o resultado os traz de volta
    gm = (await matches_of(client, pid, stage_id=g_stage["id"]))[0]
    assert (await client.post(f"/matches/{gm['id']}/invalidate", json={}, headers=auth(adm))).status_code == 200
    assert await sub_player_ids(client, sid) == set()
    assert "repechage" not in (await detail(client, pid))["config"] or not (await detail(client, pid))["config"]["repechage"]
    await play(client, adm, gm)
    assert await sub_player_ids(client, sid) == thirds


async def test_withdrawal_reaches_subtournament(client):
    adm = await admin(client)
    parent, sub, g_stage, ko_stage, users = await scenario(client, adm)
    pid, sid = parent["id"], sub["id"]
    pos = await positions(client, pid)
    manual = [pos["A"][1], pos["B"][1]]
    await client.post(f"/tournaments/{sid}/players", json={"user_ids": manual}, headers=auth(adm))
    await client.post(f"/tournaments/{sid}/start", json={"seed": 5}, headers=auth(adm))
    quitter = pos["A"][2]
    token = next(tok for uid, tok in users if uid == quitter)
    assert (await client.post(f"/tournaments/{pid}/withdraw", headers=auth(token))).status_code == 204

    sub_players = {p["user_id"]: p["status"] for p in (await client.get(f"/tournaments/{sid}/players")).json()}
    assert sub_players[quitter] == "withdrawn"
    mine = await matches_of(client, sid, player_id=quitter)
    assert len(mine) == 1 and mine[0]["is_walkover"] and mine[0]["winner_id"] != quitter

    # antes do início do subtorneio, quem desiste do principal sai da lista dele
    parent2 = await create(client, adm, {
        "name": "Copa Repescagem 2", "template": "groups_knockout", "max_players": 8,
        "config": {"groups_count": 2, "qualifiers_per_group": 1, "repechage_position": 3, "repechage_slots": 2},
    })
    sub2 = (await client.post(f"/tournaments/{parent2['id']}/subtournaments", json=SUB_BODY, headers=auth(adm))).json()
    users2 = await make_players_named(client, adm, parent2["id"], 8, "Outro")
    await client.post(f"/tournaments/{parent2['id']}/start", json={"seed": 3}, headers=auth(adm))
    await play_stage(client, adm, parent2["id"], parent2["stages"][0]["id"])
    pos2 = await positions(client, parent2["id"])
    gone = pos2["B"][2]
    token2 = next(tok for uid, tok in users2 if uid == gone)
    assert gone in await sub_player_ids(client, sub2["id"])
    assert (await client.post(f"/tournaments/{parent2['id']}/withdraw", headers=auth(token2))).status_code == 204
    assert gone not in await sub_player_ids(client, sub2["id"])


async def test_link_rule_to_chosen_subtournament(client):
    adm = await admin(client)
    parent, sub, g_stage, ko_stage, users = await scenario(client, adm, finish_groups=False)
    pid = parent["id"]
    other = (await client.post(f"/tournaments/{pid}/subtournaments", json=dict(SUB_BODY, name="Outra"), headers=auth(adm))).json()
    await play_stage(client, adm, pid, g_stage["id"])

    # com dois subtorneios e nenhuma ligação, a entrada automática não acontece
    assert await sub_player_ids(client, sub["id"]) == set() and await sub_player_ids(client, other["id"]) == set()
    rule_id = (await detail(client, pid))["repechage"][0]["rule_id"]
    assert (await detail(client, pid))["repechage"][0]["subtournament_id"] is None

    r = await client.put(f"/tournaments/{pid}/rules/{rule_id}/subtournament", json={"subtournament_id": other["id"]}, headers=auth(adm))
    assert r.status_code == 200, r.text
    assert r.json()["repechage"][0]["subtournament_id"] == other["id"]
    assert len(await sub_player_ids(client, other["id"])) == 2 and await sub_player_ids(client, sub["id"]) == set()

    # trocar a ligação move os candidatos
    r = await client.put(f"/tournaments/{pid}/rules/{rule_id}/subtournament", json={"subtournament_id": sub["id"]}, headers=auth(adm))
    assert r.status_code == 200
    assert len(await sub_player_ids(client, sub["id"])) == 2 and await sub_player_ids(client, other["id"]) == set()

    # ligações inválidas
    assert (await client.put(f"/tournaments/{pid}/rules/{rule_id}/subtournament", json={"subtournament_id": pid}, headers=auth(adm))).status_code == 422
    assert (await client.put(f"/tournaments/{pid}/rules/999999/subtournament", json={}, headers=auth(adm))).status_code == 404


async def test_subtournament_created_after_groups_finish(client):
    adm = await admin(client)
    parent = await create(client, adm, {
        "name": "Copa Tardia", "template": "groups_knockout", "max_players": 8,
        "config": {"groups_count": 2, "qualifiers_per_group": 1, "repechage_position": 3, "repechage_slots": 2},
    })
    pid = parent["id"]
    await make_players(client, adm, pid, 8)
    await client.post(f"/tournaments/{pid}/start", json={"seed": 3}, headers=auth(adm))
    await play_stage(client, adm, pid, parent["stages"][0]["id"])
    # sem subtorneio, o mata-mata aguarda e os candidatos ficam registrados
    assert await matches_of(client, pid, stage_id=parent["stages"][1]["id"]) == []
    assert len((await detail(client, pid))["config"]["repechage"][str(parent["stages"][0]["id"])]) == 2
    sub = (await client.post(f"/tournaments/{pid}/subtournaments", json=SUB_BODY, headers=auth(adm))).json()
    assert len(await sub_player_ids(client, sub["id"])) == 2

    # subtorneio pequeno demais para os candidatos: a criação é recusada (409) em vez de perder jogadores
    tiny = dict(SUB_BODY, name="Pequeno", max_players=2, rules=[dict(SUB_BODY["rules"][0], pos_to=1, to_slot_from=3)])
    tiny["stages"] = [{"name": "Final", "type": "knockout"}]
    r = await client.post(f"/tournaments/{pid}/subtournaments", json=tiny, headers=auth(adm))
    assert r.status_code == 201  # com 2 subtorneios, a ligação deixa de ser automática
    assert await sub_player_ids(client, r.json()["id"]) == set()


async def test_subtournament_cannot_start_before_parent(client):
    adm = await admin(client)
    parent = await create(client, adm, {
        "name": "Copa Cedo", "template": "groups_knockout", "max_players": 8,
        "config": {"groups_count": 2, "qualifiers_per_group": 1, "repechage_position": 3, "repechage_slots": 2},
    })
    sub = (await client.post(f"/tournaments/{parent['id']}/subtournaments", json=SUB_BODY, headers=auth(adm))).json()
    r = await client.post(f"/tournaments/{sub['id']}/start", json={"seed": 1}, headers=auth(adm))
    assert r.status_code == 409 and "principal" in r.json()["detail"]
