import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type SeriesDetail } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Loading, PlayerLink, useAction } from "../components/ui";
import { useLoad } from "../hooks";
import { fmtPeriod } from "../labels";

export default function SeriesPage() {
  const { id } = useParams();
  const { isAdmin } = useAuth();
  const nav = useNavigate();
  const s = useLoad(() => api<SeriesDetail>(`/series/${id}`), [id]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const { run, busy, box } = useAction();
  useEffect(() => {
    if (s.data) {
      setName(s.data.name);
      setDescription(s.data.description ?? "");
    }
  }, [s.data]);

  if (s.loading && !s.data) return <Loading />;
  if (!s.data) return <ErrorBox error={s.error} />;
  const d = s.data;

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (await run(() => api(`/series/${d.id}`, { method: "PUT", body: { name, description: description || null } }), "Série salva.")) await s.reload();
  };
  const remove = async () => {
    if (!window.confirm(`Apagar a série "${d.name}"? Os torneios dela continuam no acervo, só sem série.`)) return;
    if (await run(() => api(`/series/${d.id}`, { method: "DELETE" }))) nav("/acervo", { replace: true });
  };

  return (
    <>
      <p className="small"><Link to="/acervo">← Acervo</Link></p>
      <h1>{d.name}</h1>
      {d.description && <p style={{ whiteSpace: "pre-wrap" }}>{d.description}</p>}
      <section className="card">
        <h2>Edições e campeões</h2>
        {d.editions.length === 0 ? <p className="muted">Nenhum torneio ligado a esta série ainda. Ligue um torneio pela tela de edição dele no acervo.</p> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Edição</th><th>Torneio</th><th>Data</th><th>Campeão</th></tr></thead>
              <tbody>
                {d.editions.map((e) => (
                  <tr key={e.id}>
                    <td>{e.edition ? `${e.edition}ª` : "—"}</td>
                    <td><Link to={`/acervo/${e.id}`}>{e.name}</Link></td>
                    <td className="nowrap">{fmtPeriod(e.start_date, e.end_date)}</td>
                    <td>{e.champion ? <>🏆 <PlayerLink id={e.champion.user_id} name={e.champion.name} /></> : <span className="muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {isAdmin && (
        <form className="card" onSubmit={save}>
          <h2>Editar série</h2>
          {box}
          <div className="field"><label>Nome</label><input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={80} /></div>
          <div className="field"><label>Descrição</label><textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={5000} /></div>
          <div className="row between">
            <button className="btn primary" disabled={busy}>Salvar</button>
            <button type="button" className="btn danger" disabled={busy} onClick={remove}>Apagar série</button>
          </div>
        </form>
      )}
    </>
  );
}
