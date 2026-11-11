"""Calculadora de custos da temporada do Draft: funções puras (sem banco), testáveis sem interface.

Regras (edital + decisões do organizador):
- Salário: % do preço pago de TODOS os Pokémon do elenco (inscritos e reservas), por rodada JOGADA. Quem é eliminado
  nos grupos não paga as rodadas do mata-mata.
- Inscrição: os primeiros N inscritos são grátis; o k-ésimo seguinte custa k x passo. Paga uma vez por temporada
  (`registration_charge="season"`, na 1ª rodada) ou a cada rodada jogada ("round", especificação antiga).
- CT: construção na rodada escolhida (subir de nível paga a diferença); manutenção em TODAS as rodadas da temporada
  (mesmo sem jogar), a partir da seguinte à construção, com o valor do nível vigente. Quem já tem CT paga desde a 1ª.
- Treinamento: % do preço pago, cobrado na rodada em que começa. Nível 1 do CT treina posição extra; nível 2 libera a
  otimização; nível 3 treina dois Pokémon ao mesmo tempo. A espera depende só do tier (ZU 1, PU 2, NU 3...).
- Renda por rodada jogada: vitória/empate/derrota x patrocinadores; W.O. perdido não rende e paga multa.
- Prêmio por colocação: entra na última rodada da temporada.
Dinheiro sempre em euros inteiros.
"""
from app.schemas.calculator import CalcIn, CalcOut, RoundRow, Totals


def registration_fee(n: int, free: int, step: int) -> int:
    """Taxa dos inscritos acima dos gratuitos: 7º = 1 passo, 8º = 2 passos... (11 inscritos, 6 grátis = 15 passos)."""
    extra = max(0, n - free)
    return step * extra * (extra + 1) // 2


def pct(value: int, bp: int) -> int:
    """value x (bp / 10000), em euros inteiros (arredonda para baixo)."""
    return value * bp // 10_000


def tier_wait(tier: str | None, order: list[str]) -> int | None:
    """Rodadas de espera do treinamento: ZU 1, PU 2, NU 3... O tier "BL" conta como o tier de baixo (ZUBL = ZU)."""
    if not tier:
        return None
    t = tier.strip()
    if t not in order and t.upper().endswith("BL"):
        t = t[:-2]
    lower = {x.lower(): i for i, x in enumerate(order)}
    i = lower.get(t.lower())
    return None if i is None else i + 1


def _spread(total: int, n: int) -> list[int]:
    """Divide um total inteiro em n partes iguais; o resto vai para a última (a soma bate exatamente)."""
    if n <= 0:
        return []
    base = total // n
    parts = [base] * n
    parts[-1] += total - base * n
    return parts


