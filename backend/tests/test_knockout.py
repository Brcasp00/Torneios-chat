import pytest  # noqa: F401

from app.services import bracket

REPLAY = "https://replay.pokemonshowdown.com/gen9ou-777"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def win(p1_wins: bool) -> dict:
    """Corpo de resultado melhor de 1 em que o jogador 1 (ou 2) vence."""
    return {
        "p1_wins": int(p1_wins), "p2_wins": int(not p1_wins),
        "p1_remaining": 2 if p1_wins else 0, "p2_remaining": 0 if p1_wins else 2,
        "replay_urls": [REPLAY],
    }


async def setup(client, n=8, third_place=False, **cfg):
    adm = (await client.post("/auth/login", json={"name": "Admin", "password": "admin123"})).json()["access_token"]
    body = {"name": "Copa KO", "template": "knockout", "max_players": n, "config": {"third_place": third_place, **cfg}}
    tid = (await client.post("/tournaments", json=body, headers=auth(adm))).json()["id"]
    users = []
    for i in range(n):
        r = await client.post("/auth/register", json={"name": f"Treinador{i + 1}", "password": "senha123"})
        users.append((r.json()["user"]["id"], r.json()["access_token"]))
    await client.post(f"/tournaments/{tid}/players", json={"user_ids": [u for u, _ in users]}, headers=auth(adm))
    return adm, tid, users


async def start(client, adm, tid, seed=5):
    r = await client.post(f"/tournaments/{tid}/start", json={"seed": seed}, headers=auth(adm))
    assert r.status_code == 200, r.text
    return r.json()


async def bracket_of(client, tid):
    return (await client.get(f"/tournaments/{tid}/bracket")).json()[0]


async def play(client, adm, match_id, p1_wins=True):
    r = await client.post(f"/matches/{match_id}/result", json=win(p1_wins), headers=auth(adm))
    assert r.status_code == 200, r.text
    return r.json()


# ---------- lógica pura ----------
def test_round_names_and_helpers():
    assert [bracket.round_name(r, 3) for r in (1, 2, 3)] == ["Quartas de final", "Semifinal", "Final"]
    assert bracket.round_name(1, 4) == "Oitavas de final"
    assert bracket.round_name(1, 5) == "Rodada de 32"
    assert bracket.is_power_of_two(8) and not bracket.is_power_of_two(6)
    assert bracket.first_round_pairs([1, 2, 3, 4]) == [(1, 2), (3, 4)]


# ---------- API ----------
async def test_start_generates_bracket(client):
    adm, tid, users = await setup(client, 8, third_place=True)
    prev = (await client.post(f"/tournaments/{tid}/draw", json={"seed": 9}, headers=auth(adm))).json()
    assert prev["seed"] == 9 and len(prev["rounds"][0]["matches"]) == 4
    created = await start(client, adm, tid, seed=9)
    assert len(created) == 8  # 4 + 2 + 1 + disputa de 3º lugar
    br = await bracket_of(client, tid)
    assert [r["name"] for r in br["rounds"]] == ["Quartas de final", "Semifinal", "Final"]
    assert [len(r["matches"]) for r in br["rounds"]] == [4, 2, 1]
    assert br["third_place"]["group_label"] == "3rd" and br["champion"] is None
    # a prévia com a mesma seed é idêntica ao chaveamento real
    first = [(m["player1"]["id"], m["player2"]["id"]) for m in br["rounds"][0]["matches"]]
    assert first == [(m["player1"]["id"], m["player2"]["id"]) for m in prev["rounds"][0]["matches"]]
    # rodadas seguintes começam vazias
    assert all(m["player1"] is None and m["player2"] is None for m in br["rounds"][1]["matches"])
    t = (await client.get(f"/tournaments/{tid}")).json()
    assert t["status"] == "running"
    seeds = sorted(p["seed"] for p in t["players"])
    assert seeds == list(range(1, 9))


async def test_full_tournament_with_third_place(client):
    adm, tid, users = await setup(client, 4, third_place=True)
    await start(client, adm, tid)
    br = await bracket_of(client, tid)
    semis = br["rounds"][0]["matches"]
    s1, s2 = semis
    await play(client, adm, s1["id"], p1_wins=True)
    br = await bracket_of(client, tid)
    final, third = br["rounds"][1]["matches"][0], br["third_place"]
    assert final["player1"]["id"] == s1["player1"]["id"] and final["player2"] is None
    assert third["player1"]["id"] == s1["player2"]["id"]  # perdedor da semi vai para o 3º lugar
    await play(client, adm, s2["id"], p1_wins=False)
    br = await bracket_of(client, tid)
    final, third = br["rounds"][1]["matches"][0], br["third_place"]
    assert final["player2"]["id"] == s2["player2"]["id"]
    assert third["player2"]["id"] == s2["player1"]["id"]

    await play(client, adm, third["id"], p1_wins=True)
    assert (await client.get(f"/tournaments/{tid}")).json()["status"] == "running"  # falta a final
    await play(client, adm, final["id"], p1_wins=True)
    br = await bracket_of(client, tid)
    assert br["champion"]["id"] == s1["player1"]["id"] and br["status"] == "finished"
    assert (await client.get(f"/tournaments/{tid}")).json()["status"] == "finished"


