import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import { Loading } from "./components/ui";
import { roleLabel } from "./labels";
import Account from "./pages/Account";
import Admin from "./pages/Admin";
import CreateTournament from "./pages/CreateTournament";
import Home from "./pages/Home";
import Login from "./pages/Login";
import MatchPage from "./pages/MatchPage";
import TournamentPage from "./pages/TournamentPage";
import Tournaments from "./pages/Tournaments";

function Nav() {
  const { user, logout, isAdmin } = useAuth();
  return (
    <header className="nav">
      <div className="nav-inner">
        <Link to="/" className="brand">
          <span className="pokeball" /> Torneios Pokémon
        </Link>
        <nav className="nav-links">
          <NavLink to="/" end>Início</NavLink>
          <NavLink to="/torneios">Torneios</NavLink>
          {isAdmin && <NavLink to="/admin">Administração</NavLink>}
        </nav>
        <div className="nav-user">
          {user ? (
            <>
              <Link to="/conta" title={roleLabel[user.role]}>{user.name}</Link>
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
  return (
    <>
      <Nav />
      <main className="container">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/entrar" element={<Login />} />
          <Route path="/torneios" element={<Tournaments />} />
          <Route path="/torneios/novo" element={<RequireAuth staff><CreateTournament /></RequireAuth>} />
          <Route path="/torneios/:id" element={<TournamentPage />} />
          <Route path="/matches/:id" element={<MatchPage />} />
          <Route path="/conta" element={<RequireAuth><Account /></RequireAuth>} />
          <Route path="/admin" element={<RequireAuth admin><Admin /></RequireAuth>} />
          <Route path="*" element={<div className="alert">Página não encontrada. <Link to="/">Voltar ao início</Link></div>} />
        </Routes>
      </main>
    </>
  );
}