def compute(inp: CalcIn) -> CalcOut:
    c = inp.config
    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    total_rounds = c.league_rounds + c.knockout_rounds
    ko_played = inp.knockout_played
    if ko_played > c.knockout_rounds:
        errors.append(f"O mata-mata tem {c.knockout_rounds} rodada(s); não dá para disputar {ko_played}.")
        ko_played = c.knockout_rounds
    played = c.league_rounds + ko_played
    if total_rounds == 0:
        errors.append("A temporada precisa ter pelo menos uma rodada.")

    # ---------- elenco ----------
    squad = inp.squad
    count = len(squad)
    registered = sum(1 for p in squad if p.registered)
    value = sum(p.price for p in squad)
    if count > c.max_squad:
        errors.append(f"O elenco tem {count} Pokémon; o máximo é {c.max_squad}.")
    if registered > c.max_registered:
        errors.append(f"Há {registered} inscritos; o máximo é {c.max_registered}.")
    if value > c.initial_budget:
        warnings.append("O gasto com o elenco passa do orçamento inicial: o caixa já começa negativo (transferban).")
    start_cash = c.initial_budget - value
    salary = pct(value, c.salary_rate_bp)
    reg_fee = registration_fee(registered, c.registration_free_slots, c.registration_step)

    # ---------- CT ----------
    cur, target, build = inp.ct.current_level, inp.ct.target_level, inp.ct.build_round
    building = False
    if target is not None:
        if target <= cur:
            errors.append("O nível alvo do CT deve ser maior que o nível atual.")
        elif build is None or not 1 <= build <= total_rounds:
            errors.append(f"Informe a rodada da construção do CT (de 1 a {total_rounds}).")
        else:
            building = True

    def ct_level_paying(r: int) -> int:  # nível cuja manutenção é cobrada na rodada r
        return target if building and r > build else cur

    def ct_level_existing(r: int) -> int:  # nível disponível para treinar na rodada r
        return target if building and r >= build else cur

    # ---------- treinamentos ----------
    training_cost = [0] * (total_rounds + 2)
    busy: dict[int, int] = {}
    for t in inp.trainings:
        if t.pokemon >= count:
            errors.append(f"Treinamento aponta para um Pokémon que não está no elenco (linha {t.pokemon + 1}).")
            continue
        p = squad[t.pokemon]
        label = p.name or f"Pokémon {t.pokemon + 1}"
        kind = "posição extra" if t.kind == "extra" else "otimização"
        if t.round > total_rounds:
            errors.append(f"Treinamento de {label} na rodada {t.round}: a temporada tem {total_rounds} rodadas.")
            continue
        level_now = ct_level_existing(t.round)
        need = c.ct_min_level.get(t.kind, 1)
        if level_now == 0:
            warnings.append(f"Treinamento de {label} na rodada {t.round}: o CT ainda não existe nessa rodada.")
        elif level_now < need:
            warnings.append(f"Treinamento de {label} na rodada {t.round}: {kind} exige CT nível {need} (o seu é nível {level_now}).")
        training_cost[t.round] += pct(p.price, c.training_extra_bp if t.kind == "extra" else c.training_opt_bp)
        wait = tier_wait(p.tier, c.tier_order)
        if wait is None:
            notes.append(f"{label} ({kind}): informe o tier para saber quando o treinamento fica pronto.")
            continue
        notes.append(f"{label} ({kind}): começa na rodada {t.round} e vale a partir da rodada {t.round + wait}.")
        for r in range(t.round, t.round + wait):
            busy[r] = busy.get(r, 0) + 1
    for r in sorted(busy):
        if r > total_rounds:
            break
        level = ct_level_existing(r)
        cap = c.ct_parallel[level]
        if level and busy[r] > cap:
            warnings.append(f"Rodada {r}: {busy[r]} treinamentos ao mesmo tempo; o CT nível {level} permite {cap}.")

    # ---------- resultados ----------
    V = c.win_per_sponsor * c.sponsors
    D = c.draw_per_sponsor * c.sponsors
    L = c.loss_per_sponsor * c.sponsors
    income = [0] * (total_rounds + 1)
    fines = [0] * (total_rounds + 1)
    results: list[str | None] = [None] * (total_rounds + 1)
    tot_w = tot_d = tot_l = 0
    res = inp.results
    if res.mode == "simple":
        losses = played - res.wins - res.draws - res.wo
        if losses < 0:
            errors.append(
                f"Vitórias + empates + W.O. ({res.wins + res.draws + res.wo}) passam das {played} rodadas jogadas."
            )
            losses = 0
        tot_w, tot_d, tot_l = res.wins * V, res.draws * D, losses * L
        for r, part in enumerate(_spread(tot_w + tot_d + tot_l, played), start=1):
            income[r] = part
        for r, part in enumerate(_spread(res.wo * c.wo_fine, played), start=1):
            fines[r] = part
        if played:
            notes.append("Modo simples: a renda (e as multas) foram divididas igualmente entre as rodadas jogadas.")
    else:
        per = list(res.per_round[:total_rounds]) + ["-"] * max(0, total_rounds - len(res.per_round))
        for r, x in enumerate(per, start=1):
            if r > played:
                if x != "-":
                    errors.append(f"Rodada {r}: o jogador não disputa essa rodada (eliminado antes).")
                continue
            results[r] = x
            if x == "W":
                income[r] = V
                tot_w += V
            elif x == "D":
                income[r] = D
                tot_d += D
            elif x == "L":
                income[r] = L
                tot_l += L
            elif x == "WO":
                fines[r] = c.wo_fine

    # ---------- prêmio ----------
    prize = 0
    if inp.placement is not None:
        if not c.prizes:
            warnings.append("Esta configuração não tem prêmio por colocação.")
        elif inp.placement > len(c.prizes):
            errors.append(f"A tabela de prêmios vai do 1º ao {len(c.prizes)}º lugar.")
        else:
            prize = c.prizes[inp.placement - 1]

    # ---------- rodada a rodada ----------
    rows: list[RoundRow] = []
    tt = Totals()
    cash = start_cash
    first_negative = 0 if start_cash < 0 else None
    for r in range(1, total_rounds + 1):
        is_played = r <= played
        row = RoundRow(round=r, phase=c.league_label if r <= c.league_rounds else c.knockout_label, played=is_played,
                       result=results[r])
        if is_played:
            row.salaries = salary
            if c.registration_charge == "round" or r == 1:
                row.registration = reg_fee
        row.ct_maintenance = c.ct_maintenance[ct_level_paying(r)]
        if building and r == build:
            row.ct_build = c.ct_build[target] - c.ct_build[cur]
        row.trainings = training_cost[r]
        row.fine = fines[r]
        row.cost = row.salaries + row.registration + row.ct_maintenance + row.ct_build + row.trainings + row.fine
        row.income = income[r]
        if r == total_rounds:
            row.prize = prize
        row.balance = row.income + row.prize - row.cost
        cash += row.balance
        row.cash = cash
        if cash < 0 and first_negative is None:
            first_negative = r
        rows.append(row)
        for k in ("salaries", "registration", "ct_maintenance", "ct_build", "trainings", "fine", "cost", "income", "prize", "balance"):
            setattr(tt, k, getattr(tt, k) + getattr(row, k))
    tt.income_wins, tt.income_draws, tt.income_losses = tot_w, tot_d, tot_l

    # ---------- vitórias de equilíbrio (sem empates e sem W.O.) ----------
    exact = wins_needed = None
    impossible = False
    if played and V != L:
        need = (tt.cost - tt.fine) - L * played - prize
        exact = round(need / (V - L), 3) if need > 0 else 0.0
        wins_needed = max(0, -(-need // (V - L)))  # arredonda para cima, só com inteiros
        impossible = wins_needed > played
    if c.registration_charge == "season":
        notes.append("Inscrição: cada Pokémon inscrito paga uma vez por temporada (cobrada na 1ª rodada).")
    if ko_played < c.knockout_rounds and c.knockout_rounds:
        notes.append("Eliminado antes do fim: não paga salário nas rodadas que não joga, mas a manutenção do CT continua.")

    return CalcOut(
        rounds_total=total_rounds, rounds_played=played, squad_count=count, registered_count=registered,
        squad_value=value, start_cash=start_cash, final_cash=cash, totals=tt, rows=rows,
        first_negative_round=first_negative, breakeven_exact=exact, breakeven_wins=wins_needed,
        breakeven_impossible=impossible, win_value=V, draw_value=D, loss_value=L,
        errors=errors, warnings=warnings, notes=notes,
    )
