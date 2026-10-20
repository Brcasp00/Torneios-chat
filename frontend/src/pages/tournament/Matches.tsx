import { useState } from "react";
import { api, type Match, type TournamentDetail } from "../../api";
import { useAuth } from "../../auth";
import { ErrorBox, Loading, MatchRow } from "../../components/ui";
import { useLoad } from "../../hooks";
import { fmtDate, matchStatus } from "../../labels";

export default function Matches({ t }: { t: TournamentDetail }) {
  const { user } = useAuth();
  const [stageId, setStageId] = useState("");
  const [status, setStatus] = useState("");
  const [onlyMine, setOnlyMine] = useState(false);
  const [onlyPostponed, setOnlyPostponed] = useState(false);
  const ms = useLoad(
    () =>
      api<Match[]>(`/tournaments/${t.id}/matches`, {
        params: { stage_id: stageId, status_: status, player_id: onlyMine ? user?.id : undefined, postponed: onlyPostponed ? true : undefined },
      }),
    [t.id, stageId, status, onlyMine, onlyPostponed],
    20000,
  );

  const byStage = new Map<number, Map<string, Match[]>>();
  for (const m of ms.data ?? []) {
    const label = m.group_label === "3rd" ? "Disputa de 3º lugar" : `Rodada ${m.round}`;
    const stage = byStage.get(m.stage_id) ?? new Map<string, Match[]>();
    stage.set(label, [...(stage.get(label) ?? []), m]);
    byStage.set(m.stage_id, stage);
  }

  return (
    <>
      <div className="row" style={{ marginBottom: "1rem" }}>
        <select style={{ maxWidth: 220 }} value={stageId} onChange={(e) => setStageId(e.target.value)}>
          <option value="">Todas as fases</option>
          {t.stages.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <select style={{ maxWidth: 220 }} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Todos os status</option>
          {Object.entries(matchStatus).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        {user && <label className="row" style={{ margin: 0, color: "var(--text)" }}><input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} /> Só os meus</label>}
        <label className="row" style={{ margin: 0, color: "var(--text)" }}><input type="checkbox" checked={onlyPostponed} onChange={(e) => setOnlyPostponed(e.target.checked)} /> Só adiados</label>
      </div>
      <ErrorBox error={ms.error} />
      {ms.loading && <Loading />}
      {[...byStage.entries()].map(([sid, rounds]) => (
        <div key={sid} className="card">
          <h2>{t.stages.find((s) => s.id === sid)?.name}</h2>
          {[...rounds.entries()].map(([label, list]) => (
            <div key={label} style={{ marginBottom: ".9rem" }}>
              <h3>{label}{list[0]?.deadline && list[0].group_label !== "3rd" && (
                <span style={{ textTransform: "none", letterSpacing: 0, marginLeft: ".6rem", color: list.some((m) => m.overdue) ? "var(--red)" : "var(--muted)" }}>
                  · prazo {fmtDate(list[0].deadline)}
                </span>
              )}</h3>
              {list.map((m) => <MatchRow key={m.id} m={m} showRound={!!m.group_label && m.group_label !== "3rd"} />)}
            </div>
          ))}
        </div>
      ))}
      {ms.data?.length === 0 && <div className="alert">Nenhum confronto para mostrar.</div>}
    </>
  );
}
