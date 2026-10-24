// Editor do torneio personalizado "por fluxo": cada fase diz, em português, para onde vão os jogadores quando ela
// termina ("Vencedores do 1º ao 6º → Mata-mata"). Quem não é enviado a lugar nenhum é eliminado (o servidor faz isso).
//
// Por baixo, o fluxo vira as regras de passagem que a API espera (`toPayload`): as vagas de cada destino são calculadas
// sozinhas, na ordem das linhas. `analyze` aplica às regras geradas as mesmas verificações do servidor
// (templates.validate_custom) — se mudar validate_custom, mude `checkRules` também.
import { useState } from "react";

export type SType = "round" | "league" | "groups" | "knockout" | "playoff";
export type Source = "ranking" | "group_position" | "winners" | "losers";
type Target = "stage" | "repechage" | "parent_tournament";

/** Um destino: "Vencedores do 1º ao 6º → fase 3". */
export interface Out {
  key: number;
  source: Source;
  posFrom: number;
  posTo: number;
  target: Target;
  toStage: number; // posição da fase de destino (target "stage")
  parentStage: number; // subtorneio: fase do torneio principal (target "parent_tournament")
  fixedCrossing: boolean; // grupos → mata-mata: 1ºA × 2ºB...
}

export interface FStage {
  key: number;
  name: string;
  type: SType;
  bestOf: number;
  doubleRound: boolean;
  groupsCount: string; // vazio = automático
  thirdPlace: boolean;
  seeding: "" | "random" | "standard" | "sequential";
  pairing: "random" | "seeded";
  reserve: number; // vagas no fim da fase para quem volta de um torneio de repescagem separado
  outs: Out[];
}

export interface Builder { stages: FStage[] }
export interface ParentStage { position: number; name: string; reserved: [number, number][] }

let seq = 1;
const nextKey = () => seq++;

export const typeLabel: Record<SType, string> = {
  round: "Rodada única (cada um joga uma vez)",
  playoff: "Playoff / repescagem interna",
  league: "Pontos corridos",
  groups: "Fase de grupos",
  knockout: "Mata-mata",
};
const shortType: Record<SType, string> = { round: "Rodada única", playoff: "Playoff", league: "Pontos corridos", groups: "Fase de grupos", knockout: "Mata-mata" };

export function newStage(name: string, type: SType, patch: Partial<FStage> = {}): FStage {
  return { key: nextKey(), name, type, bestOf: 1, doubleRound: false, groupsCount: "", thirdPlace: false, seeding: "", pairing: "random", reserve: 0, outs: [], ...patch };
}

export function newOut(patch: Partial<Out> = {}): Out {
  return { key: nextKey(), source: "ranking", posFrom: 1, posTo: 1, target: "stage", toStage: 2, parentStage: 1, fixedCrossing: true, ...patch };
}

// ---------- exemplos prontos ----------
export interface Example { title: string; players: number; build: () => Builder }

export const examples: Example[] = [
  {
    title: "20 jogadores: rodada única → repescagem (playoff) → mata-mata de 8",
    players: 20,
    build: () => ({
      stages: [
        newStage("Rodada inicial", "round", { outs: [
          newOut({ source: "winners", posFrom: 1, posTo: 6, toStage: 3 }),
          newOut({ source: "winners", posFrom: 7, posTo: 10, toStage: 2 }),
        ] }),
        newStage("Repescagem", "playoff", { pairing: "seeded", outs: [newOut({ source: "winners", posFrom: 1, posTo: 2, toStage: 3 })] }),
        newStage("Mata-mata", "knockout", { seeding: "standard" }),
      ],
    }),
  },
  {
    title: "16 jogadores: 4 grupos → mata-mata de 8 (2 por grupo)",
    players: 16,
    build: () => ({
      stages: [
        newStage("Fase de grupos", "groups", { groupsCount: "4", outs: [newOut({ source: "group_position", posFrom: 1, posTo: 2, toStage: 2 })] }),
        newStage("Mata-mata", "knockout"),
      ],
    }),
  },
  {
    title: "8 jogadores: pontos corridos → semifinal e final com os 4 melhores",
    players: 8,
    build: () => ({
      stages: [
        newStage("Pontos corridos", "league", { outs: [newOut({ source: "ranking", posFrom: 1, posTo: 4, toStage: 2 })] }),
        newStage("Fase final", "knockout", { seeding: "standard", thirdPlace: true }),
      ],
    }),
  },
  {
    title: "12 jogadores: rodada única → pontos corridos com os 6 vencedores",
    players: 12,
    build: () => ({
      stages: [
        newStage("Rodada inicial", "round", { outs: [newOut({ source: "winners", posFrom: 1, posTo: 6, toStage: 2 })] }),
        newStage("Pontos corridos", "league"),
      ],
    }),
  },
];

