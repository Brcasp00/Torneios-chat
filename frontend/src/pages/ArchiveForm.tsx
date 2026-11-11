import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type ArchiveDetail, type ArchivePlayer, type PlayerRef, type Series } from "../api";
import { ErrorBox, Loading, useAction } from "../components/ui";
import { useLoad } from "../hooks";

/** Campo de jogador: liga a uma conta quando o nome bate com uma; senão fica só como texto. */
function PlayerField({ value, onChange, users, label }: { value: ArchivePlayer; onChange: (p: ArchivePlayer) => void; users: PlayerRef[]; label?: string }) {
  const set = (name: string) => {
    const u = users.find((x) => x.name.toLowerCase() === name.trim().toLowerCase());
    onChange({ user_id: u ? u.id : null, name });
  };
  return (
    <div className="field" style={{ margin: 0 }}>
      {label && <label>{label}</label>}
      <input list="archive-users" value={value.name} onChange={(e) => set(e.target.value)} placeholder="Nome do jogador" maxLength={60} />
      <span className="muted small">{value.name.trim() ? (value.user_id ? "✓ conta na plataforma" : "sem conta (só o nome)") : " "}</span>
    </div>
  );
}

interface PlacementRow { position: string; label: string; player: ArchivePlayer }
interface MatchRow { stage_label: string; number: string; p1: ArchivePlayer; p2: ArchivePlayer; winner: string; replay_url: string }
const empty: ArchivePlayer = { user_id: null, name: "" };

