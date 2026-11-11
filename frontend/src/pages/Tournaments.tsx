import { useState } from "react";
import { Link } from "react-router-dom";
import { api, type Match, type TournamentSummary } from "../api";
import { useAuth } from "../auth";
import TournamentCard from "../components/TournamentCard";
import { ErrorBox, Loading, MatchRow } from "../components/ui";
import { useLoad } from "../hooks";

/** Área de torneios: o que está acontecendo agora. Os encerrados vão para o acervo. */
export default function Tournaments() {
  const { user, isStaff, isAdmin } = useAuth();
  const [q, setQ] = useState("");
  const list = useLoad(() => api<TournamentSummary[]>("/tournaments", { params: { q, limit: 100 } }), [q], 30000);
  const all = list.data ?? [];
  const running = all.filter((t) => t.status === "running");
  const open = all.filter((t) => t.status === "registration" || t.status === "draft");
  const cancelled = all.filter((t) => t.status === "cancelled");

  const mine = useLoad(
    async () => {
      if (!user || running.length === 0) return [] as Match[];
      const parts = await Promise.all(
        running.slice(0, 6).map((t) => api<Match[]>(`/tournaments/${t.id}/matches`, { params: { player_id: user.id } })),
      );
      return parts.flat().filter((m) => m.status !== "validated" && m.status !== "void" && m.player1 && m.player2);
    },
    [user?.id, running.map((t) => t.id).join(",")],
    30000,
  );

  return (
    <>
      <div className="row between">
        <h1>Torneios</h1>
        {isStaff && <Link className="btn primary" to="/torneios/novo">Novo torneio</Link>}
      </div>
      <div className="row" style={{ marginBottom: "1rem" }}>
        <input style={{ maxWidth: 280 }} placeholder="Buscar por nome" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="muted small">Torneios encerrados ficam no <Link to="/acervo">Acervo</Link>.</span>
      </div>
      <ErrorBox error={list.error} />
      {list.loading && <Loading />}

      {user && (mine.data?.length ?? 0) > 0 && (
        <section className="card">
          <h2>Seus jogos pendentes</h2>
          {mine.data!.map((m) => <MatchRow key={m.id} m={m} showRound />)}
        </section>
      )}
      {running.length > 0 && (
        <section>
          <h2>Em andamento</h2>
          <div className="grid cols-2">{running.map((t) => <TournamentCard key={t.id} t={t} />)}</div>
        </section>
      )}
      {open.length > 0 && (
        <section>
          <h2>Inscrições abertas / em preparação</h2>
          <div className="grid cols-2">{open.map((t) => <TournamentCard key={t.id} t={t} />)}</div>
        </section>
      )}
      {list.data && running.length + open.length === 0 && (
        <div className="alert">Nenhum torneio em andamento ou com inscrições abertas{q ? " com esse nome" : ""}. Veja os já realizados no <Link to="/acervo">Acervo</Link>.</div>
      )}
      {isAdmin && cancelled.length > 0 && (
        <section>
          <h2>Cancelados</h2>
          <p className="muted small">Só administradores veem esta lista. Abra o torneio e use "Apagar torneio" na aba Gerenciar para removê-lo.</p>
          <div className="grid cols-2">{cancelled.map((t) => <TournamentCard key={t.id} t={t} />)}</div>
        </section>
      )}
    </>
  );
}
