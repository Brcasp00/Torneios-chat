import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type TournamentDetail } from "../api";
import { useAction } from "../components/ui";
import { template } from "../labels";

const SAMPLE_MAIN = JSON.stringify(
  {
    stages: [
      { name: "Rodada inicial", type: "round" },
      { name: "Mata-mata", type: "knockout", config: { seeding: "standard" } },
    ],
    rules: [
      { from_stage: 1, source: "winners", pos_from: 1, pos_to: 4, target: "stage", to_stage: 2, to_slot_from: 1 },
      { from_stage: 1, source: "losers", pos_from: 1, pos_to: 4, target: "eliminated" },
    ],
  },
  null,
  2,
);

const SAMPLE_SUB = JSON.stringify(
  {
    stages: [{ name: "Mata-mata da repescagem", type: "knockout" }],
    rules: [{ from_stage: 1, source: "ranking", pos_from: 1, pos_to: 2, target: "parent_tournament", parent_stage: 2, to_slot_from: 3 }],
  },
  null,
  2,
);

export default function CreateTournament() {
  const [params] = useSearchParams();
  const parent = params.get("parent");
  const nav = useNavigate();
  const { run, busy, box } = useAction();

  const [name, setName] = useState("");
  const [tpl, setTpl] = useState(parent ? "custom" : "league");
  const [maxPlayers, setMaxPlayers] = useState("8");
  const [bestOf, setBestOf] = useState("1");
  const [doubleRound, setDoubleRound] = useState(false);
  const [third, setThird] = useState(false);
  const [allowDraw, setAllowDraw] = useState("");
  const [groups, setGroups] = useState("");
  const [qualifiers, setQualifiers] = useState("2");
  const [repPos, setRepPos] = useState("");
  const [repSlots, setRepSlots] = useState("0");
  const [custom, setCustom] = useState(parent ? SAMPLE_SUB : SAMPLE_MAIN);

  const [format, setFormat] = useState("");
  const [game, setGame] = useState("");
  const [tier, setTier] = useState("");
  const [teamSize, setTeamSize] = useState("");
  const [bring, setBring] = useState("");
  const [showdown, setShowdown] = useState(true);
  const [rulesText, setRulesText] = useState("");

  const num = (s: string) => (s.trim() === "" ? null : Number(s));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    await run(async () => {
      const body: Record<string, unknown> = {
        name,
        template: tpl,
        max_players: Number(maxPlayers),
        rules_text: rulesText || null,
        battle_rules: {
          format: format || null, game: game || null, tier: tier || null,
          team_size: num(teamSize), bring: num(bring),
          showdown_required: showdown,
        },
        config: {
          best_of: Number(bestOf),
          double_round: doubleRound,
          third_place: third,
          allow_draw: allowDraw === "" ? null : allowDraw === "yes",
          groups_count: num(groups),
          qualifiers_per_group: Number(qualifiers),
          repechage_position: num(repPos),
          repechage_slots: Number(repSlots),
        },
      };
      if (tpl === "custom") {
        let parsed: { stages?: unknown; rules?: unknown };
        try {
          parsed = JSON.parse(custom);
        } catch {
          throw new Error("O JSON das fases/regras está inválido.");
        }
        body.stages = parsed.stages ?? [];
        body.rules = parsed.rules ?? [];
      }
      const t = await api<TournamentDetail>(parent ? `/tournaments/${parent}/subtournaments` : "/tournaments", { body });
      nav(`/torneios/${t.id}`);
    });
  };

  return (
    <form onSubmit={submit} style={{ maxWidth: 780 }}>
      <h1>{parent ? "Novo subtorneio (repescagem)" : "Novo torneio"}</h1>
      {parent && <p className="muted">Subtorneio do <Link to={`/torneios/${parent}`}>torneio #{parent}</Link>. Para devolver jogadores ao principal, a fase de destino dele precisa ter vagas reservadas (<code>repechage_slots</code> ou <code>external_slots</code>).</p>}
      {box}

      <div className="card">
        <h2>Formato</h2>
        <div className="form-grid">
          <div className="field"><label>Nome</label><input value={name} onChange={(e) => setName(e.target.value)} required minLength={3} maxLength={120} /></div>
          <div className="field"><label>Modelo</label>
            <select value={tpl} onChange={(e) => setTpl(e.target.value)}>
              {Object.entries(template).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div className="field"><label>Nº de jogadores</label><input type="number" min={2} max={256} value={maxPlayers} onChange={(e) => setMaxPlayers(e.target.value)} required /></div>
          <div className="field"><label>Melhor de</label>
            <select value={bestOf} onChange={(e) => setBestOf(e.target.value)}>{[1, 3, 5, 7].map((n) => <option key={n} value={n}>{n}</option>)}</select>
          </div>
        </div>
        {(tpl === "league" || tpl === "groups_knockout") && (
          <div className="field inline"><input id="dbl" type="checkbox" checked={doubleRound} onChange={(e) => setDoubleRound(e.target.checked)} /><label htmlFor="dbl">Turno e returno</label></div>
        )}
        {(tpl === "knockout" || tpl === "groups_knockout") && (
          <div className="field inline"><input id="third" type="checkbox" checked={third} onChange={(e) => setThird(e.target.checked)} /><label htmlFor="third">Disputa de 3º lugar</label></div>
        )}
        {tpl !== "knockout" && (
          <div className="field" style={{ maxWidth: 260 }}><label>Empates</label>
            <select value={allowDraw} onChange={(e) => setAllowDraw(e.target.value)}>
              <option value="">Padrão do formato</option><option value="yes">Permitidos</option><option value="no">Não permitidos</option>
            </select>
          </div>
        )}
        {tpl === "groups_knockout" && (
          <div className="form-grid">
            <div className="field"><label>Nº de grupos (vazio = automático)</label><input type="number" min={2} value={groups} onChange={(e) => setGroups(e.target.value)} /></div>
            <div className="field"><label>Classificados por grupo</label><input type="number" min={1} value={qualifiers} onChange={(e) => setQualifiers(e.target.value)} /></div>
            <div className="field"><label>Posição que vai à repescagem</label><input type="number" min={1} value={repPos} onChange={(e) => setRepPos(e.target.value)} placeholder="nenhuma" /></div>
            <div className="field"><label>Vagas de repescagem no mata-mata</label><input type="number" min={0} value={repSlots} onChange={(e) => setRepSlots(e.target.value)} /></div>
          </div>
        )}
        {tpl === "custom" && (
          <div className="field">
            <label>Fases e regras de passagem (JSON)</label>
            <textarea style={{ minHeight: 260, fontFamily: "Consolas, monospace", fontSize: ".85rem" }} value={custom} onChange={(e) => setCustom(e.target.value)} spellCheck={false} />
            <p className="muted small">Cada regra leva as posições <code>pos_from</code>–<code>pos_to</code> de uma fase para outra (<code>stage</code>), para fora (<code>eliminated</code>), para a repescagem (<code>repechage</code>) ou de volta ao principal (<code>parent_tournament</code>). O servidor valida tamanhos e vagas ao salvar.</p>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Regras de batalha</h2>
        <div className="form-grid">
          <div className="field"><label>Formato (singles, doubles…)</label><input value={format} onChange={(e) => setFormat(e.target.value)} /></div>
          <div className="field"><label>Jogo / geração</label><input value={game} onChange={(e) => setGame(e.target.value)} placeholder="Gen 9" /></div>
          <div className="field"><label>Tier</label><input value={tier} onChange={(e) => setTier(e.target.value)} placeholder="OU" /></div>
          <div className="field"><label>Pokémon no time</label><input type="number" min={1} max={6} value={teamSize} onChange={(e) => setTeamSize(e.target.value)} /></div>
          <div className="field"><label>Pokémon levados</label><input type="number" min={1} max={6} value={bring} onChange={(e) => setBring(e.target.value)} /></div>
        </div>
        <p className="muted small">As cláusulas seguem automaticamente o tier escolhido (regras da Smogon no Showdown), então não precisam ser informadas aqui.</p>
        <div className="field inline"><input id="sd" type="checkbox" checked={showdown} onChange={(e) => setShowdown(e.target.checked)} /><label htmlFor="sd">Replay do Showdown obrigatório no reporte</label></div>
        <div className="field"><label>Regras em texto livre</label><textarea value={rulesText} onChange={(e) => setRulesText(e.target.value)} maxLength={5000} /></div>
      </div>

      <button className="btn primary" disabled={busy}>{busy ? "Criando…" : "Criar torneio"}</button>
    </form>
  );
}
