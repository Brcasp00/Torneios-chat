import { api, type StageStandings, type TournamentDetail } from "../../api";
import { useAuth } from "../../auth";
import { ErrorBox, Loading, StandingsTable } from "../../components/ui";
import { useLoad } from "../../hooks";

export default function Standings({ t }: { t: TournamentDetail }) {
  const { user } = useAuth();
  const st = useLoad(() => api<StageStandings[]>(`/tournaments/${t.id}/standings`), [t.id], 20000);
  if (st.loading) return <Loading />;
  return (
    <>
      <ErrorBox error={st.error} />
      {(st.data ?? []).map((s) => {
        const stage = t.stages.find((x) => x.id === s.stage_id);
        const q = Number((stage?.config as { qualifiers_per_group?: number } | null)?.qualifiers_per_group ?? 0);
        return (
          <div key={s.stage_id} className="card">
            <h2>{s.stage_name}</h2>
            {s.stage_type === "groups" ? (
              <div className="grid cols-2">
                {s.groups.map((g) => (
                  <div key={g.label}>
                    <h3>Grupo {g.label}</h3>
                    <StandingsTable rows={g.rows} highlight={user?.id} qualifiers={q} />
                  </div>
                ))}
              </div>
            ) : (
              <StandingsTable rows={s.rows} highlight={user?.id} />
            )}
          </div>
        );
      })}
      {st.data?.length === 0 && <div className="alert">Este torneio não tem fase com tabela de pontos.</div>}
      <p className="muted small">Desempate: saldo de Pokémon (só melhor de 1), vitórias e confronto direto. J = jogos disputados — quem tem menos jogos pode ter partida adiada.</p>
    </>
  );
}
