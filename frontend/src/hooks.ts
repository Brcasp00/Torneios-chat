import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

export interface Loaded<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
}

/** Carrega dados da API; com `pollMs` atualiza sozinho (sem piscar) enquanto a aba estiver visível. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[], pollMs = 0): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback(async (silent: boolean) => {
    if (!silent) setLoading(true);
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      if (!silent || data === null) setError(e instanceof ApiError ? e.message : "Erro inesperado.");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setData(null);
    void run(false);
    if (!pollMs) return;
    const id = setInterval(() => {
      if (document.visibilityState === "visible") void run(true);
    }, pollMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, reload: () => run(true) };
}
