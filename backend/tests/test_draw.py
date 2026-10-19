import random
from types import SimpleNamespace

import pytest  # noqa: F401

from app.services import engine

REPLAY = "https://replay.pokemonshowdown.com/gen9ou-321"


def auth(token):
    return {"Authorization": f"Bearer {token}"}


async def admin(client):
    return (await client.post("/auth/login", json={"name": "Admin", "password": "admin123"})).json()["access_token"]


async def setup(client, body, n):
    adm = await admin(client)
    r = await client.post("/tournaments", json=body, headers=auth(adm))
    assert r.status_code == 201, r.text
    t = r.json()
    users = []
    for i in range(n):
        u = await client.post("/auth/register", json={"name": f"Jogador{i + 1:02d}", "password": "senha123"})
        users.append((u.json()["user"]["id"], u.json()["access_token"]))
    r = await client.post(f"/tournaments/{t['id']}/players", json={"user_ids": [u for u, _ in users]}, headers=auth(adm))
    assert r.status_code == 201, r.text
    return adm, t, users


async def set_pots(client, adm, tid, mapping):
    body = {"assignments": [{"user_id": u, "pot": p} for u, p in mapping.items()]}
    return await client.put(f"/tournaments/{tid}/pots", json=body, headers=auth(adm))


KO8 = {"name": "KO8", "template": "knockout", "max_players": 8}
GROUPS16 = {
    "name": "G16", "template": "groups_knockout", "max_players": 16,
    "config": {"groups_count": 4, "qualifiers_per_group": 2},
}


def test_tiebreak_key_is_reproducible_draw():
    t = SimpleNamespace(config={"draw_seed": 77})
    stage = SimpleNamespace(id=5)
    k1, k2 = engine._tiebreak_key(t, stage), engine._tiebreak_key(t, stage)
    assert [k1(u) for u in range(1, 9)] == [k2(u) for u in range(1, 9)]
    other = engine._tiebreak_key(SimpleNamespace(config={"draw_seed": 78}), stage)
    assert [k1(u) for u in range(1, 9)] != [other(u) for u in range(1, 9)]
    # é um sorteio de fato: a ordem por chave não coincide com a ordem dos ids
    assert sorted(range(1, 9), key=k1) != list(range(1, 9)) or sorted(range(1, 9), key=other) != list(range(1, 9))
    random.Random(1)


