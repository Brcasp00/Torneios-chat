import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type RoundHistory, type StageHistory, type TournamentDetail } from "../../api";
import SnapshotView from "../../components/SnapshotView";
import { Badge, ErrorBox, Loading, Tabs } from "../../components/ui";
import { useLoad } from "../../hooks";
import { fmtDate, stageType } from "../../labels";

type Sub = "rounds" | "stages" | "log";

export default function History({ t }: { t: TournamentDetail }) {
  const [sub, setSub] = useState<Sub>("stages");
  return (
    <>
      <p className="muted">Estado final de cada fase, tabela ao fim de cada rodada e o registro de todas as alterações. O histórico inclui a repescagem.</p>
      <Tabs<Sub>
        value={sub}
        onChange={setSub}
        tabs={[
          { id: "stages", label: "Fases encerradas" },
          { id: "rounds", label: "Rodada a rodada" },
          { id: "log", label: "Registro de alterações" },
        ]}
      />
      {sub === "stages" && <Stages t={t} />}
      {sub === "rounds" && <Rounds t={t} />}
      {sub === "log" && <Log t={t} />}
    </>
  );
}

function qualifiersOf(t: TournamentDetail, stageId: number): number {
  const stage = t.stages.find((s) => s.id === stageId);
  return Number((stage?.config as { qualifiers_per_group?: number } | null)?.qualifiers_per_group ?? 0);
}

function Stages({ t }: { t: TournamentDetail }) {
  const h = useLoad(() => api<StageHistory[]>(`/tournaments/${t.id}/history/stages`), [t.id], 30000);
  if (h.loading) return <Loading />;
  return (
    <>
      <ErrorBox error={h.error} />
      {(h.data ?? []).map((s) => (
        <div key={s.stage_id} className="card">
          <div className="row between">
            <h2>{s.stage_name}</h2>
            <span className="row">
              {s.tournament_id !== t.id && <Link to={`/torneios/${s.tournament_id}`} className="badge">{s.tournament_name}</Link>}
              <Badge>{stageType[s.stage_type]}</Badge>
              {s.versions > 1 && <Badge kind="postponed">corrigida ({s.versions} versões)</Badge>}
            </span>
          </div>
          <p className="muted small">Encerrada/atualizada em {fmtDate(s.created_at)}</p>
          <SnapshotView data={s.data} qualifiers={qualifiersOf(t, s.stage_id)} />
          <Postponed data={s.data as { played_postponed?: RoundHistory["played_postponed"] }} />
        </div>
      ))}
      {h.data?.length === 0 && <div className="alert">Nenhuma fase foi encerrada ainda.</div>}
    </>
  );
}

function Postponed({ data }: { data: { played_postponed?: RoundHistory["played_postponed"] } }) {
  const list = data.played_postponed ?? [];
  if (list.length === 0) return null;
  return (
    <p className="muted small" style={{ marginTop: ".8rem" }}>
      Jogos adiados disputados depois: {list.map((p) => `${p.player1?.name} × ${p.player2?.name} (rodada ${p.original_round})`).join("; ")}.
    </p>
  );
}

function Rounds({ t }: { t: TournamentDetail }) {
  const h = useLoad(() => api<RoundHistory[]>(`/tournaments/${t.id}/history/rounds`), [t.id], 30000);
  const [stageId, setStageId] = useState<number | null>(null);
  const [round, setRound] = useState<number | null>(null);

  const all = h.data ?? [];
  const stages = [...new Map(all.map((r) => [r.stage_id, r.stage_name])).entries()];
  const sid = stageId ?? stages[0]?.[0] ?? null;
  const rounds = all.filter((r) => r.stage_id === sid);
  useEffect(() => {
    if (rounds.length && !rounds.some((r) => r.round === round)) setRound(rounds[rounds.length - 1].round);
  }, [sid, rounds.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const cur = rounds.find((r) => r.round === round) ?? null;

  if (h.loading) return <Loading />;
  if (all.length === 0) return <>
    <ErrorBox error={h.error} />
    <div className="alert">As tabelas por rodada aparecem quando uma rodada de pontos corridos ou de grupos é concluída.</div>
  </>;

  return (
    <>
      <div className="row" style={{ marginBottom: ".8rem" }}>
        {stages.length > 1 && (
          <select style={{ maxWidth: 260 }} value={sid ?? ""} onChange={(e) => { setStageId(Number(e.target.value)); setRound(null); }}>
            {stages.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        )}
        {rounds.map((r) => (
          <button key={r.round} className={`btn small ${r.round === round ? "primary" : ""}`} onClick={() => setRound(r.round)}>
            Rodada {r.round}
          </button>
        ))}
      </div>
      {cur && (
        <div className="card">
          <div className="row between">
            <h2>Tabela ao fim da rodada {cur.round}</h2>
            {cur.reopened && <Badge kind="postponed">rodada reaberta</Badge>}
          </div>
          <p className="muted small">
            Registrada em {fmtDate(cur.created_at)}. Esta tabela não muda depois de registrada; a coluna J mostra quantos jogos cada um já disputou.
          </p>
          {cur.postponed.length > 0 && (
            <div className="alert warn">
              <strong>Jogos adiados pendentes nesta data:</strong>
              <ul style={{ margin: ".3rem 0 0", paddingLeft: "1.2rem" }}>
                {cur.postponed.map((p) => (
                  <li key={p.match_id}>
                    <Link to={`/matches/${p.match_id}`}>{p.player1?.name} × {p.player2?.name}</Link> (rodada {p.round}{p.group_label ? `, grupo ${p.group_label}` : ""}){p.reason ? ` — ${p.reason}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {cur.played_postponed.length > 0 && (
            <div className="alert ok">
              <strong>Jogos adiados disputados e incluídos nesta tabela:</strong>
              <ul style={{ margin: ".3rem 0 0", paddingLeft: "1.2rem" }}>
                {cur.played_postponed.map((p) => (
                  <li key={p.match_id}><Link to={`/matches/${p.match_id}`}>{p.player1?.name} × {p.player2?.name}</Link> (da rodada {p.original_round})</li>
                ))}
              </ul>
            </div>
          )}
          <SnapshotView data={cur.data} qualifiers={qualifiersOf(t, cur.stage_id)} />
        </div>
      )}
    </>
  );
}

interface Snap { id: number; stage_id: number | null; reason: string | null; created_at: string; kind: string; round: number | null }

function Log({ t }: { t: TournamentDetail }) {
  const h = useLoad(() => api<Snap[]>(`/tournaments/${t.id}/history`, { params: { kind: "change", limit: 200 } }), [t.id], 30000);
  if (h.loading) return <Loading />;
  return (
    <div className="card">
      <ErrorBox error={h.error} />
      <ul className="timeline">
        {(h.data ?? []).map((s) => (
          <li key={s.id}>
            <div>{s.reason ?? "Alteração"}</div>
            <div className="muted small">{fmtDate(s.created_at)}{s.stage_id ? ` · ${t.stages.find((x) => x.id === s.stage_id)?.name ?? ""}` : ""}</div>
          </li>
        ))}
      </ul>
      {h.data?.length === 0 && <p className="muted">Sem alterações registradas.</p>}
    </div>
  );
}
