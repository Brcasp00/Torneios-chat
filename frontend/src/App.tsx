import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import { Loading } from "./components/ui";
import { roleLabel } from "./labels";
import Account from "./pages/Account";
import Admin from "./pages/Admin";
import CreateTournament from "./pages/CreateTournament";
import CreateUser from "./pages/CreateUser";
import DraftClubPage from "./pages/DraftClubPage";
import DraftPokemonPage from "./pages/DraftPokemonPage";
import Archive from "./pages/Archive";
import ArchiveEntry from "./pages/ArchiveEntry";
import ArchiveForm from "./pages/ArchiveForm";
import Calculator from "./pages/Calculator";
import Hub from "./pages/Hub";
import Login from "./pages/Login";
import MatchPage from "./pages/MatchPage";
import Players from "./pages/Players";
import Pokedex from "./pages/Pokedex";
import Profile from "./pages/Profile";
import SeriesPage from "./pages/SeriesPage";
import TournamentPage from "./pages/TournamentPage";
import Tournaments from "./pages/Tournaments";

function Nav() {
  const { user, logout, isAdmin } = useAuth();
  return (
    <header className="nav">
      <div className="nav-inner">
        <Link to="/" className="brand" aria-label="Início" title="Início">
          <span className="pokeball" />
        </Link>
        <nav className="nav-links">
          <NavLink to="/" end>Início</NavLink>
          <NavLink to="/torneios">Torneios</NavLink>
          <NavLink to="/acervo">Acervo</NavLink>
          <NavLink to="/jogadores">Jogadores</NavLink>
          {isAdmin && <NavLink to="/admin">Administração</NavLink>}
        </nav>
        <div className="nav-user">
          {user ? (
            <>
              <Link to={`/jogadores/${user.id}`} title={`${roleLabel[user.role]} · ver meu perfil`}>{user.name}</Link>
              <button className="btn small ghost" onClick={logout}>Sair</button>
            </>
          ) : (
            <Link className="btn small primary" to="/entrar">Entrar</Link>
          )}
        </div>
      </div>
    </header>
  );
}

function RequireAuth({ staff, admin, children }: { staff?: boolean; admin?: boolean; children: JSX.Element }) {
  const { user, ready, isStaff, isAdmin } = useAuth();
  const loc = useLocation();
  if (!ready) return <Loading />;
  if (!user) return <Navigate to="/entrar" state={{ from: loc.pathname + loc.search }} replace />;
  if (admin && !isAdmin) return <Navigate to="/" replace />; // a administração não existe para quem não é admin
  if (staff && !isStaff) {
    return <div className="alert error">Somente administradores e organizadores podem criar torneios.</div>;
  }
  return children;
}

export default function App() {
  const { user } = useAuth();
  const loc = useLocation();
  // Senha temporária: enquanto não for trocada, a única página liberada é "Minha conta".
  if (user?.must_change_password && loc.pathname !== "/conta") return <Navigate to="/conta" replace />;
  return (
    <>
      <Nav />
      <main className="container">
        <Routes>
          <Route path="/" element={<Hub />} />
          <Route path="/entrar" element={<Login />} />
          <Route path="/torneios" element={<Tournaments />} />
          <Route path="/torneios/novo" element={<RequireAuth staff><CreateTournament /></RequireAuth>} />
          <Route path="/torneios/:id" element={<TournamentPage />} />
          <Route path="/torneios/:id/pokemon/:pid" element={<DraftPokemonPage />} />
          <Route path="/torneios/:id/clubes/:uid" element={<DraftClubPage />} />
          <Route path="/matches/:id" element={<MatchPage />} />
          <Route path="/acervo" element={<Archive />} />
          <Route path="/acervo/novo" element={<RequireAuth admin><ArchiveForm /></RequireAuth>} />
          <Route path="/acervo/series/:id" element={<SeriesPage />} />
          <Route path="/acervo/:id" element={<ArchiveEntry />} />
          <Route path="/acervo/:id/editar" element={<RequireAuth admin><ArchiveForm /></RequireAuth>} />
          <Route path="/jogadores" element={<Players />} />
          <Route path="/calculadora" element={<Calculator />} />
          <Route path="/pokedex" element={<Pokedex />} />
          <Route path="/jogadores/:id" element={<Profile />} />
          <Route path="/conta" element={<RequireAuth><Account /></RequireAuth>} />
          <Route path="/admin" element={<RequireAuth admin><Admin /></RequireAuth>} />
          <Route path="/admin/usuarios/novo" element={<RequireAuth admin><CreateUser /></RequireAuth>} />
          <Route path="*" element={<div className="alert">Página não encontrada. <Link to="/">Voltar ao início</Link></div>} />
        </Routes>
      </main>
    </>
  );
}
