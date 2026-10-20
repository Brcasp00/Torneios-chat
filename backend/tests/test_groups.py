import pytest  # noqa: F401

from app.services import stages

REPLAY = "https://replay.pokemonshowdown.com/gen9ou-555"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def admin(client):
    return (await client.post("/auth/login", json={"name": "Admin", "password": "admin123"})).json()["access_token"]


async def make_players(client, adm, tid, n):
    users = []
    for i in range(n):
        r = await client.post("/auth/register", json={"name": f"Treinador{i + 1:02d}", "password": "senha123"})
        users.append((r.json()["user"]["id"], r.json()["access_token"]))
    r = await client.post(f"/tournaments/{tid}/players", json={"user_ids": [u for u, _ in users]}, headers=auth(adm))
    assert r.status_code == 201, r.text
    return users


async def create(client, adm, body):
    r = await client.post("/tournaments", json=body, headers=auth(adm))
    assert r.status_code == 201, r.text
    return r.json()


async def matches_of(client, tid, **params):
    return (await client.get(f"/tournaments/{tid}/matches", params=params)).json()


async def play(client, adm, m, rem=2, p1_wins=None):
    """Valida o confronto; por padrão vence o jogador de menor id (resultado determinístico)."""
    if p1_wins is None:
        p1_wins = m["player1"]["id"] < m["player2"]["id"]
    body = {
        "p1_wins": int(p1_wins), "p2_wins": int(not p1_wins),
        "p1_remaining": rem if p1_wins else 0, "p2_remaining": 0 if p1_wins else rem,
        "replay_urls": [REPLAY],
    }
    r = await client.post(f"/matches/{m['id']}/result", json=body, headers=auth(adm))
    assert r.status_code == 200, r.text
    return r.json()


async def play_stage(client, adm, tid, stage_id):
    """Joga todos os confrontos pendentes de uma fase (que já tenham os dois jogadores)."""
    for m in await matches_of(client, tid, stage_id=stage_id, status_="scheduled"):
        if m["player1"] and m["player2"]:
            await play(client, adm, m)


async def detail(client, tid):
    return (await client.get(f"/tournaments/{tid}")).json()


# ---------- lógica pura ----------
def test_standard_order_and_crossing():
    assert stages.standard_order(8) == [1, 8, 4, 5, 2, 7, 3, 6]
    assert stages.standard_order(2) == [1, 2]
    order = stages.crossing_order(["A", "B", "C", "D"], [1, 2])
    pairs = [(order[i], order[i + 1]) for i in range(0, 8, 2)]
    assert pairs == [(("A", 1), ("B", 2)), (("C", 1), ("D", 2)), (("A", 2), ("B", 1)), (("C", 2), ("D", 1))]
    # q=1: 1ºA x 1ºB, 1ºC x 1ºD
    assert stages.crossing_order(["A", "B"], [1]) == [("A", 1), ("B", 1)]
    with pytest.raises(stages.StageError):
        stages.crossing_order(["A", "B", "C"], [1, 2])


