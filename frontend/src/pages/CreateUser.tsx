import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Role, type User } from "../api";
import { useAction } from "../components/ui";
import { roleLabel } from "../labels";

export default function CreateUser() {
  const nav = useNavigate();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("player");
  const { run, busy, box } = useAction();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    let created: { user: User; temporary_password: string | null } | null = null;
    const ok = await run(async () => {
      created = await api<{ user: User; temporary_password: string | null }>("/users", {
        body: { name, role, password: password || null },
      });
    });
    if (ok && created) {
      const c = created as { user: User; temporary_password: string | null };
      // Volta para a lista de usuários da administração, levando o aviso (e a senha temporária, se houver).
      nav("/admin", {
        replace: true,
        state: { created: { name: c.user.name, role: c.user.role, temporary_password: c.temporary_password } },
      });
    }
  };

  return (
    <form onSubmit={submit} style={{ maxWidth: 520 }}>
      <p className="small"><Link to="/admin">← Voltar para Administração</Link></p>
      <h1>Criar usuário</h1>
      <div className="card">
        {box}
        <div className="field">
          <label htmlFor="cu-name">Nome de treinador</label>
          <input id="cu-name" value={name} onChange={(e) => setName(e.target.value)} required minLength={3} maxLength={32} autoFocus />
          <p className="muted small" style={{ margin: ".3rem 0 0" }}>De 3 a 32 caracteres: letras, números, espaço, ponto, hífen ou _.</p>
        </div>
        <div className="field">
          <label htmlFor="cu-role">Papel</label>
          <select id="cu-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
            {Object.entries(roleLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="cu-pw">Senha (deixe vazio para gerar uma temporária)</label>
          <input id="cu-pw" type="text" value={password} onChange={(e) => setPassword(e.target.value)} minLength={6} autoComplete="off" />
          <p className="muted small" style={{ margin: ".3rem 0 0" }}>A pessoa pode trocar a senha depois em "Minha conta".</p>
        </div>
        <div className="row">
          <button className="btn primary" disabled={busy}>{busy ? "Criando…" : "Criar usuário"}</button>
          <Link className="btn" to="/admin">Cancelar</Link>
        </div>
      </div>
    </form>
  );
}
