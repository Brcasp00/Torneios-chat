"""Acervo de torneios, séries e perfil do jogador."""
from tests.test_groups import admin, auth, create, make_players, matches_of, play


async def _knockout_finished(client, adm, n=8, name="Copa Acervo"):
    t = await create(client, adm, {"name": name, "template": "knockout", "max_players": n})
    users = await make_players(client, adm, t["id"], n)
    assert (await client.post(f"/tournaments/{t['id']}/start", json={"seed": 11}, headers=auth(adm))).status_code == 200
    sid = t["stages"][0]["id"]
    for _ in range(5):
        pend = [m for m in await matches_of(client, t["id"], stage_id=sid) if m["status"] == "scheduled" and m["player1"] and m["player2"]]
        if not pend:
            break
        for m in pend:
            await play(client, adm, m)
    return t, users


async def test_finished_tournament_goes_to_the_archive_with_final_placements(client):
    adm = await admin(client)
    t, _ = await _knockout_finished(client, adm)
    assert (await client.get(f"/tournaments/{t['id']}")).json()["status"] == "finished"
    lst = (await client.get("/archive")).json()
    assert [e["tournament_id"] for e in lst] == [t["id"]]
    entry = (await client.get(f"/archive/{lst[0]['id']}")).json()
    labels = [(p["position"], p["label"]) for p in entry["placements"]]
    assert labels == [(1, "Campeão"), (2, "Vice"), (3, "Semifinal"), (3, "Semifinal")] + [(5, "Quartas de final")] * 4
    assert entry["champion"]["name"] == entry["placements"][0]["name"] and entry["players_count"] == 8
    assert entry["format"] == "Mata-mata" and entry["end_date"]
    by_t = (await client.get(f"/archive/by-tournament/{t['id']}")).json()
    assert by_t["id"] == entry["id"]


async def test_reopened_tournament_leaves_the_archive_and_keeps_admin_edits(client):
    adm = await admin(client)
    t, _ = await _knockout_finished(client, adm)
    eid = (await client.get("/archive")).json()[0]["id"]
    r = await client.put(f"/archive/{eid}/meta", headers=auth(adm),
                         json={"description": "Final histórica", "links": [{"label": "Vídeo", "url": "https://youtu.be/x"}]})
    assert r.status_code == 200
    final = next(m for m in await matches_of(client, t["id"]) if m["round"] == 3)
    assert (await client.post(f"/matches/{final['id']}/invalidate", json={}, headers=auth(adm))).status_code == 200
    assert (await client.get("/archive")).json() == []  # voltou para a área de torneios
    assert (await client.get(f"/archive/{eid}")).status_code == 404
    await play(client, adm, (await client.get(f"/matches/{final['id']}")).json(), p1_wins=False)
    again = (await client.get(f"/archive/{eid}")).json()
    assert again["description"] == "Final histórica" and again["links"][0]["url"] == "https://youtu.be/x"
    assert again["champion"]["user_id"] in (final["player1"]["id"], final["player2"]["id"])


async def test_manual_entry_with_matches_series_and_permissions(client):
    adm = await admin(client)
    player = (await client.post("/auth/register", json={"name": "Veterano", "password": "senha1234"})).json()
    body = {
        "name": "Copa Antiga 2019", "start_date": "2019-03-01", "end_date": "2019-03-20", "format": "Mata-mata de 4",
        "players_count": 4, "tier": "OU", "description": "A primeira copa.",
        "placements": [{"position": 1, "user_id": player["user"]["id"]}, {"position": 2, "name": "Fulano Sem Conta"}],
        "matches": [
            {"stage_label": "Final", "number": 1, "player1": {"user_id": player["user"]["id"]}, "player2": {"name": "Fulano Sem Conta"},
             "winner": 1, "replay_url": "https://replay.pokemonshowdown.com/gen7ou-1"},
            {"stage_label": "Semifinal", "number": 2, "player1": {"name": "A"}, "player2": {"name": "B"}},
        ],
    }
    assert (await client.post("/archive", json=body)).status_code == 401
    assert (await client.post("/archive", json=body, headers=auth(player["access_token"]))).status_code == 403
    bad = {**body, "matches": [{**body["matches"][0], "replay_url": "javascript:alert(1)"}]}
    assert (await client.post("/archive", json=bad, headers=auth(adm))).status_code == 422
    r = await client.post("/archive", json=body, headers=auth(adm))
    assert r.status_code == 201, r.text
    e = r.json()
    assert e["tournament_id"] is None and e["champion"] == {"user_id": player["user"]["id"], "name": "Veterano"}
    assert e["matches"][0]["replay_url"].startswith("https://") and e["matches"][1]["replay_url"] is None
    assert e["matches"][0]["player2"] == {"user_id": None, "name": "Fulano Sem Conta"}

    # série: criar, ligar com edição e ver a lista de campeões
    s = (await client.post("/series", json={"name": "Copa Antiga"}, headers=auth(adm))).json()
    assert (await client.post("/series", json={"name": "copa antiga"}, headers=auth(adm))).status_code == 409
    r = await client.put(f"/archive/{e['id']}/meta", headers=auth(adm), json={"description": "A primeira copa.", "series_id": s["id"], "edition": 1})
    assert r.json()["series"] == {"id": s["id"], "name": "Copa Antiga"} and r.json()["edition"] == 1
    sd = (await client.get(f"/series/{s['id']}")).json()
    assert [x["edition"] for x in sd["editions"]] == [1] and sd["editions"][0]["champion"]["name"] == "Veterano"
    assert [x["id"] for x in (await client.get("/archive", params={"series_id": s["id"]})).json()] == [e["id"]]

    # editar por inteiro (só torneio antigo) e apagar a série (o torneio fica sem série)
    body2 = {**body, "name": "Copa Antiga 2019 (1ª)", "series_id": s["id"], "edition": 1}
    assert (await client.put(f"/archive/{e['id']}", json=body2, headers=auth(adm))).json()["name"] == "Copa Antiga 2019 (1ª)"
    assert (await client.delete(f"/series/{s['id']}", headers=auth(adm))).status_code == 204
    assert (await client.get(f"/archive/{e['id']}")).json()["series"] is None