/** Começo padrão (ou, no subtorneio, uma rodada única que devolve os 2 melhores vencedores ao principal). */
export function initialBuilder(isSub: boolean, parentStages: ParentStage[] = []): Builder {
  if (isSub) {
    const target = parentStages.find((s) => s.reserved.length) ?? parentStages[parentStages.length - 1];
    return { stages: [newStage("Repescagem", "round", { outs: [newOut({ source: "winners", posFrom: 1, posTo: 2, target: "parent_tournament", parentStage: target?.position ?? 2 })] })] };
  }
  // Combina com o padrão de 8 jogadores do formulário; os exemplos prontos trazem formatos maiores.
  return {
    stages: [
      newStage("Rodada inicial", "round", { outs: [newOut({ source: "winners", posFrom: 1, posTo: 4, toStage: 2 })] }),
      newStage("Mata-mata", "knockout", { seeding: "random" }),
    ],
  };
}

// ---------- fluxo -> regras de passagem ----------
interface Rule {
  key: number; fromStage: number; source: Source; posFrom: number; posTo: number; target: Target | "eliminated";
  toStage: number; toSlotFrom: number; parentStage: number; fixedCrossing: boolean;
}
interface Plan { sizes: number[]; reserved: ([number, number] | null)[]; rules: Rule[]; counts: Map<number, number> }

// round() do Python arredonda .5 para o par (2.5 -> 2); o servidor usa isso para sugerir o nº de grupos.
function pyRound(x: number) {
  const f = Math.floor(x);
  return Math.abs(x - f - 0.5) < 1e-9 ? (f % 2 === 0 ? f : f + 1) : Math.round(x);
}
const defaultGroups = (n: number) => Math.max(2, pyRound(n / 4));
export const groupsOf = (s: Pick<FStage, "groupsCount">, size: number) => Number(s.groupsCount) || defaultGroups(Math.max(size, 4));

function plan(b: Builder, maxPlayers: number, parentStages: ParentStage[]): Plan {
  const next = new Map<number, number>(); // próxima vaga livre de cada fase de destino
  const parentNext = new Map<number, number>();
  const sizes: number[] = [];
  const reserved: ([number, number] | null)[] = [];
  const rules: Rule[] = [];
  const counts = new Map<number, number>();
  b.stages.forEach((st, i) => {
    const pos = i + 1;
    const filled = (next.get(pos) ?? 1) - 1;
    const res = pos > 1 && st.reserve > 0 ? ([filled + 1, filled + st.reserve] as [number, number]) : null;
    const size = pos === 1 ? maxPlayers : filled + (res ? st.reserve : 0);
    sizes.push(size);
    reserved.push(res);
    for (const o of st.outs) {
      const count = (o.posTo - o.posFrom + 1) * (o.source === "group_position" ? groupsOf(st, size) : 1);
      counts.set(o.key, Math.max(0, count));
      let toSlotFrom = 1;
      if (o.target === "stage") {
        toSlotFrom = next.get(o.toStage) ?? 1;
        next.set(o.toStage, toSlotFrom + Math.max(0, count));
      } else if (o.target === "parent_tournament") {
        const start = parentStages.find((p) => p.position === o.parentStage)?.reserved[0]?.[0] ?? 1;
        toSlotFrom = parentNext.get(o.parentStage) ?? start;
        parentNext.set(o.parentStage, toSlotFrom + Math.max(0, count));
      }
      rules.push({ key: o.key, fromStage: pos, source: o.source, posFrom: o.posFrom, posTo: o.posTo, target: o.target, toStage: o.toStage, toSlotFrom, parentStage: o.parentStage, fixedCrossing: o.fixedCrossing });
    }
  });
  return { sizes, reserved, rules, counts };
}

