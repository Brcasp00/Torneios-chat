import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type MatchDetail, type Report, type TimelineEvent } from "../api";
import { useAuth } from "../auth";
import { Badge, ErrorBox, Loading, useAction } from "../components/ui";
import { useLoad } from "../hooks";
import { actionLabel, fmtDate, matchStatus } from "../labels";

export default function MatchPage() {
  const { id } = useParams();
  const mid = Number(id);
  const { user } = useAuth();
  const d = useLoad(() => api<MatchDetail>(`/matches/${mid}`), [mid, user?.id], 15000);
  const tl = useLoad(() => api<TimelineEvent[]>(`/matches/${mid}/timeline`), [mid], 15000);

  if (d.loading) return <Loading />;
  if (d.error || !d.data) return <ErrorBox error={d.error ?? "Confronto não encontrado."} />;
  const m = d.data;
  const refresh = () => { void d.reload(); void tl.reload(); };
  const decided = m.status === "validated";
  const ready = !!(m.player1 && m.player2);
  const winner = decided && m.winner_id ? (m.winner_id === m.player1?.id ? m.player1 : m.player2) : null;
  const bo = m.best_of;
  // Motivo de o reporte não estar disponível (em vez de simplesmente esconder o formulário).
  const reportBlocked: string | null = decided || m.status === "void"
    ? null
    : !user
      ? "Entre na sua conta para reportar o resultado deste confronto."
      : !ready
        ? "Ainda não dá para reportar: o adversário deste confronto ainda não foi definido."
        : m.tournament_status !== "running"
          ? "Ainda não dá para reportar: o torneio não está em andamento."
          : !m.can_report && !m.can_manage
            ? "Só os dois jogadores deste confronto podem reportar o resultado."
            : null;

  return (
    <>
      <p className="small"><Link to={`/torneios/${m.tournament_id}`}>← {m.tournament_name}</Link> · {m.stage_name}</p>
      <div className="card">
        <div className="row between">
          <span className="muted">Rodada {m.round}{m.group_label ? ` · ${m.group_label === "3rd" ? "3º lugar" : `Grupo ${m.group_label}`}` : ""} · melhor de {bo}</span>
          <span className="row">
            {m.postponed && !decided && <Badge kind="postponed">adiado</Badge>}
            {m.is_walkover && <Badge>W.O.</Badge>}
            {m.is_draw && <Badge>empate</Badge>}
            <Badge kind={m.status}>{matchStatus[m.status]}</Badge>
          </span>
        </div>
        <div className="grid" style={{ gridTemplateColumns: "1fr auto 1fr", alignItems: "center", textAlign: "center", margin: "1.2rem 0" }}>
          <div style={{ fontSize: "1.4rem", fontWeight: 800, color: winner?.id === m.player1?.id ? "var(--accent)" : undefined }}>{m.player1?.name ?? "A definir"}</div>
          <div className="score" style={{ fontSize: "1.8rem", fontWeight: 800, padding: ".3rem 1rem", background: "#0e1120", borderRadius: 10 }}>
            {decided ? `${m.p1_wins} × ${m.p2_wins}` : "×"}
          </div>
          <div style={{ fontSize: "1.4rem", fontWeight: 800, color: winner?.id === m.player2?.id ? "var(--accent)" : undefined }}>{m.player2?.name ?? "A definir"}</div>
        </div>
        {decided && bo === 1 && !m.is_draw && <p className="center muted">Pokémon restantes: {m.p1_remaining} × {m.p2_remaining}</p>}
        {winner && <p className="center">Vencedor: <strong>{winner.name}</strong></p>}
        {m.postponed && m.postponed_reason && <div className="alert warn">Adiado: {m.postponed_reason}</div>}
        {m.status === "reported" && <div className="alert warn">Há um reporte aguardando validação do organizador.</div>}
      </div>

      {reportBlocked && <div className="alert">{reportBlocked}</div>}
      {m.can_report && ready && !decided && m.tournament_status === "running" && <ReportForm m={m} onDone={refresh} />}
      {m.can_manage && ready && <StaffPanel m={m} onDone={refresh} />}

      <div className="grid cols-2">
        <div className="card">
          <h2>Reportes</h2>
          {m.reports.length === 0 && <p className="muted">Nenhum reporte enviado.</p>}
          {m.reports.map((r) => <ReportItem key={r.id} r={r} m={m} />)}
        </div>
        <div className="card">
          <h2>Linha do tempo</h2>
          <ErrorBox error={tl.error} />
          <ul className="timeline">
            {(tl.data ?? []).map((e, i) => (
              <li key={i}>
                <div><strong>{actionLabel[e.action] ?? e.action}</strong> {e.actor_name && <span className="muted">— {e.actor_name}</span>}</div>
                <div className="muted small">{fmtDate(e.at)}{typeof e.data?.note === "string" && e.data.note ? ` · ${e.data.note}` : ""}{typeof e.data?.reason === "string" && e.data.reason ? ` · ${e.data.reason}` : ""}</div>
              </li>
            ))}
          </ul>
          {tl.data?.length === 0 && <p className="muted">Sem eventos ainda.</p>}
        </div>
      </div>
    </>
  );
}

