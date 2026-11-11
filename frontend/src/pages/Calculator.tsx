import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { ErrorBox, Loading } from "../components/ui";

/* Calculadora de custos da temporada (Draft). Simulação livre: nada é gravado no servidor; os valores ficam só
   neste navegador. Os valores econômicos vêm do servidor (arquivo de configuração) e podem ser ajustados aqui. */

interface EconomyConfig {
  label: string; initial_budget: number; sponsors: number; win_per_sponsor: number; draw_per_sponsor: number; loss_per_sponsor: number;
  wo_fine: number; salary_rate_bp: number; registration_step: number; registration_free_slots: number; registration_charge: "season" | "round";
  max_squad: number; max_registered: number; ct_build: number[]; ct_maintenance: number[]; ct_parallel: number[]; ct_min_level: Record<string, number>;
  training_extra_bp: number; training_opt_bp: number; tier_order: string[]; tier_prices: Record<string, number | null>; market_premium: number;
  league_rounds: number; knockout_rounds: number; league_label: string; knockout_label: string; prizes: number[];
}
interface Row { round: number; phase: string; played: boolean; result: string | null; salaries: number; registration: number; ct_maintenance: number; ct_build: number; trainings: number; fine: number; cost: number; income: number; prize: number; balance: number; cash: number }
interface CalcOut {
  rounds_total: number; rounds_played: number; squad_count: number; registered_count: number; squad_value: number; start_cash: number; final_cash: number;
  totals: Omit<Row, "round" | "phase" | "played" | "result" | "cash"> & { income_wins: number; income_draws: number; income_losses: number };
  rows: Row[]; first_negative_round: number | null; breakeven_exact: number | null; breakeven_wins: number | null; breakeven_impossible: boolean;
  win_value: number; draw_value: number; loss_value: number; errors: string[]; warnings: string[]; notes: string[];
}
interface Mon { name: string; price: string; tier: string; registered: boolean }
interface Training { pokemon: number; kind: "extra" | "opt"; round: number }
type Res = "W" | "D" | "L" | "WO" | "-";
interface State {
  preset: string; config: EconomyConfig | null; squad: Mon[];
  ct: { current: number; target: string; build: string }; trainings: Training[];
  mode: "simple" | "detailed"; wins: number; draws: number; wo: number; perRound: Res[];
  koPlayed: number; placement: string;
}

const STORE = "calculadora.v2"; // mudou a regra do CT: descarta simulações salvas com os valores antigos
const blankMon = (): Mon => ({ name: "", price: "", tier: "", registered: true });
const initial: State = {
  preset: "", config: null, squad: [blankMon()], ct: { current: 0, target: "", build: "" }, trainings: [],
  mode: "simple", wins: 0, draws: 0, wo: 0, perRound: [], koPlayed: 0, placement: "",
};

/** "30" ou "1,5" (milhões) -> euros inteiros. */
function toEur(s: string): number {
  const t = String(s).trim();
  // "1.234,5" (pt-BR) ou "1,5" -> vírgula decimal; sem vírgula, o ponto é decimal ("1.5")
  const n = Number(t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t);
  return Number.isFinite(n) ? Math.round(n * 1_000_000) : 0;
}
/** euros -> texto em milhões para campos ("1,5"). */
function toM(n: number | null | undefined): string {
  if (n == null) return "";
  return (n / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 6, useGrouping: false });
}
/** euros -> "30,00M" (com sinal negativo visível). */
export function fmtM(n: number): string {
  return `${(n / 1_000_000).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}M`;
}
const pctTxt = (bp: number) => (bp / 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 });
const fromPct = (s: string) => Math.round(Number(s.replace(",", ".")) * 100) || 0;
const CT_LEVEL: Record<number, string> = {
  1: "Nível 1 — treina posição extra",
  2: "Nível 2 — também otimiza função",
  3: "Nível 3 — dois treinos ao mesmo tempo",
};
const RES_LABEL: Record<Res, string> = { W: "Vitória", D: "Empate", L: "Derrota", WO: "W.O. perdido", "-": "Não jogada" };

function load(): State {
  try {
    const raw = localStorage.getItem(STORE);
    if (raw) return { ...initial, ...JSON.parse(raw) };
  } catch { /* navegador sem armazenamento: começa do zero */ }
  return initial;
}

