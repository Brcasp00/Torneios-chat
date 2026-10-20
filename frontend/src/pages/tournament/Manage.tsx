import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type DrawOut, type Match, type TournamentDetail } from "../../api";
import { useAuth } from "../../auth";
import { Badge, useAction } from "../../components/ui";
import { useLoad } from "../../hooks";
import { tournamentStatus } from "../../labels";

const NEXT_STATUS: Record<string, { to: string; label: string; danger?: boolean }[]> = {
  draft: [{ to: "registration", label: "Abrir inscrições" }, { to: "cancelled", label: "Cancelar torneio", danger: true }],
  registration: [{ to: "draft", label: "Voltar para rascunho" }, { to: "cancelled", label: "Cancelar torneio", danger: true }],
  running: [{ to: "finished", label: "Encerrar manualmente" }, { to: "cancelled", label: "Cancelar torneio", danger: true }],
  finished: [],
  cancelled: [],
};

export default function Manage({ t, onChanged }: { t: TournamentDetail; onChanged: () => void }) {
  const editable = t.status === "draft" || t.status === "registration";
  return (
    <div className="stack">
      <StatusCard t={t} onChanged={onChanged} />
      {(editable || t.status === "running") && <PlayersCard t={t} onChanged={onChanged} editable={editable} />}
      {editable && <DrawCard t={t} onChanged={onChanged} />}
      {t.status === "running" && <PostponeCard t={t} onChanged={onChanged} />}
      <SubtournamentsCard t={t} onChanged={onChanged} />
    </div>
  );
}

function StatusCard({ t, onChanged }: { t: TournamentDetail; onChanged: () => void }) {
  const { run, busy, box } = useAction();
  const { isAdmin } = useAuth();
  const nav = useNavigate();
  const del = async () => {
    if (!confirm(`Apagar o torneio "${t.name}" e tudo que ele contém (inclusive subtorneios)? Isso não pode ser desfeito.`)) return;
    if (await run(() => api(`/tournaments/${t.id}`, { method: "DELETE" }))) nav("/torneios");
  };
  return (
    <div className="card">
      <h2>Situação do torneio</h2>
      {box}
      <p>Status atual: <Badge kind={t.status}>{tournamentStatus[t.status]}</Badge></p>
      <div className="row">
        {(NEXT_STATUS[t.status] ?? []).map((n) => (
          <button key={n.to} className={`btn ${n.danger ? "danger" : ""}`} disabled={busy}
            onClick={async () => {
              if (n.danger && !confirm("Confirma?")) return;
              if (await run(() => api(`/tournaments/${t.id}/status`, { method: "PATCH", body: { status: n.to } }))) onChanged();
            }}>
            {n.label}
          </button>
        ))}
        {(isAdmin || t.status === "draft") && <button className="btn danger" disabled={busy} onClick={del}>Apagar torneio</button>}
      </div>
    </div>
  );
}

