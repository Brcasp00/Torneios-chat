import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type DraftClubDetail, type DraftOverview, type TournamentDetail } from "../api";
import { ErrorBox, Loading, useAction } from "../components/ui";
import { useLoad } from "../hooks";
import { fmtM, parseM } from "../labels";
import { TransactionsTable } from "./DraftPokemonPage";
import { CostsText } from "./tournament/Draft";

/** Clube de um jogador no Draft: caixa, elenco, patrocinadores e movimentações (tudo público). */
export default function DraftClubPage() {
  const { id, uid } = useParams();
  const tid = Number(id);
  const c = useLoad(() => api<DraftClubDetail>(`/tournaments/${tid}/draft/clubs/${uid}`), [tid, uid], 30000);
  const t = useLoad(() => api<TournamentDetail>(`/tournaments/${tid}`), [tid]);
  const ov = useLoad(() => api<DraftOverview>(`/tournaments/${tid}/draft`), [tid]);
  if (c.loading && !c.data) return <Loading />;
  if (!c.data) return <ErrorBox error={c.error} />;
  const d = c.data;
  const eco = ov.data?.economy;

  return (
    <>
      <p className="small"><Link to={`/torneios/${tid}`}>← {t.data?.name ?? "Torneio"}</Link> · Clube</p>
      <h1 style={{ marginBottom: ".2rem" }}>{d.user.name}</h1>
      <p className="muted" style={{ marginTop: 0 }}><Link to={`/jogadores/${d.user.id}`}>Perfil do jogador</Link></p>
      {d.transferban && <div className="alert error">Transferban: o caixa está negativo, então o clube não pode comprar Pokémon até voltar ao positivo.</div>}

      <section className="card">
        <div className="stat-row">
          <div className="stat-box"><div className="n" style={{ color: d.cash < 0 ? "var(--red)" : "var(--green)" }}>{fmtM(d.cash)}</div><div className="muted small">Caixa</div></div>
          <div className="stat-box"><div className="n">{d.squad_count}{eco ? `/${eco.max_squad}` : ""}</div><div className="muted small">Elenco</div></div>
          <div className="stat-box"><div className="n">{d.registered_count}{eco ? `/${eco.max_registered}` : ""}</div><div className="muted small">Inscritos</div></div>
          <div className="stat-box"><div className="n">{fmtM(d.squad_value)}</div><div className="muted small">Valor do elenco</div></div>
          <div className="stat-box"><div className="n">{fmtM(d.salary_per_round)}</div><div className="muted small">Salários por rodada</div></div>
        </div>
      </section>

      <div className="grid cols-2" style={{ alignItems: "start" }}>
        <Sponsors tid={tid} d={d} max={eco?.sponsors ?? 5} onDone={() => void c.reload()} />
        {ov.data?.can_manage && <Adjust tid={tid} uid={d.user.id} onDone={() => void c.reload()} />}
      </div>

      <section className="card">
        <h2>Elenco</h2>
        {d.squad.length === 0 ? <p className="muted">Nenhum Pokémon ainda.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Pokémon</th><th>Tier Draft</th><th className="num">Contrato</th><th className="num">Salário/rodada</th><th>Custo por posição</th><th>Inscrito</th></tr></thead>
              <tbody>
                {d.squad.map((p) => (
                  <tr key={p.id}>
                    <td><Link to={`/torneios/${tid}/pokemon/${p.id}`}><strong>{p.name}</strong></Link></td>
                    <td>{p.draft_tier ?? "—"}</td>
                    <td className="num nowrap">{fmtM(p.contract_price)}</td>
                    <td className="num nowrap">{fmtM(p.salary)}</td>
                    <td><CostsText p={p} /></td>
                    <td>{p.registered ? "Sim" : "Não"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>Movimentações</h2>
        <TransactionsTable items={d.transactions} />
      </section>
    </>
  );
}

function Sponsors({ tid, d, max, onDone }: { tid: number; d: DraftClubDetail; max: number; onDone: () => void }) {
  const [list, setList] = useState<string[]>(d.sponsors);
  useEffect(() => setList(d.sponsors), [d.sponsors.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps
  const { run, busy, box } = useAction();
  const save = async () => { if (await run(() => api(`/tournaments/${tid}/draft/clubs/${d.user.id}/sponsors`, { method: "PUT", body: { sponsors: list } }), "Patrocinadores salvos.")) onDone(); };
  return (
    <section className="card">
      <h2>Patrocinadores</h2>
      <p className="muted small">Cada clube tem até {max} patrocinadores (empresas à escolha do jogador). Eles pagam a renda por vitória, empate e derrota.</p>
      {box}
      {!d.can_edit ? (
        d.sponsors.length ? <ul style={{ margin: 0 }}>{d.sponsors.map((s) => <li key={s}>{s}</li>)}</ul> : <p className="muted">Nenhum patrocinador informado.</p>
      ) : (
        <>
          {Array.from({ length: max }, (_, i) => (
            <div key={i} className="field"><input value={list[i] ?? ""} maxLength={60} placeholder={`Patrocinador ${i + 1}`} onChange={(e) => {
              const next = [...list];
              while (next.length <= i) next.push("");
              next[i] = e.target.value;
              setList(next);
            }} /></div>
          ))}
          <button className="btn primary" disabled={busy} onClick={save}>Salvar patrocinadores</button>
        </>
      )}
    </section>
  );
}

function Adjust({ tid, uid, onDone }: { tid: number; uid: number; onDone: () => void }) {
  const [amount, setAmount] = useState("");
  const [sign, setSign] = useState("1");
  const [note, setNote] = useState("");
  const { run, busy, box, setMsg } = useAction();
  const save = async () => {
    const v = parseM(amount);
    if (v == null || v === 0) { setMsg({ kind: "error", text: "Informe o valor em milhões (ex.: 50 ou 0,5)." }); return; }
    if (note.trim().length < 3) { setMsg({ kind: "error", text: "Explique o motivo do ajuste (aparece nas movimentações)." }); return; }
    if (await run(() => api(`/tournaments/${tid}/draft/adjust`, { body: { user_id: uid, amount: Math.abs(v) * Number(sign), note } }), "Ajuste registrado.")) { setAmount(""); setNote(""); onDone(); }
  };
  return (
    <section className="card">
      <h2>Ajuste de caixa (organização)</h2>
      <p className="muted small">Para lançar renda, salário, multa ou corrigir algo enquanto as cobranças automáticas por rodada não existem. Fica registrado nas movimentações.</p>
      {box}
      <div className="form-grid">
        <div className="field"><label>Tipo</label><select value={sign} onChange={(e) => setSign(e.target.value)}><option value="1">Entrada (+)</option><option value="-1">Saída (−)</option></select></div>
        <div className="field"><label>Valor (M)</label><input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></div>
      </div>
      <div className="field"><label>Motivo</label><input value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder="Ex.: renda da rodada 1 (vitória)" /></div>
      <button className="btn primary" disabled={busy} onClick={save}>Registrar ajuste</button>
    </section>
  );
}