export default function Calculator() {
  const [presets, setPresets] = useState<{ default: string; presets: Record<string, EconomyConfig> } | null>(null);
  const [presetError, setPresetError] = useState<string | null>(null);
  const [s, setS] = useState<State>(load);
  const [out, setOut] = useState<CalcOut | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);
  const timer = useRef<number>();
  const set = (patch: Partial<State>) => setS((x) => ({ ...x, ...patch }));

  useEffect(() => {
    api<{ default: string; presets: Record<string, EconomyConfig> }>("/calculator/presets")
      .then((p) => {
        setPresets(p);
        setS((x) => (x.config ? x : { ...x, preset: p.default, config: p.presets[p.default] }));
      })
      .catch((e) => setPresetError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    try { localStorage.setItem(STORE, JSON.stringify(s)); } catch { /* ignora */ }
  }, [s]);

  const cfg = s.config;
  const totalRounds = cfg ? cfg.league_rounds + cfg.knockout_rounds : 0;
  const played = cfg ? cfg.league_rounds + Math.min(s.koPlayed, cfg.knockout_rounds) : 0;

  const payload = useMemo(() => cfg && {
    config: cfg,
    squad: s.squad.map((m) => ({ name: m.name, price: toEur(m.price), tier: m.tier || null, registered: m.registered })),
    ct: { current_level: s.ct.current, target_level: s.ct.target ? Number(s.ct.target) : null, build_round: s.ct.build ? Number(s.ct.build) : null },
    trainings: s.trainings,
    results: { mode: s.mode, wins: s.wins, draws: s.draws, wo: s.wo, per_round: s.perRound.slice(0, totalRounds) },
    knockout_played: s.koPlayed,
    placement: s.placement ? Number(s.placement) : null,
  }, [cfg, s, totalRounds]);

  // Recalcula a cada mudança (com uma pequena espera para não chamar o servidor a cada tecla).
  useEffect(() => {
    if (!payload) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      api<CalcOut>("/calculator", { body: payload })
        .then((r) => { setOut(r); setCalcError(null); })
        .catch((e) => setCalcError(e instanceof ApiError || e instanceof Error ? e.message : String(e)));
    }, 300);
    return () => window.clearTimeout(timer.current);
  }, [payload]);

  if (presetError) return <ErrorBox error={presetError} />;
  if (!presets || !cfg) return <Loading />;

  const setCfg = (patch: Partial<EconomyConfig>) => set({ config: { ...cfg, ...patch } });
  const choosePreset = (id: string) => set({ preset: id, config: presets.presets[id], koPlayed: 0, placement: "", perRound: [] });
  const updMon = (i: number, patch: Partial<Mon>) => set({ squad: s.squad.map((m, k) => (k === i ? { ...m, ...patch } : m)) });
  const losses = played - s.wins - s.draws - s.wo;
  const tiers = Object.keys(cfg.tier_prices);

  const exportCsv = () => {
    if (!out) return;
    const head = ["Rodada", "Fase", "Jogada", "Salários", "Inscrição", "Manutenção CT", "Construção CT", "Treinamentos", "Multa", "Custo total", "Renda", "Prêmio", "Saldo da rodada", "Caixa"];
    const eur = (n: number) => String(n);
    const lines = out.rows.map((r) => [r.round, r.phase, r.played ? "sim" : "não", r.salaries, r.registration, r.ct_maintenance, r.ct_build, r.trainings, r.fine, r.cost, r.income, r.prize, r.balance, r.cash].map((x) => (typeof x === "number" ? eur(x) : x)).join(";"));
    const csv = "﻿" + [head.join(";"), ...lines].join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = "calculadora-temporada.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <h1>Calculadora da temporada</h1>
      <p className="muted" style={{ maxWidth: 760 }}>
        Simule quanto o seu clube gasta e ganha na temporada, rodada a rodada. É só uma simulação: nada é gravado e os valores
        ficam salvos apenas neste navegador. Valores em milhões de euros (ex.: 30 ou 1,5).
      </p>

      <div className="card">
        <h2>Configuração</h2>
        <div className="form-grid">
          <div className="field"><label>Modelo</label>
            <select value={s.preset} onChange={(e) => choosePreset(e.target.value)}>
              {Object.entries(presets.presets).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
          <div className="field"><label>Orçamento inicial (M)</label><input inputMode="decimal" value={toM(cfg.initial_budget)} onChange={(e) => setCfg({ initial_budget: toEur(e.target.value) })} /></div>
          <div className="field"><label>Salário por rodada (% do preço)</label><input inputMode="decimal" value={pctTxt(cfg.salary_rate_bp)} onChange={(e) => setCfg({ salary_rate_bp: fromPct(e.target.value) })} /></div>
        </div>
        <details>
          <summary style={{ cursor: "pointer" }}>Ajustar todos os valores (formato, renda, CT, prêmios…)</summary>
          <h3>Formato</h3>
          <div className="form-grid">
            <div className="field"><label>Rodadas de liga/grupos (todos jogam)</label><input type="number" min={0} max={100} value={cfg.league_rounds} onChange={(e) => setCfg({ league_rounds: Number(e.target.value) || 0 })} /></div>
            <div className="field"><label>Rodadas de mata-mata</label><input type="number" min={0} max={10} value={cfg.knockout_rounds} onChange={(e) => setCfg({ knockout_rounds: Number(e.target.value) || 0 })} /></div>
            <div className="field"><label>Nome da 1ª fase</label><input value={cfg.league_label} onChange={(e) => setCfg({ league_label: e.target.value })} /></div>
            <div className="field"><label>Nome do mata-mata</label><input value={cfg.knockout_label} onChange={(e) => setCfg({ knockout_label: e.target.value })} /></div>
          </div>
          <p className="muted small">Ex.: tabela única de 10 jogadores em turno e returno = 18 rodadas de liga e 0 de mata-mata.</p>
          <h3>Renda</h3>
          <div className="form-grid">
            <div className="field"><label>Patrocinadores</label><input type="number" min={0} max={20} value={cfg.sponsors} onChange={(e) => setCfg({ sponsors: Number(e.target.value) || 0 })} /></div>
            <div className="field"><label>Vitória, por patrocinador (M)</label><input inputMode="decimal" value={toM(cfg.win_per_sponsor)} onChange={(e) => setCfg({ win_per_sponsor: toEur(e.target.value) })} /></div>
            <div className="field"><label>Empate, por patrocinador (M)</label><input inputMode="decimal" value={toM(cfg.draw_per_sponsor)} onChange={(e) => setCfg({ draw_per_sponsor: toEur(e.target.value) })} /></div>
            <div className="field"><label>Derrota, por patrocinador (M)</label><input inputMode="decimal" value={toM(cfg.loss_per_sponsor)} onChange={(e) => setCfg({ loss_per_sponsor: toEur(e.target.value) })} /></div>
            <div className="field"><label>Multa por W.O. (M)</label><input inputMode="decimal" value={toM(cfg.wo_fine)} onChange={(e) => setCfg({ wo_fine: toEur(e.target.value) })} /></div>
            <div className="field"><label>Prêmios por colocação (M, do 1º ao último, separados por ;)</label>
              <input value={cfg.prizes.map(toM).join("; ")} onChange={(e) => setCfg({ prizes: e.target.value.split(";").map((x) => x.trim()).filter(Boolean).map(toEur) })} />
            </div>
          </div>
          <h3>Elenco e inscrição</h3>
          <div className="form-grid">
            <div className="field"><label>Máximo no elenco</label><input type="number" min={1} value={cfg.max_squad} onChange={(e) => setCfg({ max_squad: Number(e.target.value) || 1 })} /></div>
            <div className="field"><label>Máximo de inscritos</label><input type="number" min={1} value={cfg.max_registered} onChange={(e) => setCfg({ max_registered: Number(e.target.value) || 1 })} /></div>
            <div className="field"><label>Inscritos grátis</label><input type="number" min={0} value={cfg.registration_free_slots} onChange={(e) => setCfg({ registration_free_slots: Number(e.target.value) || 0 })} /></div>
            <div className="field"><label>Passo da taxa de inscrição (M)</label><input inputMode="decimal" value={toM(cfg.registration_step)} onChange={(e) => setCfg({ registration_step: toEur(e.target.value) })} /></div>
            <div className="field"><label>Taxa de inscrição cobrada</label>
              <select value={cfg.registration_charge} onChange={(e) => setCfg({ registration_charge: e.target.value as "season" | "round" })}>
                <option value="season">Uma vez por temporada</option><option value="round">A cada rodada jogada</option>
              </select>
            </div>
          </div>
          <h3>Centro de Treinamento</h3>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Nível</th><th>Construção acumulada (M)</th><th>Manutenção por rodada (M)</th><th>Treinos ao mesmo tempo</th></tr></thead>
              <tbody>
                {[1, 2, 3].map((lv) => (
                  <tr key={lv}>
                    <td>{lv}</td>
                    <td><input inputMode="decimal" value={toM(cfg.ct_build[lv])} onChange={(e) => setCfg({ ct_build: cfg.ct_build.map((v, k) => (k === lv ? toEur(e.target.value) : v)) })} /></td>
                    <td><input inputMode="decimal" value={toM(cfg.ct_maintenance[lv])} onChange={(e) => setCfg({ ct_maintenance: cfg.ct_maintenance.map((v, k) => (k === lv ? toEur(e.target.value) : v)) })} /></td>
                    <td><input type="number" min={0} value={cfg.ct_parallel[lv]} onChange={(e) => setCfg({ ct_parallel: cfg.ct_parallel.map((v, k) => (k === lv ? Number(e.target.value) || 0 : v)) })} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="form-grid">
            <div className="field"><label>Treino de posição extra (% do preço)</label><input inputMode="decimal" value={pctTxt(cfg.training_extra_bp)} onChange={(e) => setCfg({ training_extra_bp: fromPct(e.target.value) })} /></div>
            <div className="field"><label>Treino de otimização (% do preço)</label><input inputMode="decimal" value={pctTxt(cfg.training_opt_bp)} onChange={(e) => setCfg({ training_opt_bp: fromPct(e.target.value) })} /></div>
          </div>
          <button type="button" className="btn small" onClick={() => choosePreset(s.preset)}>Voltar aos valores do modelo</button>
        </details>
      </div>

      <div className="card">
        <h2>Elenco</h2>
        <p className="muted small">O tier sugere o preço (o tier "BL" vale o de baixo + 5M). Ajuste para o valor que você realmente pagou. Reservas (não inscritos) também recebem salário.</p>
        <div className="table-wrap">
          <table>
            <thead><tr><th>#</th><th>Pokémon</th><th>Tier</th><th>Preço pago (M)</th><th>Inscrito</th><th></th></tr></thead>
            <tbody>
              {s.squad.map((m, i) => (
                <tr key={i}>
                  <td className="muted">{i + 1}</td>
                  <td><input value={m.name} maxLength={60} onChange={(e) => updMon(i, { name: e.target.value })} placeholder="Nome" /></td>
                  <td>
                    <select value={m.tier} onChange={(e) => {
                      const p = cfg.tier_prices[e.target.value];
                      updMon(i, { tier: e.target.value, ...(p != null ? { price: toM(p) } : {}) });
                    }}>
                      <option value="">—</option>
                      {tiers.map((t) => <option key={t} value={t}>{t}{cfg.tier_prices[t] == null ? " (a definir)" : ""}</option>)}
                    </select>
                  </td>
                  <td><input inputMode="decimal" style={{ maxWidth: 110 }} value={m.price} onChange={(e) => updMon(i, { price: e.target.value })} /></td>
                  <td className="center"><input type="checkbox" checked={m.registered} onChange={(e) => updMon(i, { registered: e.target.checked })} /></td>
                  <td><button type="button" className="btn small" onClick={() => set({ squad: s.squad.filter((_, k) => k !== i), trainings: s.trainings.filter((t) => t.pokemon !== i).map((t) => ({ ...t, pokemon: t.pokemon > i ? t.pokemon - 1 : t.pokemon })) })}>Remover</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="row" style={{ marginTop: ".6rem" }}>
          <button type="button" className="btn small" onClick={() => set({ squad: [...s.squad, blankMon()] })}>Adicionar Pokémon</button>
          {out && <span className="muted small">{out.squad_count} no elenco (máx. {cfg.max_squad}) · {out.registered_count} inscritos (máx. {cfg.max_registered}) · gasto na compra {fmtM(out.squad_value)}</span>}
        </div>
      </div>

      <div className="card">
        <h2>Centro de Treinamento (CT)</h2>
        <div className="form-grid">
          <div className="field"><label>Nível atual</label>
            <select value={s.ct.current} onChange={(e) => set({ ct: { ...s.ct, current: Number(e.target.value) } })}>
              <option value={0}>Não tenho CT</option>{[1, 2, 3].map((n) => <option key={n} value={n}>{CT_LEVEL[n]}</option>)}
            </select>
          </div>
          <div className="field"><label>Construir / melhorar até</label>
            <select value={s.ct.target} onChange={(e) => set({ ct: { ...s.ct, target: e.target.value } })}>
              <option value="">Não vou construir</option>{[1, 2, 3].filter((n) => n > s.ct.current).map((n) => <option key={n} value={n}>{CT_LEVEL[n]}</option>)}
            </select>
          </div>
          {s.ct.target && (
            <div className="field"><label>Na rodada</label>
              <select value={s.ct.build} onChange={(e) => set({ ct: { ...s.ct, build: e.target.value } })}>
                <option value="">Escolha</option>{Array.from({ length: totalRounds }, (_, k) => <option key={k} value={k + 1}>{k + 1}</option>)}
              </select>
            </div>
          )}
        </div>
        <p className="muted small">A manutenção é cobrada em todas as rodadas da temporada, mesmo depois de eliminado, a partir da rodada seguinte à construção.</p>
        <details open={s.trainings.length > 0}>
          <summary style={{ cursor: "pointer" }}>Treinamentos planejados ({s.trainings.length})</summary>
          {s.trainings.map((t, i) => (
            <div key={i} className="row" style={{ margin: ".4rem 0" }}>
              <select value={t.pokemon} onChange={(e) => set({ trainings: s.trainings.map((x, k) => (k === i ? { ...x, pokemon: Number(e.target.value) } : x)) })}>
                {s.squad.map((m, k) => <option key={k} value={k}>{m.name || `Pokémon ${k + 1}`}</option>)}
              </select>
              <select value={t.kind} onChange={(e) => set({ trainings: s.trainings.map((x, k) => (k === i ? { ...x, kind: e.target.value as "extra" | "opt" } : x)) })}>
                <option value="extra">Posição extra ({pctTxt(cfg.training_extra_bp)}%)</option><option value="opt">Otimização ({pctTxt(cfg.training_opt_bp)}%)</option>
              </select>
              <select value={t.round} onChange={(e) => set({ trainings: s.trainings.map((x, k) => (k === i ? { ...x, round: Number(e.target.value) } : x)) })}>
                {Array.from({ length: totalRounds }, (_, k) => <option key={k} value={k + 1}>Rodada {k + 1}</option>)}
              </select>
              <button type="button" className="btn small" onClick={() => set({ trainings: s.trainings.filter((_, k) => k !== i) })}>Remover</button>
            </div>
          ))}
          <button type="button" className="btn small" style={{ marginTop: ".4rem" }} onClick={() => set({ trainings: [...s.trainings, { pokemon: 0, kind: "extra", round: Number(s.ct.build) || 1 }] })}>Adicionar treinamento</button>
          <p className="muted small">Nível 1 treina posição extra, o nível 2 libera a otimização e o nível 3 treina dois Pokémon ao mesmo tempo. O treinamento fica pronto depois de algumas rodadas, conforme o tier do Pokémon (ZU 1, PU 2, NU 3…; "BL" conta como o tier de baixo), em qualquer nível.</p>
        </details>
      </div>

      <div className="card">
        <h2>Resultados</h2>
        <div className="form-grid">
          {cfg.knockout_rounds > 0 && (
            <div className="field"><label>Até onde vai</label>
              <select value={s.koPlayed} onChange={(e) => set({ koPlayed: Number(e.target.value) })}>
                {Array.from({ length: cfg.knockout_rounds + 1 }, (_, k) => (
                  <option key={k} value={k}>{k === 0 ? `Eliminado na ${cfg.league_label.toLowerCase()}` : `Joga ${k} rodada(s) do ${cfg.knockout_label.toLowerCase()}`}</option>
                ))}
              </select>
            </div>
          )}
          {cfg.prizes.length > 0 && (
            <div className="field"><label>Colocação final (prêmio)</label>
              <select value={s.placement} onChange={(e) => set({ placement: e.target.value })}>
                <option value="">Sem prêmio</option>
                {cfg.prizes.map((p, k) => <option key={k} value={k + 1}>{k + 1}º — {fmtM(p)}</option>)}
              </select>
            </div>
          )}
          <div className="field"><label>Modo</label>
            <select value={s.mode} onChange={(e) => set({ mode: e.target.value as "simple" | "detailed" })}>
              <option value="simple">Simples (totais)</option><option value="detailed">Rodada a rodada</option>
            </select>
          </div>
        </div>
        {s.mode === "simple" ? (
          <>
            <div className="row">
              <Stepper label="Vitórias" value={s.wins} max={played} onChange={(v) => set({ wins: v })} />
              <Stepper label="Empates" value={s.draws} max={played} onChange={(v) => set({ draws: v })} />
              <Stepper label="W.O. perdidos" value={s.wo} max={played} onChange={(v) => set({ wo: v })} />
              <div className="field"><label>Derrotas</label><div style={{ padding: ".45rem 0", fontWeight: 700, color: losses < 0 ? "var(--red)" : undefined }}>{losses}</div></div>
            </div>
            <input type="range" min={0} max={played} value={Math.min(s.wins, played)} onChange={(e) => set({ wins: Number(e.target.value) })} style={{ width: "100%", maxWidth: 420 }} aria-label="Vitórias" />
            <p className="muted small">{played} rodadas jogadas. Derrotas = rodadas − vitórias − empates − W.O. A renda é dividida igualmente entre as rodadas jogadas na tabela abaixo.</p>
          </>
        ) : (
          <div className="form-grid">
            {Array.from({ length: totalRounds }, (_, k) => (
              <div key={k} className="field"><label>Rodada {k + 1}{k + 1 > played ? " (não joga)" : ""}</label>
                <select value={s.perRound[k] ?? "-"} disabled={k + 1 > played} onChange={(e) => {
                  const next = [...s.perRound];
                  while (next.length < totalRounds) next.push("-");
                  next[k] = e.target.value as Res;
                  set({ perRound: next });
                }}>
                  {(Object.keys(RES_LABEL) as Res[]).map((r) => <option key={r} value={r}>{RES_LABEL[r]}</option>)}
                </select>
              </div>
            ))}
          </div>
        )}
      </div>

      <ErrorBox error={calcError} />
      {out && <Results out={out} cfg={cfg} onCsv={exportCsv} />}
    </>
  );
}

function Stepper({ label, value, max, onChange }: { label: string; value: number; max: number; onChange: (v: number) => void }) {
  return (
    <div className="field"><label>{label}</label>
      <div className="row" style={{ gap: ".3rem", flexWrap: "nowrap" }}>
        <button type="button" className="btn small" onClick={() => onChange(Math.max(0, value - 1))} aria-label={`Menos ${label.toLowerCase()}`}>−</button>
        <input type="number" min={0} max={max} value={value} style={{ width: 64 }} onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))} />
        <button type="button" className="btn small" onClick={() => onChange(value + 1)} aria-label={`Mais ${label.toLowerCase()}`}>+</button>
      </div>
    </div>
  );
}

function Results({ out, cfg, onCsv }: { out: CalcOut; cfg: EconomyConfig; onCsv: () => void }) {
  const t = out.totals;
  const color = (n: number) => ({ color: n < 0 ? "var(--red)" : "var(--green)" });
  const cols: [keyof Row, string][] = [
    ["salaries", "Salários"], ["registration", "Inscrição"], ["ct_maintenance", "Manut. CT"], ["ct_build", "Constr. CT"],
    ["trainings", "Treinos"], ["fine", "Multa"], ["cost", "Custo total"], ["income", "Renda"], ["prize", "Prêmio"], ["balance", "Saldo"],
  ];
  return (
    <>
      {out.errors.map((e) => <div key={e} className="alert error">{e}</div>)}
      {out.warnings.map((w) => <div key={w} className="alert warn">{w}</div>)}
      <div className="card">
        <h2>Resumo da temporada</h2>
        <div className="stat-row">
          <div className="stat-box"><div className="n">{fmtM(out.start_cash)}</div><div className="muted small">Caixa após as compras</div></div>
          <div className="stat-box"><div className="n">{fmtM(t.cost)}</div><div className="muted small">Custo total</div></div>
          <div className="stat-box"><div className="n">{fmtM(t.income + t.prize)}</div><div className="muted small">Renda + prêmio</div></div>
          <div className="stat-box"><div className="n" style={color(t.balance)}>{fmtM(t.balance)}</div><div className="muted small">Saldo da temporada</div></div>
          <div className="stat-box"><div className="n" style={color(out.final_cash)}>{fmtM(out.final_cash)}</div><div className="muted small">Caixa final</div></div>
        </div>
        <div className="grid cols-2" style={{ marginTop: "1rem", alignItems: "start" }}>
          <dl className="kv">
            <dt>Salários</dt><dd>{fmtM(t.salaries)}</dd>
            <dt>Inscrição</dt><dd>{fmtM(t.registration)}</dd>
            <dt>CT (construção)</dt><dd>{fmtM(t.ct_build)}</dd>
            <dt>CT (manutenção)</dt><dd>{fmtM(t.ct_maintenance)}</dd>
            <dt>Treinamentos</dt><dd>{fmtM(t.trainings)}</dd>
            <dt>Multas</dt><dd>{fmtM(t.fine)}</dd>
          </dl>
          <dl className="kv">
            <dt>Vitórias</dt><dd>{fmtM(t.income_wins)} <span className="muted small">({fmtM(out.win_value)} cada)</span></dd>
            <dt>Empates</dt><dd>{fmtM(t.income_draws)} <span className="muted small">({fmtM(out.draw_value)} cada)</span></dd>
            <dt>Derrotas</dt><dd>{fmtM(t.income_losses)} <span className="muted small">({fmtM(out.loss_value)} cada)</span></dd>
            <dt>Prêmio</dt><dd>{fmtM(t.prize)}</dd>
          </dl>
        </div>
        {out.first_negative_round != null && (
          <div className="alert error">
            {out.first_negative_round === 0 ? "O caixa já começa negativo, antes da 1ª rodada" : `O caixa fica negativo na rodada ${out.first_negative_round}`}: com saldo negativo o clube entra em transferban (não pode comprar).
          </div>
        )}
        {out.breakeven_wins != null && (
          <p>
            <strong>Vitórias para empatar as contas</strong> (sem empates nem W.O.{cfg.prizes.length ? ", contando o prêmio escolhido" : ""}):{" "}
            {out.breakeven_impossible
              ? <span style={{ color: "var(--red)" }}>impossível equilibrar em {out.rounds_played} rodadas.</span>
              : <>{(out.breakeven_exact ?? 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} → <strong>{out.breakeven_wins}</strong> de {out.rounds_played} ({Math.round((out.breakeven_wins / Math.max(1, out.rounds_played)) * 100)}%)</>}
          </p>
        )}
        {out.notes.length > 0 && <ul className="muted small" style={{ margin: 0 }}>{out.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      </div>

      <div className="card">
        <div className="row between">
          <h2 style={{ margin: 0 }}>Rodada a rodada</h2>
          <button type="button" className="btn small" onClick={onCsv}>Exportar CSV</button>
        </div>
        <div className="table-wrap" style={{ marginTop: ".6rem" }}>
          <table>
            <thead>
              <tr><th>Rodada</th>{cols.map(([, l]) => <th key={l} className="num">{l}</th>)}<th className="num">Caixa</th></tr>
            </thead>
            <tbody>
              {out.rows.map((r) => (
                <tr key={r.round} style={r.played ? undefined : { opacity: 0.6 }}>
                  <td className="nowrap">{r.round} <span className="muted small">{r.phase}{r.played ? "" : " · não joga"}</span></td>
                  {cols.map(([k]) => <td key={k} className="num nowrap">{fmtM(r[k] as number)}</td>)}
                  <td className="num nowrap" style={color(r.cash)}>{fmtM(r.cash)}</td>
                </tr>
              ))}
              <tr style={{ fontWeight: 800 }}>
                <td>Total</td>
                {cols.map(([k]) => <td key={k} className="num nowrap">{fmtM(t[k as keyof typeof t] as number)}</td>)}
                <td className="num nowrap" style={color(out.final_cash)}>{fmtM(out.final_cash)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