export default function ArchiveForm() {
  const { id } = useParams();
  const nav = useNavigate();
  const editing = !!id;
  const users = useLoad(() => api<PlayerRef[]>("/users", { params: { limit: 200 } }), []);
  const series = useLoad(() => api<Series[]>("/series"), []);
  const existing = useLoad(() => (id ? api<ArchiveDetail>(`/archive/${id}`) : Promise.resolve(null)), [id]);
  const platform = !!existing.data?.tournament_id;
  const { run, busy, box, setMsg } = useAction();

  const [f, setF] = useState({ name: "", start_date: "", end_date: "", format: "", players_count: "", organizer: "", tier: "", rules_text: "", description: "", series_id: "", edition: "" });
  const [placements, setPlacements] = useState<PlacementRow[]>([{ position: "1", label: "Campeão", player: empty }, { position: "2", label: "Vice", player: empty }]);
  const [matches, setMatches] = useState<MatchRow[]>([]);
  const [links, setLinks] = useState<{ label: string; url: string }[]>([]);

  useEffect(() => {
    const e = existing.data;
    if (!e) return;
    setF({
      name: e.name, start_date: e.start_date ?? "", end_date: e.end_date ?? "", format: e.format ?? "", players_count: e.players_count ? String(e.players_count) : "",
      organizer: e.organizer ?? "", tier: e.tier ?? "", rules_text: e.rules_text ?? "", description: e.description ?? "",
      series_id: e.series ? String(e.series.id) : "", edition: e.edition ? String(e.edition) : "",
    });
    setPlacements(e.placements.map((p) => ({ position: String(p.position), label: p.label ?? "", player: { user_id: p.user_id, name: p.name } })));
    setMatches(e.matches.map((m) => ({ stage_label: m.stage_label, number: m.number ? String(m.number) : "", p1: m.player1, p2: m.player2, winner: m.winner ? String(m.winner) : "", replay_url: m.replay_url ?? "" })));
    setLinks(e.links);
  }, [existing.data]);

  if (editing && existing.loading && !existing.data) return <Loading />;
  if (editing && !existing.data) return <ErrorBox error={existing.error} />;

  const up = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const num = (s: string) => (s.trim() ? Number(s) : null);
  const player = (p: ArchivePlayer) => (p.user_id ? { user_id: p.user_id } : { name: p.name.trim() });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const meta = {
      description: f.description || null,
      links: links.filter((l) => l.label.trim() || l.url.trim()),
      series_id: num(f.series_id),
      edition: num(f.edition),
    };
    if (meta.edition && !meta.series_id) return setMsg({ kind: "error", text: "A edição só vale junto com uma série: escolha a série ou apague a edição." });
    if (platform) {
      if (await run(() => api(`/archive/${id}/meta`, { method: "PUT", body: meta }))) nav(`/acervo/${id}`);
      return;
    }
    const badP = placements.findIndex((p) => !p.player.name.trim() || !p.position.trim());
    if (badP >= 0) return setMsg({ kind: "error", text: `Classificação, linha ${badP + 1}: preencha a posição e o jogador (ou remova a linha).` });
    const badM = matches.findIndex((m) => !m.stage_label.trim() || !m.p1.name.trim() || !m.p2.name.trim());
    if (badM >= 0) return setMsg({ kind: "error", text: `Partidas, linha ${badM + 1}: preencha a fase/rodada e os dois jogadores (ou remova a linha).` });
    const body = {
      ...meta,
      name: f.name, start_date: f.start_date || null, end_date: f.end_date || null, format: f.format || null,
      players_count: num(f.players_count), organizer: f.organizer || null, tier: f.tier || null, rules_text: f.rules_text || null,
      placements: placements.map((p) => ({ position: Number(p.position), label: p.label || null, ...player(p.player) })),
      matches: matches.map((m) => ({
        stage_label: m.stage_label, number: num(m.number), player1: player(m.p1), player2: player(m.p2),
        winner: num(m.winner), replay_url: m.replay_url.trim() || null,
      })),
    };
    let saved: ArchiveDetail | undefined;
    const ok = await run(async () => {
      saved = await api<ArchiveDetail>(editing ? `/archive/${id}` : "/archive", { method: editing ? "PUT" : "POST", body });
    });
    if (ok && saved) nav(`/acervo/${saved.id}`);
  };

  const userList = users.data ?? [];
  return (
    <form onSubmit={submit} style={{ maxWidth: 900 }}>
      <p className="small"><Link to={editing ? `/acervo/${id}` : "/acervo"}>← Voltar</Link></p>
      <h1>{!editing ? "Adicionar torneio antigo" : platform ? `Editar "${existing.data!.name}"` : "Editar torneio do acervo"}</h1>
      {platform && <div className="alert">Este torneio foi jogado na plataforma: a classificação, as partidas e os replays vêm dele. Aqui dá para editar a descrição, os links e a série.</div>}
      <datalist id="archive-users">{userList.map((u) => <option key={u.id} value={u.name} />)}</datalist>
      {box}

      {!platform && (
        <section className="card">
          <h2>Informações</h2>
          <div className="form-grid">
            <div className="field"><label>Nome</label><input value={f.name} onChange={up("name")} required minLength={3} maxLength={120} /></div>
            <div className="field"><label>Início</label><input type="date" value={f.start_date} onChange={up("start_date")} /></div>
            <div className="field"><label>Término</label><input type="date" value={f.end_date} onChange={up("end_date")} /></div>
            <div className="field"><label>Formato</label><input value={f.format} onChange={up("format")} placeholder="Ex.: grupos + mata-mata" maxLength={200} /></div>
            <div className="field"><label>Nº de participantes</label><input type="number" min={2} max={1024} value={f.players_count} onChange={up("players_count")} /></div>
            <div className="field"><label>Organizador (opcional)</label><input value={f.organizer} onChange={up("organizer")} maxLength={80} /></div>
            <div className="field"><label>Tier</label><input value={f.tier} onChange={up("tier")} placeholder="Ex.: OU, VGC" maxLength={60} /></div>
          </div>
          <div className="field"><label>Regras</label><textarea value={f.rules_text} onChange={up("rules_text")} maxLength={5000} /></div>
        </section>
      )}

      <section className="card">
        <h2>Descrição e série</h2>
        <div className="field"><label>Descrição (a história do torneio)</label><textarea value={f.description} onChange={up("description")} maxLength={20000} style={{ minHeight: 120 }} /></div>
        <div className="form-grid">
          <div className="field"><label>Série</label>
            <select value={f.series_id} onChange={up("series_id")}>
              <option value="">Nenhuma</option>
              {(series.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          <div className="field"><label>Edição</label><input type="number" min={1} value={f.edition} onChange={up("edition")} placeholder="Ex.: 3" /></div>
        </div>
        <p className="muted small">Para criar uma série nova, use a seção "Séries" na página do Acervo.</p>
      </section>

      <section className="card">
        <h2>Links</h2>
        <p className="muted small">Vídeos, Discord, fotos... (cada link com um nome).</p>
        {links.map((l, k) => (
          <div className="editor-row" key={k}>
            <div className="field" style={{ margin: 0 }}><label>Nome</label><input value={l.label} onChange={(e) => setLinks(links.map((x, j) => (j === k ? { ...x, label: e.target.value } : x)))} maxLength={80} /></div>
            <div className="field" style={{ margin: 0, gridColumn: "span 2" }}><label>Endereço</label><input value={l.url} onChange={(e) => setLinks(links.map((x, j) => (j === k ? { ...x, url: e.target.value } : x)))} placeholder="https://..." maxLength={500} /></div>
            <button type="button" className="btn small ghost" onClick={() => setLinks(links.filter((_, j) => j !== k))}>Remover</button>
          </div>
        ))}
        <button type="button" className="btn small" onClick={() => setLinks([...links, { label: "", url: "" }])}>+ Adicionar link</button>
      </section>

      {!platform && (
        <>
          <section className="card">
            <h2>Classificação final</h2>
            <p className="muted small">Posições iguais valem para empates (ex.: dois em 3º). O rótulo é opcional ("Campeão", "Semifinal").</p>
            {placements.map((p, k) => (
              <div className="editor-row" key={k}>
                <div className="field" style={{ margin: 0 }}><label>Posição</label><input type="number" min={1} value={p.position} onChange={(e) => setPlacements(placements.map((x, j) => (j === k ? { ...x, position: e.target.value } : x)))} /></div>
                <PlayerField label="Jogador" value={p.player} users={userList} onChange={(pl) => setPlacements(placements.map((x, j) => (j === k ? { ...x, player: pl } : x)))} />
                <div className="field" style={{ margin: 0 }}><label>Rótulo</label><input value={p.label} onChange={(e) => setPlacements(placements.map((x, j) => (j === k ? { ...x, label: e.target.value } : x)))} maxLength={40} /></div>
                <button type="button" className="btn small ghost" onClick={() => setPlacements(placements.filter((_, j) => j !== k))}>Remover</button>
              </div>
            ))}
            <button type="button" className="btn small" onClick={() => setPlacements([...placements, { position: String((Number(placements[placements.length - 1]?.position) || 0) + 1), label: "", player: empty }])}>+ Adicionar colocação</button>
          </section>

          <section className="card">
            <h2>Partidas</h2>
            <p className="muted small">Uma linha por partida, ex.: "Rodada 4", partida 3. O link do replay pode ficar vazio.</p>
            {matches.map((m, k) => {
              const set = (patch: Partial<MatchRow>) => setMatches(matches.map((x, j) => (j === k ? { ...x, ...patch } : x)));
              return (
                <div className="editor-row" key={k}>
                  <div className="field" style={{ margin: 0 }}><label>Fase/rodada</label><input value={m.stage_label} onChange={(e) => set({ stage_label: e.target.value })} placeholder="Rodada 4" maxLength={60} /></div>
                  <div className="field" style={{ margin: 0 }}><label>Partida nº</label><input type="number" min={1} value={m.number} onChange={(e) => set({ number: e.target.value })} /></div>
                  <PlayerField label="Jogador 1" value={m.p1} users={userList} onChange={(p) => set({ p1: p })} />
                  <PlayerField label="Jogador 2" value={m.p2} users={userList} onChange={(p) => set({ p2: p })} />
                  <div className="field" style={{ margin: 0 }}><label>Vencedor</label>
                    <select value={m.winner} onChange={(e) => set({ winner: e.target.value })}>
                      <option value="">Não informado</option><option value="1">Jogador 1</option><option value="2">Jogador 2</option>
                    </select>
                  </div>
                  <div className="field" style={{ margin: 0 }}><label>Link do replay</label><input value={m.replay_url} onChange={(e) => set({ replay_url: e.target.value })} placeholder="https://..." maxLength={500} /></div>
                  <button type="button" className="btn small ghost" onClick={() => setMatches(matches.filter((_, j) => j !== k))}>Remover</button>
                </div>
              );
            })}
            <button type="button" className="btn small" onClick={() => {
              const last = matches[matches.length - 1];
              setMatches([...matches, { stage_label: last?.stage_label ?? "", number: last?.number ? String(Number(last.number) + 1) : "1", p1: empty, p2: empty, winner: "", replay_url: "" }]);
            }}>+ Adicionar partida</button>
          </section>
        </>
      )}

      <button className="btn primary" disabled={busy}>{busy ? "Salvando…" : editing ? "Salvar" : "Adicionar ao acervo"}</button>
    </form>
  );
}