export function toPayload(b: Builder, maxPlayers: number, parentStages: ParentStage[] = []) {
  const p = plan(b, maxPlayers, parentStages);
  const stages = b.stages.map((s, i) => {
    const config: Record<string, unknown> = { best_of: s.bestOf || 1 };
    if (s.type === "league" || s.type === "groups") config.double_round = s.doubleRound;
    if (s.type === "groups" && s.groupsCount.trim()) config.groups_count = Number(s.groupsCount);
    if (s.type === "knockout") {
      config.third_place = s.thirdPlace;
      if (s.seeding) config.seeding = s.seeding;
    }
    if ((s.type === "round" || s.type === "playoff") && s.pairing === "seeded") config.pairing = "seeded";
    if (p.reserved[i]) config.external_slots = [p.reserved[i]];
    return { name: s.name.trim() || shortType[s.type], type: s.type, config };
  });
  // Quem não é citado é eliminado pelo servidor (a fase tem destinos adiante), então não há regras de eliminação.
  const rules = p.rules.map((r) => {
    const out: Record<string, unknown> = { from_stage: r.fromStage, source: r.source, pos_from: r.posFrom, pos_to: r.posTo, target: r.target, config: {} };
    if (r.target === "stage") Object.assign(out, { to_stage: r.toStage, to_slot_from: r.toSlotFrom });
    if (r.target === "parent_tournament") Object.assign(out, { parent_stage: r.parentStage, to_slot_from: r.toSlotFrom });
    if (r.source === "group_position" && r.target === "stage" && r.fixedCrossing && b.stages[r.toStage - 1]?.type === "knockout") {
      out.config = { fixed_crossing: true };
    }
    return out;
  });
  return { stages, rules };
}

// ---------- verificação ----------
export interface Analysis {
  sizes: number[];
  counts: Map<number, number>; // jogadores por destino (chave = out.key)
  slots: Map<number, [number, number]>; // vagas ocupadas por destino
  reserved: ([number, number] | null)[];
  leftover: number[]; // jogadores eliminados ao fim de cada fase (-1 = não dá para calcular)
  errors: string[];
}

const isPow2 = (n: number) => n >= 2 && (n & (n - 1)) === 0;

