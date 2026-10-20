import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { api, type AuthOptions } from "../api";
import { useAuth } from "../auth";
import { useLoad } from "../hooks";
import Turnstile from "../components/Turnstile";
import { PasswordInput, useAction } from "../components/ui";

export default function Login() {
  const { user, login, register } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const from = (loc.state as { from?: string } | null)?.from ?? "/";
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [resetCaptcha, setResetCaptcha] = useState(0);
  const { run, busy, box, setMsg } = useAction();
  // O servidor diz se o cadastro está aberto e se exige a verificação anti-robô.
  const options = useLoad(() => api<AuthOptions>("/auth/options"), []);
  const registrationOpen = options.data?.registration_open ?? false;
  const siteKey = options.data?.turnstile_site_key ?? null;

  if (user) return <Navigate to={from} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (mode === "register" && password !== again) {
      setMsg({ kind: "error", text: "As senhas não conferem." });
      return;
    }
    if (mode === "register" && siteKey && !captcha) {
      setMsg({ kind: "error", text: "Conclua a verificação anti-robô (a caixinha acima do botão) antes de cadastrar." });
      return;
    }
    const ok = await run(() => (mode === "login" ? login(name, password) : register(name, password, captcha)));
    if (ok) nav(from, { replace: true });
    else if (mode === "register" && siteKey) setResetCaptcha((n) => n + 1); // o comprovante só vale uma vez
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
            <PasswordInput id="pw" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={mode === "register" ? 8 : 1} />
          </div>
          {mode === "register" && (
            <div className="field">
              <label htmlFor="pw2">Repita a senha</label>
              <PasswordInput id="pw2" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
            </div>
          )}
          {mode === "register" && siteKey && <Turnstile siteKey={siteKey} onToken={setCaptcha} resetKey={resetCaptcha} />}
          <div className="row between">
            <button className="btn primary" disabled={busy}>{busy ? "Aguarde…" : mode === "login" ? "Entrar" : "Cadastrar"}</button>
            {(registrationOpen || mode === "register") && (
              <button type="button" className="btn ghost" onClick={() => { setMode(mode === "login" ? "register" : "login"); setMsg(null); }}>
                {mode === "login" ? "Criar conta" : "Já tenho conta"}
              </button>
            )}
          </div>
          {!registrationOpen && mode === "login" && options.data && (
            <p className="muted small" style={{ margin: ".8rem 0 0" }}>Não tem conta? Peça a um admin para criar a sua.</p>
          )}
        </form>
      </div>
    </div>
  );
}