async def test_no_draws_in_knockout_even_if_allowed(client):
    adm, tid, users = await setup(client, 4, allow_draw=True)
    await start(client, adm, tid)
    m = (await bracket_of(client, tid))["rounds"][0]["matches"][0]
    r = await client.post(f"/matches/{m['id']}/result", json={"p1_wins": 0, "p2_wins": 0, "is_draw": True, "replay_urls": [REPLAY]}, headers=auth(adm))
    assert r.status_code == 422
    tok = next(t for u, t in users if u == m["player1"]["id"])
    r = await client.post(f"/matches/{m['id']}/report", json={"p1_wins": 0, "p2_wins": 0, "replay_urls": [REPLAY]}, headers=auth(tok))
    assert r.status_code == 422


async def test_player_report_flow_advances_winner(client):
    adm, tid, users = await setup(client, 4)
    await start(client, adm, tid)
    m = (await bracket_of(client, tid))["rounds"][0]["matches"][0]
    tok = next(t for u, t in users if u == m["player2"]["id"])
    r = await client.post(f"/matches/{m['id']}/report", json=win(False), headers=auth(tok))
    assert r.status_code == 200
    final = (await bracket_of(client, tid))["rounds"][1]["matches"][0]
    assert final["player1"] is None  # reporte ainda não avança ninguém
    await client.post(f"/matches/{m['id']}/validate", json={}, headers=auth(adm))
    final = (await bracket_of(client, tid))["rounds"][1]["matches"][0]
    assert final["player1"]["id"] == m["player2"]["id"]


async def test_cannot_report_before_opponent_known(client):
    adm, tid, users = await setup(client, 4)
    await start(client, adm, tid)
    br = await bracket_of(client, tid)
    s1 = br["rounds"][0]["matches"][0]
    await play(client, adm, s1["id"], True)
    final = (await bracket_of(client, tid))["rounds"][1]["matches"][0]
    tok = next(t for u, t in users if u == final["player1"]["id"])
    detail = (await client.get(f"/matches/{final['id']}", headers=auth(tok))).json()
    assert detail["can_report"] is False
    assert (await client.post(f"/matches/{final['id']}/report", json=win(True), headers=auth(tok))).status_code == 409
    assert (await client.post(f"/matches/{final['id']}/result", json=win(True), headers=auth(adm))).status_code == 409


async def test_correction_changes_winner_when_next_not_played(client):
    adm, tid, users = await setup(client, 4)
    await start(client, adm, tid)
    s1 = (await bracket_of(client, tid))["rounds"][0]["matches"][0]
    await play(client, adm, s1["id"], True)
    # corrige: na verdade o jogador 2 venceu
    await play(client, adm, s1["id"], False)
    final = (await bracket_of(client, tid))["rounds"][1]["matches"][0]
    assert final["player1"]["id"] == s1["player2"]["id"]
    # invalidar tira o jogador da final
    r = await client.post(f"/matches/{s1['id']}/invalidate", json={"note": "irregular"}, headers=auth(adm))
    assert r.status_code == 200
    assert (await bracket_of(client, tid))["rounds"][1]["matches"][0]["player1"] is None


async def test_cascade_blocked_when_next_already_played(client):
    adm, tid, users = await setup(client, 4)
    await start(client, adm, tid)
    br = await bracket_of(client, tid)
    s1, s2 = br["rounds"][0]["matches"]
    await play(client, adm, s1["id"], True)
    await play(client, adm, s2["id"], True)
    final = (await bracket_of(client, tid))["rounds"][1]["matches"][0]
    await play(client, adm, final["id"], True)
    assert (await client.get(f"/tournaments/{tid}")).json()["status"] == "finished"

    # trocar o vencedor da semi 1 com a final já jogada => 409 e nada muda
    r = await client.post(f"/matches/{s1['id']}/result", json=win(False), headers=auth(adm))
    assert r.status_code == 409 and "Invalide" in r.json()["detail"]
    r = await client.post(f"/matches/{s1['id']}/invalidate", json={}, headers=auth(adm))
    assert r.status_code == 409
    s1_now = (await client.get(f"/matches/{s1['id']}")).json()
    assert s1_now["status"] == "validated" and s1_now["winner_id"] == s1["player1"]["id"]
    assert (await bracket_of(client, tid))["rounds"][1]["matches"][0]["player1"]["id"] == s1["player1"]["id"]

    # mudar só os Pokémon restantes (mesmo vencedor) é permitido mesmo com a final jogada
    ok = await client.post(f"/matches/{s1['id']}/result", json={**win(True), "p1_remaining": 5}, headers=auth(adm))
    assert ok.status_code == 200

    # invalidando de trás para frente funciona e reabre o torneio
    assert (await client.post(f"/matches/{final['id']}/invalidate", json={}, headers=auth(adm))).status_code == 200
    assert (await client.get(f"/tournaments/{tid}")).json()["status"] == "running"
    assert (await client.post(f"/matches/{s1['id']}/result", json=win(False), headers=auth(adm))).status_code == 200
    final = (await bracket_of(client, tid))["rounds"][1]["matches"][0]
    assert final["player1"]["id"] == s1["player2"]["id"]