# ---------- grupos + mata-mata ----------
async def test_groups_knockout_end_to_end(client):
    adm = await admin(client)
    t = await create(client, adm, {
        "name": "Copa Grupos", "template": "groups_knockout", "max_players": 8,
        "config": {"groups_count": 2, "qualifiers_per_group": 2},
    })
    tid = t["id"]
    g_stage, ko_stage = t["stages"]
    await make_players(client, adm, tid, 8)

    prev = (await client.post(f"/tournaments/{tid}/draw", json={"seed": 4}, headers=auth(adm))).json()
    assert {m["group_label"] for rnd in prev["rounds"] for m in rnd["matches"]} == {"A", "B"}
    created = (await client.post(f"/tournaments/{tid}/start", json={"seed": 4}, headers=auth(adm))).json()
    assert len(created) == 12  # 2 grupos x 6 confrontos
    assert {m["group_label"] for m in created} == {"A", "B"}
    tpl = await detail(client, tid)
    assert {p["group_label"] for p in tpl["players"]} == {"A", "B"}

    st = (await client.get(f"/tournaments/{tid}/standings")).json()[0]
    assert st["stage_type"] == "groups" and [g["label"] for g in st["groups"]] == ["A", "B"]
    assert all(len(g["rows"]) == 4 for g in st["groups"])

    # o mata-mata ainda não existe
    assert await matches_of(client, tid, stage_id=ko_stage["id"]) == []
    await play_stage(client, adm, tid, g_stage["id"])

    st = (await client.get(f"/tournaments/{tid}/standings")).json()[0]
    pos = {g["label"]: [r["user_id"] for r in g["rows"]] for g in st["groups"]}
    assert all(r["played"] == 3 for g in st["groups"] for r in g["rows"])
    assert pos["A"] == sorted(pos["A"]) and pos["B"] == sorted(pos["B"])  # vence quem tem menor id

    # mata-mata criado com cruzamento fixo: 1ºA x 2ºB e 2ºA x 1ºB
    ko = await matches_of(client, tid, stage_id=ko_stage["id"])
    r1 = sorted([m for m in ko if m["round"] == 1], key=lambda m: m["slot"])
    assert [{m["player1"]["id"], m["player2"]["id"]} for m in r1] == [
        {pos["A"][0], pos["B"][1]}, {pos["A"][1], pos["B"][0]},
    ]
    td = await detail(client, tid)
    status_of = {p["user_id"]: p["status"] for p in td["players"]}
    assert all(status_of[u] == "active" for u in pos["A"][:2] + pos["B"][:2])
    assert all(status_of[u] == "eliminated" for u in pos["A"][2:] + pos["B"][2:])
    assert td["status"] == "running"

    await play_stage(client, adm, tid, ko_stage["id"])  # semis
    await play_stage(client, adm, tid, ko_stage["id"])  # final
    td = await detail(client, tid)
    assert td["status"] == "finished" and all(s["status"] == "finished" for s in td["stages"])
    br = (await client.get(f"/tournaments/{tid}/bracket")).json()[0]
    assert br["champion"] is not None


async def test_groups_knockout_16_players_crossing_order(client):
    adm = await admin(client)
    t = await create(client, adm, {
        "name": "Copa 16", "template": "groups_knockout", "max_players": 16,
        "config": {"groups_count": 4, "qualifiers_per_group": 2, "repechage_position": 3},
    })
    tid = t["id"]
    g_stage, ko_stage = t["stages"]
    await make_players(client, adm, tid, 16)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 2}, headers=auth(adm))
    await play_stage(client, adm, tid, g_stage["id"])

    st = (await client.get(f"/tournaments/{tid}/standings")).json()[0]
    pos = {g["label"]: [r["user_id"] for r in g["rows"]] for g in st["groups"]}
    ko = await matches_of(client, tid, stage_id=ko_stage["id"])
    r1 = sorted([m for m in ko if m["round"] == 1], key=lambda m: m["slot"])
    got = [{m["player1"]["id"], m["player2"]["id"]} for m in r1]
    assert got == [
        {pos["A"][0], pos["B"][1]}, {pos["C"][0], pos["D"][1]},
        {pos["A"][1], pos["B"][0]}, {pos["C"][1], pos["D"][0]},
    ]
    # repescagem: 3º de cada grupo fica de fora do principal e registrado para a Fase 7
    td = await detail(client, tid)
    thirds = [pos[g][2] for g in "ABCD"]
    assert sorted(td["config"]["repechage"][str(g_stage["id"])]) == sorted(thirds)
    status_of = {p["user_id"]: p["status"] for p in td["players"]}
    assert all(status_of[u] == "eliminated" for u in thirds)


