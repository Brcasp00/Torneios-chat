import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type DraftOverview, type DraftPokemonDetail, type DraftTransaction, type TournamentDetail } from "../api";
import { ErrorBox, Loading, PlayerLink, useAction } from "../components/ui";
import { useLoad } from "../hooks";
import { fmtDate, fmtM, parseM, positionLabel, POSITIONS, txKind, viaLabel } from "../labels";

const TYPE_PT: Record<string, string> = {
  Normal: "Normal", Fire: "Fogo", Water: "Água", Grass: "Planta", Electric: "Elétrico", Ice: "Gelo", Fighting: "Lutador", Poison: "Venenoso",
  Ground: "Terrestre", Flying: "Voador", Psychic: "Psíquico", Bug: "Inseto", Rock: "Pedra", Ghost: "Fantasma", Dragon: "Dragão", Dark: "Sombrio",
  Steel: "Aço", Fairy: "Fada",
};

export function TransactionsTable({ items, showUser = false, showPokemon = true }: { items: DraftTransaction[]; showUser?: boolean; showPokemon?: boolean }) {
  if (!items.length) return <p className="muted">Nenhuma movimentação ainda.</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Quando</th><th>Tipo</th>{showUser && <th>Clube</th>}{showPokemon && <th>Pokémon</th>}<th className="num">Valor</th><th>Observação</th></tr></thead>
        <tbody>
          {items.map((x) => (
            <tr key={x.id}>
              <td className="small nowrap">{fmtDate(x.created_at)}</td>
              <td>{txKind[x.kind] ?? x.kind}</td>
              {showUser && <td>{x.user ? <PlayerLink id={x.user.id} name={x.user.name} /> : "—"}</td>}
              {showPokemon && <td>{x.pokemon_name ?? "—"}</td>}
              <td className="num nowrap" style={{ color: x.amount < 0 ? "var(--red)" : "var(--green)" }}>{x.amount > 0 ? "+" : ""}{fmtM(x.amount)}</td>
              <td className="small muted">{x.note}{x.created_by ? ` · por ${x.created_by.name}` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Painel de um Pokémon do lote: dono, contrato, posições, custo por posição e salário. */
export default function DraftPokemonPage() {
  const { id, pid } = useParams();
  const tid = Number(id);
  const d = useLoad(() => api<DraftPokemonDetail>(`/tournaments/${tid}/draft/pokemon/${pid}`), [tid, pid], 30000);
  const t = useLoad(() => api<TournamentDetail>(`/tournaments/${tid}`), [tid]);
  const ov = useLoad(() => api<DraftOverview>(`/tournaments/${tid}/draft`), [tid]);
  if (d.loading && !d.data) return <Loading />;
  if (!d.data) return <ErrorBox error={d.error} />;
  const p = d.data;
  const refresh = () => { void d.reload(); void ov.reload(); };

  return (
    <>
      <p className="small"><Link to={`/torneios/${tid}`}>← {t.data?.name ?? "Torneio"}</Link> · Pokémon do Draft</p>
      <div className="row between">
        <div>
          <h1 style={{ marginBottom: ".2rem" }}>{p.name}</h1>
          <span className="muted">#{p.num} · {p.types.map((x) => TYPE_PT[x] ?? x).join(" / ")} · {p.region}</span>
        </div>
        {p.owner ? <span className="badge">Dono: {p.owner.name}</span> : <span className="badge">Livre</span>}
      </div>

      <div className="grid cols-2" style={{ alignItems: "start", marginTop: "1rem" }}>
        <section className="card">
          <h2>Contrato</h2>
          <dl className="kv">
            <dt>Dono</dt><dd>{p.owner ? <Link to={`/torneios/${tid}/clubes/${p.owner.id}`}>{p.owner.name}</Link> : "Livre (sem dono)"}</dd>
            <dt>Valor do contrato</dt><dd>{p.owner ? fmtM(p.contract_price) : "—"}</dd>
            <dt>Salário por rodada</dt><dd>{p.owner ? fmtM(p.salary) : "—"}</dd>
            <dt>Origem</dt><dd>{p.acquired_via ? `${viaLabel[p.acquired_via] ?? p.acquired_via}${p.acquired_at ? ` · ${fmtDate(p.acquired_at)}` : ""}` : "—"}</dd>
            <dt>Inscrito</dt><dd>{p.registered ? "Sim" : "Não"}</dd>
          </dl>
        </section>
        <section className="card">
          <h2>Posições e pontos</h2>
          <dl className="kv">
            <dt>Tier do Draft</dt><dd>{p.draft_tier ?? "—"}</dd>
            <dt>Preço de referência</dt><dd>{fmtM(p.price)}</dd>
            <dt>Posição(ões)</dt><dd>{p.positions.length ? p.positions.map((k) => positionLabel[k]).join(", ") : "—"}</dd>
          </dl>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Jogando como</th><th className="num">Custo (pontos)</th></tr></thead>
              <tbody>
                {POSITIONS.map((k) => (
                  <tr key={k}>
                    <td>{positionLabel[k]}{p.positions.includes(k) && <span className="muted small"> · posição própria</span>}</td>
                    <td className="num">{p.costs[k] ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small" style={{ marginBottom: 0 }}>Referência Smogon: Gen 9 National Dex {p.tier9 ?? "—"} · Gen 7 {p.tier7 ?? "—"}</p>
        </section>
      </div>

      {ov.data?.can_manage && <StaffPanel tid={tid} p={p} ov={ov.data} onDone={refresh} />}

      <section className="card">
        <h2>Histórico</h2>
        <TransactionsTable items={p.transactions} showUser showPokemon={false} />
      </section>
    </>
  );
}

function StaffPanel({ tid, p, ov, onDone }: { tid: number; p: DraftPokemonDetail; ov: DraftOverview; onDone: () => void }) {
  const nav = useNavigate();
  const [tier, setTier] = useState(p.draft_tier ?? "");
  const [price, setPrice] = useState(p.price != null ? String(p.price / 1_000_000).replace(".", ",") : "");
  const [positions, setPositions] = useState<string[]>(p.positions);
  const [costs, setCosts] = useState<Record<string, string>>(Object.fromEntries(POSITIONS.map((k) => [k, p.costs[k] != null ? String(p.costs[k]) : ""])));
  const [buyer, setBuyer] = useState("");
  const [paid, setPaid] = useState("");
  const [via, setVia] = useState("auction");
  const [negative, setNegative] = useState(false);
  const edit = useAction();
  const sale = useAction();
  useEffect(() => { if (p.price != null && !paid) setPaid(String(p.price / 1_000_000).replace(".", ",")); }, [p.price]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveEdit = async () => {
    const parsed: Record<string, number> = {};
    for (const k of POSITIONS) {
      if (costs[k].trim() === "") continue;
      const n = Number(costs[k]);
      if (!Number.isInteger(n) || n < 0 || n > 100) { edit.setMsg({ kind: "error", text: `Custo de ${positionLabel[k]}: use um número inteiro de 0 a 100.` }); return; }
      parsed[k] = n;
    }
    const pr = price.trim() ? parseM(price) : null;
    if (price.trim() && pr == null) { edit.setMsg({ kind: "error", text: "Preço inválido: use milhões, ex.: 30 ou 27,5." }); return; }
    if (await edit.run(() => api(`/tournaments/${tid}/draft/pokemon/${p.id}`, { method: "PUT", body: { draft_tier: tier || null, price: pr, positions, costs: parsed } }), "Pokémon atualizado.")) onDone();
  };
  const assign = async () => {
    if (!buyer) { sale.setMsg({ kind: "error", text: "Escolha o clube que comprou." }); return; }
    const v = parseM(paid);
    if (v == null) { sale.setMsg({ kind: "error", text: "Informe o valor pago em milhões (ex.: 30 ou 27,5)." }); return; }
    if (await sale.run(() => api(`/tournaments/${tid}/draft/pokemon/${p.id}/assign`, { body: { user_id: Number(buyer), price: v, via, allow_negative: negative } }), "Compra registrada.")) onDone();
  };
  const unassign = async () => {
    if (!confirm(`Desfazer o registro de ${p.name}? O valor pago (${fmtM(p.contract_price)}) volta ao caixa de ${p.owner?.name} e o Pokémon fica livre.`)) return;
    if (await sale.run(() => api(`/tournaments/${tid}/draft/pokemon/${p.id}/unassign`, { body: { note: null } }), "Registro desfeito.")) onDone();
  };
  const remove = async () => {
    if (p.owner) { sale.setMsg({ kind: "error", text: "Este Pokémon tem dono: desfaça o registro antes de tirá-lo do lote." }); return; }
    if (!confirm(`Tirar ${p.name} do lote?`)) return;
    if (await sale.run(() => api(`/tournaments/${tid}/draft/pokemon/${p.id}`, { method: "DELETE" }))) nav(`/torneios/${tid}`);
  };

  return (
    <div className="grid cols-2" style={{ alignItems: "start" }}>
      <section className="card">
        <h2>Editar (organização)</h2>
        {edit.box}
        <div className="form-grid">
          <div className="field"><label>Tier do Draft</label><input value={tier} maxLength={10} onChange={(e) => setTier(e.target.value)} placeholder="Ex.: OU" /></div>
          <div className="field"><label>Preço de referência (M)</label><input inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} /></div>
        </div>
        <div className="field"><label>Posição(ões) própria(s)</label>
          <div className="row">
            {POSITIONS.map((k) => (
              <label key={k} className="row" style={{ gap: ".3rem" }}>
                <input type="checkbox" checked={positions.includes(k)} onChange={(e) => setPositions(e.target.checked ? [...positions, k] : positions.filter((x) => x !== k))} />{positionLabel[k]}
              </label>
            ))}
          </div>
        </div>
        <div className="form-grid">
          {POSITIONS.map((k) => (
            <div key={k} className="field"><label>Custo como {positionLabel[k]} (pontos)</label><input type="number" min={0} max={100} value={costs[k]} onChange={(e) => setCosts({ ...costs, [k]: e.target.value })} /></div>
          ))}
        </div>
        <button className="btn primary" disabled={edit.busy} onClick={saveEdit}>Salvar</button>
      </section>
      <section className="card">
        <h2>{p.owner ? "Contrato" : "Registrar compra"}</h2>
        {sale.box}
        {p.owner ? (
          <>
            <p className="muted small">Registro errado? Desfazer devolve o valor pago ao caixa do clube (fica registrado como correção) e o Pokémon volta a ficar livre.</p>
            <button className="btn danger" disabled={sale.busy} onClick={unassign}>Desfazer registro</button>
          </>
        ) : (
          <>
            <p className="muted small">O leilão acontece no Discord: registre aqui quem levou e quanto pagou. O valor sai do caixa do clube.</p>
            <div className="form-grid">
              <div className="field"><label>Clube</label>
                <select value={buyer} onChange={(e) => setBuyer(e.target.value)}>
                  <option value="">Escolha</option>
                  {ov.clubs.map((c) => <option key={c.user.id} value={c.user.id}>{c.user.name} — caixa {fmtM(c.cash)}{c.transferban ? " (transferban)" : ""}</option>)}
                </select>
              </div>
              <div className="field"><label>Valor pago (M)</label><input inputMode="decimal" value={paid} onChange={(e) => setPaid(e.target.value)} /></div>
              <div className="field"><label>Origem</label>
                <select value={via} onChange={(e) => setVia(e.target.value)}><option value="auction">Leilão</option><option value="market">Mercado</option></select>
              </div>
            </div>
            <div className="field inline"><input id="neg" type="checkbox" checked={negative} onChange={(e) => setNegative(e.target.checked)} /><label htmlFor="neg">Permitir que o caixa fique negativo (o clube entra em transferban)</label></div>
            <button className="btn primary" disabled={sale.busy} onClick={assign}>Registrar compra</button>
          </>
        )}
        <hr style={{ borderColor: "var(--line)", margin: "1rem 0" }} />
        <button className="btn small danger" disabled={sale.busy} onClick={remove}>Tirar do lote</button>
      </section>
    </div>
  );
}