async def test_withdrawal_before_playing_gives_walkover_and_advances(client):
    adm, tid, users = await setup(client, 4)
    await start(client, adm, tid)
    br = await bracket_of(client, tid)
    s1 = br["rounds"][0]["matches"][0]
    quitter = s1["player1"]["id"]
    tok = next(t for u, t in users if u == quitter)
    assert (await client.post(f"/tournaments/{tid}/withdraw", headers=auth(tok))).status_code == 204
    s1_now = (await client.get(f"/matches/{s1['id']}")).json()
    assert s1_now["is_walkover"] is True and s1_now["winner_id"] == s1["player2"]["id"]
    final = (await bracket_of(client, tid))["rounds"][1]["matches"][0]
    assert final["player1"]["id"] == s1["player2"]["id"]


async def test_withdrawal_with_future_opponent_resolves_when_opponent_arrives(client):
    adm, tid, users = await setup(client, 8)
    await start(client, adm, tid)
    br = await bracket_of(client, tid)
    q1, q2 = br["rounds"][0]["matches"][0], br["rounds"][0]["matches"][1]
    await play(client, adm, q1["id"], True)  # vencedor de q1 avança e espera o vencedor de q2
    quitter = q1["player1"]["id"]
    tok = next(t for u, t in users if u == quitter)
    await client.post(f"/tournaments/{tid}/withdraw", headers=auth(tok))
    semi = (await bracket_of(client, tid))["rounds"][1]["matches"][0]
    assert semi["status"] == "scheduled" and semi["player1"]["id"] == quitter and semi["player2"] is None

    await play(client, adm, q2["id"], False)  # o adversário chega: ganha por W.O. e já vai para a final
    br = await bracket_of(client, tid)
    semi = br["rounds"][1]["matches"][0]
    assert semi["is_walkover"] is True and semi["winner_id"] == q2["player2"]["id"]
    final = br["rounds"][2]["matches"][0]
    assert final["player1"]["id"] == q2["player2"]["id"]


async def test_reported_result_survives_withdrawal_in_knockout(client):
    adm, tid, users = await setup(client, 4)
    await start(client, adm, tid)
    s1 = (await bracket_of(client, tid))["rounds"][0]["matches"][0]
    opp = s1["player2"]["id"]
    opp_tok = next(t for u, t in users if u == opp)
    await client.post(f"/matches/{s1['id']}/report", json=win(False), headers=auth(opp_tok))  # oponente reporta vitória
    quitter_tok = next(t for u, t in users if u == s1["player1"]["id"])
    await client.post(f"/tournaments/{tid}/withdraw", headers=auth(quitter_tok))
    cur = (await client.get(f"/matches/{s1['id']}")).json()
    assert cur["status"] == "reported" and cur["is_walkover"] is False
    r = await client.post(f"/matches/{s1['id']}/validate", json={}, headers=auth(adm))
    assert r.json()["winner_id"] == opp


async def test_snapshot_history_for_bracket(client):
    adm, tid, _ = await setup(client, 4)
    await start(client, adm, tid)
    s1 = (await bracket_of(client, tid))["rounds"][0]["matches"][0]
    await play(client, adm, s1["id"], True)
    hist = (await client.get(f"/tournaments/{tid}/history")).json()
    assert len(hist) == 2
    snap = (await client.get(f"/tournaments/{tid}/history/{hist[0]['id']}")).json()
    assert {m["round"] for m in snap["data"]["matches"]} == {1, 2}


async def test_best_of_3_knockout(client):
    adm, tid, _ = await setup(client, 4, best_of=3)
    await start(client, adm, tid)
    m = (await bracket_of(client, tid))["rounds"][0]["matches"][0]
    assert m["best_of"] == 3
    r = await client.post(f"/matches/{m['id']}/result", json={"p1_wins": 2, "p2_wins": 1, "replay_urls": [REPLAY] * 3}, headers=auth(adm))
    assert r.status_code == 200