async def test_group_result_change_rebuilds_or_blocks_knockout(client):
    adm = await admin(client)
    t = await create(client, adm, {
        "name": "Copa Cascata", "template": "groups_knockout", "max_players": 8,
        "config": {"groups_count": 2, "qualifiers_per_group": 2},
    })
    tid = t["id"]
    g_stage, ko_stage = t["stages"]
    await make_players(client, adm, tid, 8)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 1}, headers=auth(adm))
    await play_stage(client, adm, tid, g_stage["id"])
    assert len(await matches_of(client, tid, stage_id=ko_stage["id"])) == 3

    # invalidar um jogo de grupo reabre a fase e desfaz o mata-mata (ainda sem jogos)
    gm = (await matches_of(client, tid, stage_id=g_stage["id"]))[0]
    r = await client.post(f"/matches/{gm['id']}/invalidate", json={"note": "teste"}, headers=auth(adm))
    assert r.status_code == 200
    assert await matches_of(client, tid, stage_id=ko_stage["id"]) == []
    td = await detail(client, tid)
    assert {s["id"]: s["status"] for s in td["stages"]}[ko_stage["id"]] == "pending"
    assert all(p["status"] == "active" for p in td["players"])  # eliminados voltam a ativos enquanto o grupo está aberto

    # refazendo o resultado, o mata-mata volta
    await play(client, adm, gm)
    ko = await matches_of(client, tid, stage_id=ko_stage["id"])
    assert len(ko) == 3

    # com um jogo do mata-mata já validado, mexer no grupo é bloqueado e nada muda
    semi = next(m for m in ko if m["round"] == 1 and m["player1"] and m["player2"])
    await play(client, adm, semi)
    r = await client.post(f"/matches/{gm['id']}/invalidate", json={}, headers=auth(adm))
    assert r.status_code == 409 and "Invalide" in r.json()["detail"]
    assert (await client.get(f"/matches/{gm['id']}")).json()["status"] == "validated"
    assert len(await matches_of(client, tid, stage_id=ko_stage["id"])) == 3


async def test_withdrawal_in_groups(client):
    adm = await admin(client)
    t = await create(client, adm, {
        "name": "Copa Desist", "template": "groups_knockout", "max_players": 8,
        "config": {"groups_count": 2, "qualifiers_per_group": 2},
    })
    tid = t["id"]
    users = await make_players(client, adm, tid, 8)
    await client.post(f"/tournaments/{tid}/start", json={"seed": 1}, headers=auth(adm))
    uid, tok = users[0]
    await client.post(f"/tournaments/{tid}/withdraw", headers=auth(tok))
    mine = await matches_of(client, tid, player_id=uid)
    assert len(mine) == 3 and all(m["is_walkover"] and m["winner_id"] != uid for m in mine)
    st = (await client.get(f"/tournaments/{tid}/standings")).json()[0]
    row = next(r for g in st["groups"] for r in g["rows"] if r["user_id"] == uid)
    assert row["withdrawn"] is True and row["points"] == 0


# ---------- cenário dos 20 jogadores (custom) ----------
def twenty_players_body():
    return {
        "name": "Torneio 20", "template": "custom", "max_players": 20,
        "stages": [
            {"name": "Rodada inicial", "type": "round"},
            {"name": "Playoff", "type": "playoff"},
            {"name": "Mata-mata", "type": "knockout", "config": {"seeding": "standard"}},
        ],
        "rules": [
            {"from_stage": 1, "source": "losers", "pos_from": 1, "pos_to": 10, "target": "eliminated"},
            {"from_stage": 1, "source": "winners", "pos_from": 1, "pos_to": 6, "target": "stage", "to_stage": 3, "to_slot_from": 1},
            {"from_stage": 1, "source": "winners", "pos_from": 7, "pos_to": 10, "target": "stage", "to_stage": 2, "to_slot_from": 1},
            {"from_stage": 2, "source": "losers", "pos_from": 1, "pos_to": 2, "target": "eliminated"},
            {"from_stage": 2, "source": "winners", "pos_from": 1, "pos_to": 2, "target": "stage", "to_stage": 3, "to_slot_from": 7},
        ],
    }


