import { useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAction } from "../components/ui";
import { roleLabel } from "../labels";

export default function Account() {
  const { user } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const { run, busy, box } = useAction();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const ok = await run(() => api("/auth/change-password", { body: { current_password: current, new_password: next } }), "Senha alterada.");
    if (ok) {
      setCurrent("");
      setNext("");
    }
  };

  return (
    <div style={{ maxWidth: 480 }}>
      <h1>Minha conta</h1>
      <div className="card">
        <dl className="kv">
          <dt>Nome</dt><dd>{user?.name}</dd>
          <dt>Papel</dt><dd>{user ? roleLabel[user.role] : ""}</dd>
        </dl>
      </div>
      <form className="card" onSubmit={submit}>
        <h2>Alterar senha</h2>
        {box}
        <div className="field">
          <label htmlFor="cur">Senha atual</label>
          <input id="cur" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
        </div>
        <div className="field">
          <label htmlFor="new">Nova senha (mínimo 6 caracteres)</label>
          <input id="new" type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required minLength={6} />
        </div>
        <button className="btn primary" disabled={busy}>Salvar</button>
      </form>
    </div>
  );
}
