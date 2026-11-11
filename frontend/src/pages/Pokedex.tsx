import { useMemo, useState } from "react";
import { api } from "../api";
import { ErrorBox, Loading } from "../components/ui";
import { useLoad } from "../hooks";

/* Catálogo de Pokémon (dados do Showdown): tiers da Geração 9 National Dex e da Geração 7 lado a lado.
   A lista inteira vem de uma vez e os filtros são aplicados aqui, sem nova consulta. */

export interface PokemonInfo { id: string; name: string; num: number; base: string; forme: string | null; region: string; types: string[]; tier9: string | null; tier7: string | null }
interface Meta { total: number; regions: string[]; tiers9: string[]; tiers7: string[] }

const PAGE = 100;
const TYPE_PT: Record<string, string> = {
  Normal: "Normal", Fire: "Fogo", Water: "Água", Grass: "Planta", Electric: "Elétrico", Ice: "Gelo", Fighting: "Lutador",
  Poison: "Venenoso", Ground: "Terrestre", Flying: "Voador", Psychic: "Psíquico", Bug: "Inseto", Rock: "Pedra", Ghost: "Fantasma",
  Dragon: "Dragão", Dark: "Sombrio", Steel: "Aço", Fairy: "Fada", Stellar: "Estelar",
};

export default function Pokedex() {
  const meta = useLoad(() => api<Meta>("/pokedex/meta"), []);
  const all = useLoad(() => api<PokemonInfo[]>("/pokedex"), []);
  const [q, setQ] = useState("");
  const [region, setRegion] = useState("");
  const [tier9, setTier9] = useState("");
  const [tier7, setTier7] = useState("");
  const [baseOnly, setBaseOnly] = useState(false);
  const [shown, setShown] = useState(PAGE);

  const list = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (all.data ?? []).filter((p) =>
      (!term || p.name.toLowerCase().includes(term) || String(p.num) === term)
      && (!region || p.region === region)
      && (!tier9 || (tier9 === "-" ? !p.tier9 : p.tier9 === tier9))
      && (!tier7 || (tier7 === "-" ? !p.tier7 : p.tier7 === tier7))
      && (!baseOnly || !p.forme));
  }, [all.data, q, region, tier9, tier7, baseOnly]);

  if ((all.loading && !all.data) || (meta.loading && !meta.data)) return <Loading />;
  if (!all.data || !meta.data) return <ErrorBox error={all.error ?? meta.error} />;
  const m = meta.data;
  const reset = (fn: () => void) => { fn(); setShown(PAGE); };

  return (
    <>
      <h1>Pokédex</h1>
      <p className="muted" style={{ maxWidth: 760 }}>
        Todos os {m.total} Pokémon jogáveis no Showdown, com as formas (regionais, Megas, Rotom…) como Pokémon separados.
        Os tiers aparecem lado a lado: <strong>Geração 9 National Dex</strong> e <strong>Geração 7</strong> ("—" = não existia
        na Geração 7). A região segue o número da Pokédex; formas regionais contam na região da forma.
      </p>
      <div className="card">
        <div className="form-grid">
          <div className="field"><label>Buscar (nome ou nº)</label><input value={q} onChange={(e) => reset(() => setQ(e.target.value))} placeholder="Ex.: Garchomp" /></div>
          <div className="field"><label>Região</label>
            <select value={region} onChange={(e) => reset(() => setRegion(e.target.value))}>
              <option value="">Todas</option>{m.regions.map((r) => <option key={r}>{r}</option>)}
            </select>
          </div>
          <div className="field"><label>Tier Gen 9 National Dex</label>
            <select value={tier9} onChange={(e) => reset(() => setTier9(e.target.value))}>
              <option value="">Todos</option>{m.tiers9.map((t) => <option key={t}>{t}</option>)}<option value="-">Sem tier</option>
            </select>
          </div>
          <div className="field"><label>Tier Gen 7</label>
            <select value={tier7} onChange={(e) => reset(() => setTier7(e.target.value))}>
              <option value="">Todos</option>{m.tiers7.map((t) => <option key={t}>{t}</option>)}<option value="-">Não existia na Gen 7</option>
            </select>
          </div>
        </div>
        <div className="field inline"><input id="base" type="checkbox" checked={baseOnly} onChange={(e) => reset(() => setBaseOnly(e.target.checked))} /><label htmlFor="base">Só a forma principal (sem Megas e formas alternativas)</label></div>
      </div>

      <div className="card">
        <p className="muted small" style={{ marginTop: 0 }}>{list.length} Pokémon encontrados.</p>
        <div className="table-wrap">
          <table>
            <thead><tr><th className="num">Nº</th><th>Pokémon</th><th>Tipos</th><th>Região</th><th>Gen 9 NatDex</th><th>Gen 7</th></tr></thead>
            <tbody>
              {list.slice(0, shown).map((p) => (
                <tr key={p.id}>
                  <td className="num muted">{p.num}</td>
                  <td><strong>{p.name}</strong></td>
                  <td className="small">{p.types.map((t) => TYPE_PT[t] ?? t).join(" / ")}</td>
                  <td>{p.region}</td>
                  <td>{p.tier9 ?? <span className="muted">—</span>}</td>
                  <td>{p.tier7 ?? <span className="muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {list.length > shown && <button className="btn" style={{ marginTop: ".6rem" }} onClick={() => setShown(shown + PAGE)}>Mostrar mais ({list.length - shown} restantes)</button>}
      </div>
    </>
  );
}
