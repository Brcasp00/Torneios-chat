from types import SimpleNamespace

import pytest  # noqa: F401

from app.services import schedule, standings

REPLAY = "https://replay.pokemonshowdown.com/gen9ou-123456"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- lógica pura ----------
def test_round_robin_even_and_odd():
    for n in (2, 4, 6, 5):
        ids = list(range(1, n + 1))
        rounds = schedule.round_robin(ids)
        pairs = [frozenset((a, b)) for rnd in rounds for a, b, _ in rnd]
        assert len(pairs) == len(set(pairs)) == n * (n - 1) // 2  # todos contra todos, sem repetir
        for rnd in rounds:
            seen = [p for a, b, _ in rnd for p in (a, b)]
            assert len(seen) == len(set(seen))  # ninguém joga duas vezes na mesma rodada
    assert len(schedule.round_robin(list(range(4)))) == 3
    assert len(schedule.round_robin(list(range(5)))) == 5  # ímpar: um descansa por rodada


def test_round_robin_double_round_and_seed():
    rounds = schedule.round_robin([1, 2, 3, 4], double_round=True)
    assert len(rounds) == 6
    first = {(a, b) for rnd in rounds[:3] for a, b, _ in rnd}
    second = {(b, a) for rnd in rounds[3:] for a, b, _ in rnd}
    assert first == second
    assert {leg for rnd in rounds[3:] for *_, leg in rnd} == {2}
    assert schedule.shuffled([1, 2, 3, 4, 5, 6], 42) == schedule.shuffled([1, 2, 3, 4, 5, 6], 42)


def _m(p1, p2, w1, w2, r1, r2, draw=False, best_of=1):
    winner = None if draw else (p1 if w1 > w2 else p2)
    return SimpleNamespace(player1_id=p1, player2_id=p2, p1_wins=w1, p2_wins=w2, p1_remaining=r1, p2_remaining=r2,
                           is_draw=draw, winner_id=winner, status="validated", best_of=best_of)


def test_standings_points_and_saldo_tiebreak():
    players = {1: ("Ana", False), 2: ("Bia", False), 3: ("Caio", False)}
    # Ana e Bia vencem Caio; Ana vence Bia por menos saldo que Bia fez em Caio... todos com 6 pts
    ms = [_m(1, 3, 1, 0, 2, 0), _m(2, 3, 1, 0, 5, 0), _m(1, 2, 0, 1, 0, 1)]
    rows = standings.compute(players, ms, {})
    assert [r.name for r in rows] == ["Bia", "Ana", "Caio"]  # Bia: saldo +6; Ana: +1
    assert rows[0].points == 6 and rows[2].points == 0 and rows[0].saldo == 6


def test_standings_head_to_head_after_saldo_and_wins():
    players = {1: ("Zeca", False), 2: ("Bia", False), 3: ("Caio", False), 4: ("Dani", False)}
    ms = [
        _m(1, 2, 1, 0, 3, 0),  # Zeca > Bia  (+3 / -3)
        _m(3, 1, 1, 0, 3, 0),  # Caio > Zeca (+3 / -3)
        _m(2, 4, 1, 0, 3, 0),  # Bia  > Dani (+3 / -3)
    ]
    rows = standings.compute(players, ms, {})
    # Zeca e Bia: 3 pts, saldo 0, 1 vitória. Só o confronto direto (Zeca venceu) os separa;
    # sem ele, a ordem alfabética colocaria Bia na frente.
    assert [r.name for r in rows] == ["Caio", "Zeca", "Bia", "Dani"]


def test_standings_saldo_ignored_in_best_of_3():
    players = {1: ("Ana", False), 2: ("Bia", False)}
    rows = standings.compute(players, [_m(1, 2, 2, 0, 4, 0, best_of=3)], {})
    assert rows[0].saldo == 0 and rows[0].points == 3


