"""Fase 8: histórico por rodada/final de fase e adiamento de jogos e rodadas."""
from tests.test_groups import admin, auth, create, detail, make_players, matches_of, play, play_stage  # noqa: F401
from tests.test_repechage import scenario, SUB_BODY  # noqa: F401


async def league(client, adm, players=4):
    t = await create(client, adm, {"name": "Liga Hist", "template": "league", "max_players": players})
    users = await make_players(client, adm, t["id"], players)
    r = await client.post(f"/tournaments/{t['id']}/start", json={"seed": 7}, headers=auth(adm))
    assert r.status_code == 200, r.text
    return t, users, t["stages"][0]["id"]


async def round_matches(client, tid, sid, rnd):
    return [m for m in await matches_of(client, tid, stage_id=sid) if m["round"] == rnd]


async def play_round(client, adm, tid, sid, rnd):
    for m in await round_matches(client, tid, sid, rnd):
        if m["status"] == "scheduled" and not m["postponed"]:
            await play(client, adm, m)


async def rounds_hist(client, tid, **params):
    r = await client.get(f"/tournaments/{tid}/history/rounds", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def played(snapshot):
    return {r["user_id"]: r["played"] for r in snapshot["data"]["rows"]}


async def test_every_round_is_saved_in_history(client):
    adm = await admin(client)
    t, users, sid = await league(client, adm)
    tid = t["id"]
    assert await rounds_hist(client, tid) == []
    for rnd in (1, 2, 3):
        await play_round(client, adm, tid, sid, rnd)
        hist = await rounds_hist(client, tid)
        assert [h["round"] for h in hist] == list(range(1, rnd + 1))
        assert all(v == rnd for v in played(hist[-1]).values())
    # cada rodada guarda a tabela daquele momento (a 1ª continua mostrando só 1 jogo por jogador)
    hist = await rounds_hist(client, tid)
    assert all(v == 1 for v in played(hist[0]).values()) and all(v == 2 for v in played(hist[1]).values())
    assert hist[0]["data"]["rounds_total"] == 3 and hist[0]["postponed"] == []

    # estado final da fase
    fin = (await client.get(f"/tournaments/{tid}/history/stages")).json()
    assert len(fin) == 1 and fin[0]["stage_type"] == "league" and fin[0]["versions"] == 1
    assert [r["position"] for r in fin[0]["data"]["rows"]] == [1, 2, 3, 4]
    # registros por tipo
    kinds = (await client.get(f"/tournaments/{tid}/history", params={"kind": "round"})).json()
    assert len(kinds) == 3 and all(k["kind"] == "round" for k in kinds)
    snap = (await client.get(f"/tournaments/{tid}/history/{kinds[0]['id']}")).json()
    assert snap["tournament_id"] == tid and snap["data"]["rows"]


async def test_postponed_game_enters_the_round_where_it_is_played(client):
    adm = await admin(client)
    t, users, sid = await league(client, adm)
    tid = t["id"]
    r1 = await round_matches(client, tid, sid, 1)
    postponed = r1[0]
    p_ids = {postponed["player1"]["id"], postponed["player2"]["id"]}

    # só admin/organizador adia; jogador comum não
    token = next(tok for uid, tok in users if uid in p_ids)
    r = await client.post(f"/matches/{postponed['id']}/postpone", json={"reason": "viagem"}, headers=auth(token))
    assert r.status_code == 403
    r = await client.post(f"/matches/{postponed['id']}/postpone", json={"reason": "viagem"}, headers=auth(adm))
    assert r.status_code == 200 and r.json()["postponed"] is True and r.json()["postponed_reason"] == "viagem"

    # rodada 1 fecha com o jogo adiado: tabela com 'jogos' diferentes e registro do adiamento
    await play_round(client, adm, tid, sid, 1)
    h1 = (await rounds_hist(client, tid))[0]
    assert [p["match_id"] for p in h1["postponed"]] == [postponed["id"]] and h1["postponed"][0]["reason"] == "viagem"
    assert {u for u, n in played(h1).items() if n == 0} == p_ids and {n for u, n in played(h1).items() if u not in p_ids} == {1}
    original = h1["data"]

    await play_round(client, adm, tid, sid, 2)
    h2 = (await rounds_hist(client, tid))[1]
    assert [p["match_id"] for p in h2["postponed"]] == [postponed["id"]]  # ainda pendente
    # o jogo adiado é disputado durante a rodada 3: entra na tabela da rodada 3, não na da rodada 1
    await play(client, adm, postponed)
    await play_round(client, adm, tid, sid, 3)
    hist = await rounds_hist(client, tid)
    assert [h["round"] for h in hist] == [1, 2, 3]
    assert hist[0]["data"] == original and hist[1]["postponed"][0]["match_id"] == postponed["id"]
    h3 = hist[2]
    assert [p["match_id"] for p in h3["played_postponed"]] == [postponed["id"]] and h3["played_postponed"][0]["original_round"] == 1
    assert h3["postponed"] == [] and all(v == 3 for v in played(h3).values())
    # a rodada original não foi tocada e o histórico lembra que houve adiamento
    assert (await client.get(f"/matches/{postponed['id']}")).json()["postponed"] is True


async def test_stage_does_not_finish_while_postponed_game_is_pending(client):
    adm = await admin(client)
    t, users, sid = await league(client, adm)
    tid = t["id"]
    last = (await round_matches(client, tid, sid, 3))[0]
    # adiar a rodada inteira (todos os jogos pendentes dela)
    r = await client.post(f"/tournaments/{tid}/rounds/postpone", json={"stage_id": sid, "round": 3, "reason": "feriado"}, headers=auth(adm))
    assert r.status_code == 200 and len(r.json()) == 2 and all(m["postponed"] for m in r.json())
    assert len((await matches_of(client, tid, postponed="true"))) == 2
    await play_round(client, adm, tid, sid, 1)
    await play_round(client, adm, tid, sid, 2)

    # rodada 3 fecha no histórico (adiada), mas a fase e o torneio não encerram
    hist = await rounds_hist(client, tid)
    assert [h["round"] for h in hist] == [1, 2, 3] and len(hist[2]["postponed"]) == 2
    td = await detail(client, tid)
    assert td["status"] == "running" and td["stages"][0]["status"] == "running"
    assert (await client.get(f"/tournaments/{tid}/history/stages")).json() == []
    r = await client.patch(f"/tournaments/{tid}/status", json={"status": "finished"}, headers=auth(adm))
    assert r.status_code == 409 and "adiado" in r.json()["detail"]

    # jogadores ainda podem reportar o jogo adiado; ao validar, a fase encerra
    for m in await round_matches(client, tid, sid, 3):
        await play(client, adm, m)
    td = await detail(client, tid)
    assert td["status"] == "finished"
    fin = (await client.get(f"/tournaments/{tid}/history/stages")).json()
    assert len(fin) == 1 and len(fin[0]["data"]["played_postponed"]) == 2
    assert last["id"] in [p["match_id"] for p in fin[0]["data"]["played_postponed"]]


async def test_postpone_rules_and_resume(client):
    adm = await admin(client)
    t, users, sid = await league(client, adm)
    tid = t["id"]
    m1, m2 = (await round_matches(client, tid, sid, 1))
    await play(client, adm, m1)
    # jogo já decidido não pode ser adiado; rodada inexistente; jogador comum não adia
    assert (await client.post(f"/matches/{m1['id']}/postpone", json={}, headers=auth(adm))).status_code == 409
    assert (await client.post(f"/tournaments/{tid}/rounds/postpone", json={"stage_id": sid, "round": 99}, headers=auth(adm))).status_code == 404
    tok = users[0][1]
    assert (await client.post(f"/tournaments/{tid}/rounds/postpone", json={"stage_id": sid, "round": 2}, headers=auth(tok))).status_code == 403
    # retomar
    assert (await client.post(f"/matches/{m2['id']}/postpone", json={}, headers=auth(adm))).status_code == 200
    assert (await client.post(f"/matches/{m2['id']}/postpone", json={}, headers=auth(adm))).status_code == 409
    h = await rounds_hist(client, tid)
    assert len(h) == 1 and not h[0]["reopened"]
    assert (await client.post(f"/matches/{m2['id']}/resume", headers=auth(adm))).status_code == 200
    assert (await client.post(f"/matches/{m2['id']}/resume", headers=auth(adm))).status_code == 409
    h = await rounds_hist(client, tid)  # a rodada voltou a ter jogo em aberto
    assert h[0]["reopened"] is True
    await play(client, adm, m2)
    h = await rounds_hist(client, tid)
    assert len(h) == 1 and h[0]["reopened"] is False and all(v == 1 for v in played(h[0]).values())
    # retomar rodada sem adiados
    assert (await client.post(f"/tournaments/{tid}/rounds/resume", json={"stage_id": sid, "round": 2}, headers=auth(adm))).status_code == 409


async def test_knockout_is_not_postponable(client):
    adm = await admin(client)
    t = await create(client, adm, {"name": "Mata Hist", "template": "knockout", "max_players": 4})
    await make_players(client, adm, t["id"], 4)
    await client.post(f"/tournaments/{t['id']}/start", json={"seed": 1}, headers=auth(adm))
    m = (await matches_of(client, t["id"]))[0]
    assert (await client.post(f"/matches/{m['id']}/postpone", json={}, headers=auth(adm))).status_code == 409


async def test_final_state_of_groups_repechage_and_knockout(client):
    adm = await admin(client)
    parent, sub, g_stage, ko_stage, users = await scenario(client, adm)
    pid, sid = parent["id"], sub["id"]
    # fase de grupos encerrada: estado final salvo; rodadas dos grupos consultáveis
    fin = (await client.get(f"/tournaments/{pid}/history/stages")).json()
    assert [(f["stage_type"], f["tournament_id"]) for f in fin] == [("groups", pid)]
    assert set(fin[0]["data"]["groups"]) == {"A", "B"}
    rounds = await rounds_hist(client, pid)
    assert [r["round"] for r in rounds] == [1, 2, 3] and set(rounds[0]["data"]["groups"]) == {"A", "B"}

    pos = {label: [r["user_id"] for r in rows] for label, rows in fin[0]["data"]["groups"].items()}
    manual = [pos["A"][1], pos["B"][1]]
    await client.post(f"/tournaments/{sid}/players", json={"user_ids": manual}, headers=auth(adm))
    await client.post(f"/tournaments/{sid}/start", json={"seed": 5}, headers=auth(adm))
    sub_stage = sub["stages"][0]["id"]
    await play_stage(client, adm, sid, sub_stage)
    await play_stage(client, adm, sid, sub_stage)

    # repescagem encerrada aparece no histórico do principal, com o chaveamento final
    fin = (await client.get(f"/tournaments/{pid}/history/stages")).json()
    assert [(f["stage_type"], f["tournament_id"]) for f in fin] == [("groups", pid), ("knockout", sid)]
    assert fin[1]["tournament_name"] == "Repescagem" and len(fin[1]["data"]["ranking"]) == 4

    await play_stage(client, adm, pid, ko_stage["id"])
    await play_stage(client, adm, pid, ko_stage["id"])
    fin = (await client.get(f"/tournaments/{pid}/history/stages")).json()
    assert [f["stage_id"] for f in fin] == [g_stage["id"], ko_stage["id"], sub["stages"][0]["id"]]
    ko = fin[1]
    assert ko["stage_type"] == "knockout" and ko["data"]["ranking"][0]["position"] == 1 and len(ko["data"]["matches"]) == 3

    # corrigir um resultado depois de encerrado cria nova versão do estado final
    final = max(await matches_of(client, pid, stage_id=ko_stage["id"]), key=lambda m: m["round"])
    await client.post(f"/matches/{final['id']}/invalidate", json={}, headers=auth(adm))
    await play(client, adm, final, p1_wins=final["player1"]["id"] > final["player2"]["id"])
    fin = (await client.get(f"/tournaments/{pid}/history/stages")).json()
    assert next(f for f in fin if f["stage_id"] == ko_stage["id"])["versions"] == 2
