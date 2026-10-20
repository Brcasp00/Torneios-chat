import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type TournamentSummary } from "../api";
import { useAuth } from "../auth";
import TournamentCard from "../components/TournamentCard";
import { ErrorBox, Loading } from "../components/ui";
import { useLoad } from "../hooks";
import { tournamentStatus } from "../labels";

export default function Tournaments() {
  const { isStaff } = useAuth();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const list = useLoad(() => api<TournamentSummary[]>("/tournaments", { params: { status_: status, q, limit: 100 } }), [status, q], 30000);

  return (
    <>
      <div className="row between">
        <h1>Torneios</h1>
        {isStaff && <Link className="btn primary" to="/torneios/novo">Novo torneio</Link>}
      </div>
      <div className="row" style={{ marginBottom: "1rem" }}>
        <input style={{ maxWidth: 280 }} placeholder="Buscar por nome" value={q} onChange={(e) => setQ(e.target.value)} />
        <select style={{ maxWidth: 200 }} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Todos os status</option>
          {Object.entries(tournamentStatus).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </div>
      <ErrorBox error={list.error} />
      {list.loading && <Loading />}
      <div className="grid cols-2">{(list.data ?? []).map((t) => <TournamentCard key={t.id} t={t} />)}</div>
      {list.data?.length === 0 && <div className="alert">Nenhum torneio encontrado.</div>}
    </>
  );
}
