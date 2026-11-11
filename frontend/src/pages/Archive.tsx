import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, type ArchiveSummary, type Series } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Loading, useAction } from "../components/ui";
import { useLoad } from "../hooks";
import { fmtPeriod } from "../labels";

export function ArchiveCard({ e }: { e: ArchiveSummary }) {
  return (
    <Link to={`/acervo/${e.id}`} className="card" style={{ display: "block", color: "inherit" }}>
      <div className="row between">
        <h2 style={{ margin: 0 }}>{e.name}</h2>
        {e.series && <span className="badge">{e.series.name}{e.edition ? ` · ${e.edition}ª edição` : ""}</span>}
      </div>
      <p className="muted small" style={{ margin: ".4rem 0 0" }}>
        {fmtPeriod(e.start_date, e.end_date)}
        {e.format ? ` · ${e.format}` : ""}
        {e.players_count ? ` · ${e.players_count} jogadores` : ""}
        {e.tournament_id ? " · jogado na plataforma" : ""}
      </p>
      <p style={{ margin: ".5rem 0 0" }}>{e.champion ? <>🏆 <strong>{e.champion.name}</strong></> : <span className="muted small">Campeão não informado</span>}</p>
    </Link>
  );
}

export default function Archive() {
  const { isAdmin } = useAuth();
  const [q, setQ] = useState("");
  const [seriesId, setSeriesId] = useState("");
  const list = useLoad(() => api<ArchiveSummary[]>("/archive", { params: { q, series_id: seriesId, limit: 500 } }), [q, seriesId]);
  const series = useLoad(() => api<Series[]>("/series"), []);
  const [name, setName] = useState("");
  const { run, busy, box } = useAction();

  const createSeries = async (e: FormEvent) => {
    e.preventDefault();
    if (await run(() => api("/series", { body: { name } }), "Série criada.")) {
      setName("");
      await series.reload();
    }
  };

  return (
    <>
      <div className="row between">
        <h1>Acervo</h1>
        {isAdmin && <Link className="btn primary" to="/acervo/novo">Adicionar torneio antigo</Link>}
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Todos os torneios já realizados. Os jogados na plataforma entram aqui sozinhos quando terminam; os mais antigos são cadastrados pelos administradores.
      </p>
      <div className="row" style={{ marginBottom: "1rem" }}>
        <input style={{ maxWidth: 280 }} placeholder="Buscar por nome" value={q} onChange={(e) => setQ(e.target.value)} />
        <select style={{ maxWidth: 240 }} value={seriesId} onChange={(e) => setSeriesId(e.target.value)}>
          <option value="">Todas as séries</option>
          {(series.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      <ErrorBox error={list.error} />
      {list.loading && <Loading />}
      <div className="grid cols-2">{(list.data ?? []).map((e) => <ArchiveCard key={e.id} e={e} />)}</div>
      {list.data?.length === 0 && <div className="alert">Nenhum torneio no acervo{q || seriesId ? " com esses filtros" : " ainda"}.</div>}

      <section className="card" style={{ marginTop: "1.5rem" }}>
        <h2>Séries</h2>
        <p className="muted small">Torneios recorrentes (ex.: várias edições de uma mesma copa). Cada série mostra suas edições e campeões.</p>
        {(series.data ?? []).length === 0 && <p className="muted">Nenhuma série cadastrada.</p>}
        <div className="row">{(series.data ?? []).map((s) => <Link key={s.id} className="chip" to={`/acervo/series/${s.id}`}>{s.name}</Link>)}</div>
        {isAdmin && (
          <form onSubmit={createSeries} className="row" style={{ marginTop: ".8rem" }}>
            {box}
            <input style={{ maxWidth: 280 }} placeholder="Nome da nova série" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} maxLength={80} />
            <button className="btn" disabled={busy}>Criar série</button>
          </form>
        )}
      </section>
    </>
  );
}
