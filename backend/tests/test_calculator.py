"""Calculadora de custos da temporada (Draft): valores de referência da especificação e regras do edital."""
from app.schemas.calculator import CalcIn
from app.services import calculator, draft_config

M = 1_000_000


def calc(preset="serie_a_18", squad=None, rate_bp=500, **kw):
    cfg = {**draft_config.PRESETS[preset], "salary_rate_bp": rate_bp}
    cfg.update(kw.pop("config", {}))
    return calculator.compute(CalcIn(config=cfg, squad=squad or [], **kw))


def team(*groups):
    """team((5, 60), (6, 50)) -> 5 Pokémon de 60 mi + 6 de 50 mi, todos inscritos."""
    return [{"name": f"P{i}", "price": price * M, "registered": True} for n, price in groups for i in range(n)]


META = team((5, 60), (6, 50))  # 600 mi
EQUIL = team((2, 60), (3, 50), (3, 40), (3, 30))  # 480 mi
# Na especificação o "Time Econômico" é descrito como 4 UU + 4 NU + 3 PU (= 380 mi), mas os valores de referência dela
# (189 / 286,2 / 351 mi) correspondem a um elenco de 360 mi; o teste usa 360 mi para conferir esses números.
ECON = team((4, 50), (4, 30), (2, 20)) + [{"name": "P", "price": 0, "registered": True}]  # 360 mi, 11 inscritos


def season_cost(out):
    return out.totals.cost


def test_registration_fee():
    assert calculator.registration_fee(6, 6, 100_000) == 0
    assert calculator.registration_fee(7, 6, 100_000) == 100_000
    assert calculator.registration_fee(11, 6, 100_000) == 1_500_000


def test_reference_values_from_the_spec():
    # Time Meta: salário 15 / 24 / 30 mi por rodada; custo da temporada 297 / 459 / 567 mi.
    for bp, per_round, total in ((250, 15, 297), (400, 24, 459), (500, 30, 567)):
        out = calc(squad=META, rate_bp=bp)
        assert out.rows[0].salaries == per_round * M and season_cost(out) == total * M
        assert out.totals.registration == 27 * M
    out = calc(squad=META)
    assert out.breakeven_exact == 9.675 and out.breakeven_wins == 10
    # Time Equilibrado: 243 / 372,6 / 459 mi; 9V 9D a 5% = renda 540 e saldo +81; equilíbrio 6,975 -> 7.
    for bp, total in ((250, 243 * M), (400, 372_600_000), (500, 459 * M)):
        assert season_cost(calc(squad=EQUIL, rate_bp=bp)) == total
    out = calc(squad=EQUIL, results={"wins": 9})
    assert out.totals.income == 540 * M and out.totals.balance == 81 * M
    assert out.breakeven_exact == 6.975 and out.breakeven_wins == 7
    # Time Econômico: 189 / 286,2 / 351 mi; equilíbrio 4,275 -> 5.
    for bp, total in ((250, 189 * M), (400, 286_200_000), (500, 351 * M)):
        assert season_cost(calc(squad=ECON, rate_bp=bp)) == total
    assert calc(squad=ECON).breakeven_wins == 5
    # Com CT: constrói o nível 1 na rodada 1 -> 25 mi + 0,5 mi x 17 = 33,5 mi a mais; total 492,5 mi.
    out = calc(squad=EQUIL, ct={"current_level": 0, "target_level": 1, "build_round": 1})
    assert out.totals.ct_build == 25 * M and out.totals.ct_maintenance == 8_500_000
    assert season_cost(out) == 492_500_000 and out.rows[0].ct_maintenance == 0 and out.rows[1].ct_maintenance == 500_000
    # Bordas: 0 vitórias = 180 mi de renda; empate = 25 mi; 7 inscritos = 100 mil por rodada.
    assert calc(squad=EQUIL).totals.income == 180 * M
    assert calc(squad=EQUIL, results={"mode": "detailed", "per_round": ["D"]}).rows[0].income == 25 * M
    seven = [{**p, "registered": i < 7} for i, p in enumerate(EQUIL)]
    assert calc(squad=seven).rows[0].registration == 100_000


def test_validation_errors():
    out = calc(squad=team((16, 10)))
    assert any("máximo é 15" in e for e in out.errors) and any("inscritos" in e for e in out.errors)
    out = calc(squad=META, results={"wins": 15, "draws": 4})
    assert any("passam das 18 rodadas" in e for e in out.errors)
    assert calc(squad=META, ct={"current_level": 2, "target_level": 1, "build_round": 1}).errors
    assert not any("orçamento" in w for w in calc(squad=team((11, 50))).warnings)  # 550 mi cabe nos 600 mi
    assert any("orçamento" in w for w in calc(squad=team((11, 60))).warnings)  # 660 mi > 600 mi


