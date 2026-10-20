import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, tokenStore, type Token, type User } from "./api";

interface AuthCtx {
  user: User | null;
  ready: boolean;
  login: (name: string, password: string) => Promise<void>;
  register: (name: string, password: string, captchaToken?: string | null) => Promise<void>;
  logout: () => void;
  /** Recarrega os dados do usuário logado (ex.: depois de trocar a senha temporária). */
  refresh: () => Promise<void>;
  isStaff: boolean;
  isAdmin: boolean;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!tokenStore.get()) {
      setReady(true);
      return;
    }
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => tokenStore.set(null))
      .finally(() => setReady(true));
  }, []);

  const finish = useCallback((t: Token) => {
    tokenStore.set(t.access_token);
    setUser(t.user);
  }, []);

  const value = useMemo<AuthCtx>(
    () => ({
      user,
      ready,
      login: async (name, password) => finish(await api<Token>("/auth/login", { body: { name, password } })),
      register: async (name, password, captchaToken) =>
        finish(await api<Token>("/auth/register", { body: { name, password, captcha_token: captchaToken ?? null } })),
      refresh: async () => setUser(await api<User>("/auth/me")),
      logout: () => {
        tokenStore.set(null);
        setUser(null);
      },
      isStaff: user?.role === "admin" || user?.role === "organizer",
      isAdmin: user?.role === "admin",
    }),
    [user, ready, finish],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth fora do AuthProvider");
  return v;
}
