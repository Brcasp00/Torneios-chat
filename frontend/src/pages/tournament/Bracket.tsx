import { api, type BracketStage, type TournamentDetail } from "../../api";
import { BracketMatch, ErrorBox, Loading } from "../../components/ui";
import { useLoad } from "../../hooks";

export default function Bracket({ t }: { t: TournamentDetail }) {
  const br = useLoad(() => api<BracketStage[]>(`/tournaments/${t.id}/bracket`), [t.id], 20000);
  if (br.loading) return <Loading />;
  return (
    <>
      <ErrorBox error={br.error} />
      {(br.data ?? []).map((s) => (
        <div key={s.stage_id} className="card">
          <div className="row between">
            <h2>{s.stage_name}</h2>
          </div>
          {s.rounds.length === 0 ? (
            <p className="muted">O chaveamento aparece quando a fase começa.</p>
          ) : (
            <div className="bracket">
              {s.rounds.map((r) => (
                <div key={r.round} className="col">
                  <h3>{r.name}</h3>
                  {r.matches.map((m) => <BracketMatch key={m.id} m={m} />)}
                </div>
              ))}
              {s.champion && (
                <div className="col" style={{ minWidth: 200 }}>
                  <h3>Campeão</h3>
                  <div className="champion"><div className="muted small">🏆</div><div className="name">{s.champion.name}</div></div>
                </div>
              )}
            </div>
          )}
          {s.third_place && (
            <div style={{ maxWidth: 300, marginTop: "1rem" }}>
              <h3>Disputa de 3º lugar</h3>
              <BracketMatch m={s.third_place} />
            </div>
          )}
        </div>
      ))}
      {br.data?.length === 0 && <div className="alert">Este torneio não tem fase de mata-mata.</div>}
    </>
  );
}
