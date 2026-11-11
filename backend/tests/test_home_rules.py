"""Mando de campo (escolhas do mandante), saldo por jogos em séries e desempate por sorteio."""
from types import SimpleNamespace

from app.services import standings
from tests.test_groups import REPLAY, admin, auth, create, make_players, matches_of, play

DRAFT = {
    "name": "Draft Carreira", "template": "groups_knockout", "max_players": 8,
    "config": {
        "groups_count": 2, "qualifiers_per_group": 2, "double_round": True, "third_place": True,
        "best_of": 1, "knockout_best_of": 3, "home_rules": True, "series_saldo": "games",
        "tiebreakers": ["confronto_direto", "saldo", "sorteio"],
    },
}


async def _result(client, adm, m, p1_wins, p2_wins, p1_rem=0, p2_rem=0):
    body = {"p1_wins": p1_wins, "p2_wins": p2_wins, "p1_remaining": p1_rem, "p2_remaining": p2_rem, "replay_urls": [REPLAY]}
    r = await client.post(f"/matches/{m['id']}/result", json=body, headers=auth(adm))
    assert r.status_code == 200, r.text
    return r.json()


def _home_token(m, users):
    home_id = m["player1"]["id"] if m["home"] == 1 else m["player2"]["id"]
    other_id = m["player2"]["id"] if m["home"] == 1 else m["player1"]["id"]
    tokens = dict(users)
    return tokens[home_id], tokens[other_id]


async def test_draft_tournament_home_choices_and_series_saldo(client):
    adm = await admin(client)
    t = await create(client, adm, DRAFT)
    g_stage, ko_stage = t["stages"]
    assert g_stage["config"]["best_of"] == 1 and ko_stage["config"]["best_of"] == 3
    users = await make_players(client, adm, t["id"], 8)
    assert (await client.post(f"/tournaments/{t['id']}/start", json={"seed": 21}, headers=auth(adm))).status_code == 200

    ms = await matches_of(client, t["id"], stage_id=g_stage["id"])
    assert len(ms) == 24 and all(m["home"] == 1 for m in ms)
    # returno inverte o mando: cada par se enfrenta uma vez como mandante de cada lado
    legs = {(m["player1"]["id"], m["player2"]["id"]): m["leg"] for m in ms}
    assert all(legs.get((b, a)) == 3 - leg for (a, b), leg in legs.items())

    m = ms[0]
    home, away = _home_token(m, users)
    url = f"/matches/{m['id']}/settings"
    md1 = {"format": "singles", "best_of": 1, "turn_cap": 40, "chat": "private"}
    assert (await client.put(url, json=md1, headers=auth(away))).status_code == 403
    assert (await client.put(url, json={**md1, "turn_cap": 39}, headers=auth(home))).status_code == 422
    assert (await client.put(url, json={**md1, "turn_cap": None}, headers=auth(home))).status_code == 422
    r = await client.put(url, json={"format": "doubles", "best_of": 3, "turn_cap": 80, "chat": "open"}, headers=auth(home))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["best_of"] == 3 and d["settings"]["turn_cap"] is None  # teto suspenso em md3
    assert d["settings"]["format"] == "doubles" and d["home_rules"] and d["can_set_settings"]
    # md3 na fase de grupos vale uma partida; o saldo é a diferença de jogos (2x0 = +2)
    await _result(client, adm, m, 2, 0)
    rows = {r["user_id"]: r for g in (await client.get(f"/tournaments/{t['id']}/standings")).json()[0]["groups"] for r in g["rows"]}
    assert rows[m["player1"]["id"]]["saldo"] == 2 and rows[m["player1"]["id"]]["points"] == 3
    assert rows[m["player2"]["id"]]["saldo"] == -2
    # depois do resultado, as escolhas não mudam mais
    r = await client.put(url, json=md1, headers=auth(home))
    assert r.status_code == 409 and "antes" in r.json()["detail"]
    tl = (await client.get(f"/matches/{m['id']}/timeline")).json()
    assert any(e["action"] == "match.settings" for e in tl)

    for x in ms[1:]:
        await play(client, adm, x)
    ko = await matches_of(client, t["id"], stage_id=ko_stage["id"])
    semis = [x for x in ko if x["round"] == 1]
    assert len(semis) == 2 and all(x["best_of"] == 3 and x["home"] in (1, 2) for x in ko)
    # semifinal é md3 obrigatoriamente: o mandante não volta para melhor de 1
    s = semis[0]
    home, _ = _home_token(s, users)
    r = await client.put(f"/matches/{s['id']}/settings", json=md1, headers=auth(home))
    assert r.status_code == 200 and r.json()["best_of"] == 3 and r.json()["stage_best_of"] == 3


async def test_settings_blocked_without_home_rules(client):
    adm = await admin(client)
    t = await create(client, adm, {"name": "Liga Comum", "template": "league", "max_players": 4})
    users = await make_players(client, adm, t["id"], 4)
    await client.post(f"/tournaments/{t['id']}/start", json={"seed": 2}, headers=auth(adm))
    m = (await matches_of(client, t["id"]))[0]
    d = (await client.get(f"/matches/{m['id']}", headers=auth(dict(users)[m["player1"]["id"]]))).json()
    assert not d["home_rules"] and not d["can_set_settings"] and "não usa mando" in d["settings_blocked"]
    r = await client.put(f"/matches/{m['id']}/settings", json={"format": "singles", "turn_cap": 50},
                         headers=auth(dict(users)[m["player1"]["id"]]))
    assert r.status_code == 409


def _m(p1, p2, w1, w2, best_of=1, r1=0, r2=0):
    return SimpleNamespace(status="validated", player1_id=p1, player2_id=p2, p1_wins=w1, p2_wins=w2, best_of=best_of,
                           p1_remaining=r1, p2_remaining=r2, is_draw=w1 == w2, winner_id=None if w1 == w2 else (p1 if w1 > w2 else p2))


def test_series_saldo_and_draw_tiebreak():
    m = _m(1, 2, 2, 1, best_of=3)
    assert standings._side_saldo(m, 1) == 0  # padrão: série não conta saldo
    assert standings._side_saldo(m, 1, {"series_saldo": "games"}) == 1
    assert standings._side_saldo(m, 2, {"series_saldo": "games"}) == -1
    # 4 jogadores, todos com 1 vitória e 1 derrota iguais entre si: só o sorteio separa
    players = {i: (f"J{i}", False) for i in (1, 2, 3, 4)}
    ms = [_m(1, 2, 1, 0, r1=2), _m(2, 1, 1, 0, r1=2), _m(3, 4, 1, 0, r1=2), _m(4, 3, 1, 0, r1=2)]
    a = [r.user_id for r in standings.compute(players, ms, {"draw_seed": 5, "tiebreakers": ["confronto_direto", "saldo", "sorteio"]})]
    b = [r.user_id for r in standings.compute(players, ms, {"draw_seed": 5, "tiebreakers": ["confronto_direto", "saldo", "sorteio"]})]
    c = {tuple(r.user_id for r in standings.compute(players, ms, {"draw_seed": s, "tiebreakers": ["sorteio"]})) for s in range(1, 30)}
    assert a == b and len(c) > 1  # reproduzível com a mesma semente; muda com outra
