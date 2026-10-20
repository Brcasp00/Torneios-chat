"""Grupos de tamanhos diferentes (ex.: 14 jogadores em 4 grupos = 4, 4, 3, 3).

Antes, a regra "3º e 4º eliminados" falhava nos grupos de 3 e a validação do último jogo dos grupos era recusada
(torneio travado). Achado na simulação de um torneio completo.
"""
from tests.test_groups import REPLAY, admin, auth, create, make_players, matches_of, play  # noqa: F401


async def _play_stage(client, adm, tid, sid):
    for m in await matches_of(client, tid, stage_id=sid):
        if m["status"] == "scheduled" and m["player1"] and m["player2"]:
            await play(client, adm, m)


async def test_fourteen_players_default_groups_reach_the_knockout(client):
    adm = await admin(client)
    t = await create(client, adm, {"name": "Copa 14", "template": "groups_knockout", "max_players": 14})
    assert t["config"]["groups_count"] == 4  # padrão: ~4 por grupo -> 4, 4, 3, 3
    await make_players(client, adm, t["id"], 14)
    assert (await client.post(f"/tournaments/{t['id']}/start", json={"seed": 9}, headers=auth(adm))).status_code == 200
    await _play_stage(client, adm, t["id"], t["stages"][0]["id"])
    d = (await client.get(f"/tournaments/{t['id']}")).json()
    assert d["stages"][0]["status"] == "finished"
    ko = await matches_of(client, t["id"], stage_id=t["stages"][1]["id"])
    assert sum(1 for m in ko if m["player1"] and m["player2"]) == 4  # 4 grupos x 2 = 8 no mata-mata
    eliminated = [p for p in d["players"] if p["status"] == "eliminated"]
    assert len(eliminated) == 6  # 3º e 4º de cada grupo (os grupos de 3 só têm 3º)


async def test_uneven_groups_with_repechage_fill_the_reserved_slots(client):
    adm = await admin(client)
    t = await create(client, adm, {"name": "Copa 16/6", "template": "groups_knockout", "max_players": 16,
                                   "config": {"groups_count": 6, "qualifiers_per_group": 1, "repechage_position": 2, "repechage_slots": 2}})
    await make_players(client, adm, t["id"], 16)
    sub = await client.post(f"/tournaments/{t['id']}/subtournaments", headers=auth(adm), json={
        "name": "Repescagem", "template": "custom", "max_players": 6,
        "stages": [{"name": "Repescagem", "type": "round"}],
        "rules": [
            {"from_stage": 1, "source": "winners", "pos_from": 1, "pos_to": 2, "target": "parent_tournament", "parent_stage": 2, "to_slot_from": 7},
            {"from_stage": 1, "source": "winners", "pos_from": 3, "pos_to": 3, "target": "eliminated"},
            {"from_stage": 1, "source": "losers", "pos_from": 1, "pos_to": 3, "target": "eliminated"},
        ],
    })
    assert sub.status_code == 201, sub.text
    sub = sub.json()
    assert (await client.post(f"/tournaments/{t['id']}/start", json={"seed": 42}, headers=auth(adm))).status_code == 200
    await _play_stage(client, adm, t["id"], t["stages"][0]["id"])
    s = (await client.get(f"/tournaments/{sub['id']}")).json()
    assert len(s["players"]) == 6  # o 2º de cada um dos 6 grupos (inclusive os de 2 jogadores)
    assert (await client.post(f"/tournaments/{sub['id']}/start", json={"seed": 1}, headers=auth(adm))).status_code == 200
    await _play_stage(client, adm, sub["id"], s["stages"][0]["id"])
    ko = await matches_of(client, t["id"], stage_id=t["stages"][1]["id"])
    assert sum(1 for m in ko if m["player1"] and m["player2"]) == 4  # 6 diretos + 2 da repescagem


async def test_template_rejects_qualifiers_missing_from_the_smallest_group(client):
    adm = await admin(client)
    # 10 jogadores em 4 grupos = 3, 3, 2, 2: 2 classificados não sobrariam nos grupos de 2
    r = await client.post("/tournaments", headers=auth(adm), json={
        "name": "Copa 10", "template": "groups_knockout", "max_players": 10, "config": {"groups_count": 4, "qualifiers_per_group": 2}})
    assert r.status_code == 422 and "menor grupo" in r.json()["detail"]
