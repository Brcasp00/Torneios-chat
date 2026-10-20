import { useState, type InputHTMLAttributes, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Match, StandingRow } from "../api";
import { matchStatus, scoreText } from "../labels";

export function Loading({ text = "Carregando…" }: { text?: string }) {
  return <div className="loading">{text}</div>;
}

export function ErrorBox({ error }: { error: string | null }) {
  return error ? <div className="alert error">{error}</div> : null;
}

export function Badge({ kind, children }: { kind?: string; children: ReactNode }) {
  return <span className={`badge ${kind ?? ""}`}>{children}</span>;
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string }[]; value: T; onChange: (t: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} className={`tab ${value === t.id ? "active" : ""}`} onClick={() => onChange(t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

/** Mensagem de sucesso/erro de uma ação + executor que trata exceções. */
export function useAction() {
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>, okText?: string): Promise<boolean> => {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      if (okText) setMsg({ kind: "ok", text: okText });
      return true;
    } catch (e) {
      setMsg({ kind: "error", text: e instanceof Error ? e.message : "Erro inesperado." });
      return false;
    } finally {
      setBusy(false);
    }
  };
  const box = msg ? <div className={`alert ${msg.kind}`}>{msg.text}</div> : null;
  return { run, busy, box, setMsg };
}

export function StandingsTable({ rows, highlight, qualifiers = 0 }: { rows: StandingRow[]; highlight?: number; qualifiers?: number }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Jogador</th>
            <th className="num" title="Pontos">Pts</th>
            <th className="num" title="Jogos disputados">J</th>
            <th className="num" title="Vitórias">V</th>
            <th className="num" title="Empates">E</th>
            <th className="num" title="Derrotas">D</th>
            <th className="num" title="Saldo de Pokémon">Saldo</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.user_id} className={r.user_id === highlight ? "me" : ""}>
              <td>
                <span className={`pos ${r.position === 1 ? "p1" : r.position <= qualifiers ? "q" : ""}`}>{r.position}</span>
              </td>
              <td>
                {r.name} {r.withdrawn && <span className="badge withdrawn">desistiu</span>}
              </td>
              <td className="num"><strong>{r.points}</strong></td>
              <td className="num">{r.played}</td>
              <td className="num">{r.wins}</td>
              <td className="num">{r.draws}</td>
              <td className="num">{r.losses}</td>
              <td className="num">{r.saldo > 0 ? `+${r.saldo}` : r.saldo}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function MatchRow({ m, showRound = false }: { m: Match; showRound?: boolean }) {
  const decided = m.status === "validated" && m.winner_id !== null;
  const cls = (id?: number) => (decided && id === m.winner_id ? "win" : "");
  return (
    <Link to={`/matches/${m.id}`} className="match">
      <span className={`p ${m.player1 ? cls(m.player1.id) : "tbd"}`}>{m.player1?.name ?? "A definir"}</span>
      <span className="score">{scoreText(m)}</span>
      <span className={`p r ${m.player2 ? cls(m.player2.id) : "tbd"}`}>{m.player2?.name ?? "A definir"}</span>
      <span className="meta">
        {showRound && <span className="muted small">R{m.round}{m.group_label ? ` · ${m.group_label}` : ""}</span>}
        {m.postponed && m.status !== "validated" && <Badge kind="postponed">adiado</Badge>}
        {m.is_walkover && <Badge>W.O.</Badge>}
        {m.is_draw && <Badge>empate</Badge>}
        <Badge kind={m.status}>{matchStatus[m.status] ?? m.status}</Badge>
      </span>
    </Link>
  );
}

export function BracketMatch({ m }: { m: Match }) {
  const decided = m.status === "validated" && m.winner_id !== null;
  const line = (p: Match["player1"], wins: number | null) => (
    <div className={`line ${p ? (decided && p.id === m.winner_id ? "win" : "") : "tbd"}`}>
      <span>{p?.name ?? "A definir"}</span>
      <span>{m.status === "validated" ? wins : ""}</span>
    </div>
  );
  return (
    <Link to={`/matches/${m.id}`} className="bmatch">
      {line(m.player1, m.p1_wins)}
      {line(m.player2, m.p2_wins)}
    </Link>
  );
}

/** Campo de senha com botão para mostrar/ocultar o que foi digitado. */
export function PasswordInput(props: Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const [show, setShow] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <input {...props} type={show ? "text" : "password"} style={{ ...props.style, paddingRight: "5.2rem" }} />
      <button
        type="button"
        className="btn small ghost"
        style={{ position: "absolute", right: 4, top: "50%", transform: "translateY(-50%)" }}
        aria-pressed={show}
        aria-label={show ? "Ocultar senha" : "Mostrar senha"}
        onClick={() => setShow(!show)}
      >
        {show ? "Ocultar" : "Mostrar"}
      </button>
    </div>
  );
}
