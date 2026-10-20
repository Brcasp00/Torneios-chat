// Editor visual do torneio personalizado: fases + regras de passagem, sem JSON na tela.
// O que o usuário preenche é convertido no formato que a API espera (`toPayload`), e `analyze` repete no navegador as
// mesmas verificações que o servidor faz (templates.validate_custom), para mostrar os problemas antes de salvar.
import { useState } from "react";
import { stageType } from "../labels";

export type SType = "round" | "league" | "groups" | "knockout" | "playoff";
export type Source = "ranking" | "group_position" | "winners" | "losers";
export type Target = "stage" | "eliminated" | "repechage" | "parent_tournament";

export interface BStage {
  key: number;
  name: string;
  type: SType;
  bestOf: number;
  doubleRound: boolean;
  groupsCount: string; // vazio = automático
  thirdPlace: boolean;
  seeding: "" | "standard" | "sequential";
  pairing: "random" | "seeded";
  reservedFrom: string; // vagas reservadas a quem volta da repescagem (vazio = nenhuma)
  reservedTo: string;
}

export interface BRule {
  key: number;
  fromStage: number; // posição da fase (1 = primeira)
  source: Source;
  posFrom: number;
  posTo: number;
  target: Target;
  toStage: number;
  toSlotFrom: number;
  parentStage: number; // subtorneio: posição da fase do torneio principal
  fixedCrossing: boolean;
}

export interface Builder { stages: BStage[]; rules: BRule[] }
export interface ParentStage { position: number; name: string; reserved: [number, number][] }

let seq = 1;
const nextKey = () => seq++;

export function newStage(name: string, type: SType): BStage {
  return { key: nextKey(), name, type, bestOf: 1, doubleRound: false, groupsCount: "", thirdPlace: false, seeding: "", pairing: "random", reservedFrom: "", reservedTo: "" };
}

export function newRule(fromStage: number, patch: Partial<BRule> = {}): BRule {
  return { key: nextKey(), fromStage, source: "ranking", posFrom: 1, posTo: 1, target: "eliminated", toStage: fromStage + 1, toSlotFrom: 1, parentStage: 1, fixedCrossing: true, ...patch };
}

/** Exemplo inicial: rodada única cujos vencedores vão ao mata-mata (ou, no subtorneio, um mata-mata que devolve 2). */
export function initialBuilder(isSub: boolean, parentStages: ParentStage[] = []): Builder {
  if (isSub) {
    const target = parentStages.find((s) => s.reserved.length) ?? parentStages[parentStages.length - 1];
    return {
      stages: [newStage("Mata-mata da repescagem", "knockout")],
      rules: [newRule(1, { posFrom: 1, posTo: 2, target: "parent_tournament", parentStage: target?.position ?? 2, toSlotFrom: target?.reserved[0]?.[0] ?? 1 })],
    };
  }
  return {
    stages: [newStage("Rodada inicial", "round"), { ...newStage("Mata-mata", "knockout"), seeding: "standard" }],
    rules: [
      newRule(1, { source: "winners", posFrom: 1, posTo: 4, target: "stage", toStage: 2, toSlotFrom: 1 }),
      newRule(1, { source: "losers", posFrom: 1, posTo: 4, target: "eliminated" }),
    ],
  };
}