# ---------- API ----------
async def setup(client, n=4, **cfg):
    adm = (await client.post("/auth/login", json={"name": "Admin", "password": "admin123"})).json()["access_token"]
    body = {"name": "Liga Teste", "template": "league", "max_players": n, "config": cfg}
    tid = (await client.post("/tournaments", json=body, headers=auth(adm))).json()["id"]
    users = []
    for i in range(n):
        r = await client.post("/auth/register", json={"name": f"Jogador{i + 1}", "password": "senha123"})
        users.append((r.json()["user"]["id"], r.json()["access_token"]))
    await client.post(f"/tournaments/{tid}/players", json={"user_ids": [u for u, _ in users]}, headers=auth(adm))
    return adm, tid, users


async def matches(client, tid):
    return (await client.get(f"/tournaments/{tid}/matches")).json()


async def test_preview_matches_start_with_same_seed(client):
    adm, tid, _ = await setup(client)
    prev = (await client.post(f"/tournaments/{tid}/draw", json={"seed": 7}, headers=auth(adm))).json()
    assert prev["seed"] == 7 and len(prev["rounds"]) == 3
    assert (await client.get(f"/tournaments/{tid}/matches")).json() == []  # prévia não salva nada
    r = await client.post(f"/tournaments/{tid}/start", json={"seed": 7}, headers=auth(adm))
    assert r.status_code == 200 and len(r.json()) == 6
    started = [(m["round"], m["player1"]["id"], m["player2"]["id"]) for m in r.json()]
    expected = [(i, mm["player1"]["id"], mm["player2"]["id"]) for i, rnd in enumerate(prev["rounds"], 1) for mm in rnd["matches"]]
    assert started == expected
    t = (await client.get(f"/tournaments/{tid}")).json()
    assert t["status"] == "running" and t["config"]["draw_seed"] == 7
    assert (await client.post(f"/tournaments/{tid}/start", json={}, headers=auth(adm))).status_code == 409


async def test_start_requires_staff_and_full(client):
    adm, tid, users = await setup(client)
    assert (await client.post(f"/tournaments/{tid}/start", json={}, headers=auth(users[0][1]))).status_code == 403
    await client.delete(f"/tournaments/{tid}/players/{users[0][0]}", headers=auth(adm))
    assert (await client.post(f"/tournaments/{tid}/start", json={}, headers=auth(adm))).status_code == 409


async def test_report_validate_and_standings(client):
    adm, tid, users = await setup(client)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 1}, headers=auth(adm))
    m = (await matches(client, tid))[0]
    p1_tok = next(t for u, t in users if u == m["player1"]["id"])
    outsider = next(t for u, t in users if u not in (m["player1"]["id"], m["player2"]["id"]))
    mid = m["id"]

    detail = (await client.get(f"/matches/{mid}")).json()
    assert detail["can_report"] is False and detail["tournament_name"] == "Liga Teste"
    detail = (await client.get(f"/matches/{mid}", headers=auth(p1_tok))).json()
    assert detail["can_report"] is True

    body = {"p1_wins": 1, "p2_wins": 0, "p1_remaining": 3, "p2_remaining": 0, "replay_urls": [REPLAY]}
    assert (await client.post(f"/matches/{mid}/report", json=body, headers=auth(outsider))).status_code == 403
    assert (await client.post(f"/matches/{mid}/report", json=body)).status_code == 401
    assert (await client.post(f"/matches/{mid}/report", json={**body, "replay_urls": []}, headers=auth(p1_tok))).status_code == 422
    assert (await client.post(f"/matches/{mid}/report", json={**body, "replay_urls": ["http://evil.com/x"]}, headers=auth(p1_tok))).status_code == 422
    assert (await client.post(f"/matches/{mid}/report", json={**body, "p2_remaining": 2}, headers=auth(p1_tok))).status_code == 422  # perdedor com vivo
    assert (await client.post(f"/matches/{mid}/report", json={**body, "p1_remaining": 0}, headers=auth(p1_tok))).status_code == 422
    r = await client.post(f"/matches/{mid}/report", json=body, headers=auth(p1_tok))
    assert r.status_code == 200 and r.json()["status"] == "reported"

    # reporte ainda não conta na tabela
    table = (await client.get(f"/tournaments/{tid}/standings")).json()[0]["rows"]
    assert all(row["played"] == 0 for row in table)

    # jogador não valida
    assert (await client.post(f"/matches/{mid}/validate", json={}, headers=auth(p1_tok))).status_code == 403
    r = await client.post(f"/matches/{mid}/validate", json={}, headers=auth(adm))
    assert r.status_code == 200 and r.json()["status"] == "validated" and r.json()["winner_id"] == m["player1"]["id"]
    table = (await client.get(f"/tournaments/{tid}/standings")).json()[0]["rows"]
    assert table[0]["user_id"] == m["player1"]["id"] and table[0]["points"] == 3 and table[0]["saldo"] == 3
    assert table[-1]["saldo"] == -3 and sum(row["played"] for row in table) == 2

    # já validado: jogador não reporta mais
    assert (await client.post(f"/matches/{mid}/report", json=body, headers=auth(p1_tok))).status_code == 409


