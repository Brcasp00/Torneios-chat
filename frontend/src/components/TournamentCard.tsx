import { Link } from "react-router-dom";
import type { TournamentSummary } from "../api";
import { template, tournamentStatus } from "../labels";
import { Badge } from "./ui";

export default function TournamentCard({ t }: { t: TournamentSummary }) {
  return (
    <Link to={`/torneios/${t.id}`} className="card" style={{ display: "block", color: "inherit" }}>
      <div className="row between">
        <h2 style={{ margin: 0 }}>{t.name}</h2>
        <Badge kind={t.status}>{tournamentStatus[t.status] ?? t.status}</Badge>
      </div>
      <p className="muted small" style={{ margin: ".4rem 0 0" }}>
        {template[t.template] ?? t.template} · {t.players_count}/{t.max_players} jogadores
      </p>
    </Link>
  );
}
