import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type PlayerRef } from "../api";
import { ErrorBox, Loading } from "../components/ui";
import { useLoad } from "../hooks";

export default function Players() {
  const [q, setQ] = useState("");
  const list = useLoad(() => api<PlayerRef[]>("/users", { params: { q, limit: 200 } }), [q]);
  return (
    <>
      <h1>Jogadores</h1>
      <input style={{ maxWidth: 280, marginBottom: "1rem" }} placeholder="Buscar por nome" value={q} onChange={(e) => setQ(e.target.value)} />
      <ErrorBox error={list.error} />
      {list.loading && <Loading />}
      <div className="row">
        {(list.data ?? []).map((u) => <Link key={u.id} className="chip" to={`/jogadores/${u.id}`}>{u.name}</Link>)}
      </div>
      {list.data?.length === 0 && <div className="alert">Nenhum jogador encontrado.</div>}
    </>
  );
}