async def test_twenty_players_scenario(client):
    adm = await admin(client)
    t = await create(client, adm, twenty_players_body())
    tid = t["id"]
    s1, s2, s3 = t["stages"]
    await make_players(client, adm, tid, 20)

    created = (await client.post(f"/tournaments/{tid}/start", json={"seed": 8}, headers=auth(adm))).json()
    assert len(created) == 10 and {m["stage_id"] for m in created} == {s1["id"]}

    # saldo dos vencedores: slots 1-6 com 6,6,5,5,4,4 vivos; slots 7-10 com 3,3,2,1 (corte nítido no 6º/7º)
    rem_by_slot = {1: 6, 2: 6, 3: 5, 4: 5, 5: 4, 6: 4, 7: 3, 8: 3, 9: 2, 10: 1}
    ms = await matches_of(client, tid, stage_id=s1["id"])
    winners = {}
    for i, m in enumerate(sorted(ms, key=lambda x: x["slot"]), start=1):
        res = await play(client, adm, m, rem=rem_by_slot[i])
        winners[i] = res["winner_id"]
    top6 = {winners[i] for i in range(1, 7)}
    bottom4 = {winners[i] for i in range(7, 11)}

    # playoff: só os 4 piores vencedores, 2 confrontos; mata-mata ainda não existe
    po = await matches_of(client, tid, stage_id=s2["id"])
    assert len(po) == 2 and {p["id"] for m in po for p in (m["player1"], m["player2"])} == bottom4
    assert await matches_of(client, tid, stage_id=s3["id"]) == []

    po_winners = set()
    for m in po:
        po_winners.add((await play(client, adm, m))["winner_id"])

    # mata-mata com 8: 6 diretos + 2 do playoff, chaveados por seed (1x8, 4x5, 3x6, 2x7)
    ko = await matches_of(client, tid, stage_id=s3["id"])
    r1 = sorted([m for m in ko if m["round"] == 1], key=lambda m: m["slot"])
    assert len(r1) == 4
    entrants = {p["id"] for m in r1 for p in (m["player1"], m["player2"])}
    assert entrants == top6 | po_winners
    top2 = {winners[1], winners[2]}  # os dois melhores saldos (6 vivos) enfrentam os classificados do playoff
    for m in r1:
        ids = {m["player1"]["id"], m["player2"]["id"]}
        if ids & po_winners:
            assert len(ids & po_winners) == 1 and (ids - po_winners) <= top2
    assert top6 | po_winners == entrants

    # eliminados: 10 perdedores da rodada + 2 do playoff
    td = await detail(client, tid)
    statuses = {}
    for p in td["players"]:
        statuses.setdefault(p["status"], []).append(p["user_id"])
    assert len(statuses["eliminated"]) == 12 and set(statuses["active"]) == entrants

    await play_stage(client, adm, tid, s3["id"])
    await play_stage(client, adm, tid, s3["id"])
    await play_stage(client, adm, tid, s3["id"])
    td = await detail(client, tid)
    assert td["status"] == "finished"
    assert (await client.get(f"/tournaments/{tid}/bracket")).json()[0]["champion"] is not None


async def test_custom_static_validation(client):
    adm = await admin(client)
    base = {"name": "Custom V", "template": "custom", "max_players": 8}

    async def post(stages_, rules_, **over):
        return await client.post("/tournaments", json={**base, "stages": stages_, "rules": rules_, **over}, headers=auth(adm))

    st = [{"name": "A", "type": "round"}, {"name": "B", "type": "knockout"}]
    ok_rule = {"from_stage": 1, "source": "winners", "pos_from": 1, "pos_to": 4, "target": "stage", "to_stage": 2, "to_slot_from": 1}
    assert (await post(st, [ok_rule])).status_code == 201
    # vagas não começam em 1
    assert (await post(st, [{**ok_rule, "to_slot_from": 2}])).status_code == 422
    # mata-mata com 3 jogadores
    assert (await post(st, [{**ok_rule, "pos_to": 3}])).status_code == 422
    # só existem 4 vencedores numa rodada de 8
    assert (await post(st, [{**ok_rule, "pos_to": 5}])).status_code == 422
    # fase sem entrada
    assert (await post(st, [])).status_code == 422
    # 'winners' em fase de liga
    assert (await post([{"name": "L", "type": "league"}, {"name": "B", "type": "knockout"}], [ok_rule])).status_code == 422
    # sobreposição de posições
    assert (await post(st, [ok_rule, {**ok_rule, "pos_from": 2, "pos_to": 3, "to_slot_from": 5}])).status_code == 422
    # group_position em fase que não é de grupos
    assert (await post(st, [{**ok_rule, "source": "group_position"}])).status_code == 422


async def test_start_rejects_bad_group_setup(client):
    adm = await admin(client)
    t = await create(client, adm, {
        "name": "Grupos Curtos", "template": "custom", "max_players": 4,
        "stages": [{"name": "Grupos", "type": "groups", "config": {"groups_count": 2}}],
    })
    await make_players(client, adm, t["id"], 4)
    r = await client.post(f"/tournaments/{t['id']}/start", json={"seed": 1}, headers=auth(adm))
    assert r.status_code == 200  # 2 grupos de 2 é válido
    assert len(r.json()) == 2