function PlayersCard({ t, onChanged, editable }: { t: TournamentDetail; onChanged: () => void; editable: boolean }) {
  const [q, setQ] = useState("");
  const { run, busy, box } = useAction();
  const found = useLoad(() => api<{ id: number; name: string }[]>("/users", { params: { q, limit: 20 } }), [q]);
  const inside = new Set(t.players.map((p) => p.user_id));
  const [pots, setPots] = useState<Record<number, string>>({});

  const add = async (id: number) => { if (await run(() => api(`/tournaments/${t.id}/players`, { body: { user_ids: [id] } }))) onChanged(); };
  const remove = async (id: number, name: string) => {
    const msg = editable ? `Remover ${name} da lista?` : `Marcar ${name} como desistente? Os jogos pendentes dele viram W.O. para os adversários.`;
    if (confirm(msg) && (await run(() => api(`/tournaments/${t.id}/players/${id}`, { method: "DELETE" })))) onChanged();
  };
  const savePots = async () => {
    const assignments = t.players.map((p) => ({ user_id: p.user_id, pot: pots[p.user_id] !== undefined ? (pots[p.user_id] === "" ? null : Number(pots[p.user_id])) : p.pot }));
    if (await run(() => api(`/tournaments/${t.id}/pots`, { method: "PUT", body: { assignments } }), "Potes salvos.")) onChanged();
  };

  return (
    <div className="card">
      <h2>Jogadores ({t.players.filter((p) => p.status !== "withdrawn").length}/{t.max_players})</h2>
      {box}
      {editable && (
        <div className="field">
          <label htmlFor="search">Inscrever jogador (busque pelo nome)</label>
          <input id="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nome do treinador" />
          <div style={{ marginTop: ".5rem" }}>
            {(found.data ?? []).filter((u) => !inside.has(u.id)).slice(0, 8).map((u) => (
              <button key={u.id} className="chip" style={{ cursor: "pointer", color: "var(--text)" }} disabled={busy} onClick={() => add(u.id)}>+ {u.name}</button>
            ))}
          </div>
        </div>
      )}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Jogador</th>{editable && <th>Pote</th>}<th></th></tr></thead>
          <tbody>
            {t.players.filter((p) => p.status !== "withdrawn").map((p) => (
              <tr key={p.user_id}>
                <td>{p.name}</td>
                {editable && (
                  <td style={{ width: 90 }}>
                    <input type="number" min={1} max={8} value={pots[p.user_id] ?? (p.pot ?? "")} onChange={(e) => setPots({ ...pots, [p.user_id]: e.target.value })} />
                  </td>
                )}
                <td className="right"><button className="btn small danger" disabled={busy} onClick={() => remove(p.user_id, p.name)}>{editable ? "Remover" : "Desistência"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editable && t.players.length > 0 && (
        <div className="row" style={{ marginTop: ".6rem" }}>
          <button className="btn small" disabled={busy} onClick={savePots}>Salvar potes</button>
          <span className="muted small">Pote 1 = mais forte (cabeças de chave). Deixe vazio para não usar potes.</span>
        </div>
      )}
    </div>
  );
}

function DrawCard({ t, onChanged }: { t: TournamentDetail; onChanged: () => void }) {
  const [seed, setSeed] = useState("");
  const [usePots, setUsePots] = useState(true);
  const [preview, setPreview] = useState<DrawOut | null>(null);
  const { run, busy, box } = useAction();
  const body = () => ({ seed: seed ? Number(seed) : undefined, use_pots: usePots });
  const count = t.players.filter((p) => p.status === "active").length;

  const doPreview = async () => {
    await run(async () => {
      const r = await api<DrawOut>(`/tournaments/${t.id}/draw`, { body: body() });
      setPreview(r);
      setSeed(String(r.seed)); // fixa a seed para o início reproduzir exatamente a prévia
    });
  };
  const start = async () => {
    if (!confirm("Iniciar o torneio com este sorteio? Depois disso não dá para mudar os inscritos.")) return;
    if (await run(() => api(`/tournaments/${t.id}/start`, { body: body() }))) onChanged();
  };

  return (
    <div className="card">
      <h2>Sorteio e início</h2>
      {box}
      {t.parent_id && <div className="alert warn">Subtorneio: só pode começar quando o torneio principal estiver em andamento e com exatamente {t.max_players} jogadores.</div>}
      <p className="muted">{count}/{t.max_players} jogadores inscritos. O torneio só começa com todas as vagas preenchidas.</p>
      <div className="form-grid">
        <div className="field"><label htmlFor="seed">Seed do sorteio (opcional)</label><input id="seed" type="number" min={1} value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="aleatória" /></div>
        <div className="field inline" style={{ alignSelf: "end" }}><input id="pots" type="checkbox" checked={usePots} onChange={(e) => setUsePots(e.target.checked)} /><label htmlFor="pots">Usar potes (se definidos)</label></div>
      </div>
      <div className="row">
        <button className="btn" disabled={busy || count < 2} onClick={doPreview}>Prévia do sorteio</button>
        <button className="btn primary" disabled={busy || count !== t.max_players} onClick={start}>Sortear e iniciar</button>
      </div>
      {preview && (
        <div style={{ marginTop: "1rem" }}>
          <p className="muted small">Modo: {preview.mode} · seed {preview.seed}. Esta é só uma prévia; ao iniciar, a mesma seed gera exatamente estes confrontos.</p>
          {preview.rounds.slice(0, 3).map((r) => (
            <div key={r.round} style={{ marginBottom: ".6rem" }}>
              <h3>Rodada {r.round}</h3>
              {r.matches.map((m, i) => (
                <div key={i} className="match" style={{ gridTemplateColumns: "1fr auto 1fr" }}>
                  <span className="p">{m.player1.name}</span><span className="score">×</span><span className="p r">{m.player2.name}</span>
                </div>
              ))}
            </div>
          ))}
          {preview.rounds.length > 3 && <p className="muted small">… e mais {preview.rounds.length - 3} rodadas.</p>}
        </div>
      )}
    </div>
  );
}

function PostponeCard({ t, onChanged }: { t: TournamentDetail; onChanged: () => void }) {
  const stages = t.stages.filter((s) => (s.type === "league" || s.type === "groups") && s.status === "running");
  const [stageId, setStageId] = useState<number | "">(stages[0]?.id ?? "");
  const [round, setRound] = useState("");
  const [group, setGroup] = useState("");
  const [reason, setReason] = useState("");
  const { run, busy, box } = useAction();
  const ms = useLoad(() => api<Match[]>(`/tournaments/${t.id}/matches`, { params: { stage_id: stageId } }), [t.id, stageId]);
  if (stages.length === 0) return null;
  const rounds = [...new Set((ms.data ?? []).map((m) => m.round))].sort((a, b) => a - b);
  const labels = [...new Set((ms.data ?? []).map((m) => m.group_label).filter(Boolean))].sort() as string[];
  const pending = (ms.data ?? []).filter((m) => m.postponed && m.status !== "validated");

  const act = async (kind: "postpone" | "resume") => {
    const ok = await run(
      () => api(`/tournaments/${t.id}/rounds/${kind}`, { body: { stage_id: stageId, round: Number(round), group_label: group || null, reason: reason || null } }),
      kind === "postpone" ? "Rodada adiada." : "Adiamento removido.",
    );
    if (ok) { await ms.reload(); onChanged(); }
  };

  return (
    <div className="card">
      <h2>Adiar rodada</h2>
      <p className="muted">
        Marca os jogos pendentes da rodada como adiados. Eles ainda podem ser jogados e reportados depois, mas a fase só encerra quando todos forem disputados.
        Para adiar um jogo específico, abra o confronto.
      </p>
      {box}
      <div className="form-grid">
        <div className="field"><label>Fase</label><select value={stageId} onChange={(e) => { setStageId(Number(e.target.value)); setRound(""); }}>{stages.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div className="field"><label>Rodada</label><select value={round} onChange={(e) => setRound(e.target.value)}><option value="">Escolha…</option>{rounds.map((r) => <option key={r} value={r}>Rodada {r}</option>)}</select></div>
        {labels.length > 0 && <div className="field"><label>Grupo</label><select value={group} onChange={(e) => setGroup(e.target.value)}><option value="">Todos</option>{labels.map((l) => <option key={l} value={l}>{l}</option>)}</select></div>}
        <div className="field"><label>Motivo (opcional)</label><input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} /></div>
      </div>
      <div className="row">
        <button className="btn primary" disabled={busy || !round} onClick={() => act("postpone")}>Adiar rodada</button>
        <button className="btn" disabled={busy || !round} onClick={() => act("resume")}>Remover adiamento</button>
      </div>
      {pending.length > 0 && (
        <div style={{ marginTop: "1rem" }}>
          <h3>Jogos adiados pendentes</h3>
          {pending.map((m) => (
            <Link key={m.id} to={`/matches/${m.id}`} className="match" style={{ gridTemplateColumns: "1fr auto 1fr auto" }}>
              <span className="p">{m.player1?.name}</span><span className="score">×</span><span className="p r">{m.player2?.name}</span>
              <span className="meta muted small">R{m.round}{m.group_label ? ` · ${m.group_label}` : ""}{m.postponed_reason ? ` · ${m.postponed_reason}` : ""}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function SubtournamentsCard({ t, onChanged }: { t: TournamentDetail; onChanged: () => void }) {
  const { run, busy, box } = useAction();
  if (t.parent_id) return null;
  const hasRepechage = t.rules.some((r) => r.target === "repechage");
  return (
    <div className="card">
      <h2>Subtorneios (repescagem)</h2>
      {box}
      <p className="muted">
        {hasRepechage
          ? "Este torneio envia candidatos à repescagem. Crie o subtorneio; com apenas um, a ligação é automática e os candidatos entram quando a fase de origem terminar."
          : "Este torneio não tem regra de repescagem, mas você ainda pode criar um subtorneio manual."}
      </p>
      {t.repechage.length > 0 && t.subtournaments.length > 1 && t.repechage.map((r) => (
        <div key={r.rule_id} className="field">
          <label>Para onde vão os candidatos da fase "{t.stages.find((s) => s.id === r.stage_id)?.name}"</label>
          <select value={r.subtournament_id ?? ""} disabled={busy}
            onChange={async (e) => {
              const v = e.target.value ? Number(e.target.value) : null;
              if (await run(() => api(`/tournaments/${t.id}/rules/${r.rule_id}/subtournament`, { method: "PUT", body: { subtournament_id: v } }), "Ligação atualizada.")) onChanged();
            }}>
            <option value="">Escolha o subtorneio…</option>
            {t.subtournaments.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      ))}
      <Link className="btn" to={`/torneios/novo?parent=${t.id}`}>Criar subtorneio</Link>
    </div>
  );
}
