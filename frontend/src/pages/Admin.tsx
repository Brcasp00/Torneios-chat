import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, type AuditItem, type Role, type User } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, Loading, Tabs, useAction } from "../components/ui";
import { useLoad } from "../hooks";
import { actionLabel, fmtDate, roleLabel } from "../labels";

type Tab = "users" | "audit";

export default function Admin() {
  const [tab, setTab] = useState<Tab>("users");
  return (
    <>
      <h1>Administração</h1>
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ id: "users", label: "Usuários" }, { id: "audit", label: "Auditoria" }]} />
      {tab === "users" ? <Users /> : <Audit />}
    </>
  );
}

function Users() {
  const { user: me } = useAuth();
  const list = useLoad(() => api<User[]>("/users/admin"), []);
  const { run, busy, box } = useAction();
  const [q, setQ] = useState("");
  const [temp, setTemp] = useState<string | null>(null);

  // Aviso vindo da página "Criar usuário" (que volta para cá ao terminar).
  const loc = useLocation();
  const nav = useNavigate();
  const [created, setCreated] = useState(
    (loc.state as { created?: { name: string; role: Role; temporary_password: string | null } } | null)?.created ?? null,
  );
  useEffect(() => {
    if (created) nav(loc.pathname, { replace: true, state: null }); // evita repetir o aviso ao recarregar a página
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const change = async (fn: () => Promise<unknown>, ok?: string) => { if (await run(fn, ok)) await list.reload(); };
  const reset = async (u: User) => {
    if (!confirm(`Gerar uma senha temporária para ${u.name}?`)) return;
    await run(async () => {
      const r = await api<{ temporary_password: string | null }>(`/users/${u.id}/reset-password`, { body: {} });
      setTemp(`${u.name}: ${r.temporary_password}`);
    });
  };

  if (list.loading) return <Loading />;
  const users = (list.data ?? []).filter((u) => u.name.toLowerCase().includes(q.toLowerCase()));
  return (
    <>
      <ErrorBox error={list.error} />
      <div className="row between" style={{ marginBottom: "1rem" }}>
        <input style={{ maxWidth: 280 }} placeholder="Buscar usuário" value={q} onChange={(e) => setQ(e.target.value)} />
        <Link className="btn primary" to="/admin/usuarios/novo">Criar usuário</Link>
      </div>
      {created && (
        <div className={`alert ${created.temporary_password ? "warn" : "ok"}`}>
          Usuário <strong>{created.name}</strong> criado como {roleLabel[created.role].toLowerCase()}.
          {created.temporary_password && <> Senha temporária: <strong>{created.temporary_password}</strong>. Envie por um canal seguro; ela não será mostrada de novo. A pessoa pode trocá-la em "Minha conta".</>}
          {" "}<button className="btn small ghost" onClick={() => setCreated(null)}>Fechar</button>
        </div>
      )}
      {box}
      {temp && <div className="alert warn">Senha temporária — <strong>{temp}</strong>. Envie ao usuário por um canal seguro; ela não será mostrada de novo.</div>}
      <div className="card table-wrap">
        <table>
          <thead><tr><th>Nome</th><th>Papel</th><th>Conta</th><th>Cadastro</th><th></th></tr></thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.name}{u.id === me?.id && <span className="muted small"> (você)</span>}</td>
                <td>
                  <select style={{ minWidth: 140 }} value={u.role} disabled={busy || u.id === me?.id}
                    onChange={(e) => change(() => api(`/users/${u.id}/role`, { method: "PATCH", body: { role: e.target.value as Role } }))}>
                    {Object.entries(roleLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </td>
                <td>{u.is_active ? "ativa" : "desativada"}</td>
                <td>{fmtDate(u.created_at)}</td>
                <td className="right nowrap">
                  <button className="btn small" disabled={busy} onClick={() => reset(u)}>Redefinir senha</button>{" "}
                  {u.id !== me?.id && (
                    <button className="btn small" disabled={busy} onClick={() => change(() => api(`/users/${u.id}/active`, { method: "PATCH", body: { is_active: !u.is_active } }))}>
                      {u.is_active ? "Desativar" : "Ativar"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

interface Page { total: number; items: AuditItem[] }
const PAGE = 30;

function Audit() {
  const [action, setAction] = useState("");
  const [entity, setEntity] = useState("");
  const [actor, setActor] = useState("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [offset, setOffset] = useState(0);
  const users = useLoad(() => api<User[]>("/users/admin"), []);
  const page = useLoad(
    () =>
      api<Page>("/audit", {
        params: {
          action, entity, actor_id: actor,
          since: since ? new Date(since).toISOString() : undefined,
          until: until ? new Date(until + "T23:59:59").toISOString() : undefined,
          limit: PAGE, offset,
        },
      }),
    [action, entity, actor, since, until, offset],
  );
  const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setOffset(0); };
  const total = page.data?.total ?? 0;

  return (
    <>
      <div className="form-grid" style={{ marginBottom: "1rem" }}>
        <div className="field"><label>Ação</label>
          <select value={action} onChange={(e) => reset(setAction)(e.target.value)}>
            <option value="">Todas</option>
            <option value="match.">Confrontos (todas)</option>
            <option value="tournament.">Torneios (todas)</option>
            <option value="round.">Rodadas (todas)</option>
            <option value="user.">Usuários (todas)</option>
            {Object.entries(actionLabel).filter(([k]) => !k.startsWith("report.")).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="field"><label>Entidade</label>
          <select value={entity} onChange={(e) => reset(setEntity)(e.target.value)}>
            <option value="">Todas</option><option value="match">Confronto</option><option value="tournament">Torneio</option><option value="user">Usuário</option>
          </select>
        </div>
        <div className="field"><label>Autor</label>
          <select value={actor} onChange={(e) => reset(setActor)(e.target.value)}>
            <option value="">Todos</option>
            {(users.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </div>
        <div className="field"><label>De</label><input type="date" value={since} onChange={(e) => reset(setSince)(e.target.value)} /></div>
        <div className="field"><label>Até</label><input type="date" value={until} onChange={(e) => reset(setUntil)(e.target.value)} /></div>
      </div>
      <ErrorBox error={page.error} />
      {page.loading ? <Loading /> : (
        <div className="card table-wrap">
          <table>
            <thead><tr><th>Quando</th><th>Quem</th><th>O quê</th><th>Alvo</th><th>Detalhes</th></tr></thead>
            <tbody>
              {(page.data?.items ?? []).map((a) => (
                <tr key={a.id}>
                  <td>{fmtDate(a.created_at)}</td>
                  <td>{a.actor_name ?? "—"}</td>
                  <td>{actionLabel[a.action] ?? a.action}</td>
                  <td>{a.entity} #{a.entity_id ?? "—"}</td>
                  <td className="muted small" style={{ maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis" }}>{a.data ? JSON.stringify(a.data) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {page.data?.items.length === 0 && <p className="muted">Nada encontrado com esses filtros.</p>}
        </div>
      )}
      <div className="row between">
        <span className="muted small">{total} registro(s)</span>
        <span className="row">
          <button className="btn small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Anterior</button>
          <button className="btn small" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Próxima</button>
        </span>
      </div>
    </>
  );
}
