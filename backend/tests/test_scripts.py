"""Scripts de manutenção: backup/restauração (ida e volta) e remoção de contas de teste."""
import json

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.scripts import backup, delete_users, restore
from tests.test_groups import admin, auth, create, make_players, matches_of, play


async def _session():
    from app.db.session import get_session
    from app.main import app

    return app.dependency_overrides[get_session]


async def _tournament_with_bracket(client):
    """Grupos + mata-mata jogado até o chaveamento existir (confrontos ligados por next_match_id, histórico, reportes)."""
    adm = await admin(client)
    t = await create(client, adm, {"name": "Copa Backup", "template": "groups_knockout", "max_players": 8,
                                   "config": {"groups_count": 2, "qualifiers_per_group": 2}})
    await make_players(client, adm, t["id"], 8)
    assert (await client.post(f"/tournaments/{t['id']}/start", json={"seed": 3}, headers=auth(adm))).status_code == 200
    for m in await matches_of(client, t["id"], stage_id=t["stages"][0]["id"]):
        await play(client, adm, m)
    ko = [m for m in await matches_of(client, t["id"], stage_id=t["stages"][1]["id"]) if m["player1"] and m["player2"]]
    assert ko, "o mata-mata deveria ter sido montado"
    await play(client, adm, ko[0])
    return t, adm


def _canon(data: dict) -> str:
    return json.dumps(data["tables"], default=backup._json_default, sort_keys=True)


async def test_backup_and_restore_round_trip(client):
    await _tournament_with_bracket(client)
    async for s in (await _session())():
        async with s.bind.connect() as conn:
            original = await backup.dump(conn)
    assert any(r["next_match_id"] for r in original["tables"]["matches"])
    assert original["tables"]["standings_snapshots"] and original["tables"]["audit_log"]

    target = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with target.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    data = json.loads(json.dumps(original, default=backup._json_default))  # como se viesse do arquivo
    async with target.begin() as conn:
        counts = await restore.load(conn, data, replace=False)
    assert counts["users"] == len(original["tables"]["users"])
    async with target.connect() as conn:
        assert _canon(await backup.dump(conn)) == _canon(original)

    # banco com dados: recusa sem --substituir; com --substituir, troca tudo
    async with target.begin() as conn:
        with pytest.raises(SystemExit):
            await restore.load(conn, data, replace=False)
    async with target.begin() as conn:
        await restore.load(conn, data, replace=True)
    async with target.connect() as conn:
        assert _canon(await backup.dump(conn)) == _canon(original)
    await target.dispose()


async def test_delete_test_users_with_their_tournaments(client):
    t, adm = await _tournament_with_bracket(client)
    keeper = (await client.post("/auth/register", json={"name": "Jogador Real", "password": "senha1234"})).json()["user"]["id"]
    async for s in (await _session())():
        plano = await delete_users.planejar(s, ["admin"], r"^Treinador\d+$")
        assert len(plano.users) == 8 and plano.admins == ["Admin"]  # admin casou pelo nome, mas nunca é apagado
        assert [x[0] for x in plano.tournaments] == [t["id"]] and plano.tournaments[0][4] == 0
        await delete_users.executar(s, plano)

    users = (await client.get("/users")).json()
    assert {u["name"] for u in users} == {"Admin", "Jogador Real"} and any(u["id"] == keeper for u in users)
    assert (await client.get(f"/tournaments/{t['id']}")).status_code == 404
    log = (await client.get("/audit", params={"action": "user.delete"}, headers=auth(adm))).json()
    assert log["total"] == 8 and log["items"][0]["data"]["via"] == "script"
