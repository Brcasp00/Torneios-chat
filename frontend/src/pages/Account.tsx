import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { useAction } from "../components/ui";
import { roleLabel } from "../labels";

export default function Account() {
  const { user, refresh, logout } = useAuth();
  const nav = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const { run, busy, box } = useAction();
  const forced = !!user?.must_change_password;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== again) {
      await run(async () => { throw new Error("A confirmação não confere com a nova senha."); });
      return;
    }
    const ok = await run(async () => {
      await api("/auth/change-password", { body: { current_password: current, new_password: next } });
      await refresh();
    }, "Senha alterada.");
    if (ok) {
      setCurrent("");
      setNext("");
      setAgain("");
      if (forced) nav("/", { replace: true });
    }
  };

  return (
    <div style={{ maxWidth: 480 }}>
      <h1>{forced ? "Defina uma nova senha" : "Minha conta"}</h1>
      {forced && (
        <div className="alert warn">
          Você entrou com uma <strong>senha temporária</strong>. Por segurança, escolha uma senha só sua para continuar usando a plataforma.
          Informe a senha temporária no campo "Senha atual".
        </div>
      )}
      {!forced && (
        <div className="card">
          <dl className="kv">
            <dt>Nome</dt><dd>{user?.name}</dd>
            <dt>Papel</dt><dd>{user ? roleLabel[user.role] : ""}</dd>
          </dl>
        </div>
      )}
      <form className="card" onSubmit={submit}>
        <h2>Alterar senha</h2>
        {box}
        <div className="field">
          <label htmlFor="cur">{forced ? "Senha atual (a temporária)" : "Senha atual"}</label>
          <input id="cur" type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
        </div>
        <div className="field">
          <label htmlFor="new">Nova senha (mínimo 6 caracteres, diferente da atual)</label>
          <input id="new" type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required minLength={6} />
        </div>
        <div className="field">
          <label htmlFor="again">Repita a nova senha</label>
          <input id="again" type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
        </div>
        <div className="row">
          <button className="btn primary" disabled={busy}>Salvar</button>
          {forced && <button type="button" className="btn ghost" onClick={logout}>Sair</button>}
        </div>
      </form>
    </div>
  );
}