async def test_platform_entry_cannot_be_fully_edited_and_delete_removes_the_tournament(client):
    adm = await admin(client)
    t, _ = await _knockout_finished(client, adm, n=4, name="Copa Para Apagar")
    eid = (await client.get("/archive")).json()[0]["id"]
    full = {"name": "Outro", "placements": [], "matches": []}
    assert (await client.put(f"/archive/{eid}", json=full, headers=auth(adm))).status_code == 409
    assert (await client.post(f"/archive/{eid}/delete", json={"confirm_name": "outro nome"}, headers=auth(adm))).status_code == 422
    r = await client.post(f"/archive/{eid}/delete", json={"confirm_name": "  copa para   apagar "}, headers=auth(adm))
    assert r.status_code == 204
    assert (await client.get(f"/tournaments/{t['id']}")).status_code == 404
    assert (await client.get("/archive")).json() == []
    log = (await client.get("/audit", params={"action": "archive.delete"}, headers=auth(adm))).json()
    assert log["total"] == 1 and log["items"][0]["data"]["tournament_id"] == t["id"]


async def test_player_profile(client):
    adm = await admin(client)
    t, users = await _knockout_finished(client, adm, n=4)
    entry = (await client.get(f"/archive/{(await client.get('/archive')).json()[0]['id']}")).json()
    champ = entry["placements"][0]["user_id"]
    # título também num torneio antigo
    await client.post("/archive", headers=auth(adm), json={"name": "Copa Velha", "end_date": "2018-01-01",
                                                          "placements": [{"position": 1, "user_id": champ}]})
    p = (await client.get(f"/players/{champ}")).json()
    assert p["stats"]["wins"] == 2 and p["stats"]["losses"] == 0 and p["stats"]["played"] == 2
    assert [f["name"] for f in p["titles"]] == ["Copa Acervo", "Copa Velha"]  # mais recente primeiro
    assert p["podiums"] == [] and p["current"] == []
    vice = entry["placements"][1]["user_id"]
    pv = (await client.get(f"/players/{vice}")).json()
    assert [f["position"] for f in pv["podiums"]] == [2] and pv["stats"]["losses"] == 1
    assert (await client.get("/players/99999")).status_code == 404


async def test_custom_flow_tournament_places_everyone(client):
    """Rodada única de 8 -> 4 vencedores no mata-mata: os 4 da rodada dividem o 5º lugar."""
    adm = await admin(client)
    t = await create(client, adm, {
        "name": "Fluxo", "template": "custom", "max_players": 8,
        "stages": [{"name": "Rodada inicial", "type": "round"}, {"name": "Mata-mata", "type": "knockout"}],
        "rules": [{"from_stage": 1, "source": "winners", "pos_from": 1, "pos_to": 4, "target": "stage", "to_stage": 2, "to_slot_from": 1}],
    })
    await make_players(client, adm, t["id"], 8)
    await client.post(f"/tournaments/{t['id']}/start", json={"seed": 3}, headers=auth(adm))
    for sid in (s["id"] for s in t["stages"]):
        for _ in range(3):
            for m in await matches_of(client, t["id"], stage_id=sid):
                if m["status"] == "scheduled" and m["player1"] and m["player2"]:
                    await play(client, adm, m)
    e = (await client.get(f"/archive/{(await client.get('/archive')).json()[0]['id']}")).json()
    assert len(e["placements"]) == 8
    assert [(p["position"], p["label"]) for p in e["placements"][4:]] == [(5, "Rodada inicial")] * 4