function ReportItem({ r, m }: { r: Report; m: MatchDetail }) {
  return (
    <div className="card flat" style={{ padding: ".6rem .8rem", background: "var(--panel-2)" }}>
      <div className="row between">
        <strong>{r.p1_wins} × {r.p2_wins}</strong>
        <Badge kind={r.status === "pending" ? "reported" : r.status}>{{ pending: "pendente", validated: "validado", rejected: "rejeitado" }[r.status] ?? r.status}</Badge>
      </div>
      {m.best_of === 1 && <div className="muted small">Pokémon restantes: {r.p1_remaining} × {r.p2_remaining}</div>}
      {(r.replay_urls ?? []).map((u) => <div key={u} className="small"><a href={u} target="_blank" rel="noreferrer noopener">Replay: {u.replace("https://replay.pokemonshowdown.com/", "")}</a></div>)}
      {r.notes && <div className="muted small">"{r.notes}"</div>}
      <div className="muted small">{fmtDate(r.created_at)}{r.review_note ? ` · ${r.review_note}` : ""}</div>
    </div>
  );
}

function ScoreFields({ m, v, set }: { m: MatchDetail; v: Score; set: (s: Score) => void }) {
  const need = Math.floor(m.best_of / 2) + 1;
  return (
    <div className="form-grid">
      <div className="field"><label>Vitórias de {m.player1?.name}</label><input type="number" min={0} max={need} value={v.p1_wins} onChange={(e) => set({ ...v, p1_wins: e.target.value })} required /></div>
      <div className="field"><label>Vitórias de {m.player2?.name}</label><input type="number" min={0} max={need} value={v.p2_wins} onChange={(e) => set({ ...v, p2_wins: e.target.value })} required /></div>
      {m.best_of === 1 && (
        <>
          <div className="field"><label>Pokémon vivos de {m.player1?.name}</label><input type="number" min={0} max={6} value={v.p1_remaining} onChange={(e) => set({ ...v, p1_remaining: e.target.value })} /></div>
          <div className="field"><label>Pokémon vivos de {m.player2?.name}</label><input type="number" min={0} max={6} value={v.p2_remaining} onChange={(e) => set({ ...v, p2_remaining: e.target.value })} /></div>
        </>
      )}
    </div>
  );
}

interface Score { p1_wins: string; p2_wins: string; p1_remaining: string; p2_remaining: string; replays: string; notes: string }
const blank: Score = { p1_wins: "", p2_wins: "", p1_remaining: "0", p2_remaining: "0", replays: "", notes: "" };

function payload(v: Score) {
  return {
    p1_wins: Number(v.p1_wins), p2_wins: Number(v.p2_wins),
    p1_remaining: Number(v.p1_remaining || 0), p2_remaining: Number(v.p2_remaining || 0),
    replay_urls: v.replays.split("\n").map((s) => s.trim()).filter(Boolean),
    notes: v.notes || null,
  };
}

function ReportForm({ m, onDone }: { m: MatchDetail; onDone: () => void }) {
  const [v, setV] = useState<Score>(blank);
  const { run, busy, box } = useAction();
  const submit = async () => { if (await run(() => api(`/matches/${m.id}/report`, { body: payload(v) }), "Reporte enviado! Aguarde a validação do organizador.")) { setV(blank); onDone(); } };
  return (
    <form className="card" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
      <h2>Reportar resultado</h2>
      <p className="muted small">
        Informe o placar da série. {m.best_of === 1 ? "Em melhor de 1, o vencedor precisa ter ao menos 1 Pokémon vivo e o perdedor 0. " : ""}
        Empate (onde permitido) é 0 × 0. Um novo reporte substitui o pendente.
      </p>
      {box}
      <ScoreFields m={m} v={v} set={setV} />
      <div className="field"><label>Links dos replays do Showdown (um por linha)</label><textarea value={v.replays} onChange={(e) => setV({ ...v, replays: e.target.value })} placeholder="https://replay.pokemonshowdown.com/gen9ou-123456789" /></div>
      <div className="field"><label>Observações (opcional)</label><input value={v.notes} onChange={(e) => setV({ ...v, notes: e.target.value })} maxLength={1000} /></div>
      <button className="btn primary" disabled={busy}>{busy ? "Enviando…" : "Enviar reporte"}</button>
    </form>
  );
}

