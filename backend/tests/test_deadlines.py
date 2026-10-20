"""Prazo das rodadas: empate automático, aviso de prazo vencido e liberação pelo admin."""
from datetime import datetime, timedelta, timezone

from app.services import deadlines
from tests.test_groups import REPLAY, admin, auth, create, make_players, matches_of, play  # noqa: F401


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


async def league(client, adm, **cfg):
    t = await create(client, adm, {"name": "Liga Prazo", "template": "league", "max_players": 4, "config": cfg})
    users = await make_players(client, adm, t["id"], 4)
    await client.post(f"/tournaments/{t['id']}/start", json={"seed": 7}, headers=auth(adm))
    return t, users, t["stages"][0]["id"]


async def put_deadline(client, adm, t, sid, rnd, when):
    return await client.put(f"/tournaments/{t['id']}/stages/{sid}/deadlines", json={"deadlines": {str(rnd): when}}, headers=auth(adm))


def travel(monkeypatch, delta):
    monkeypatch.setattr(deadlines, "now", lambda: datetime.now(timezone.utc) + delta)


async def test_expired_round_becomes_draw_and_can_be_waived(client, monkeypatch):
    adm = await admin(client)
    t, users, sid = await league(client, adm)
    tid = t["id"]
    r1 = [m for m in await matches_of(client, tid, stage_id=sid) if m["round"] == 1]
    soon = datetime.now(timezone.utc) + timedelta(hours=2)

    # só staff define; data passada é recusada
    assert (await put_deadline(client, users[0][1] and users[0][1], t, sid, 1, iso(soon))).status_code in (401, 403)
    assert (await put_deadline(client, adm, t, sid, 1, iso(datetime.now(timezone.utc) - timedelta(hours=1)))).status_code == 422
    r = await put_deadline(client, adm, t, sid, 1, iso(soon))
    assert r.status_code == 200 and r.json()["config"]["deadlines"]["1"]
    played, open_one = r1
    await play(client, adm, played)
    ms = {m["id"]: m for m in await matches_of(client, tid, stage_id=sid)}
    assert ms[open_one["id"]]["deadline"] and ms[open_one["id"]]["overdue"] is False

    # passa o prazo: o jogo que sobrou vira empate automático (uma única vez)
    travel(monkeypatch, timedelta(hours=3))
    m = (await client.get(f"/matches/{open_one['id']}")).json()
    assert m["status"] == "validated" and m["is_draw"] and m["auto_result"] is True and m["p1_wins"] == 0
    assert (await client.get(f"/matches/{played['id']}")).json()["auto_result"] is False
    log = (await client.get("/audit", params={"action": "match.auto_draw"}, headers=auth(adm))).json()
    assert log["total"] == 1 and log["items"][0]["actor_id"] is None
    await client.get(f"/tournaments/{tid}")
    assert (await client.get("/audit", params={"action": "match.auto_draw"}, headers=auth(adm))).json()["total"] == 1
    st = (await client.get(f"/tournaments/{tid}/standings")).json()[0]["rows"]
    ids = {open_one["player1"]["id"], open_one["player2"]["id"]}
    assert all(r["points"] == 1 and r["draws"] == 1 for r in st if r["user_id"] in ids)

    # admin anula o empate: o prazo deixa de valer para esse jogo e a entrega atrasada é possível
    r = await client.post(f"/matches/{open_one['id']}/invalidate", json={"note": "entrega atrasada liberada"}, headers=auth(adm))
    assert r.status_code == 200 and r.json()["status"] == "scheduled" and r.json()["deadline_waived"] is True
    await client.get(f"/tournaments/{tid}/matches")
    again = (await client.get(f"/matches/{open_one['id']}")).json()
    assert again["status"] == "scheduled" and again["overdue"] is False and again["auto_result"] is False
    await play(client, adm, again)
    assert (await client.get(f"/matches/{open_one['id']}")).json()["status"] == "validated"


async def test_reported_and_postponed_games_are_not_auto_drawn(client, monkeypatch):
    adm = await admin(client)
    t, users, sid = await league(client, adm)
    tid = t["id"]
    a, b = [m for m in await matches_of(client, tid, stage_id=sid) if m["round"] == 1]
    await put_deadline(client, adm, t, sid, 1, iso(datetime.now(timezone.utc) + timedelta(hours=1)))
    # a: reporte pendente; b: adiado
    tok = next(tk for uid, tk in users if uid == a["player1"]["id"])
    body = {"p1_wins": 1, "p2_wins": 0, "p1_remaining": 2, "p2_remaining": 0, "replay_urls": [REPLAY]}
    assert (await client.post(f"/matches/{a['id']}/report", json=body, headers=auth(tok))).status_code == 200
    assert (await client.post(f"/matches/{b['id']}/postpone", json={}, headers=auth(adm))).status_code == 200
    travel(monkeypatch, timedelta(hours=2))
    ms = {m["id"]: m for m in await matches_of(client, tid, stage_id=sid)}
    assert ms[a["id"]]["status"] == "reported" and ms[b["id"]]["status"] == "scheduled" and not ms[b["id"]]["overdue"]
    # retomar depois do prazo: será disputado, não empatado
    assert (await client.post(f"/matches/{b['id']}/resume", headers=auth(adm))).json()["deadline_waived"] is True
    assert (await client.get(f"/matches/{b['id']}")).json()["status"] == "scheduled"


async def test_no_draw_tournament_only_warns(client, monkeypatch):
    adm = await admin(client)
    t, users, sid = await league(client, adm, allow_draw=False)
    tid = t["id"]
    await put_deadline(client, adm, t, sid, 1, iso(datetime.now(timezone.utc) + timedelta(hours=1)))
    travel(monkeypatch, timedelta(hours=2))
    r1 = [m for m in await matches_of(client, tid, stage_id=sid) if m["round"] == 1]
    assert all(m["status"] == "scheduled" and m["overdue"] is True for m in r1)
    assert (await client.get("/audit", params={"action": "match.auto_draw"}, headers=auth(adm))).json()["total"] == 0


async def test_knockout_overdue_is_only_a_warning_and_deadline_can_be_removed(client, monkeypatch):
    adm = await admin(client)
    t = await create(client, adm, {"name": "Mata Prazo", "template": "knockout", "max_players": 4})
    await make_players(client, adm, t["id"], 4)
    await client.post(f"/tournaments/{t['id']}/start", json={"seed": 1}, headers=auth(adm))
    sid = t["stages"][0]["id"]
    await put_deadline(client, adm, t, sid, 1, iso(datetime.now(timezone.utc) + timedelta(hours=1)))
    travel(monkeypatch, timedelta(hours=2))
    ms = [m for m in await matches_of(client, t["id"], stage_id=sid) if m["round"] == 1]
    assert all(m["status"] == "scheduled" and m["overdue"] for m in ms)
    # remover o prazo tira o aviso
    r = await client.put(f"/tournaments/{t['id']}/stages/{sid}/deadlines", json={"deadlines": {"1": None}}, headers=auth(adm))
    assert r.status_code == 200 and "deadlines" not in (r.json()["config"] or {})
    assert not any(m["overdue"] for m in await matches_of(client, t["id"], stage_id=sid))
    assert (await client.put(f"/tournaments/{t['id']}/stages/99999/deadlines", json={"deadlines": {}}, headers=auth(adm))).status_code == 404