def test_draft_rules_eliminated_in_groups():
    """Edital: 6 rodadas de grupos + 2 de mata-mata. Eliminado nos grupos não paga salário depois, mas paga o CT."""
    squad = team((8, 40), (3, 30))  # 410 mi, 11 inscritos
    out = calc("draft", squad=squad, knockout_played=0, placement=5, results={"wins": 3, "draws": 1},
               ct={"target_level": 1, "build_round": 1})
    assert out.rounds_total == 8 and out.rounds_played == 6
    assert [r.salaries for r in out.rows] == [20_500_000] * 6 + [0, 0]
    assert [r.registration for r in out.rows] == [1_500_000] + [0] * 7  # uma vez por temporada
    assert [r.ct_maintenance for r in out.rows] == [0] + [500_000] * 7  # todas as rodadas, mesmo sem jogar
    assert out.totals.income == 3 * 50 * M + 25 * M + 2 * 10 * M and out.rows[-1].prize == 32 * M
    assert out.start_cash == 90 * M
    expected = 90 * M - (6 * 20_500_000 + 1_500_000 + 25 * M + 7 * 500_000) + 195 * M + 32 * M
    assert out.final_cash == expected == out.rows[-1].cash
    # a tabela por rodada soma exatamente os totais
    assert sum(r.cost for r in out.rows) == out.totals.cost and sum(r.balance for r in out.rows) == out.totals.balance


def test_draft_semifinalist_and_walkover():
    squad = team((10, 40))
    out = calc("draft", squad=squad, knockout_played=2, placement=1,
               results={"mode": "detailed", "per_round": ["W", "WO", "L", "D", "W", "W", "W", "W"]})
    assert out.rounds_played == 8 and all(r.salaries == 20 * M for r in out.rows)
    assert out.rows[1].income == 0 and out.rows[1].fine == 500_000  # W.O. perdido: sem renda e com multa
    assert out.rows[-1].prize == 70 * M and out.totals.registration == 1_000_000  # 10 inscritos = 100+200+300+400 mil
    bad = calc("draft", squad=squad, knockout_played=0, results={"mode": "detailed", "per_round": ["W"] * 7})
    assert any("Rodada 7" in e for e in bad.errors)
    assert any("3 rodada" in e or "não dá" in e for e in calc("draft", squad=squad, knockout_played=3).errors)


def test_trainings_cost_wait_and_capacity():
    squad = [{"name": "Mew", "price": 50 * M, "tier": "UUBL", "registered": True},
             {"name": "Rattata", "price": 10 * M, "tier": "ZU", "registered": True}]
    out = calc("draft", squad=squad, ct={"target_level": 1, "build_round": 2},
               trainings=[{"pokemon": 0, "kind": "opt", "round": 2}, {"pokemon": 1, "kind": "extra", "round": 2},
                          {"pokemon": 1, "kind": "extra", "round": 1}])
    assert out.rows[1].trainings == 20 * M + 2 * M  # otimização 40% de 50 mi + posição extra 20% de 10 mi
    assert any("CT ainda não existe" in w for w in out.warnings)  # treinamento na rodada 1, CT só na 2
    assert any("Rodada 2: 2 treinamentos" in w for w in out.warnings)  # nível 1 = 1 por vez
    assert any("otimização exige CT nível 2" in w for w in out.warnings)  # nível 1 só treina posição extra
    lvl3 = calc("draft", squad=squad, ct={"current_level": 3},
                trainings=[{"pokemon": 0, "kind": "opt", "round": 1}, {"pokemon": 1, "kind": "extra", "round": 1}])
    assert lvl3.warnings == []  # nível 3: dois ao mesmo tempo, com otimização
    lvl2 = calc("draft", squad=squad, ct={"current_level": 2},
                trainings=[{"pokemon": 0, "kind": "opt", "round": 1}, {"pokemon": 1, "kind": "extra", "round": 1}])
    assert [w for w in lvl2.warnings if "ao mesmo tempo" in w] and not [w for w in lvl2.warnings if "exige" in w]
    assert any("Mew (otimização): começa na rodada 2 e vale a partir da rodada 7" in n for n in out.notes)  # UUBL = UU = 5
    assert [calculator.tier_wait(t, draft_config.TIER_ORDER) for t in ("ZU", "ZUBL", "PU", "NU", "OUBL", "xx")] == [1, 1, 2, 3, 6, None]


async def test_calculator_api(client):
    p = (await client.get("/calculator/presets")).json()
    assert p["default"] == "draft" and p["presets"]["draft"]["initial_budget"] == 500 * M
    r = await client.post("/calculator", json={"config": p["presets"]["draft"], "squad": team((11, 30)), "results": {"wins": 4}})
    assert r.status_code == 200 and r.json()["rounds_played"] == 6 and r.json()["rows"][0]["registration"] == 1_500_000
