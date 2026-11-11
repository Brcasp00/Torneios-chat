import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type TournamentDetail } from "../api";
import CustomBuilder, { analyze, initialBuilder, toPayload, type Builder, type ParentStage } from "../components/CustomBuilder";
import { useAction } from "../components/ui";
import { useLoad } from "../hooks";
import { template, tiebreakLabel } from "../labels";

export default function CreateTournament() {
  const [params] = useSearchParams();
  const parent = params.get("parent");
  const nav = useNavigate();
  const { run, busy, box } = useAction();

  // Subtorneio: as fases do principal (e as vagas que elas reservam) alimentam as opções de "volta ao principal".
  const parentT = useLoad(() => (parent ? api<TournamentDetail>(`/tournaments/${parent}`) : Promise.resolve(null)), [parent]);
  const parentStages: ParentStage[] = useMemo(
    () => (parentT.data?.stages ?? []).map((s) => ({
      position: s.position,
      name: s.name,
      reserved: ((s.config?.external_slots as [number, number][] | undefined) ?? []).map(([a, z]) => [Number(a), Number(z)] as [number, number]),
    })),
    [parentT.data],
  );
  const [builder, setBuilder] = useState<Builder>(() => initialBuilder(!!parent));
  // Quando as fases do principal chegam, o exemplo do subtorneio já aponta para as vagas reservadas.
  useEffect(() => {
    if (parent && parentStages.length) setBuilder(initialBuilder(true, parentStages));
  }, [parent, parentStages]);

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

  const [koBestOf, setKoBestOf] = useState("");
  const [homeRules, setHomeRules] = useState(false);
  const [minCap, setMinCap] = useState("40");
  const [seriesSaldo, setSeriesSaldo] = useState("none");
  const [tiebreakers, setTiebreakers] = useState<string[]>(["saldo", "vitorias", "confronto_direto"]);

  /** Preenche o formato do Draft (edital): 8 jogadores, 2 grupos de 4 em turno e returno, semifinais/final/3º em md3. */
  const draftPreset = () => {
    setTpl("groups_knockout"); setMaxPlayers("8"); setGroups("2"); setQualifiers("2"); setRepPos(""); setRepSlots("0");
    setDoubleRound(true); setThird(true); setAllowDraw("yes"); setBestOf("1"); setKoBestOf("3");
    setHomeRules(true); setMinCap("40"); setSeriesSaldo("games"); setTiebreakers(["confronto_direto", "saldo", "sorteio"]);
  };

  const [format, setFormat] = useState("");
  const [game, setGame] = useState("");
  const [tier, setTier] = useState("");
  const [teamSize, setTeamSize] = useState("");
  const [bring, setBring] = useState("");
  const [showdown, setShowdown] = useState(true);
  const [rulesText, setRulesText] = useState("");

  const num = (s: string) => (s.trim() === "" ? null : Number(s));
  const analysis = useMemo(() => analyze(builder, Number(maxPlayers) || 0, !!parent, parentStages), [builder, maxPlayers, parent, parentStages]);

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
          knockout_best_of: tpl === "groups_knockout" && koBestOf ? Number(koBestOf) : null,
          home_rules: homeRules,
          home_min_turn_cap: Number(minCap) || 40,
          series_saldo: seriesSaldo,
          tiebreakers,
        },
      };
      if (tpl === "custom") {
        if (analysis.errors.length) throw new Error(`Ajuste a estrutura do torneio antes de criar: ${analysis.errors[0]}`);
        Object.assign(body, toPayload(builder, Number(maxPlayers), parentStages));
      }
      const t = await api<TournamentDetail>(parent ? `/tournaments/${parent}/subtournaments` : "/tournaments", { body });
      nav(`/torneios/${t.id}`);
    });
  };

  return (
    <form onSubmit={submit} style={{ maxWidth: 780 }}>
      <h1>{parent ? "Novo subtorneio (repescagem)" : "Novo torneio"}</h1>
      {parent && <p className="muted">Subtorneio do <Link to={`/torneios/${parent}`}>torneio #{parent}</Link>. Para devolver jogadores ao principal, a fase de destino dele precisa ter vagas reservadas para quem volta da repescagem (definidas ao criar o torneio principal).</p>}
      {box}
      {!parent && (
        <div className="alert">
          Atalho: <button type="button" className="btn small" onClick={draftPreset}>Preencher com o formato do Draft</button>{" "}
          <span className="muted small">8 jogadores, 2 grupos de 4 em turno e returno, 2 classificados por grupo, semifinais, final e 3º lugar em md3, mando de campo e desempate por confronto direto → saldo → sorteio. Dá para ajustar tudo depois.</span>
        </div>
      )}

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
          {tpl !== "custom" && (
            <div className="field"><label>Melhor de</label>
              <select value={bestOf} onChange={(e) => setBestOf(e.target.value)}>{[1, 3, 5, 7].map((n) => <option key={n} value={n}>{n}</option>)}</select>
            </div>
          )}
        </div>
        {tpl === "custom" && <p className="muted small">No personalizado, o "melhor de" e as demais opções são escolhidos em cada fase, logo abaixo.</p>}
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
            <div className="field"><label>Melhor de no mata-mata</label>
              <select value={koBestOf} onChange={(e) => setKoBestOf(e.target.value)}>
                <option value="">Igual aos grupos</option>{[1, 3, 5, 7].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Partidas, saldo e desempate</h2>
        <div className="field inline"><input id="home" type="checkbox" checked={homeRules} onChange={(e) => setHomeRules(e.target.checked)} /><label htmlFor="home">Mando de campo</label></div>
        <p className="muted small" style={{ marginTop: 0 }}>
          Com mando de campo, cada confronto tem um mandante (sorteado; no returno o mando se inverte). Antes da partida ele
          escolhe o formato (1v1 ou 2v2), se é melhor de 3, o teto de empate e se o chat é aberto. Em fases que já são
          melhor de 3 ou mais, o md3 é obrigatório.
        </p>
        {homeRules && (
          <div className="field" style={{ maxWidth: 260 }}><label>Teto de empate mínimo (turnos)</label><input type="number" min={1} max={1000} value={minCap} onChange={(e) => setMinCap(e.target.value)} /></div>
        )}
        <div className="field" style={{ maxWidth: 420 }}><label>Saldo em séries (melhor de 3 ou mais)</label>
          <select value={seriesSaldo} onChange={(e) => setSeriesSaldo(e.target.value)}>
            <option value="none">Não conta saldo</option>
            <option value="games">Jogos ganhos menos jogos perdidos (2 × 0 = +2)</option>
          </select>
        </div>
        <div className="field"><label>Desempate (depois dos pontos), em ordem</label>
          <div className="row">
            {[0, 1, 2, 3].map((i) => (
              <select key={i} style={{ maxWidth: 190 }} value={tiebreakers[i] ?? ""} onChange={(e) => {
                const next = [...tiebreakers];
                if (e.target.value) next[i] = e.target.value; else next.splice(i);
                setTiebreakers(next.filter((x, k) => x && next.indexOf(x) === k));
              }}>
                <option value="">{i === 0 ? "—" : "(nenhum)"}</option>
                {Object.entries(tiebreakLabel).map(([k, v]) => <option key={k} value={k}>{`${i + 1}º: ${v}`}</option>)}
              </select>
            ))}
          </div>
          <span className="muted small">Saldo em melhor de 1 = Pokémon restantes. "Sorteio" é feito pelo sistema com a semente do sorteio do torneio (sempre o mesmo resultado).</span>
        </div>
      </div>

      {tpl === "custom" && (
        <div className="card">
          <h2>Estrutura do torneio</h2>
          <CustomBuilder value={builder} onChange={setBuilder} maxPlayers={Number(maxPlayers) || 0} onMaxPlayers={(n) => setMaxPlayers(String(n))} isSub={!!parent} parentStages={parentStages} analysis={analysis} />
        </div>
      )}

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
