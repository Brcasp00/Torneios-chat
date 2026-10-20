import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { useAction } from "../components/ui";

export default function Login() {
  const { user, login, register } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const from = (loc.state as { from?: string } | null)?.from ?? "/";
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const { run, busy, box } = useAction();

  if (user) return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (mode === "register" && password !== again) {
      await run(async () => { throw new Error("As senhas não conferem."); });
      return;
    }
    const ok = await run(() => (mode === "login" ? login(name, password) : register(name, password)));
    if (ok) nav(from, { replace: true });
  };

  return (
    <div style={{ maxWidth: 420, margin: "2rem auto" }}>
      <div className="card">
        <h1>{mode === "login" ? "Entrar" : "Criar conta"}</h1>
        <p className="muted">
          {mode === "login" ? "Use o nome e a senha da sua conta." : "Todo cadastro novo começa como jogador. Não há recuperação por e-mail: se esquecer a senha, peça a um admin para redefinir."}
        </p>
        <form onSubmit={submit}>
          {box}
          <div className="field">
            <label htmlFor="name">Nome de treinador</label>
            <input id="name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="username" required minLength={3} maxLength={32} />
          </div>
          <div className="field">
            <label htmlFor="pw">Senha</label>
            <input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={mode === "register" ? 6 : 1} />
          </div>
          {mode === "register" && (
            <div className="field">
              <label htmlFor="pw2">Repita a senha</label>
              <input id="pw2" type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
            </div>
          )}
          <div className="row between">
            <button className="btn primary" disabled={busy}>{busy ? "Aguarde…" : mode === "login" ? "Entrar" : "Cadastrar"}</button>
            <button type="button" className="btn ghost" onClick={() => setMode(mode === "login" ? "register" : "login")}>
              {mode === "login" ? "Criar conta" : "Já tenho conta"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
