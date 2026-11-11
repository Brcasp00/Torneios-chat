"""Valores econômicos do Draft Pokémon (Modo Carreira) — ÚNICO lugar onde eles ficam.

O organizador ajusta aqui. Dinheiro sempre em euros inteiros (30 milhões = 30_000_000); percentuais em pontos-base
(500 = 5%), para nunca usar ponto flutuante com dinheiro.

Cada "modelo" (preset) é uma configuração completa. A calculadora deixa o visitante partir de um modelo e mudar qualquer
valor (inclusive o formato: rodadas de liga/grupos e de mata-mata), sem tocar no código.
"""
M = 1_000_000

# Ordem dos tiers. O tier "BL" vale, no preço, o tier de baixo + 5 mi; na espera do CT, conta como o tier de baixo.
TIER_ORDER = ["ZU", "PU", "NU", "RU", "UU", "OU", "Ubers"]

TIER_PRICES = {
    "ZU": 10 * M, "ZUBL": 15 * M, "PU": 20 * M, "PUBL": 25 * M, "NU": 30 * M, "NUBL": 35 * M,
    "RU": 40 * M, "RUBL": 45 * M, "UU": 50 * M, "UUBL": 55 * M, "OU": 60 * M, "OUBL": 65 * M,
    "Ubers": None,  # a definir pelo organizador
}

# Edital atual: 8 jogadores, 2 grupos de 4 em turno e returno (6 rodadas) + semifinal e final/3º lugar (2 rodadas).
DRAFT = {
    "label": "Draft — edital atual (8 jogadores, grupos + mata-mata)",
    "initial_budget": 500 * M,
    "sponsors": 5,
    "win_per_sponsor": 10 * M,
    "draw_per_sponsor": 5 * M,  # metade da vitória
    "loss_per_sponsor": 2 * M,
    "wo_fine": 500_000,  # quem perde por W.O. paga a multa e não recebe a renda da derrota
    "salary_rate_bp": 500,  # 5% do preço de compra, por rodada jogada
    "registration_step": 100_000,  # 7º inscrito 100 mil, 8º 200 mil ... 11º 500 mil
    "registration_free_slots": 6,
    "registration_charge": "season",  # "season" = cada Pokémon paga uma vez por temporada; "round" = toda rodada jogada
    "max_squad": 15,
    "max_registered": 11,
    "ct_build": [0, 25 * M, 50 * M, 90 * M],  # preço acumulado do nível (subir de nível paga a diferença)
    "ct_maintenance": [0, 500_000, 1 * M, 2 * M],  # por rodada da temporada (mesmo sem jogar), a partir da seguinte à construção
    "ct_parallel": [0, 1, 1, 2],  # treinamentos ao mesmo tempo por nível: só o nível 3 treina dois de uma vez
    "ct_min_level": {"extra": 1, "opt": 2},  # nível 1 treina posição extra; nível 2 libera a otimização
    # Espera do treinamento (posição extra ou otimização): depende do tier do Pokémon, não do nível do CT.
    "training_extra_bp": 2000,  # posição extra: 20% do preço pago
    "training_opt_bp": 4000,  # otimização: 40% do preço pago
    "tier_order": TIER_ORDER,  # espera do treinamento: ZU 1 rodada, PU 2, NU 3... (+1 por tier)
    "tier_prices": TIER_PRICES,
    "market_premium": 5 * M,  # Pokémon livre no mercado = preço do tier + 5 mi
    "league_rounds": 6,  # rodadas que todos jogam (liga/grupos)
    "knockout_rounds": 2,  # rodadas do mata-mata (só para quem avança)
    "league_label": "Fase de grupos",
    "knockout_label": "Mata-mata",
    "prizes": [70 * M, 55 * M, 45 * M, 38 * M, 32 * M, 28 * M, 24 * M, 21 * M],  # 1º ao 8º
}

# Especificação antiga da calculadora (Série A, 10 jogadores, 18 rodadas de pontos corridos, inscrição por rodada).
# Mantida como configuração alternativa e para os testes de referência.
SERIE_A_18 = {
    **DRAFT,
    "label": "Pontos corridos — 10 jogadores, 18 rodadas (especificação antiga)",
    "initial_budget": 600 * M,
    "registration_charge": "round",
    "league_rounds": 18,
    "knockout_rounds": 0,
    "league_label": "Pontos corridos",
    "prizes": [],
}

PRESETS = {"draft": DRAFT, "serie_a_18": SERIE_A_18}
DEFAULT_PRESET = "draft"
