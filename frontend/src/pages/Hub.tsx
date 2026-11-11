import { Link } from "react-router-dom";
import { api, type ArchiveSummary, type TournamentSummary } from "../api";
import { useAuth } from "../auth";
import { useLoad } from "../hooks";

/** Tela de entrada: leva às áreas da plataforma (torneios, acervo, jogadores). Pública. */
export default function Hub() {
  const { user } = useAuth();
  const tours = useLoad(() => api<TournamentSummary[]>("/tournaments", { params: { limit: 100 } }), [], 60000);
  const archive = useLoad(() => api<ArchiveSummary[]>("/archive", { params: { limit: 1 } }), [], 60000);
  const running = (tours.data ?? []).filter((t) => t.status === "running").length;
  const open = (tours.data ?? []).filter((t) => t.status === "registration").length;
  const last = archive.data?.[0];

  const cards = [
    {
      to: "/torneios", icon: "🏆", title: "Torneios",
      text: "Torneios em andamento e com inscrições abertas: tabelas, chaveamentos, confrontos e reporte de resultados.",
      extra: tours.data ? `${running} em andamento · ${open} com inscrições abertas` : null,
    },
    {
      to: "/acervo", icon: "📚", title: "Acervo",
      text: "O histórico de todos os torneios da comunidade: campeões, classificações, partidas e séries.",
      extra: last ? `Mais recente: ${last.name}${last.champion ? ` — campeão ${last.champion.name}` : ""}` : null,
    },
    { to: "/jogadores", icon: "👥", title: "Jogadores", text: "Perfis dos jogadores: títulos, pódios, torneios disputados e números.", extra: null },
    { to: "/pokedex", icon: "📖", title: "Pokédex", text: "Todos os Pokémon jogáveis, com as formas separadas e os tiers da Gen 9 National Dex e da Gen 7 lado a lado.", extra: null },
    { to: "/calculadora", icon: "🧮", title: "Calculadora da temporada", text: "Simule gastos e ganhos do seu clube no Draft: salários, inscrição, CT, renda e prêmios, rodada a rodada.", extra: null },
    ...(user ? [{ to: `/jogadores/${user.id}`, icon: "⭐", title: "Meu perfil", text: "Seus títulos, seus torneios e seus números.", extra: null }] : []),
  ];

  return (
    <>
      <section className="hero">
        <h1>Bem-vindo</h1>
        <p className="muted" style={{ maxWidth: 620 }}>Torneios, histórico e jogadores da comunidade Pokémon. Escolha por onde começar.</p>
      </section>
      <div className="grid cols-2">
        {cards.map((c) => (
          <Link key={c.to} to={c.to} className="card hub-card">
            <div className="icon" aria-hidden>{c.icon}</div>
            <h2>{c.title}</h2>
            <p className="muted" style={{ margin: 0 }}>{c.text}</p>
            {c.extra && <p className="small" style={{ margin: ".6rem 0 0" }}>{c.extra}</p>}
          </Link>
        ))}
      </div>
    </>
  );
}