async def test_reject_then_new_report(client):
    adm, tid, users = await setup(client)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 1}, headers=auth(adm))
    m = (await matches(client, tid))[0]
    tok = next(t for u, t in users if u == m["player2"]["id"])
    body = {"p1_wins": 0, "p2_wins": 1, "p1_remaining": 0, "p2_remaining": 2, "replay_urls": [REPLAY]}
    await client.post(f"/matches/{m['id']}/report", json=body, headers=auth(tok))
    r = await client.post(f"/matches/{m['id']}/reject", json={"note": "replay errado"}, headers=auth(adm))
    assert r.json()["status"] == "scheduled" and r.json()["reports"][0]["status"] == "rejected"
    r = await client.post(f"/matches/{m['id']}/report", json=body, headers=auth(tok))
    assert r.json()["status"] == "reported"
    # novo reporte substitui o pendente anterior
    r = await client.post(f"/matches/{m['id']}/report", json={**body, "p2_remaining": 4}, headers=auth(tok))
    assert [x["status"] for x in r.json()["reports"]] == ["pending", "rejected", "rejected"]


async def test_draws_follow_tournament_rule(client):
    adm, tid, users = await setup(client, allow_draw=False)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 1}, headers=auth(adm))
    m = (await matches(client, tid))[0]
    r = await client.post(f"/matches/{m['id']}/result", json={"p1_wins": 0, "p2_wins": 0, "is_draw": True, "replay_urls": [REPLAY]}, headers=auth(adm))
    assert r.status_code == 422


async def test_draw_and_admin_correction_and_invalidate(client):
    adm, tid, users = await setup(client, allow_draw=True)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 1}, headers=auth(adm))
    ms = await matches(client, tid)
    a, b = ms[0], ms[1]
    r = await client.post(f"/matches/{a['id']}/result", json={"p1_wins": 0, "p2_wins": 0, "p1_remaining": 2, "p2_remaining": 2, "is_draw": True, "replay_urls": [REPLAY]}, headers=auth(adm))
    assert r.status_code == 200 and r.json()["is_draw"] is True
    table = (await client.get(f"/tournaments/{tid}/standings")).json()[0]["rows"]
    drawn = {a["player1"]["id"], a["player2"]["id"]}
    assert {row["user_id"]: row["points"] for row in table if row["user_id"] in drawn} == {i: 1 for i in drawn}

    # corrige para vitória: recalcula em cascata
    r = await client.post(f"/matches/{a['id']}/result", json={"p1_wins": 1, "p2_wins": 0, "p1_remaining": 1, "p2_remaining": 0, "replay_urls": [REPLAY]}, headers=auth(adm))
    assert r.json()["is_draw"] is False
    table = (await client.get(f"/tournaments/{tid}/standings")).json()[0]["rows"]
    assert table[0]["user_id"] == a["player1"]["id"] and table[0]["points"] == 3

    # invalida: volta ao estado inicial
    r = await client.post(f"/matches/{a['id']}/invalidate", json={"note": "irregularidade"}, headers=auth(adm))
    assert r.json()["status"] == "scheduled" and r.json()["p1_wins"] is None
    table = (await client.get(f"/tournaments/{tid}/standings")).json()[0]["rows"]
    assert all(row["points"] == 0 for row in table)
    assert (await client.post(f"/matches/{a['id']}/invalidate", json={}, headers=auth(adm))).status_code == 409

    # histórico guarda cada etapa
    hist = (await client.get(f"/tournaments/{tid}/history")).json()
    assert len(hist) >= 4
    snap = (await client.get(f"/tournaments/{tid}/history/{hist[-1]['id']}")).json()
    assert len(snap["data"]["rows"]) == 4
    assert (await client.get(f"/tournaments/{tid}/history/99999")).status_code == 404


