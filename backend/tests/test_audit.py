from tests.test_groups import admin, auth, create, make_players, matches_of, play


async def test_audit_log_filters_and_permissions(client):
    adm = await admin(client)
    t = await create(client, adm, {"name": "Liga Audit", "template": "league", "max_players": 4})
    users = await make_players(client, adm, t["id"], 4)
    await client.post(f"/tournaments/{t['id']}/start", json={"seed": 1}, headers=auth(adm))
    m = (await matches_of(client, t["id"]))[0]
    await play(client, adm, m)

    assert (await client.get("/audit")).status_code == 401
    assert (await client.get("/audit", headers=auth(users[0][1]))).status_code == 403

    page = (await client.get("/audit", headers=auth(adm))).json()
    assert page["total"] >= 4 and page["items"][0]["actor_name"] == "Admin"
    assert page["items"][0]["id"] > page["items"][-1]["id"]  # mais recentes primeiro
    only_match = (await client.get("/audit", params={"action": "match."}, headers=auth(adm))).json()
    assert only_match["total"] == 1 and only_match["items"][0]["action"] == "match.set_result"
    exact = (await client.get("/audit", params={"action": "tournament.start"}, headers=auth(adm))).json()
    assert exact["total"] == 1
    by_entity = (await client.get("/audit", params={"entity": "match", "entity_id": m["id"]}, headers=auth(adm))).json()
    assert by_entity["total"] == 1
    paged = (await client.get("/audit", params={"limit": 2, "offset": 1}, headers=auth(adm))).json()
    assert len(paged["items"]) == 2 and paged["total"] == page["total"]
    future = (await client.get("/audit", params={"since": "2999-01-01T00:00:00"}, headers=auth(adm))).json()
    assert future["total"] == 0


async def test_match_timeline(client):
    adm = await admin(client)
    t = await create(client, adm, {"name": "Liga Tempo", "template": "league", "max_players": 4})
    users = await make_players(client, adm, t["id"], 4)
    await client.post(f"/tournaments/{t['id']}/start", json={"seed": 1}, headers=auth(adm))
    m = (await matches_of(client, t["id"]))[0]
    tok = next(tk for uid, tk in users if uid == m["player1"]["id"])
    body = {"p1_wins": 1, "p2_wins": 0, "p1_remaining": 2, "p2_remaining": 0,
            "replay_urls": ["https://replay.pokemonshowdown.com/gen9ou-1"]}
    assert (await client.post(f"/matches/{m['id']}/report", json=body, headers=auth(tok))).status_code == 200
    assert (await client.post(f"/matches/{m['id']}/validate", json={}, headers=auth(adm))).status_code == 200
    await client.post(f"/matches/{m['id']}/invalidate", json={"note": "teste"}, headers=auth(adm))

    ev = (await client.get(f"/matches/{m['id']}/timeline")).json()
    actions = [e["action"] for e in ev]
    assert ev[0]["kind"] == "report" and ev[0]["actor_id"] == m["player1"]["id"] and ev[0]["data"]["replay_urls"]
    assert "match.validate" in actions and "match.invalidate" in actions
    assert (await client.get("/matches/99999/timeline")).status_code == 404
