import { Link } from "react-router-dom";
import { api, type Match, type TournamentSummary } from "../api";
import { useAuth } from "../auth";
import TournamentCard from "../components/TournamentCard";
import { ErrorBox, Loading, MatchRow } from "../components/ui";
import { useLoad } from "../hooks";

export default function Home() {
  const { user } = useAuth();
  const list = useLoad(() => api<TournamentSummary[]>("/tournaments", { params: { limit: 100 } }), [], 30000);
  const running = (list.data ?? []).filter((t) => t.status === "running");
  const open = (list.data ?? []).filter((t) => t.status === "registration" || t.status === "draft");
  const finished = (list.data ?? []).filter((t) => t.status === "finished").slice(0, 4);

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
      <section className="hero">
        <h1>Torneios Pokémon da comunidade</h1>
        <p className="muted" style={{ maxWidth: 620 }}>
          Acompanhe tabelas, chaveamentos e histórico dos torneios, reporte seus resultados com o replay do Showdown e veja quem avança.
        </p>
        <div className="row">
          <Link className="btn primary" to="/torneios">Ver torneios</Link>
          {!user && <Link className="btn" to="/entrar">Entrar / Cadastrar</Link>}
        </div>
      </section>

      <ErrorBox error={list.error} />
      {list.loading && <Loading />}

      {user && (mine.data?.length ?? 0) > 0 && (
        <section className="card">
          <h2>Seus jogos pendentes</h2>
          {mine.data!.map((m) => (
            <MatchRow key={m.id} m={m} showRound />
          ))}
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
      {finished.length > 0 && (
        <section>
          <h2>Encerrados recentemente</h2>
          <div className="grid cols-2">{finished.map((t) => <TournamentCard key={t.id} t={t} />)}</div>
        </section>
      )}
      {list.data && list.data.length === 0 && <div className="alert">Nenhum torneio cadastrado ainda.</div>}
    </>
  );
}