function checkRules(stages: FStage[], p: Plan, isSub: boolean): string[] {
  // Mesmas verificações de templates.validate_custom, aplicadas às regras geradas.
  const errors: string[] = [];
  const n = stages.length;
  const name = (pos: number) => `"${stages[pos - 1]?.name || shortType[stages[pos - 1]?.type ?? "knockout"]}"`;
  const slots = new Map<number, [number, number][]>();
  for (const r of p.rules) if (r.target === "stage") (slots.get(r.toStage) ?? slots.set(r.toStage, []).get(r.toStage)!).push([r.toSlotFrom, r.toSlotFrom + (p.counts.get(r.key) ?? 0) - 1]);
  for (let pos = 1; pos <= n; pos++) {
    const st = stages[pos - 1];
    const size = p.sizes[pos - 1];
    const label = `A fase ${pos} (${name(pos)})`;
    if (pos > 1 && !(slots.get(pos)?.length) && !p.reserved[pos - 1]) errors.push(`${label} não recebe ninguém: adicione um destino que mande jogadores para ela.`);
    if (st.type === "knockout" && size && !isPow2(size)) errors.push(`${label} é mata-mata e recebe ${size} jogadores; precisa ser 2, 4, 8, 16 ou 32 (sem byes).`);
    if ((st.type === "round" || st.type === "playoff") && size && (size < 2 || size % 2)) errors.push(`${label} recebe ${size} jogadores; precisa ser um número par.`);
    if (st.type === "groups" && size && size < 2 * groupsOf(st, size)) errors.push(`${label} tem ${size} jogadores para ${groupsOf(st, size)} grupos (mínimo de 2 por grupo).`);
    const used: Record<string, [number, number][]> = {};
    for (const r of p.rules.filter((x) => x.fromStage === pos)) {
      if (r.posTo < r.posFrom) errors.push(`Na fase ${pos}, um destino vai do ${r.posFrom}º ao ${r.posTo}º: o segundo número precisa ser maior ou igual ao primeiro.`);
      if (r.target === "stage" && r.toStage <= pos) errors.push(`Na fase ${pos}, um destino aponta para uma fase que não vem depois dela.`);
      if (r.target === "repechage" && isSub) errors.push("Um subtorneio não pode mandar jogadores para outra repescagem.");
      if ((r.source === "winners" || r.source === "losers") && st.type !== "round" && st.type !== "playoff") errors.push(`"Vencedores/perdedores" só existe em rodada única ou playoff (fase ${pos}).`);
      if (r.source === "group_position" && st.type !== "groups") errors.push(`"Colocados de cada grupo" só existe em fase de grupos (fase ${pos}).`);
      if (r.source === "ranking" && size && r.posTo > size) errors.push(`A fase ${pos} tem ${size} jogadores; um destino pede até o ${r.posTo}º.`);
      if ((r.source === "winners" || r.source === "losers") && size && r.posTo > size / 2) errors.push(`A fase ${pos} terá ${size / 2} ${r.source === "winners" ? "vencedores" : "perdedores"}; um destino pede até o ${r.posTo}º.`);
      if (r.source === "group_position") {
        const g = groupsOf(st, size);
        if (size && r.posTo > Math.floor(size / g)) errors.push(`Os grupos da fase ${pos} têm no mínimo ${Math.floor(size / g)} jogadores; um destino pede o ${r.posTo}º de cada grupo.`);
        if (r.fixedCrossing && r.target === "stage" && stages[r.toStage - 1]?.type === "knockout" && g % 2) errors.push(`O cruzamento fixo precisa de número par de grupos (a fase ${pos} tem ${g}).`);
      }
      for (const [a0, b0] of used[r.source] ?? []) if (!(r.posTo < a0 || r.posFrom > b0)) errors.push(`Na fase ${pos}, dois destinos pegam as mesmas posições.`);
      (used[r.source] ??= []).push([r.posFrom, r.posTo]);
    }
  }
  return errors;
}

export function analyze(b: Builder, maxPlayers: number, isSub: boolean, parentStages: ParentStage[] = []): Analysis {
  const p = plan(b, maxPlayers, parentStages);
  const errors = b.stages.length ? checkRules(b.stages, p, isSub) : ["Adicione ao menos uma fase."];
  const last = b.stages.length;
  b.stages.forEach((st, i) => {
    const forward = st.outs.some((o) => o.target !== "repechage");
    if (i + 1 < last && !forward) errors.push(`A fase ${i + 1} ("${st.name || shortType[st.type]}") não manda ninguém adiante: adicione um destino (ou remova as fases seguintes).`);
    if (isSub && i + 1 === last && !st.outs.some((o) => o.target === "parent_tournament")) errors.push("A última fase da repescagem precisa devolver jogadores ao torneio principal.");
  });
  if (isSub) {
    for (const r of p.rules.filter((x) => x.target === "parent_tournament")) {
      const ps = parentStages.find((x) => x.position === r.parentStage);
      const end = r.toSlotFrom + (p.counts.get(r.key) ?? 0) - 1;
      if (ps && !ps.reserved.some(([a, z]) => a <= r.toSlotFrom && end <= z)) {
        errors.push(ps.reserved.length
          ? `A fase "${ps.name}" do torneio principal reservou as vagas ${ps.reserved.map(([a, z]) => `${a}–${z}`).join(", ")}; a repescagem está devolvendo ${end - r.toSlotFrom + 1} jogador(es) a partir da vaga ${r.toSlotFrom}.`
          : `A fase "${ps.name}" do torneio principal não reservou vagas para a repescagem.`);
      }
    }
  }
  const slots = new Map<number, [number, number]>();
  for (const r of p.rules) if (r.target !== "repechage") slots.set(r.key, [r.toSlotFrom, r.toSlotFrom + (p.counts.get(r.key) ?? 0) - 1]);
  const leftover = b.stages.map((st, i) => {
    if (!st.outs.length || st.outs.some((o) => o.source === "group_position")) return -1;
    return Math.max(0, p.sizes[i] - st.outs.reduce((acc, o) => acc + (p.counts.get(o.key) ?? 0), 0));
  });
  return { sizes: p.sizes, counts: p.counts, slots, reserved: p.reserved, leftover, errors: [...new Set(errors)] };
}

