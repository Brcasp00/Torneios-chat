import { Link, useParams } from "react-router-dom";
import { api, type Finish, type Profile as P } from "../api";
import { useAuth } from "../auth";
import { Badge, ErrorBox, Loading } from "../components/ui";
import { useLoad } from "../hooks";
import { fmtDay, playerStatus, roleLabel, tournamentStatus } from "../labels";

function FinishList({ items, empty }: { items: Finish[]; empty: string }) {
  if (!items.length) return <p className="muted">{empty}</p>;
  return (
    <div className="table-wrap">
      <table>
        <tbody>
          {items.map((f) => (
            <tr key={f.archive_id}>
              <td><span className={`pos ${f.position === 1 ? "p1" : f.position <= 3 ? "q" : ""}`}>{f.position}</span></td>
              <td>
                <Link to={`/acervo/${f.archive_id}`}>{f.name}</Link>
                <div className="muted small">{[f.label, f.date ? fmtDay(f.date) : null].filter(Boolean).join(" · ")}</div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Profile() {
  const { id } = useParams();
  const { user } = useAuth();
  const p = useLoad(() => api<P>(`/players/${id}`), [id]);
  if (p.loading && !p.data) return <Loading />;
  if (!p.data) return <ErrorBox error={p.error} />;
  const d = p.data;
  const s = d.stats;
  const own = user?.id === d.id;

  return (
    <>
      <div className="row between">
        <div>
          <h1 style={{ marginBottom: ".2rem" }}>{d.name}</h1>
          <p className="muted" style={{ margin: 0 }}>{roleLabel[d.role]} · membro desde {fmtDay(d.member_since)}</p>
        </div>
        {own && <Link className="btn small" to="/conta">Minha conta</Link>}
      </div>

      <section className="card" style={{ marginTop: "1rem" }}>
        <div className="stat-row">
          <div className="stat-box"><div className="n">{d.titles.length}</div><div className="muted small">Títulos</div></div>
          <div className="stat-box"><div className="n">{d.podiums.length}</div><div className="muted small">Pódios (2º/3º)</div></div>
          <div className="stat-box"><div className="n">{s.played}</div><div className="muted small">Jogos</div></div>
          <div className="stat-box"><div className="n">{s.wins}</div><div className="muted small">Vitórias</div></div>
          <div className="stat-box"><div className="n">{s.draws}</div><div className="muted small">Empates</div></div>
          <div className="stat-box"><div className="n">{s.losses}</div><div className="muted small">Derrotas</div></div>
          <div className="stat-box"><div className="n">{s.saldo > 0 ? `+${s.saldo}` : s.saldo}</div><div className="muted small">Saldo</div></div>
        </div>
        <p className="muted small" style={{ margin: ".6rem 0 0" }}>Jogos e saldo contam as partidas disputadas na plataforma; títulos e pódios contam todo o acervo.</p>
      </section>

      {d.current.length > 0 && (
        <section className="card">
          <h2>Torneios em andamento</h2>
          {d.current.map((c) => (
            <div key={c.tournament_id} className="row between" style={{ padding: ".3rem 0" }}>
              <Link to={`/torneios/${c.tournament_id}`}>{c.name}</Link>
              <span className="row"><Badge kind={c.status}>{tournamentStatus[c.status] ?? c.status}</Badge><Badge kind={c.player_status}>{playerStatus[c.player_status] ?? c.player_status}</Badge></span>
            </div>
          ))}
        </section>
      )}
      <div className="grid cols-2" style={{ alignItems: "start" }}>
        <section className="card"><h2>🏆 Títulos</h2><FinishList items={d.titles} empty="Nenhum título ainda." /></section>
        <section className="card"><h2>Pódios</h2><FinishList items={d.podiums} empty="Nenhum pódio ainda." /></section>
      </div>
      <section className="card"><h2>Torneios disputados (acervo)</h2><FinishList items={d.archive} empty="Nenhum torneio no acervo ainda." /></section>
    </>
  );
}