// ---------- conversão para a API ----------
export function toPayload(b: Builder, defaultBestOf: number) {
  const stages = b.stages.map((s) => {
    const config: Record<string, unknown> = { best_of: s.bestOf || defaultBestOf };
    if (s.type === "league" || s.type === "groups") config.double_round = s.doubleRound;
    if (s.type === "groups" && s.groupsCount.trim()) config.groups_count = Number(s.groupsCount);
    if (s.type === "knockout") {
      config.third_place = s.thirdPlace;
      if (s.seeding) config.seeding = s.seeding;
    }
    if ((s.type === "round" || s.type === "playoff") && s.pairing === "seeded") config.pairing = "seeded";
    const range = reserved(s);
    if (range) config.external_slots = [range];
    return { name: s.name.trim() || stageType[s.type], type: s.type, config };
  });
  const rules = b.rules.map((r) => {
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

function reserved(s: BStage): [number, number] | null {
  if (!s.reservedFrom.trim() || !s.reservedTo.trim()) return null;
  return [Number(s.reservedFrom), Number(s.reservedTo)];
}

// ---------- verificação (mesmas regras do servidor) ----------
const isPow2 = (n: number) => n >= 2 && (n & (n - 1)) === 0;
// round() do Python arredonda .5 para o par (2.5 -> 2); o servidor usa isso para sugerir o nº de grupos.
function pyRound(x: number) {
  const f = Math.floor(x);
  return Math.abs(x - f - 0.5) < 1e-9 ? (f % 2 === 0 ? f : f + 1) : Math.round(x);
}
const defaultGroups = (n: number) => Math.max(2, pyRound(n / 4));
export const groupsOf = (s: BStage, size: number) => Number(s.groupsCount) || defaultGroups(Math.max(size, 4));

export interface Analysis {
  sizes: number[]; // jogadores que chegam a cada fase (índice = posição - 1)
  counts: Map<number, number>; // jogadores movidos por regra (chave = rule.key)
  errors: string[];
}

export function analyze(b: Builder, maxPlayers: number, isSub: boolean): Analysis {
  const errors: string[] = [];
  const n = b.stages.length;
  const sizes: number[] = [];
  const counts = new Map<number, number>();
  if (!n) return { sizes, counts, errors: ["Adicione ao menos uma fase."] };
  for (const r of b.rules) {
    if (r.posTo < r.posFrom) errors.push(`Uma regra da fase ${r.fromStage} vai da posição ${r.posFrom} até a ${r.posTo}: a final precisa ser maior ou igual à inicial.`);
    if (r.target === "stage" && r.toStage <= r.fromStage) errors.push(`Uma regra da fase ${r.fromStage} manda jogadores para a fase ${r.toStage}: o destino precisa vir depois da origem.`);
  }
  const slots = new Map<number, [number, number][]>();
  for (let pos = 1; pos <= n; pos++) {
    const st = b.stages[pos - 1];
    const label = `A fase ${pos} ("${st.name || stageType[st.type]}")`;
    let size = pos === 1 ? maxPlayers : 0;
    const res = reserved(st);
    if (pos === 1 && res) errors.push(`${label} é a primeira: ela recebe todos os inscritos e não pode reservar vagas para a repescagem.`);
    if (res && (res[0] < 1 || res[1] < res[0])) errors.push(`${label} tem as vagas reservadas invertidas (de ${res[0]} até ${res[1]}).`);
    if (pos > 1) {
      const ranges = [...(slots.get(pos) ?? []), ...(res ? [res] : [])].sort((a, z) => a[0] - z[0]);
      if (!ranges.length) {
        errors.push(`${label} não recebe jogadores de nenhuma regra.`);
      } else {
        let expected = 1;
        for (const [a, z] of ranges) {
          if (a !== expected) {
            errors.push(a > expected
              ? `${label}: as vagas precisam ser contínuas a partir de 1, mas a vaga ${expected} ficou vazia.`
              : `${label}: duas regras ocupam a vaga ${a}.`);
            break;
          }
          expected = z + 1;
        }
        size = Math.max(...ranges.map((r) => r[1]));
      }
    }
    sizes.push(size);
    if (st.type === "knockout" && size && !isPow2(size)) errors.push(`${label} é mata-mata e recebe ${size} jogadores; precisa ser 2, 4, 8, 16, 32...`);
    if ((st.type === "round" || st.type === "playoff") && size && (size < 2 || size % 2)) errors.push(`${label} recebe ${size} jogadores; precisa ser um número par.`);
    if (st.type === "groups" && size) {
      const g = groupsOf(st, size);
      if (size < 2 * g) errors.push(`${label} tem ${size} jogadores para ${g} grupos (mínimo de 2 por grupo).`);
    }
    const used: Record<string, [number, number][]> = {};
    for (const r of b.rules.filter((x) => x.fromStage === pos)) {
      if (r.target === "parent_tournament" && !isSub) errors.push("A volta ao torneio principal só existe em subtorneios.");
      if (r.target === "repechage" && isSub) errors.push("Um subtorneio não pode mandar jogadores para outra repescagem.");
      if (r.source === "group_position" && st.type !== "groups") errors.push(`"Posição em cada grupo" só vale para fase de grupos (fase ${pos}).`);
      if ((r.source === "winners" || r.source === "losers") && st.type !== "round" && st.type !== "playoff") errors.push(`"Vencedores/perdedores" só vale para rodada única ou playoff (fase ${pos}); use "classificação".`);
      if (r.source === "ranking" && size && r.posTo > size) errors.push(`A fase ${pos} só tem ${size} jogadores; uma regra pede até a ${r.posTo}ª posição.`);
      if ((r.source === "winners" || r.source === "losers") && size && r.posTo > size / 2) errors.push(`A fase ${pos} tem ${size / 2} vencedores e ${size / 2} perdedores; uma regra pede até o ${r.posTo}º.`);
      let count = r.posTo - r.posFrom + 1;
      if (r.source === "group_position") {
        const g = groupsOf(st, size);
        if (size && r.posTo > Math.floor(size / g)) errors.push(`Os grupos da fase ${pos} têm no mínimo ${Math.floor(size / g)} jogadores; uma regra pede a ${r.posTo}ª posição.`);
        if (r.fixedCrossing && r.target === "stage" && b.stages[r.toStage - 1]?.type === "knockout" && g % 2) errors.push(`Cruzamento fixo exige número par de grupos (a fase ${pos} tem ${g}).`);
        count *= g;
      }
      counts.set(r.key, count);
      for (const [a0, b0] of used[r.source] ?? []) {
        if (!(r.posTo < a0 || r.posFrom > b0)) errors.push(`Duas regras da fase ${pos} pegam as mesmas posições.`);
      }
      (used[r.source] ??= []).push([r.posFrom, r.posTo]);
      if (r.target === "stage") {
        if (!slots.has(r.toStage)) slots.set(r.toStage, []);
        slots.get(r.toStage)!.push([r.toSlotFrom, r.toSlotFrom + count - 1]);
      }
    }
  }
  return { sizes, counts, errors: [...new Set(errors)] };
}

// ---------- textos ----------
const sourceOptions: Record<SType, Source[]> = {
  round: ["winners", "losers", "ranking"],
  playoff: ["winners", "losers", "ranking"],
  groups: ["group_position", "ranking"],
  league: ["ranking"],
  knockout: ["ranking"],
};
const sourceLabel: Record<Source, string> = {
  ranking: "Classificação final",
  group_position: "Posição em cada grupo",
  winners: "Vencedores (por saldo)",
  losers: "Perdedores (menor prejuízo)",
};

function describe(r: BRule, b: Builder, count: number | undefined, parentStages: ParentStage[]): string {
  const range = r.posFrom === r.posTo ? `o ${r.posFrom}º` : `do ${r.posFrom}º ao ${r.posTo}º`;
  const who = {
    ranking: `${range} colocado${r.posFrom === r.posTo ? "" : "s"} da classificação`,
    group_position: `${range} de cada grupo`,
    winners: `${range} melhor${r.posFrom === r.posTo ? "" : "es"} vencedor${r.posFrom === r.posTo ? "" : "es"}`,
    losers: `${range} melhor${r.posFrom === r.posTo ? "" : "es"} perdedor${r.posFrom === r.posTo ? "" : "es"}`,
  }[r.source];
  const n = count ? ` (${count} jogador${count === 1 ? "" : "es"})` : "";
  const end = count ? r.toSlotFrom + count - 1 : r.toSlotFrom;
  const slots = end > r.toSlotFrom ? `vagas ${r.toSlotFrom} a ${end}` : `vaga ${r.toSlotFrom}`;
  const dest = {
    stage: `vão para a fase ${r.toStage} ("${b.stages[r.toStage - 1]?.name || "?"}"), ${slots}`,
    eliminated: "são eliminados",
    repechage: "vão para a repescagem (subtorneio)",
    parent_tournament: `voltam ao torneio principal, fase "${parentStages.find((p) => p.position === r.parentStage)?.name ?? r.parentStage}", ${slots}`,
  }[r.target];
  return `Da fase ${r.fromStage}: ${who}${n} ${dest}.`;
}

// ---------- componente ----------
interface Props {
  value: Builder;
  onChange: (b: Builder) => void;
  maxPlayers: number;
  isSub: boolean;
  parentStages: ParentStage[];
  analysis: Analysis;
}

export default function CustomBuilder({ value: b, onChange, maxPlayers, isSub, parentStages, analysis }: Props) {
  const setStage = (i: number, patch: Partial<BStage>) => onChange({ ...b, stages: b.stages.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  const setRule = (key: number, patch: Partial<BRule>) => onChange({ ...b, rules: b.rules.map((r) => (r.key === key ? { ...r, ...patch } : r)) });

  const changeType = (i: number, type: SType) => {
    // Fontes que não servem para o novo tipo voltam para "classificação".
    const pos = i + 1;
    const rules = b.rules.map((r) => (r.fromStage === pos && !sourceOptions[type].includes(r.source) ? { ...r, source: sourceOptions[type][0] } : r));
    onChange({ stages: b.stages.map((s, j) => (j === i ? { ...s, type } : s)), rules });
  };

  const [note, setNote] = useState<{ at: "stage" | "rule"; text: string } | null>(null);

  const addStage = () => {
    if (b.stages.length >= 12) return setNote({ at: "stage", text: "O torneio pode ter no máximo 12 fases." });
    setNote(null);
    onChange({ ...b, stages: [...b.stages, newStage(`Fase ${b.stages.length + 1}`, "knockout")] });
  };

  const removeStage = (i: number) => {
    if (b.stages.length === 1) return setNote({ at: "stage", text: "O torneio precisa de ao menos uma fase; troque o tipo dela em vez de remover." });
    setNote(null);
    const pos = i + 1;
    const rules = b.rules
      .filter((r) => r.fromStage !== pos && !(r.target === "stage" && r.toStage === pos))
      .map((r) => ({ ...r, fromStage: r.fromStage > pos ? r.fromStage - 1 : r.fromStage, toStage: r.toStage > pos ? r.toStage - 1 : r.toStage }));
    onChange({ stages: b.stages.filter((_, j) => j !== i), rules });
  };

  const move = (i: number, dir: -1 | 1) => {
    const j = i + dir;
    if (j < 0 || j >= b.stages.length) return;
    const stages = [...b.stages];
    [stages[i], stages[j]] = [stages[j], stages[i]];
    const map = (p: number) => (p === i + 1 ? j + 1 : p === j + 1 ? i + 1 : p);
    onChange({ stages, rules: b.rules.map((r) => ({ ...r, fromStage: map(r.fromStage), toStage: map(r.toStage) })) });
  };

  const addRule = () => {
    if (b.rules.length >= 60) return setNote({ at: "rule", text: "O torneio pode ter no máximo 60 regras de passagem." });
    setNote(null);
    const from = 1;
    const st = b.stages[0];
    const target: Target = isSub ? "parent_tournament" : b.stages.length > 1 ? "stage" : "eliminated";
    // Sugere a primeira vaga livre da fase seguinte.
    const taken = b.rules.filter((r) => r.target === "stage" && r.toStage === 2).map((r) => r.toSlotFrom + (analysis.counts.get(r.key) ?? 1) - 1);
    const parent = parentStages.find((s) => s.reserved.length);
    onChange({
      ...b,
      rules: [...b.rules, newRule(from, {
        source: st ? sourceOptions[st.type][0] : "ranking",
        target,
        toStage: 2,
        toSlotFrom: taken.length ? Math.max(...taken) + 1 : 1,
        parentStage: parent?.position ?? 1,
        ...(isSub && parent ? { toSlotFrom: parent.reserved[0][0] } : {}),
      })],
    });
  };

  const num = (v: string, min = 1) => Math.max(min, Math.floor(Number(v) || min));

  return (
    <div>
      <h3>Fases</h3>
      <p className="muted small">As fases acontecem em ordem. A primeira recebe todos os {maxPlayers} inscritos; as seguintes recebem os jogadores enviados pelas regras de passagem.</p>
      {b.stages.map((s, i) => {
        const size = analysis.sizes[i] ?? 0;
        const g = s.type === "groups" ? groupsOf(s, size) : 0;
        return (
          <div className="card flat" key={s.key}>
            <div className="row between">
              <strong>Fase {i + 1}{size ? <span className="muted small"> — recebe {size} jogador{size === 1 ? "" : "es"}{g ? ` (${g} grupos)` : ""}</span> : null}</strong>
              <div className="row">
                {i > 0 && <button type="button" className="btn small ghost" onClick={() => move(i, -1)} title="Mover para cima">↑</button>}
                {i < b.stages.length - 1 && <button type="button" className="btn small ghost" onClick={() => move(i, 1)} title="Mover para baixo">↓</button>}
                <button type="button" className="btn small danger" onClick={() => removeStage(i)}>Remover</button>
              </div>
            </div>
            <div className="form-grid">
              <div className="field"><label>Nome</label><input value={s.name} onChange={(e) => setStage(i, { name: e.target.value })} maxLength={80} /></div>
              <div className="field"><label>Tipo</label>
                <select value={s.type} onChange={(e) => changeType(i, e.target.value as SType)}>
                  {(Object.keys(stageType) as SType[]).map((t) => <option key={t} value={t}>{stageType[t]}</option>)}
                </select>
              </div>
              <div className="field"><label>Melhor de</label>
                <select value={s.bestOf} onChange={(e) => setStage(i, { bestOf: Number(e.target.value) })}>{[1, 3, 5, 7].map((n) => <option key={n} value={n}>{n}</option>)}</select>
              </div>
              {s.type === "groups" && (
                <div className="field"><label>Nº de grupos</label><input type="number" min={2} max={32} value={s.groupsCount} onChange={(e) => setStage(i, { groupsCount: e.target.value })} placeholder={`automático (${groupsOf({ ...s, groupsCount: "" }, size || maxPlayers)})`} /></div>
              )}
              {s.type === "knockout" && (
                <div className="field"><label>Montagem da chave</label>
                  <select value={s.seeding} onChange={(e) => setStage(i, { seeding: e.target.value as BStage["seeding"] })}>
                    <option value="">Automática</option>
                    <option value="standard">Por posição: 1º × último, 2º × penúltimo…</option>
                    <option value="sequential">Na ordem das vagas (1×2, 3×4…)</option>
                  </select>
                </div>
              )}
              {(s.type === "round" || s.type === "playoff") && i > 0 && (
                <div className="field"><label>Pares</label>
                  <select value={s.pairing} onChange={(e) => setStage(i, { pairing: e.target.value as BStage["pairing"] })}>
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
            {i > 0 && !isSub && (
              <div className="form-grid">
                <div className="field"><label>Vagas para quem volta da repescagem: de</label><input type="number" min={1} value={s.reservedFrom} onChange={(e) => setStage(i, { reservedFrom: e.target.value })} placeholder="nenhuma" /></div>
                <div className="field"><label>até</label><input type="number" min={1} value={s.reservedTo} onChange={(e) => setStage(i, { reservedTo: e.target.value })} placeholder="nenhuma" /></div>
              </div>
            )}
          </div>
        );
      })}
      {note?.at === "stage" && <div className="alert warn">{note.text}</div>}
      <button type="button" className="btn" onClick={addStage}>+ Adicionar fase</button>

      <h3 style={{ marginTop: "1.2rem" }}>Regras de passagem</h3>
      <p className="muted small">Cada regra diz para onde vão os jogadores de uma fase quando ela termina. Quem não for enviado para outra fase deve ter uma regra de eliminação.</p>
      {b.rules.length === 0 && <p className="muted">Nenhuma regra ainda.</p>}
      {b.rules.map((r) => {
        const from = b.stages[r.fromStage - 1];
        const sources = from ? sourceOptions[from.type] : (["ranking"] as Source[]);
        const later = b.stages.map((s, j) => ({ s, pos: j + 1 })).filter((x) => x.pos > r.fromStage);
        const targets: Target[] = isSub ? ["parent_tournament", "stage", "eliminated"] : ["stage", "eliminated", "repechage"];
        const toKnockout = r.target === "stage" && b.stages[r.toStage - 1]?.type === "knockout";
        return (
          <div className="card flat" key={r.key}>
            <div className="form-grid">
              <div className="field"><label>Da fase</label>
                <select value={r.fromStage} onChange={(e) => {
                  const pos = Number(e.target.value);
                  const st = b.stages[pos - 1];
                  setRule(r.key, { fromStage: pos, source: st && !sourceOptions[st.type].includes(r.source) ? sourceOptions[st.type][0] : r.source, toStage: Math.max(r.toStage, pos + 1) });
                }}>
                  {b.stages.map((s, j) => <option key={s.key} value={j + 1}>{j + 1}. {s.name || stageType[s.type]}</option>)}
                </select>
              </div>
              <div className="field"><label>Quem</label>
                <select value={r.source} onChange={(e) => setRule(r.key, { source: e.target.value as Source })}>
                  {sources.map((src) => <option key={src} value={src}>{sourceLabel[src]}</option>)}
                </select>
              </div>
              <div className="field"><label>Da posição</label><input type="number" min={1} value={r.posFrom} onChange={(e) => setRule(r.key, { posFrom: num(e.target.value) })} /></div>
              <div className="field"><label>Até a posição</label><input type="number" min={1} value={r.posTo} onChange={(e) => setRule(r.key, { posTo: num(e.target.value) })} /></div>
              <div className="field"><label>Vão para</label>
                <select value={r.target} onChange={(e) => setRule(r.key, { target: e.target.value as Target })}>
                  {targets.map((t) => <option key={t} value={t}>{{ stage: "Outra fase", eliminated: "Eliminados", repechage: "Repescagem (subtorneio)", parent_tournament: "Torneio principal" }[t]}</option>)}
                </select>
              </div>
              {r.target === "stage" && (
                <div className="field"><label>Fase de destino</label>
                  <select value={r.toStage} onChange={(e) => setRule(r.key, { toStage: Number(e.target.value) })}>
                    {later.length === 0 && <option value={r.toStage}>(adicione uma fase depois desta)</option>}
                    {later.map(({ s, pos }) => <option key={s.key} value={pos}>{pos}. {s.name || stageType[s.type]}</option>)}
                  </select>
                </div>
              )}
              {r.target === "parent_tournament" && (
                <div className="field"><label>Fase do torneio principal</label>
                  <select value={r.parentStage} onChange={(e) => {
                    const p = parentStages.find((x) => x.position === Number(e.target.value));
                    setRule(r.key, { parentStage: Number(e.target.value), toSlotFrom: p?.reserved[0]?.[0] ?? r.toSlotFrom });
                  }}>
                    {parentStages.map((p) => <option key={p.position} value={p.position}>{p.position}. {p.name}{p.reserved.length ? ` (vagas reservadas ${p.reserved.map(([a, z]) => `${a}–${z}`).join(", ")})` : " (sem vagas reservadas)"}</option>)}
                  </select>
                </div>
              )}
              {(r.target === "stage" || r.target === "parent_tournament") && (
                <div className="field"><label>A partir da vaga</label><input type="number" min={1} value={r.toSlotFrom} onChange={(e) => setRule(r.key, { toSlotFrom: num(e.target.value) })} /></div>
              )}
            </div>
            {r.source === "group_position" && toKnockout && (
              <div className="field inline"><input id={`fx${r.key}`} type="checkbox" checked={r.fixedCrossing} onChange={(e) => setRule(r.key, { fixedCrossing: e.target.checked })} /><label htmlFor={`fx${r.key}`}>Cruzamento fixo entre grupos (1ºA × 2ºB, 1ºB × 2ºA…)</label></div>
            )}
            <div className="row between">
              <span className="small">{describe(r, b, analysis.counts.get(r.key), parentStages)}</span>
              <button type="button" className="btn small danger" onClick={() => onChange({ ...b, rules: b.rules.filter((x) => x.key !== r.key) })}>Remover</button>
            </div>
          </div>
        );
      })}
      {note?.at === "rule" && <div className="alert warn">{note.text}</div>}
      <button type="button" className="btn" onClick={addRule}>+ Adicionar regra</button>

      <h3 style={{ marginTop: "1.2rem" }}>Verificação</h3>
      {analysis.errors.length ? (
        <div className="alert warn">
          <strong>Ajuste antes de criar:</strong>
          <ul style={{ margin: ".4rem 0 0", paddingLeft: "1.2rem" }}>{analysis.errors.map((e) => <li key={e}>{e}</li>)}</ul>
        </div>
      ) : (
        <div className="alert ok">
          Estrutura válida: {b.stages.map((s, i) => `${s.name || stageType[s.type]} (${analysis.sizes[i]} jogadores)`).join(" → ")}.
          O servidor confere tudo de novo ao criar.
        </div>
      )}
    </div>
  );
}
