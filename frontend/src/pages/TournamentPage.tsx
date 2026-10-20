import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type TournamentDetail } from "../api";
import { Badge, ErrorBox, Loading, Tabs } from "../components/ui";
import { useLoad } from "../hooks";
import { template, tournamentStatus } from "../labels";
import Bracket from "./tournament/Bracket";
import History from "./tournament/History";
import Manage from "./tournament/Manage";
import Matches from "./tournament/Matches";
import Overview from "./tournament/Overview";
import Standings from "./tournament/Standings";

type Tab = "overview" | "standings" | "bracket" | "matches" | "history" | "manage";

export default function TournamentPage() {
  const { id } = useParams();
  const tid = Number(id);
  const [tab, setTab] = useState<Tab>("overview");
  const d = useLoad(() => api<TournamentDetail>(`/tournaments/${tid}`), [tid], 20000);

  if (d.loading) return <Loading />;
  if (d.error || !d.data) return <ErrorBox error={d.error ?? "Torneio não encontrado."} />;
  const t = d.data;

  const hasTable = t.stages.some((s) => s.type === "league" || s.type === "groups");
  const hasBracket = t.stages.some((s) => s.type === "knockout");
  const tabs: { id: Tab; label: string }[] = [{ id: "overview", label: "Visão geral" }];
  if (hasTable) tabs.push({ id: "standings", label: "Tabela" });
  if (hasBracket) tabs.push({ id: "bracket", label: "Chaveamento" });
  tabs.push({ id: "matches", label: "Confrontos" }, { id: "history", label: "Histórico" });
  if (t.can_manage) tabs.push({ id: "manage", label: "Gerenciar" });
  const current = tabs.some((x) => x.id === tab) ? tab : "overview";

  return (
    <>
      {t.parent && <p className="small"><Link to={`/torneios/${t.parent.id}`}>← {t.parent.name}</Link> (subtorneio)</p>}
      <div className="row between">
        <div>
          <h1 style={{ marginBottom: ".2rem" }}>{t.name}</h1>
          <span className="muted">{template[t.template] ?? t.template} · {t.players_count}/{t.max_players} jogadores</span>
        </div>
        <div className="row">
          <Badge kind={t.status}>{tournamentStatus[t.status]}</Badge>
          {t.subtournaments.map((s) => (
            <Link key={s.id} className="btn small" to={`/torneios/${s.id}`}>Repescagem: {s.name} ({tournamentStatus[s.status]})</Link>
          ))}
        </div>
      </div>

      <Tabs<Tab> tabs={tabs} value={current} onChange={setTab} />
      {current === "overview" && <Overview t={t} />}
      {current === "standings" && <Standings t={t} />}
      {current === "bracket" && <Bracket t={t} />}
      {current === "matches" && <Matches t={t} />}
      {current === "history" && <History t={t} />}
      {current === "manage" && <Manage t={t} onChanged={() => void d.reload()} />}
    </>
  );
}
