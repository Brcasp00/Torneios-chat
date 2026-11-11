import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type ArchiveDetail, type ArchiveMatch } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Loading, PlayerLink, useAction } from "../components/ui";
import { useLoad } from "../hooks";
import { fmtPeriod } from "../labels";

function groupMatches(ms: ArchiveMatch[]): [string, ArchiveMatch[]][] {
  const out: [string, ArchiveMatch[]][] = [];
  for (const m of ms) {
    const last = out[out.length - 1];
    if (last && last[0] === m.stage_label) last[1].push(m);
    else out.push([m.stage_label, [m]]);
  }
  return out;
}

export default function ArchiveEntry() {
  const { id } = useParams();
  const { isAdmin } = useAuth();
  const nav = useNavigate();
  const d = useLoad(() => api<ArchiveDetail>(`/archive/${id}`), [id]);
  const [confirm, setConfirm] = useState("");
  const { run, busy, box, setMsg } = useAction();

  if (d.loading && !d.data) return <Loading />;
  if (!d.data) return <ErrorBox error={d.error} />;
  const e = d.data;

  const remove = async () => {
    if (confirm.trim().replace(/\s+/g, " ").toLowerCase() !== e.name.toLowerCase()) {
      setMsg({ kind: "error", text: `Para confirmar, digite exatamente o nome do torneio: "${e.name}".` });
      return;
    }
    if (await run(() => api(`/archive/${e.id}/delete`, { body: { confirm_name: confirm } }))) nav("/acervo", { replace: true });
  };

  return (
    <>
      <p className="small"><Link to="/acervo">← Acervo</Link></p>
      <div className="row between">
        <h1 style={{ marginBottom: 0 }}>{e.name}</h1>
        {isAdmin && <Link className="btn" to={`/acervo/${e.id}/editar`}>Editar</Link>}
      </div>
      {e.series && (
        <p style={{ marginTop: ".3rem" }}>
          <Link to={`/acervo/series/${e.series.id}`}>{e.series.name}</Link>{e.edition ? ` · ${e.edition}ª edição` : ""}
        </p>
      )}

      <div className="grid cols-2">
        <section className="card">
          <h2>Informações</h2>
          <dl className="kv">
            <dt>Data</dt><dd>{fmtPeriod(e.start_date, e.end_date)}</dd>
            {e.format && <><dt>Formato</dt><dd>{e.format}</dd></>}
            {e.players_count && <><dt>Participantes</dt><dd>{e.players_count}</dd></>}
            {e.organizer && <><dt>Organizador</dt><dd>{e.organizer}</dd></>}
            {e.tier && <><dt>Tier</dt><dd>{e.tier}</dd></>}
          </dl>
          {e.rules_text && <><h3>Regras</h3><p style={{ whiteSpace: "pre-wrap" }}>{e.rules_text}</p></>}
          {e.tournament_id && (
            <p style={{ marginBottom: 0 }}>
              <Link className="btn" to={`/torneios/${e.tournament_id}`}>Ver o torneio completo</Link>
              <span className="muted small"> tabelas, chaveamento, confrontos e replays</span>
            </p>
          )}
        </section>
        <section className="card">
          <h2>Classificação final</h2>
          {e.placements.length === 0 ? <p className="muted">Não informada.</p> : (
            <div className="table-wrap">
              <table>
                <tbody>
                  {e.placements.map((p, k) => (
                    <tr key={k}>
                      <td><span className={`pos ${p.position === 1 ? "p1" : p.position <= 3 ? "q" : ""}`}>{p.position}</span></td>
                      <td><PlayerLink id={p.user_id} name={p.name} />{p.position === 1 && " 🏆"}</td>
                      <td className="muted small">{p.label}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      {e.description && (
        <section className="card">
          <h2>Sobre o torneio</h2>
          <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{e.description}</p>
        </section>
      )}
      {e.links.length > 0 && (
        <section className="card">
          <h2>Links</h2>
          <ul style={{ margin: 0 }}>{e.links.map((l, k) => <li key={k}><a href={l.url} target="_blank" rel="noreferrer noopener">{l.label}</a></li>)}</ul>
        </section>
      )}
      {e.matches.length > 0 && (
        <section className="card">
          <h2>Partidas</h2>
          {groupMatches(e.matches).map(([label, ms]) => (
            <div key={label + ms[0].id}>
              <h3>{label}</h3>
              <div className="table-wrap">
                <table>
                  <tbody>
                    {ms.map((m) => (
                      <tr key={m.id}>
                        <td className="muted small nowrap">{m.number ? `Partida ${m.number}` : ""}</td>
                        <td style={{ fontWeight: m.winner === 1 ? 800 : undefined }}><PlayerLink id={m.player1.user_id} name={m.player1.name} /></td>
                        <td className="muted">×</td>
                        <td style={{ fontWeight: m.winner === 2 ? 800 : undefined }}><PlayerLink id={m.player2.user_id} name={m.player2.name} /></td>
                        <td className="right">{m.replay_url ? <a href={m.replay_url} target="_blank" rel="noreferrer noopener">Replay</a> : <span className="muted small">sem link</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </section>
      )}

      {isAdmin && (
        <section className="card">
          <h2>Remover do acervo</h2>
          <p className="muted small">
            {e.tournament_id
              ? "Este torneio foi jogado na plataforma: removê-lo do acervo APAGA o torneio de vez (confrontos, tabelas, histórico). Só dá para recuperar restaurando um backup."
              : "Remove este torneio do acervo de vez. Só dá para recuperar restaurando um backup."}
          </p>
          {box}
          <div className="row">
            <input style={{ maxWidth: 320 }} placeholder="Digite o nome do torneio para confirmar" value={confirm} onChange={(ev) => setConfirm(ev.target.value)} />
            <button className="btn danger" disabled={busy} onClick={remove}>Remover do acervo</button>
          </div>
        </section>
      )}
    </>
  );
}
