import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type DraftOverview, type DraftPokemon, type TournamentDetail } from "../../api";
import { ErrorBox, Loading, useAction } from "../../components/ui";
import { useLoad } from "../../hooks";
import { fmtM, positionLabel, POSITIONS } from "../../labels";
import type { PokemonInfo } from "../Pokedex";

/** Custos por posição em texto curto: "Atacante 20 · Meio 25 · Defensor 25" (a própria posição em destaque). */
export function CostsText({ p }: { p: DraftPokemon }) {
  const parts = POSITIONS.filter((k) => p.costs[k] != null);
  if (!parts.length) return <span className="muted">—</span>;
  return (
    <span className="small">
      {parts.map((k, i) => (
        <span key={k}>
          {i > 0 && " · "}
          <span style={p.positions.includes(k) ? { fontWeight: 800, color: "var(--accent)" } : undefined}>{positionLabel[k]} {p.costs[k]}</span>
        </span>
      ))}
    </span>
  );
}

/** Aba "Pokémon" do torneio de Draft: o lote, com dono, contrato, salário, posições e custos. */
export function DraftPokemonTab({ t }: { t: TournamentDetail }) {
  const lote = useLoad(() => api<DraftPokemon[]>(`/tournaments/${t.id}/draft/pokemon`), [t.id], 30000);
  const ov = useLoad(() => api<DraftOverview>(`/tournaments/${t.id}/draft`), [t.id]);
  const [q, setQ] = useState("");
  const [owner, setOwner] = useState("");
  const [pos, setPos] = useState("");
  const list = useMemo(() => (lote.data ?? []).filter((p) =>
    (!q.trim() || p.name.toLowerCase().includes(q.trim().toLowerCase()) || (p.draft_tier ?? "").toLowerCase() === q.trim().toLowerCase())
    && (!owner || (owner === "free" ? !p.owner : owner === "owned" ? !!p.owner : String(p.owner?.id) === owner))
    && (!pos || p.positions.includes(pos as DraftPokemon["positions"][number]))), [lote.data, q, owner, pos]);

  if (lote.loading && !lote.data) return <Loading />;
  if (!lote.data) return <ErrorBox error={lote.error} />;
  const canManage = !!ov.data?.can_manage;

  return (
    <div className="stack">
      {canManage && <AddToLote t={t} regions={ov.data?.regions ?? []} inLote={new Set(lote.data.map((p) => p.species_id))} onDone={() => void lote.reload()} />}
      <div className="card">
        <p className="muted small" style={{ marginTop: 0 }}>
          Lote de {lote.data.length} Pokémon{ov.data?.regions.length ? ` (${ov.data.regions.join(", ")})` : ""}. Tier e preço do Draft são definidos pela
          organização; os tiers da Smogon (Gen 9 National Dex / Gen 7) ficam só como referência. Na coluna de custos, a posição própria do Pokémon aparece em destaque.
        </p>
        <div className="form-grid">
          <div className="field"><label>Buscar (nome ou tier do Draft)</label><input value={q} onChange={(e) => setQ(e.target.value)} /></div>
          <div className="field"><label>Dono</label>
            <select value={owner} onChange={(e) => setOwner(e.target.value)}>
              <option value="">Todos</option><option value="free">Livres</option><option value="owned">Com dono</option>
              {(ov.data?.clubs ?? []).map((c) => <option key={c.user.id} value={c.user.id}>{c.user.name}</option>)}
            </select>
          </div>
          <div className="field"><label>Posição própria</label>
            <select value={pos} onChange={(e) => setPos(e.target.value)}>
              <option value="">Todas</option>{POSITIONS.map((k) => <option key={k} value={k}>{positionLabel[k]}</option>)}
            </select>
          </div>
        </div>
        {lote.data.length === 0 ? (
          <p className="muted">{canManage ? "O lote está vazio: adicione Pokémon acima." : "A organização ainda não montou o lote."}</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Pokémon</th><th>Tier Draft</th><th className="num">Preço</th><th>Dono</th><th className="num">Contrato</th><th className="num">Salário/rodada</th><th>Custo por posição</th><th>Smogon (G9 ND / G7)</th></tr></thead>
              <tbody>
                {list.map((p) => (
                  <tr key={p.id}>
                    <td><Link to={`/torneios/${t.id}/pokemon/${p.id}`}><strong>{p.name}</strong></Link>{p.registered && <span className="muted small"> · inscrito</span>}</td>
                    <td>{p.draft_tier ?? <span className="muted">—</span>}</td>
                    <td className="num nowrap">{fmtM(p.price)}</td>
                    <td>{p.owner ? <Link to={`/torneios/${t.id}/clubes/${p.owner.id}`}>{p.owner.name}</Link> : <span className="muted">livre</span>}</td>
                    <td className="num nowrap">{p.owner ? fmtM(p.contract_price) : "—"}</td>
                    <td className="num nowrap">{p.owner ? fmtM(p.salary) : "—"}</td>
                    <td><CostsText p={p} /></td>
                    <td className="small muted nowrap">{p.tier9 ?? "—"} / {p.tier7 ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

/** Organização: adiciona Pokémon do catálogo ao lote (só das regiões do torneio). */
function AddToLote({ t, regions, inLote, onDone }: { t: TournamentDetail; regions: string[]; inLote: Set<string>; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const all = useLoad(() => (open ? api<PokemonInfo[]>("/pokedex") : Promise.resolve([] as PokemonInfo[])), [open]);
  const [q, setQ] = useState("");
  const [region, setRegion] = useState("");
  const [baseOnly, setBaseOnly] = useState(true);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const { run, busy, box, setMsg } = useAction();
  const candidates = useMemo(() => (all.data ?? []).filter((p) =>
    regions.includes(p.region) && !inLote.has(p.id) && (!region || p.region === region) && (!baseOnly || !p.forme)
    && (!q.trim() || p.name.toLowerCase().includes(q.trim().toLowerCase()))), [all.data, regions, inLote, region, baseOnly, q]);

  const toggle = (id: string) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const add = async (ids: string[]) => {
    if (!ids.length) { setMsg({ kind: "error", text: "Marque ao menos um Pokémon (ou use \"Marcar todos os filtrados\")." }); return; }
    if (await run(async () => {
      const r = await api<{ added: number }>(`/tournaments/${t.id}/draft/pokemon`, { body: { species_ids: ids } });
      return r;
    }, `${ids.length} Pokémon enviados ao lote.`)) { setPicked(new Set()); onDone(); }
  };

  return (
    <div className="card">
      <div className="row between">
        <h2 style={{ margin: 0 }}>Montar o lote</h2>
        <button className="btn small" onClick={() => setOpen(!open)}>{open ? "Fechar" : "Adicionar Pokémon do catálogo"}</button>
      </div>
      {open && (
        <>
          <p className="muted small">Só aparecem Pokémon das regiões do lote ({regions.join(", ")}) que ainda não estão nele. Depois, abra cada Pokémon para definir tier do Draft, preço, posições e custos.</p>
          {box}
          {all.loading && !all.data ? <Loading /> : (
            <>
              <div className="form-grid">
                <div className="field"><label>Buscar</label><input value={q} onChange={(e) => setQ(e.target.value)} /></div>
                <div className="field"><label>Região</label>
                  <select value={region} onChange={(e) => setRegion(e.target.value)}><option value="">Todas do lote</option>{regions.map((r) => <option key={r}>{r}</option>)}</select>
                </div>
              </div>
              <div className="field inline"><input id="bo" type="checkbox" checked={baseOnly} onChange={(e) => setBaseOnly(e.target.checked)} /><label htmlFor="bo">Só a forma principal</label></div>
              <div className="row" style={{ margin: ".4rem 0" }}>
                <button className="btn small" onClick={() => setPicked(new Set(candidates.map((p) => p.id)))}>Marcar todos os filtrados ({candidates.length})</button>
                <button className="btn small" onClick={() => setPicked(new Set())}>Desmarcar</button>
                <button className="btn primary small" disabled={busy} onClick={() => add([...picked])}>Adicionar marcados ({picked.size})</button>
              </div>
              <div className="table-wrap" style={{ maxHeight: 360, overflowY: "auto" }}>
                <table>
                  <tbody>
                    {candidates.slice(0, 400).map((p) => (
                      <tr key={p.id} onClick={() => toggle(p.id)} style={{ cursor: "pointer" }}>
                        <td><input type="checkbox" checked={picked.has(p.id)} readOnly /></td>
                        <td className="muted num">{p.num}</td><td><strong>{p.name}</strong></td><td>{p.region}</td>
                        <td className="small muted">{p.tier9 ?? "—"} / {p.tier7 ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {candidates.length > 400 && <p className="muted small">Mostrando 400 de {candidates.length}; use a busca ou "Marcar todos os filtrados".</p>}
            </>
          )}
        </>
      )}
    </div>
  );
}

/** Aba "Clubes": caixa, transferban, elenco e salários de cada jogador. */
export function DraftClubsTab({ t }: { t: TournamentDetail }) {
  const ov = useLoad(() => api<DraftOverview>(`/tournaments/${t.id}/draft`), [t.id], 30000);
  if (ov.loading && !ov.data) return <Loading />;
  if (!ov.data) return <ErrorBox error={ov.error} />;
  const eco = ov.data.economy;
  return (
    <div className="card">
      <p className="muted small" style={{ marginTop: 0 }}>
        Orçamento inicial {fmtM(eco?.initial_budget)}. Caixa = orçamento + todas as movimentações (compras, ajustes…). Com caixa negativo o clube fica em
        transferban (não pode comprar). Lote: {ov.data.lote_count} Pokémon, {ov.data.free_count} livres.
      </p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Clube</th><th className="num">Caixa</th><th className="num">Elenco</th><th className="num">Inscritos</th><th className="num">Valor do elenco</th><th className="num">Salários/rodada</th><th>Patrocinadores</th><th>CT</th></tr></thead>
          <tbody>
            {ov.data.clubs.map((c) => (
              <tr key={c.user.id}>
                <td><Link to={`/torneios/${t.id}/clubes/${c.user.id}`}><strong>{c.user.name}</strong></Link>{c.transferban && <span className="badge" style={{ marginLeft: ".4rem", color: "var(--red)" }}>transferban</span>}</td>
                <td className="num nowrap" style={{ color: c.cash < 0 ? "var(--red)" : undefined }}>{fmtM(c.cash)}</td>
                <td className="num">{c.squad_count}/{eco?.max_squad}</td>
                <td className="num">{c.registered_count}/{eco?.max_registered}</td>
                <td className="num nowrap">{fmtM(c.squad_value)}</td>
                <td className="num nowrap">{fmtM(c.salary_per_round)}</td>
                <td className="small">{c.sponsors.length ? c.sponsors.join(", ") : <span className="muted">—</span>}</td>
                <td>{c.ct_level ? `Nível ${c.ct_level}` : <span className="muted">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Cartão da aba Gerenciar: liga o modo Draft e escolhe as regiões do lote. */
export function DraftSetupCard({ t, onChanged }: { t: TournamentDetail; onChanged: () => void }) {
  const current = (t.config?.draft as { regions?: string[] } | undefined)?.regions;
  const regions = useLoad(() => api<{ regions: string[] }>("/pokedex/meta"), []);
  const [picked, setPicked] = useState<string[]>(current ?? []);
  const { run, busy, box, setMsg } = useAction();
  const save = async () => {
    if (!picked.length) { setMsg({ kind: "error", text: "Escolha ao menos uma região para o lote de Pokémon." }); return; }
    const ov = current ? await api<DraftOverview>(`/tournaments/${t.id}/draft`).catch(() => null) : null;
    if (await run(() => api(`/tournaments/${t.id}/draft`, { method: "PUT", body: { regions: picked, economy: ov?.economy ?? null } }),
      current ? "Regiões do lote atualizadas." : "Modo Draft ligado: veja as abas Pokémon e Clubes.")) onChanged();
  };
  return (
    <div className="card">
      <h2>Modo Draft</h2>
      <p className="muted small">
        {current
          ? "Este torneio usa o modo Draft. As regiões definem quais Pokémon podem entrar no lote (Pokémon já no lote não saem ao mudar)."
          : "Liga a economia do Draft neste torneio: lote de Pokémon por região, registro do leilão, caixa dos clubes e patrocinadores. Os valores econômicos vêm do arquivo de configuração (orçamento de € 500 mi etc.)."}
      </p>
      {box}
      <div className="row">
        {(regions.data?.regions ?? []).map((r) => (
          <label key={r} className="row" style={{ gap: ".3rem" }}>
            <input type="checkbox" checked={picked.includes(r)} onChange={(e) => setPicked(e.target.checked ? [...picked, r] : picked.filter((x) => x !== r))} />{r}
          </label>
        ))}
      </div>
      <button className="btn primary" style={{ marginTop: ".6rem" }} disabled={busy} onClick={save}>{current ? "Salvar regiões" : "Ligar modo Draft"}</button>
    </div>
  );
}