async def test_walkover_and_withdrawal(client):
    adm, tid, users = await setup(client)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 1}, headers=auth(adm))
    ms = await matches(client, tid)
    # 1 jogo já validado antes da desistência
    first = ms[0]
    await client.post(f"/matches/{first['id']}/result", json={"p1_wins": 1, "p2_wins": 0, "p1_remaining": 2, "p2_remaining": 0, "replay_urls": [REPLAY]}, headers=auth(adm))
    quitter_id, quitter_tok = users[0]
    pending_of_quitter = [m for m in ms if quitter_id in (m["player1"]["id"], m["player2"]["id"]) and m["id"] != first["id"]]

    assert (await client.post(f"/tournaments/{tid}/withdraw", headers=auth(quitter_tok))).status_code == 204
    after = {m["id"]: m for m in await matches(client, tid)}
    for m in pending_of_quitter:
        cur = after[m["id"]]
        assert cur["status"] == "validated" and cur["is_walkover"] is True
        assert cur["winner_id"] not in (None, quitter_id)
    table = (await client.get(f"/tournaments/{tid}/standings")).json()[0]["rows"]
    quitter_row = next(r for r in table if r["user_id"] == quitter_id)
    assert quitter_row["withdrawn"] is True
    # cada adversário que ainda ia jogar com o desistente ganhou 3 pontos e +3 de saldo no W.O.
    wo_winners = [after[m["id"]]["winner_id"] for m in pending_of_quitter]
    assert len(wo_winners) == len(set(wo_winners)) and all(w != quitter_id for w in wo_winners)

    # W.O. manual do admin
    other = next(m for m in after.values() if m["status"] == "scheduled")
    r = await client.post(f"/matches/{other['id']}/walkover", json={"winner_id": other["player2"]["id"]}, headers=auth(adm))
    assert r.json()["is_walkover"] is True and r.json()["p2_remaining"] == 3
    assert (await client.post(f"/matches/{other['id']}/walkover", json={"winner_id": 99999}, headers=auth(adm))).status_code == 422


async def test_tournament_finishes_when_all_matches_done(client):
    adm, tid, _ = await setup(client, n=3)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 3}, headers=auth(adm))
    ms = await matches(client, tid)
    assert len(ms) == 3
    for m in ms:
        await client.post(f"/matches/{m['id']}/result", json={"p1_wins": 1, "p2_wins": 0, "p1_remaining": 1, "p2_remaining": 0, "replay_urls": [REPLAY]}, headers=auth(adm))
    t = (await client.get(f"/tournaments/{tid}")).json()
    assert t["status"] == "finished" and t["stages"][0]["status"] == "finished"
    # invalidar reabre o torneio
    await client.post(f"/matches/{ms[0]['id']}/invalidate", json={}, headers=auth(adm))
    assert (await client.get(f"/tournaments/{tid}")).json()["status"] == "running"


async def test_best_of_3_rules(client):
    adm, tid, users = await setup(client, best_of=3)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 1}, headers=auth(adm))
    m = (await matches(client, tid))[0]
    assert m["best_of"] == 3
    bad = await client.post(f"/matches/{m['id']}/result", json={"p1_wins": 1, "p2_wins": 0, "replay_urls": [REPLAY]}, headers=auth(adm))
    assert bad.status_code == 422  # precisa de 2 vitórias
    ok = await client.post(f"/matches/{m['id']}/result", json={"p1_wins": 2, "p2_wins": 1, "p1_remaining": 4, "replay_urls": [REPLAY] * 3}, headers=auth(adm))
    assert ok.status_code == 200
    table = (await client.get(f"/tournaments/{tid}/standings")).json()[0]["rows"]
    assert all(r["saldo"] == 0 for r in table)  # em melhor de 3 o saldo não conta
    assert (await client.post(f"/matches/{m['id']}/result", json={"p1_wins": 2, "p2_wins": 0, "replay_urls": [REPLAY] * 4}, headers=auth(adm))).status_code == 422


