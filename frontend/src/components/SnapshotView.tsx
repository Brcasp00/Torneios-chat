import { Link } from "react-router-dom";
import type { SnapshotData } from "../api";
import { StandingsTable } from "./ui";

/** Mostra o conteúdo de um registro do histórico: tabela, grupos ou confrontos de mata-mata/rodada. */
export default function SnapshotView({ data, qualifiers = 0 }: { data: SnapshotData; qualifiers?: number }) {
  const names = data.players ?? {};
  const nm = (id: number | null) => (id === null ? "A definir" : names[String(id)] ?? `#${id}`);
  const rounds = new Map<number, NonNullable<SnapshotData["matches"]>>();
  for (const m of data.matches ?? []) rounds.set(m.round, [...(rounds.get(m.round) ?? []), m]);

  return (
    <div className="stack">
      {data.rows && <StandingsTable rows={data.rows} qualifiers={qualifiers} />}
      {data.groups &&
        Object.entries(data.groups).map(([label, rows]) => (
          <div key={label}>
            <h3>Grupo {label}</h3>
            <StandingsTable rows={rows} qualifiers={qualifiers} />
          </div>
        ))}
      {data.ranking && data.ranking.length > 0 && (
        <div>
          <h3>Classificação final</h3>
          <div className="table-wrap">
            <table>
              <tbody>
                {data.ranking.map((r) => (
                  <tr key={r.user_id}>
                    <td><span className={`pos ${r.position === 1 ? "p1" : ""}`}>{r.position}º</span></td>
                    <td>{r.name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {rounds.size > 0 &&
        [...rounds.entries()].sort((a, b) => a[0] - b[0]).map(([round, ms]) => (
          <div key={round}>
            <h3>Rodada {round}</h3>
            {ms.map((m) => (
              <Link key={m.id} to={`/matches/${m.id}`} className="match">
                <span className={`p ${m.winner_id === m.player1_id && m.winner_id ? "win" : ""}`}>{nm(m.player1_id)}</span>
                <span className="score">{m.status === "validated" ? `${m.p1_wins} × ${m.p2_wins}` : "×"}</span>
                <span className={`p r ${m.winner_id === m.player2_id && m.winner_id ? "win" : ""}`}>{nm(m.player2_id)}</span>
                <span className="meta muted small">{m.group_label === "3rd" ? "3º lugar" : ""}</span>
              </Link>
            ))}
          </div>
        ))}
    </div>
  );
}