// ---------- textos de ajuda ----------
const sourcesFor: Record<SType, Source[]> = {
  round: ["winners", "losers"],
  playoff: ["winners", "losers"],
  groups: ["group_position", "ranking"],
  league: ["ranking"],
  knockout: ["ranking"],
};
const sourceLabel = (s: Source, t: SType): string =>
  ({
    winners: "Vencedores",
    losers: "Perdedores",
    group_position: "Colocados de cada grupo",
    ranking: t === "groups" ? "Melhores no geral (todos os grupos)" : t === "knockout" ? "Classificação final (campeão, vice…)" : "Classificação",
  })[s];
const sourceHint: Record<Source, string> = {
  winners: "na ordem do saldo de Pokémon (quem venceu com mais Pokémon vivos vem primeiro; empate de saldo é sorteado)",
  losers: "na ordem do menor prejuízo de saldo (quem perdeu por menos vem primeiro)",
  group_position: "o mesmo colocado de cada grupo",
  ranking: "na ordem da classificação",
};
const plural = (n: number, s: string, p: string) => `${n} ${n === 1 ? s : p}`;

// ---------- componente ----------
interface Props {
  value: Builder;
  onChange: (b: Builder) => void;
  maxPlayers: number;
  onMaxPlayers: (n: number) => void;
  isSub: boolean;
  parentStages: ParentStage[];
  analysis: Analysis;
}