async def test_pots_groups_one_per_pot(client):
    adm, t, users = await setup(client, GROUPS16, 16)
    ids = [u for u, _ in users]
    pots = {uid: i // 4 + 1 for i, uid in enumerate(ids)}  # 4 potes de 4 jogadores
    r = await set_pots(client, adm, t["id"], pots)
    assert r.status_code == 200 and {p["user_id"]: p["pot"] for p in r.json()} == pots

    prev = (await client.post(f"/tournaments/{t['id']}/draw", json={"seed": 5}, headers=auth(adm))).json()
    assert prev["mode"] == "pots"
    groups = prev["arrangement"]["groups"]
    assert sorted(groups) == ["A", "B", "C", "D"]
    for members in groups.values():
        assert sorted(pots[u] for u in members) == [1, 2, 3, 4]  # um jogador de cada pote por grupo

    # a mesma seed reproduz o mesmo sorteio no /start
    started = (await client.post(f"/tournaments/{t['id']}/start", json={"seed": 5}, headers=auth(adm))).json()
    td = (await client.get(f"/tournaments/{t['id']}")).json()
    got = {}
    for p in td["players"]:
        got.setdefault(p["group_label"], []).append(p["user_id"])
    assert {k: sorted(v) for k, v in got.items()} == {k: sorted(v) for k, v in groups.items()}
    assert len(started) == 24  # 4 grupos x 6 confrontos


async def test_pots_knockout_makes_seeded_bracket(client):
    adm, t, users = await setup(client, KO8, 8)
    ids = [u for u, _ in users]
    pots = {ids[0]: 1, ids[1]: 1, ids[2]: 2, ids[3]: 2, **{u: 3 for u in ids[4:]}}
    await set_pots(client, adm, t["id"], pots)
    prev = (await client.post(f"/tournaments/{t['id']}/draw", json={"seed": 3}, headers=auth(adm))).json()
    slots = prev["arrangement"]["slots"]
    # cabeças de chave (pote 1) em metades opostas e enfrentando o pote mais fraco
    top = [slots.index(ids[0]), slots.index(ids[1])]
    assert {i // 4 for i in top} == {0, 1}
    for i in top:
        opp = slots[i + 1] if i % 2 == 0 else slots[i - 1]
        assert pots[opp] == 3
    await client.post(f"/tournaments/{t['id']}/start", json={"seed": 3}, headers=auth(adm))
    td = (await client.get(f"/tournaments/{t['id']}")).json()
    seeds = {p["user_id"]: p["seed"] for p in td["players"]}
    assert sorted(seeds.values()) == list(range(1, 9)) and {seeds[ids[0]], seeds[ids[1]]} == {1, 2}


async def test_pots_validation_and_permissions(client):
    adm, t, users = await setup(client, KO8, 8)
    tid = t["id"]
    ids = [u for u, _ in users]
    # só staff
    r = await client.put(f"/tournaments/{tid}/pots", json={"assignments": [{"user_id": ids[0], "pot": 1}]}, headers=auth(users[0][1]))
    assert r.status_code == 403
    # pote fora do intervalo / jogador não inscrito
    assert (await set_pots(client, adm, tid, {ids[0]: 9})).status_code == 422
    assert (await set_pots(client, adm, tid, {99999: 1})).status_code == 404
    # sorteio com potes incompletos
    await set_pots(client, adm, tid, {ids[0]: 1})
    r = await client.post(f"/tournaments/{tid}/draw", json={"seed": 1}, headers=auth(adm))
    assert r.status_code == 409 and "sem pote" in r.json()["detail"]
    # ignorar potes (use_pots=false) volta ao sorteio aleatório
    r = await client.post(f"/tournaments/{tid}/draw", json={"seed": 1, "use_pots": False}, headers=auth(adm))
    assert r.status_code == 200 and r.json()["mode"] == "random"
    # remover o pote (null) também libera
    await set_pots(client, adm, tid, {ids[0]: None})
    assert (await client.post(f"/tournaments/{tid}/draw", json={"seed": 1}, headers=auth(adm))).json()["mode"] == "random"
    # depois do início não muda mais
    await client.post(f"/tournaments/{tid}/start", json={}, headers=auth(adm))
    assert (await set_pots(client, adm, tid, {ids[0]: 2})).status_code == 409


async def test_manual_knockout_arrangement(client):
    adm, t, users = await setup(client, KO8, 8)
    tid = t["id"]
    ids = [u for u, _ in users]
    slots = [ids[0], ids[7], ids[3], ids[4], ids[1], ids[6], ids[2], ids[5]]  # posicionados à mão
    prev = (await client.post(f"/tournaments/{tid}/draw", json={"arrangement": {"slots": slots}}, headers=auth(adm))).json()
    assert prev["mode"] == "manual" and prev["arrangement"]["slots"] == slots
    pairs = [(m["player1"]["id"], m["player2"]["id"]) for m in prev["rounds"][0]["matches"]]
    assert pairs == [(ids[0], ids[7]), (ids[3], ids[4]), (ids[1], ids[6]), (ids[2], ids[5])]

    # inválidos: jogador faltando, repetido, fora da lista, quantidade errada
    for bad in (slots[:-1], slots[:-1] + [slots[0]], slots[:-1] + [99999], slots[:6]):
        r = await client.post(f"/tournaments/{tid}/draw", json={"arrangement": {"slots": bad}}, headers=auth(adm))
        assert r.status_code == 409, bad
    r = await client.post(f"/tournaments/{tid}/draw", json={"arrangement": {"groups": {"A": ids}}}, headers=auth(adm))
    assert r.status_code == 409

    started = (await client.post(f"/tournaments/{tid}/start", json={"seed": 9, "arrangement": {"slots": slots}}, headers=auth(adm))).json()
    r1 = sorted([m for m in started if m["round"] == 1], key=lambda m: m["slot"])
    assert [(m["player1"]["id"], m["player2"]["id"]) for m in r1] == pairs
    rec = (await client.get(f"/tournaments/{tid}/draw")).json()
    assert rec["mode"] == "manual" and rec["seed"] == 9 and rec["arrangement"]["slots"] == slots
    assert rec["drawn_by"] is not None and {p["id"] for p in rec["players"]} == set(ids)


async def test_manual_groups_and_pairs_and_league(client):
    adm, t, users = await setup(client, {
        "name": "Grupos 8", "template": "groups_knockout", "max_players": 8,
        "config": {"groups_count": 2, "qualifiers_per_group": 2},
    }, 8)
    tid = t["id"]
    ids = [u for u, _ in users]
    arr = {"groups": {"A": ids[:4], "B": ids[4:]}}
    prev = (await client.post(f"/tournaments/{tid}/draw", json={"arrangement": arr}, headers=auth(adm))).json()
    assert prev["mode"] == "manual" and prev["arrangement"]["groups"] == arr["groups"]
    # número de grupos diferente do configurado, grupo pequeno demais
    r = await client.post(f"/tournaments/{tid}/draw", json={"arrangement": {"groups": {"A": ids[:4], "B": ids[4:6], "C": ids[6:]}}}, headers=auth(adm))
    assert r.status_code == 409
    r = await client.post(f"/tournaments/{tid}/draw", json={"arrangement": {"groups": {"A": ids[:7], "B": ids[7:]}}}, headers=auth(adm))
    assert r.status_code == 409
    await client.post(f"/tournaments/{tid}/start", json={"arrangement": arr}, headers=auth(adm))
    td = (await client.get(f"/tournaments/{tid}")).json()
    assert {p["user_id"]: p["group_label"] for p in td["players"]} == {**{u: "A" for u in ids[:4]}, **{u: "B" for u in ids[4:]}}

    # rodada única com pares manuais
    adm2, t2, users2 = await setup2(client, adm)
    ids2 = users2
    pairs = [[ids2[0], ids2[5]], [ids2[1], ids2[4]], [ids2[2], ids2[3]], [ids2[6], ids2[7]]]
    r = await client.post(f"/tournaments/{t2['id']}/start", json={"arrangement": {"pairs": pairs}}, headers=auth(adm))
    assert r.status_code == 200
    got = sorted([[m["player1"]["id"], m["player2"]["id"]] for m in r.json()])
    assert got == sorted(pairs)

    # pontos corridos: não se aplica
    t3 = (await client.post("/tournaments", json={"name": "Liga X", "template": "league", "max_players": 4}, headers=auth(adm))).json()
    await client.post(f"/tournaments/{t3['id']}/players", json={"user_ids": ids2[:4]}, headers=auth(adm))
    r = await client.post(f"/tournaments/{t3['id']}/draw", json={"arrangement": {"pairs": [[ids2[0], ids2[1]], [ids2[2], ids2[3]]]}}, headers=auth(adm))
    assert r.status_code == 409


async def setup2(client, adm):
    """Torneio custom de rodada única (8 jogadores) reaproveitando jogadores já cadastrados."""
    body = {"name": "Rodada Unica", "template": "custom", "max_players": 8, "stages": [{"name": "Rodada", "type": "round"}]}
    t = (await client.post("/tournaments", json=body, headers=auth(adm))).json()
    users = (await client.get("/users", params={"limit": 50})).json()
    ids = [u["id"] for u in users if u["name"].startswith("Jogador")][:8]
    await client.post(f"/tournaments/{t['id']}/players", json={"user_ids": ids}, headers=auth(adm))
    return adm, t, ids


async def test_draw_record_requires_start(client):
    adm, t, _ = await setup(client, KO8, 8)
    assert (await client.get(f"/tournaments/{t['id']}/draw")).status_code == 404
    await client.post(f"/tournaments/{t['id']}/start", json={"seed": 12}, headers=auth(adm))
    rec = (await client.get(f"/tournaments/{t['id']}/draw")).json()  # público
    assert rec["seed"] == 12 and rec["mode"] == "random" and len(rec["arrangement"]["slots"]) == 8


def result(m, rem):
    p1 = m["player1"]["id"] < m["player2"]["id"]
    return {"p1_wins": int(p1), "p2_wins": int(not p1), "p1_remaining": rem if p1 else 0,
            "p2_remaining": 0 if p1 else rem, "replay_urls": [REPLAY]}


async def run_round_to_ko(client, seeding):
    adm = await admin(client)
    ko_cfg = {"seeding": seeding} if seeding else {}
    body = {
        "name": f"Seeding {seeding}", "template": "custom", "max_players": 8,
        "stages": [{"name": "Rodada", "type": "round"}, {"name": "Mata-mata", "type": "knockout", "config": ko_cfg}],
        "rules": [
            {"from_stage": 1, "source": "losers", "pos_from": 1, "pos_to": 4, "target": "eliminated"},
            {"from_stage": 1, "source": "winners", "pos_from": 1, "pos_to": 4, "target": "stage", "to_stage": 2, "to_slot_from": 1},
        ],
    }
    t = (await client.post("/tournaments", json=body, headers=auth(adm))).json()
    users = [(await client.post("/auth/register", json={"name": f"Seed{seeding or 'dflt'}{i}", "password": "senha123"})).json()["user"]["id"] for i in range(8)]
    await client.post(f"/tournaments/{t['id']}/players", json={"user_ids": users}, headers=auth(adm))
    await client.post(f"/tournaments/{t['id']}/start", json={"seed": 4}, headers=auth(adm))
    ms = sorted((await client.get(f"/tournaments/{t['id']}/matches", params={"stage_id": t["stages"][0]["id"]})).json(), key=lambda m: m["slot"])
    winners = []
    for rank, m in enumerate(ms, start=1):  # saldos 4,3,2,1: vencedor do confronto k tem ranking k
        res = await client.post(f"/matches/{m['id']}/result", json=result(m, 5 - rank), headers=auth(adm))
        winners.append(res.json()["winner_id"])
    ko = await client.get(f"/tournaments/{t['id']}/matches", params={"stage_id": t["stages"][1]["id"]})
    r1 = sorted([m for m in ko.json() if m["round"] == 1], key=lambda m: m["slot"])
    return winners, [(m["player1"]["id"], m["player2"]["id"]) for m in r1]


async def test_default_seeding_is_standard_and_sequential_is_available(client):
    winners, pairs = await run_round_to_ko(client, None)  # padrão: standard (1x4, 2x3)
    assert pairs == [(winners[0], winners[3]), (winners[1], winners[2])]
    winners2, pairs2 = await run_round_to_ko(client, "sequential")  # posição literal na chave
    assert pairs2 == [(winners2[0], winners2[1]), (winners2[2], winners2[3])]