async def test_delete_started_tournament_as_admin(client):
    adm, tid, _ = await setup(client)
    await client.post(f"/tournaments/{tid}/start", json={}, headers=auth(adm))
    assert (await client.delete(f"/tournaments/{tid}", headers=auth(adm))).status_code == 204
    assert (await client.get(f"/tournaments/{tid}")).status_code == 404


async def test_draw_only_as_0x0(client):
    adm, tid, users = await setup(client, allow_draw=True, best_of=3)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 1}, headers=auth(adm))
    m = (await matches(client, tid))[0]
    tok = next(t for u, t in users if u == m["player1"]["id"])
    # 1x1 em melhor de 3 não é empate válido
    r = await client.post(f"/matches/{m['id']}/report", json={"p1_wins": 1, "p2_wins": 1, "replay_urls": [REPLAY]}, headers=auth(tok))
    assert r.status_code == 422
    # 0x0 é aceito pelo jogador e o admin valida como empate
    r = await client.post(f"/matches/{m['id']}/report", json={"p1_wins": 0, "p2_wins": 0, "replay_urls": [REPLAY]}, headers=auth(tok))
    assert r.status_code == 200
    r = await client.post(f"/matches/{m['id']}/validate", json={"is_draw": True}, headers=auth(adm))
    assert r.json()["is_draw"] is True and r.json()["winner_id"] is None


async def test_admin_marks_draw_on_reported_winner(client):
    adm, tid, users = await setup(client, allow_draw=True)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 1}, headers=auth(adm))
    m = (await matches(client, tid))[0]
    tok = next(t for u, t in users if u == m["player1"]["id"])
    body = {"p1_wins": 1, "p2_wins": 0, "p1_remaining": 2, "p2_remaining": 0, "replay_urls": [REPLAY]}
    await client.post(f"/matches/{m['id']}/report", json=body, headers=auth(tok))
    r = await client.post(f"/matches/{m['id']}/validate", json={"is_draw": True}, headers=auth(adm))
    assert r.json()["is_draw"] is True and (r.json()["p1_wins"], r.json()["p2_wins"]) == (0, 0)


async def test_reported_result_survives_withdrawal(client):
    adm, tid, users = await setup(client)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 1}, headers=auth(adm))
    ms = await matches(client, tid)
    quitter_id, quitter_tok = users[0]
    mine = [m for m in ms if quitter_id in (m["player1"]["id"], m["player2"]["id"])]
    reported = mine[0]
    # o ADVERSÁRIO do desistente reporta que venceu, antes da desistência
    opp_id = reported["player2"]["id"] if reported["player1"]["id"] == quitter_id else reported["player1"]["id"]
    opp_tok = next(t for u, t in users if u == opp_id)
    p1_wins = 1 if reported["player1"]["id"] == opp_id else 0
    body = {"p1_wins": p1_wins, "p2_wins": 1 - p1_wins, "p1_remaining": 2 * p1_wins, "p2_remaining": 2 * (1 - p1_wins), "replay_urls": [REPLAY]}
    assert (await client.post(f"/matches/{reported['id']}/report", json=body, headers=auth(opp_tok))).status_code == 200

    assert (await client.post(f"/tournaments/{tid}/withdraw", headers=auth(quitter_tok))).status_code == 204
    after = {m["id"]: m for m in await matches(client, tid)}
    assert after[reported["id"]]["status"] == "reported" and after[reported["id"]]["is_walkover"] is False
    for m in mine[1:]:
        assert after[m["id"]]["is_walkover"] is True  # os demais jogos sem reporte viram W.O.
    # o admin ainda valida o reporte, e o resultado reportado vale
    r = await client.post(f"/matches/{reported['id']}/validate", json={}, headers=auth(adm))
    assert r.status_code == 200 and r.json()["winner_id"] == opp_id and r.json()["is_walkover"] is False