export default function CustomBuilder({ value: b, onChange, maxPlayers, onMaxPlayers, isSub, parentStages, analysis: a }: Props) {
  const [note, setNote] = useState<string | null>(null);
  const setStages = (stages: FStage[]) => onChange({ stages });
  const setStage = (i: number, patch: Partial<FStage>) => setStages(b.stages.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const setOut = (i: number, key: number, patch: Partial<Out>) => setStage(i, { outs: b.stages[i].outs.map((o) => (o.key === key ? { ...o, ...patch } : o)) });
  const usesSub = !isSub && b.stages.some((s) => s.outs.some((o) => o.target === "repechage"));

  const changeType = (i: number, type: SType) =>
    setStage(i, { type, outs: b.stages[i].outs.map((o) => (sourcesFor[type].includes(o.source) ? o : { ...o, source: sourcesFor[type][0] })) });

  const remap = (stages: FStage[], map: (pos: number) => number | null) =>
    stages.map((s) => ({ ...s, outs: s.outs.flatMap((o) => (o.target !== "stage" ? [o] : map(o.toStage) === null ? [] : [{ ...o, toStage: map(o.toStage)! }])) }));

  const addStage = () => {
    if (b.stages.length >= 12) return setNote("O torneio pode ter no máximo 12 fases.");
    setNote(null);
    setStages([...b.stages, newStage(`Fase ${b.stages.length + 1}`, "knockout")]);
  };
  const removeStage = (i: number) => {
    if (b.stages.length === 1) return setNote("O torneio precisa de ao menos uma fase; troque o tipo dela em vez de remover.");
    setNote(null);
    const pos = i + 1;
    setStages(remap(b.stages.filter((_, j) => j !== i), (p) => (p === pos ? null : p > pos ? p - 1 : p)));
  };
  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    const stages = [...b.stages];
    [stages[i], stages[j]] = [stages[j], stages[i]];
    setStages(remap(stages, (p) => (p === i + 1 ? j + 1 : p === j + 1 ? i + 1 : p)));
  };
  const addOut = (i: number) => {
    const st = b.stages[i];
    const source = sourcesFor[st.type][0];
    const taken = st.outs.filter((o) => o.source === source).map((o) => o.posTo);
    const start = taken.length ? Math.max(...taken) + 1 : 1;
    const parent = parentStages.find((p) => p.reserved.length);
    const target: Target = isSub && i + 1 === b.stages.length ? "parent_tournament" : "stage";
    setStage(i, { outs: [...st.outs, newOut({ source, posFrom: start, posTo: start, target, toStage: Math.min(i + 2, b.stages.length), parentStage: parent?.position ?? 1 })] });
  };
  const applyExample = (ex: Example) => {
    onChange(ex.build());
    onMaxPlayers(ex.players);
    setNote(`Exemplo aplicado (${ex.players} jogadores). Ajuste à vontade.`);
  };
  const num = (v: string) => Math.max(1, Math.floor(Number(v) || 1));

  return (
    <div>
      {!isSub && (
        <div className="field">
          <label>Começar de um exemplo</label>
          <select value="" onChange={(e) => e.target.value !== "" && applyExample(examples[Number(e.target.value)])}>
            <option value="">Escolha um formato para preencher…</option>
            {examples.map((ex, k) => <option key={ex.title} value={k}>{ex.title}</option>)}
          </select>
        </div>
      )}
      <p className="muted small">
        As fases acontecem em ordem. A primeira recebe todos os {maxPlayers} inscritos. Em cada fase, diga para onde vão os jogadores quando ela
        termina; quem não for enviado a lugar nenhum é eliminado.
      </p>
      {note && <div className="alert warn">{note}</div>}

      {b.stages.map((s, i) => {
        const pos = i + 1;
        const size = a.sizes[i] ?? 0;
        const g = s.type === "groups" ? groupsOf(s, size) : 0;
        const isLast = pos === b.stages.length;
        const destinations = b.stages.map((d, j) => ({ d, p: j + 1 })).filter((x) => x.p > pos);
        return (
          <div className="card flat" key={s.key}>
            <div className="row between">
              <strong>Fase {pos} · {s.name || shortType[s.type]}{size ? <span className="muted small"> — recebe {plural(size, "jogador", "jogadores")}{g ? ` em ${g} grupos` : ""}</span> : null}</strong>
              <div className="row">
                {i > 0 && <button type="button" className="btn small ghost" onClick={() => move(i, -1)} title="Mover para cima">↑</button>}
                {!isLast && <button type="button" className="btn small ghost" onClick={() => move(i, 1)} title="Mover para baixo">↓</button>}
                <button type="button" className="btn small danger" onClick={() => removeStage(i)}>Remover fase</button>
              </div>
            </div>
            <div className="form-grid">
              <div className="field"><label>Nome</label><input value={s.name} onChange={(e) => setStage(i, { name: e.target.value })} maxLength={80} /></div>
              <div className="field"><label>Tipo</label>
                <select value={s.type} onChange={(e) => changeType(i, e.target.value as SType)}>
                  {(Object.keys(typeLabel) as SType[]).map((t) => <option key={t} value={t}>{typeLabel[t]}</option>)}
                </select>
              </div>
              <div className="field"><label>Melhor de</label>
                <select value={s.bestOf} onChange={(e) => setStage(i, { bestOf: Number(e.target.value) })}>{[1, 3, 5, 7].map((n) => <option key={n} value={n}>{n}</option>)}</select>
              </div>
              {s.type === "groups" && (
                <div className="field"><label>Nº de grupos</label><input type="number" min={2} max={32} value={s.groupsCount} onChange={(e) => setStage(i, { groupsCount: e.target.value })} placeholder={`automático (${groupsOf({ groupsCount: "" }, size || maxPlayers)})`} /></div>
              )}
              {s.type === "knockout" && (
                <div className="field"><label>Montagem da chave</label>
                  <select value={s.seeding} onChange={(e) => setStage(i, { seeding: e.target.value as FStage["seeding"] })}>
                    <option value="">Automática</option>
                    <option value="random">Por sorteio</option>
                    <option value="standard">Por posição (o melhor enfrenta o pior)</option>
                    <option value="sequential">Na ordem das vagas (1×2, 3×4…)</option>
                  </select>
                </div>
              )}
              {(s.type === "round" || s.type === "playoff") && i > 0 && (
                <div className="field"><label>Pares</label>
                  <select value={s.pairing} onChange={(e) => setStage(i, { pairing: e.target.value as FStage["pairing"] })}>
                    <option value="random">Sorteados</option>
                    <option value="seeded">Melhor × pior</option>
                  </select>
                </div>
              )}
            </div>
            {(s.type === "league" || s.type === "groups") && (
              <div className="field inline"><input id={`dr${s.key}`} type="checkbox" checked={s.doubleRound} onChange={(e) => setStage(i, { doubleRound: e.target.checked })} /><label htmlFor={`dr${s.key}`}>Turno e returno</label></div>
            )}
            {s.type === "knockout" && (
              <div className="field inline"><input id={`tp${s.key}`} type="checkbox" checked={s.thirdPlace} onChange={(e) => setStage(i, { thirdPlace: e.target.checked })} /><label htmlFor={`tp${s.key}`}>Disputa de 3º lugar</label></div>
            )}
            {s.type === "knockout" && s.seeding === "standard" && (
              <p className="muted small" style={{ marginTop: 0 }}>A posição de cada um segue a ordem dos destinos que mandam jogadores para esta fase (o primeiro destino = os melhores).</p>
            )}
            {i > 0 && (usesSub || s.reserve > 0) && (
              <div className="field" style={{ maxWidth: 420 }}>
                <label>Vagas para quem volta do torneio de repescagem separado</label>
                <input type="number" min={0} max={64} value={s.reserve} onChange={(e) => setStage(i, { reserve: Math.max(0, Math.floor(Number(e.target.value) || 0)) })} />
                {a.reserved[i] && <p className="muted small" style={{ margin: ".3rem 0 0" }}>Ficam no fim desta fase: vagas {a.reserved[i]![0]} a {a.reserved[i]![1]}. Ao criar o subtorneio, ele devolve os vencedores para elas.</p>}
              </div>
            )}

            <div style={{ marginTop: ".4rem" }}>
              <strong className="small">Depois desta fase:</strong>
              {s.outs.length === 0 && (
                <p className="muted small" style={{ margin: ".3rem 0" }}>
                  {isLast
                    ? s.type === "knockout" ? "É a última fase: o vencedor do mata-mata é o campeão." : "É a última fase: o primeiro da classificação é o campeão."
                    : "Ninguém segue adiante ainda. Adicione um destino."}
                </p>
              )}
              {s.outs.map((o) => {
                const count = a.counts.get(o.key) ?? 0;
                const sl = a.slots.get(o.key);
                const dest = o.target === "stage" ? b.stages[o.toStage - 1] : null;
                const value = o.target === "stage" ? `s${o.toStage}` : o.target === "repechage" ? "rep" : `p${o.parentStage}`;
                return (
                  <div key={o.key} style={{ borderLeft: "3px solid var(--line)", paddingLeft: ".6rem", margin: ".5rem 0" }}>
                    <div className="row">
                      <select value={o.source} onChange={(e) => setOut(i, o.key, { source: e.target.value as Source })} aria-label="Quem">
                        {sourcesFor[s.type].map((src) => <option key={src} value={src}>{sourceLabel(src, s.type)}</option>)}
                      </select>
                      <span>do</span>
                      <input type="number" min={1} value={o.posFrom} onChange={(e) => setOut(i, o.key, { posFrom: num(e.target.value) })} style={{ width: "4.5rem" }} aria-label="Da posição" />
                      <span>º ao</span>
                      <input type="number" min={1} value={o.posTo} onChange={(e) => setOut(i, o.key, { posTo: num(e.target.value) })} style={{ width: "4.5rem" }} aria-label="Até a posição" />
                      <span>º →</span>
                      <select value={value} aria-label="Vão para" onChange={(e) => {
                        const v = e.target.value;
                        if (v === "rep") setOut(i, o.key, { target: "repechage" });
                        else if (v.startsWith("p")) setOut(i, o.key, { target: "parent_tournament", parentStage: Number(v.slice(1)) });
                        else setOut(i, o.key, { target: "stage", toStage: Number(v.slice(1)) });
                      }}>
                        {destinations.map(({ d, p }) => <option key={d.key} value={`s${p}`}>Fase {p}: {d.name || shortType[d.type]}</option>)}
                        {isSub && parentStages.map((p) => <option key={p.position} value={`p${p.position}`}>Volta ao torneio principal: {p.name}</option>)}
                        {!isSub && <option value="rep">Torneio de repescagem separado (subtorneio)</option>}
                        {destinations.length === 0 && !isSub && o.target === "stage" && <option value={value}>(adicione uma fase depois desta)</option>}
                      </select>
                      <button type="button" className="btn small ghost" onClick={() => setStage(i, { outs: s.outs.filter((x) => x.key !== o.key) })} title="Remover destino">✕</button>
                    </div>
                    <p className="muted small" style={{ margin: ".25rem 0 0" }}>
                      {plural(count, "jogador", "jogadores")}{o.source === "group_position" && g ? ` (${o.posTo - o.posFrom + 1} de cada um dos ${g} grupos)` : ""}, {sourceHint[o.source]}.
                      {o.target === "stage" && dest && sl && count > 0 && ` Ocupam ${sl[0] === sl[1] ? `a vaga ${sl[0]}` : `as vagas ${sl[0]} a ${sl[1]}`} de "${dest.name || shortType[dest.type]}".`}
                      {o.target === "parent_tournament" && sl && count > 0 && ` Voltam para ${sl[0] === sl[1] ? `a vaga ${sl[0]}` : `as vagas ${sl[0]} a ${sl[1]}`} do torneio principal.`}
                      {o.target === "repechage" && " Eles saem deste torneio e entram no subtorneio de repescagem (crie-o depois, na aba Gerenciar)."}
                    </p>
                    {o.source === "group_position" && dest?.type === "knockout" && (
                      <div className="field inline" style={{ margin: ".3rem 0 0" }}><input id={`fx${o.key}`} type="checkbox" checked={o.fixedCrossing} onChange={(e) => setOut(i, o.key, { fixedCrossing: e.target.checked })} /><label htmlFor={`fx${o.key}`}>Cruzamento fixo entre grupos (1ºA × 2ºB, 1ºB × 2ºA…)</label></div>
                    )}
                  </div>
                );
              })}
              {(s.outs.length > 0 || !isLast || isSub) && (
                <button type="button" className="btn small" onClick={() => addOut(i)}>+ Adicionar destino</button>
              )}
              {s.outs.length > 0 && (
                <p className="muted small" style={{ margin: ".4rem 0 0" }}>
                  {a.leftover[i] > 0 ? `Os demais (${plural(a.leftover[i], "jogador", "jogadores")}) são eliminados.` : a.leftover[i] === 0 ? "Ninguém é eliminado nesta fase." : "Os demais são eliminados."}
                </p>
              )}
            </div>
          </div>
        );
      })}
      <button type="button" className="btn" onClick={addStage}>+ Adicionar fase</button>

      <h3 style={{ marginTop: "1.2rem" }}>Resumo</h3>
      {a.errors.length ? (
        <div className="alert warn">
          <strong>Ajuste antes de criar:</strong>
          <ul style={{ margin: ".4rem 0 0", paddingLeft: "1.2rem" }}>{a.errors.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      ) : (
        <div className="alert ok">
          {b.stages.map((s, i) => (
            <div key={s.key}>
              <strong>{s.name || shortType[s.type]}</strong> ({plural(a.sizes[i], "jogador", "jogadores")})
              {s.outs.length > 0 && ": "}
              {s.outs.map((o) => {
                const who = { winners: "vencedores", losers: "perdedores", group_position: "classificados", ranking: "melhores" }[o.source];
                const to = o.target === "stage" ? b.stages[o.toStage - 1]?.name || "?" : o.target === "repechage" ? "repescagem separada" : "torneio principal";
                return `${a.counts.get(o.key)} ${who} → ${to}`;
              }).join(" · ")}
              {a.leftover[i] > 0 && ` · ${a.leftover[i]} eliminados`}
            </div>
          ))}
          <div className="small" style={{ marginTop: ".3rem" }}>Estrutura válida. O servidor confere tudo de novo ao criar.</div>
        </div>
      )}
    </div>
  );
}