function StaffPanel({ m, onDone }: { m: MatchDetail; onDone: () => void }) {
  const { run, busy, box } = useAction();
  const [v, setV] = useState<Score>(blank);
  const [draw, setDraw] = useState(false);
  const [note, setNote] = useState("");
  const pending = m.reports.filter((r) => r.status === "pending");
  const decided = m.status === "validated";
  const act = async (fn: () => Promise<unknown>, ok: string) => { if (await run(fn, ok)) onDone(); };
  const canPostpone = m.status === "scheduled" && !m.postponed;

  return (
    <div className="card">
      <h2>Painel do organizador</h2>
      {box}
      <div className="field"><label>Observação / motivo (opcional)</label><input value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} /></div>

      {pending.length > 0 && !decided && (
        <div className="row" style={{ marginBottom: "1rem" }}>
          <span>Reporte pendente: <strong>{pending[pending.length - 1].p1_wins} × {pending[pending.length - 1].p2_wins}</strong></span>
          <button className="btn primary" disabled={busy} onClick={() => act(() => api(`/matches/${m.id}/validate`, { body: { note: note || null } }), "Resultado validado.")}>Validar</button>
          <button className="btn danger" disabled={busy} onClick={() => act(() => api(`/matches/${m.id}/reject`, { body: { note: note || null } }), "Reporte rejeitado.")}>Rejeitar</button>
        </div>
      )}

      <details>
        <summary style={{ cursor: "pointer", marginBottom: ".6rem" }}>{decided ? "Corrigir resultado" : "Lançar resultado direto"}</summary>
        <ScoreFields m={m} v={v} set={setV} />
        <div className="field"><label>Replays (um por linha)</label><textarea value={v.replays} onChange={(e) => setV({ ...v, replays: e.target.value })} /></div>
        <div className="field inline"><input id="dr" type="checkbox" checked={draw} onChange={(e) => setDraw(e.target.checked)} /><label htmlFor="dr">Empate (0 × 0)</label></div>
        <button className="btn" disabled={busy} onClick={() => act(() => api(`/matches/${m.id}/result`, { body: { ...payload(v), is_draw: draw } }), "Resultado lançado.")}>Gravar resultado</button>
      </details>

      <div className="row" style={{ marginTop: "1rem" }}>
        {!decided && m.player1 && m.player2 && (
          <>
            <button className="btn" disabled={busy} onClick={() => act(() => api(`/matches/${m.id}/walkover`, { body: { winner_id: m.player1!.id, note: note || null } }), "W.O. aplicado.")}>W.O. p/ {m.player1.name}</button>
            <button className="btn" disabled={busy} onClick={() => act(() => api(`/matches/${m.id}/walkover`, { body: { winner_id: m.player2!.id, note: note || null } }), "W.O. aplicado.")}>W.O. p/ {m.player2.name}</button>
          </>
        )}
        {decided && <button className="btn danger" disabled={busy} onClick={() => confirm("Invalidar este resultado? A tabela/chaveamento será recalculada.") && act(() => api(`/matches/${m.id}/invalidate`, { body: { note: note || null } }), "Resultado invalidado.")}>Invalidar resultado</button>}
        {canPostpone && <button className="btn" disabled={busy} onClick={() => act(() => api(`/matches/${m.id}/postpone`, { body: { reason: note || null } }), "Jogo adiado.")}>Adiar jogo</button>}
        {m.postponed && !decided && <button className="btn" disabled={busy} onClick={() => act(() => api(`/matches/${m.id}/resume`, { method: "POST", body: {} }), "Adiamento removido.")}>Remover adiamento</button>}
      </div>
      <p className="muted small" style={{ marginTop: ".6rem" }}>Adiar só vale para pontos corridos e fase de grupos. A fase não encerra enquanto houver jogo adiado pendente.</p>
    </div>
  );
}
