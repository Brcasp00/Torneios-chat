import { useEffect, useRef, useState } from "react";

// Caixinha anti-robô da Cloudflare (Turnstile). Quando a pessoa passa na verificação, `onToken` recebe o comprovante
// (de uso único) que vai junto com o cadastro; ao expirar ou falhar, recebe null.
interface TurnstileApi {
  render: (el: HTMLElement, opts: Record<string, unknown>) => string;
  reset: (id: string) => void;
  remove: (id: string) => void;
}
declare global {
  interface Window { turnstile?: TurnstileApi }
}

const SRC = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
let loading: Promise<void> | null = null;

function loadScript(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  if (!loading) {
    loading = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = SRC;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => { loading = null; reject(new Error("turnstile")); };
      document.head.appendChild(s);
    });
  }
  return loading;
}

/** `resetKey`: mude o valor para pedir uma verificação nova (o comprovante só vale uma vez). */
export default function Turnstile({ siteKey, onToken, resetKey }: { siteKey: string; onToken: (t: string | null) => void; resetKey: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const widget = useRef<string | null>(null);
  const cb = useRef(onToken);
  cb.current = onToken;
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadScript()
      .then(() => {
        if (cancelled || !ref.current || !window.turnstile) return;
        widget.current = window.turnstile.render(ref.current, {
          sitekey: siteKey,
          theme: "dark",
          language: "pt-br",
          callback: (t: string) => cb.current(t),
          "expired-callback": () => cb.current(null),
          "error-callback": () => cb.current(null),
        });
      })
      .catch(() => setFailed(true));
    return () => {
      cancelled = true;
      if (widget.current && window.turnstile) window.turnstile.remove(widget.current);
      widget.current = null;
    };
  }, [siteKey]);

  useEffect(() => {
    if (resetKey && widget.current && window.turnstile) {
      window.turnstile.reset(widget.current);
      cb.current(null);
    }
  }, [resetKey]);

  if (failed) return <div className="alert error">Não foi possível carregar a verificação anti-robô. Recarregue a página e tente de novo.</div>;
  return <div className="field" ref={ref} />;
}
