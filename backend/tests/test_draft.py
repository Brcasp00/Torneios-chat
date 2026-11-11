"""Draft: configuração, lote de Pokémon, registro do leilão, caixa dos clubes e patrocinadores."""
from tests.test_groups import admin, auth, create, make_players

M = 1_000_000


async def _draft(client, adm, regions=("Kanto",), n=4):
    t = await create(client, adm, {"name": "Draft Teste", "template": "league", "max_players": n})
    users = await make_players(client, adm, t["id"], n)
    r = await client.put(f"/tournaments/{t['id']}/draft", json={"regions": list(regions)}, headers=auth(adm))
    assert r.status_code == 200, r.text
    return t, users


async def test_setup_and_lote(client):
    adm = await admin(client)
    t = await create(client, adm, {"name": "Sem Draft", "template": "league", "max_players": 4})
    users = await make_players(client, adm, t["id"], 4)
    assert (await client.get(f"/tournaments/{t['id']}/draft")).json()["enabled"] is False
    assert (await client.get(f"/tournaments/{t['id']}/draft/pokemon")).status_code == 409
    assert (await client.put(f"/tournaments/{t['id']}/draft", json={"regions": ["Atlantis"]}, headers=auth(adm))).status_code == 422
    assert (await client.put(f"/tournaments/{t['id']}/draft", json={"regions": ["Kanto"]}, headers=auth(users[0][1]))).status_code == 403
    r = (await client.put(f"/tournaments/{t['id']}/draft", json={"regions": ["Kanto", "Alola"]}, headers=auth(adm))).json()
    assert r["enabled"] and r["economy"]["initial_budget"] == 500 * M and len(r["clubs"]) == 4
    assert all(c["cash"] == 500 * M and not c["transferban"] for c in r["clubs"])
    url = f"/tournaments/{t['id']}/draft/pokemon"
    # fora das regiões: nada é adicionado
    bad = await client.post(url, json={"species_ids": ["charizard", "kingambit"]}, headers=auth(adm))
    assert bad.status_code == 422 and "Kingambit" in bad.json()["detail"]
    ok = (await client.post(url, json={"species_ids": ["charizard", "charizardmegax", "raichualola", "charizard"]}, headers=auth(adm))).json()
    assert ok == {"added": 3, "skipped": 1}
    again = (await client.post(url, json={"species_ids": ["charizard"]}, headers=auth(adm))).json()
    assert again == {"added": 0, "skipped": 1}
    lote = (await client.get(url)).json()
    assert [p["name"] for p in lote] == ["Charizard", "Charizard-Mega-X", "Raichu-Alola"]
    zard = lote[0]
    assert zard["tier9"] and zard["tier7"] and zard["owner"] is None and zard["region"] == "Kanto"
    # o organizador define tier do Draft, preço, posições e custo por posição
    body = {"draft_tier": "OU", "price": 60 * M, "positions": ["atacante"], "costs": {"atacante": 20, "meio": 25, "defensor": 25}}
    r = await client.put(f"{url}/{zard['id']}", json=body, headers=auth(adm))
    assert r.status_code == 200 and r.json()["costs"]["atacante"] == 20 and r.json()["draft_tier"] == "OU"
    assert (await client.put(f"{url}/{zard['id']}", json={**body, "costs": {"meio": 101}}, headers=auth(adm))).status_code == 422
    # mudar o formato do torneio não apaga a configuração do Draft
    assert (await client.patch(f"/tournaments/{t['id']}", json={"name": "Draft Renomeado", "max_players": 4}, headers=auth(adm))).status_code == 200
    assert (await client.get(f"/tournaments/{t['id']}/draft")).json()["regions"] == ["Kanto", "Alola"]


