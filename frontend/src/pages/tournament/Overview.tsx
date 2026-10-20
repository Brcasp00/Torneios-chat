import { Link } from "react-router-dom";
import { api, type DrawRecord, type TournamentDetail } from "../../api";
import { Badge } from "../../components/ui";
import { useLoad } from "../../hooks";
import { fmtDate, playerStatus, stageType, template, tournamentStatus } from "../../labels";

const BR_LABELS: Record<string, string> = { format: "Formato", game: "Jogo", tier: "Tier", team_size: "Time", bring: "Levar", level_cap: "Nível máx.", timer: "Timer" };

export default function Overview({ t }: { t: TournamentDetail }) {
  const draw = useLoad(() => api<DrawRecord>(`/tournaments/${t.id}/draw`).catch(() => null), [t.id, t.status]);
  const br = t.battle_rules ?? {};
  const clauses = (br.clauses as string[] | undefined) ?? [];
  const cfg = t.config ?? {};
  const groups = [...new Set(t.players.map((p) => p.group_label).filter(Boolean))].sort() as string[];

  return (
    <div className="grid cols-2">
      <div>
        <div className="card">
          <h2>Informações</h2>
          <dl className="kv">
            <dt>Formato</dt><dd>{template[t.template] ?? t.template}</dd>
            <dt>Status</dt><dd><Badge kind={t.status}>{tournamentStatus[t.status]}</Badge></dd>
            <dt>Jogadores</dt><dd>{t.players_count}/{t.max_players}</dd>
            <dt>Melhor de</dt><dd>{String(cfg.best_of ?? 1)}</dd>
            <dt>Pontuação</dt><dd>V {String(cfg.points_win ?? 3)} · E {String(cfg.points_draw ?? 1)} · D {String(cfg.points_loss ?? 0)}</dd>
            <dt>Empates</dt><dd>{cfg.allow_draw ? "permitidos" : "não permitidos"}</dd>
            <dt>Criado em</dt><dd>{fmtDate(t.created_at)}</dd>
          </dl>
        </div>

        <div className="card">
          <h2>Regras de batalha</h2>
          <dl className="kv">
            {Object.entries(BR_LABELS).map(([k, label]) => br[k] !== undefined && br[k] !== null && (
              <FragmentRow key={k} label={label} value={typeof br[k] === "boolean" ? (br[k] ? "sim" : "não") : String(br[k])} />
            ))}
            <dt>Replay Showdown</dt><dd>{br.showdown_required === false ? "opcional" : "obrigatório"}</dd>
          </dl>
          {clauses.length > 0 && <p style={{ marginTop: ".6rem" }}>{clauses.map((c) => <span className="chip" key={c}>{c}</span>)}</p>}
          {t.rules_text && <p className="muted" style={{ whiteSpace: "pre-wrap", marginTop: ".6rem" }}>{t.rules_text}</p>}
        </div>

        <div className="card">
          <h2>Fases</h2>
          <ol style={{ margin: 0, paddingLeft: "1.2rem" }}>
            {t.stages.map((s) => (
              <li key={s.id}>
                {s.name} <span className="muted small">({stageType[s.type]})</span> <Badge kind={s.status === "pending" ? "" : s.status}>{s.status === "pending" ? "aguardando" : s.status === "running" ? "em andamento" : "encerrada"}</Badge>
              </li>
            ))}
          </ol>
        </div>
      </div>

      <div>
        {(t.parent || t.subtournaments.length > 0) && (
          <div className="card">
            <h2>Repescagem</h2>
            {t.parent && <p>Este é um subtorneio de <Link to={`/torneios/${t.parent.id}`}>{t.parent.name}</Link>.</p>}
            {t.subtournaments.map((s) => (
              <div key={s.id} className="row between" style={{ marginBottom: ".4rem" }}>
                <span>{s.name} <span className="muted small">{s.players_count}/{s.max_players}</span></span>
                <span className="row"><Badge kind={s.status}>{tournamentStatus[s.status]}</Badge><Link className="btn small" to={`/torneios/${s.id}`}>Abrir</Link></span>
              </div>
            ))}
            {t.repechage.map((r) => (
              <p key={r.rule_id} className="muted small">
                Candidatos da fase "{t.stages.find((s) => s.id === r.stage_id)?.name}":{" "}
                {r.user_ids.length === 0 ? "ainda não definidos" : r.user_ids.map((id) => t.players.find((p) => p.user_id === id)?.name ?? `#${id}`).join(", ")}
              </p>
            ))}
          </div>
        )}

        <div className="card">
          <h2>Jogadores</h2>
          {t.players.length === 0 ? <p className="muted">Nenhum jogador inscrito.</p> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Jogador</th>{groups.length > 0 && <th>Grupo</th>}<th>Seed</th><th>Status</th></tr></thead>
                <tbody>
                  {t.players.map((p) => (
                    <tr key={p.user_id}>
                      <td>{p.name}</td>
                      {groups.length > 0 && <td>{p.group_label ?? "—"}</td>}
                      <td>{p.seed ?? "—"}</td>
                      <td><Badge kind={p.status}>{playerStatus[p.status]}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {draw.data && (
          <div className="card">
            <h2>Sorteio</h2>
            <dl className="kv">
              <dt>Modo</dt><dd>{{ random: "aleatório", pots: "por potes", manual: "manual" }[draw.data.mode] ?? draw.data.mode}</dd>
              <dt>Seed</dt><dd>{draw.data.seed}</dd>
              <dt>Realizado em</dt><dd>{fmtDate(draw.data.drawn_at)}</dd>
            </dl>
            <p className="muted small">A seed permite reproduzir o sorteio e conferir que ele foi justo.</p>
          </div>
        )}
      </div>
    </div>
  );
}

function FragmentRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}