async def test_auction_registration_cash_and_transferban(client):
    adm = await admin(client)
    t, users = await _draft(client, adm)
    base = f"/tournaments/{t['id']}/draft"
    await client.post(f"{base}/pokemon", json={"species_ids": ["bulbasaur", "charmander", "squirtle", "pikachu"]}, headers=auth(adm))
    lote = {p["name"]: p for p in (await client.get(f"{base}/pokemon")).json()}
    uid, tok = users[0]
    r = await client.post(f"{base}/pokemon/{lote['Bulbasaur']['id']}/assign", json={"user_id": uid, "price": 300 * M}, headers=auth(adm))
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["owner"]["id"] == uid and p["contract_price"] == 300 * M and p["salary"] == 15 * M and p["acquired_via"] == "auction"
    # já tem dono
    assert (await client.post(f"{base}/pokemon/{lote['Bulbasaur']['id']}/assign", json={"user_id": users[1][0], "price": 1}, headers=auth(adm))).status_code == 409
    # caixa insuficiente: recusa, a não ser que permita caixa negativo
    r = await client.post(f"{base}/pokemon/{lote['Charmander']['id']}/assign", json={"user_id": uid, "price": 250 * M}, headers=auth(adm))
    assert r.status_code == 409 and "Caixa insuficiente" in r.json()["detail"]
    r = await client.post(f"{base}/pokemon/{lote['Charmander']['id']}/assign",
                          json={"user_id": uid, "price": 250 * M, "via": "market", "allow_negative": True}, headers=auth(adm))
    assert r.status_code == 200
    club = (await client.get(f"{base}/clubs/{uid}")).json()
    assert club["cash"] == -50 * M and club["transferban"] and club["squad_count"] == 2 and club["salary_per_round"] == 27_500_000
    assert [x["kind"] for x in club["transactions"]] == ["purchase", "purchase"]
    # transferban: nenhuma compra
    r = await client.post(f"{base}/pokemon/{lote['Squirtle']['id']}/assign", json={"user_id": uid, "price": 0}, headers=auth(adm))
    assert r.status_code == 409 and "Transferban" in r.json()["detail"]
    # ajuste manual tira do transferban
    r = await client.post(f"{base}/adjust", json={"user_id": uid, "amount": 60 * M, "note": "Renda da rodada 1"}, headers=auth(adm))
    assert r.json()["cash"] == 10 * M and not r.json()["transferban"]
    # desfazer registro devolve o valor e libera o Pokémon
    r = await client.post(f"{base}/pokemon/{lote['Charmander']['id']}/unassign", json={"note": "Registro errado"}, headers=auth(adm))
    assert r.status_code == 200 and r.json()["owner"] is None
    assert (await client.get(f"{base}/clubs/{uid}")).json()["cash"] == 260 * M
    panel = (await client.get(f"{base}/pokemon/{lote['Charmander']['id']}")).json()
    assert [x["kind"] for x in panel["transactions"]] == ["correction", "purchase"]
    # jogador não registra compras; Pokémon com dono não sai do lote
    assert (await client.post(f"{base}/pokemon/{lote['Squirtle']['id']}/assign", json={"user_id": uid, "price": 1}, headers=auth(tok))).status_code == 403
    assert (await client.delete(f"{base}/pokemon/{lote['Bulbasaur']['id']}", headers=auth(adm))).status_code == 409
    assert (await client.delete(f"{base}/pokemon/{lote['Pikachu']['id']}", headers=auth(adm))).status_code == 204
    # quem não está no torneio não compra
    outsider = (await client.post("/auth/register", json={"name": "Forasteiro", "password": "senha1234"})).json()["user"]["id"]
    assert (await client.post(f"{base}/pokemon/{lote['Squirtle']['id']}/assign", json={"user_id": outsider, "price": 1}, headers=auth(adm))).status_code == 422


async def test_squad_limit_and_sponsors(client):
    adm = await admin(client)
    t, users = await _draft(client, adm)
    base = f"/tournaments/{t['id']}/draft"
    eco = (await client.get(base)).json()["economy"]
    await client.put(base, json={"regions": ["Kanto"], "economy": {**eco, "max_squad": 2}}, headers=auth(adm))
    await client.post(f"{base}/pokemon", json={"species_ids": ["bulbasaur", "charmander", "squirtle"]}, headers=auth(adm))
    lote = (await client.get(f"{base}/pokemon")).json()
    uid, tok = users[0]
    for p in lote[:2]:
        assert (await client.post(f"{base}/pokemon/{p['id']}/assign", json={"user_id": uid, "price": M}, headers=auth(adm))).status_code == 200
    r = await client.post(f"{base}/pokemon/{lote[2]['id']}/assign", json={"user_id": uid, "price": M}, headers=auth(adm))
    assert r.status_code == 409 and "máximo 2" in r.json()["detail"]
    # patrocinadores: o próprio jogador informa (até 5); outro jogador não
    r = await client.put(f"{base}/clubs/{uid}/sponsors", json={"sponsors": ["Silph Co.", "  Devon  Corp ", ""]}, headers=auth(tok))
    assert r.status_code == 200 and r.json()["sponsors"] == ["Silph Co.", "Devon Corp"]
    assert (await client.put(f"{base}/clubs/{uid}/sponsors", json={"sponsors": ["x"] * 6}, headers=auth(tok))).status_code == 422
    assert (await client.put(f"{base}/clubs/{uid}/sponsors", json={"sponsors": ["x"]}, headers=auth(users[1][1]))).status_code == 403
    clubs = (await client.get(base)).json()["clubs"]
    assert next(c for c in clubs if c["user"]["id"] == uid)["sponsors"] == ["Silph Co.", "Devon Corp"]
