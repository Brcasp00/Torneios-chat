"""Ponto de entrada local da plataforma: liga o back-end (FastAPI) e o front-end (Vite) juntos.

Uso (na raiz do projeto, PowerShell):
    py main.py              # sobe API (http://localhost:8000) e site (http://localhost:5173)
    py main.py --status     # só verifica se os dois já estão no ar
    py main.py --only back  # só a API   (ou: --only front)
    py main.py --open       # abre o navegador quando tudo estiver pronto
    py main.py --install    # força `npm install` antes de subir o front

Ctrl+C encerra os dois. Serve apenas para desenvolvimento local; em produção cada parte é hospedada separadamente
(API no Render, front como site estático).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
IS_WIN = os.name == "nt"

COLORS = {"api": "\033[36m", "web": "\033[35m", "main": "\033[33m"}
RESET = "\033[0m"


def log(tag: str, msg: str) -> None:
    color = COLORS.get(tag, "") if sys.stdout.isatty() else ""
    print(f"{color}[{tag}]{RESET if color else ''} {msg}", flush=True)


def venv_python() -> Path | None:
    exe = BACKEND / ".venv" / ("Scripts/python.exe" if IS_WIN else "bin/python")
    return exe if exe.exists() else None


def is_up(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 500
    except urllib.error.HTTPError:
        return True  # respondeu (ex.: 404): o servidor está no ar
    except Exception:
        return False


def wait_for(url: str, seconds: float) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if is_up(url):
            return True
        time.sleep(0.5)
    return False


def pump(tag: str, proc: subprocess.Popen) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        log(tag, line.rstrip())


def spawn(tag: str, cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.Popen:
    proc = subprocess.Popen(
        cmd, cwd=cwd, env={**os.environ, **(env or {})}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if IS_WIN else 0,
    )
    threading.Thread(target=pump, args=(tag, proc), daemon=True).start()
    return proc


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if IS_WIN:  # encerra a árvore inteira (npm -> node, uvicorn --reload -> worker)
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # o Vite imprime símbolos que o cp1252 do Windows não codifica
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Liga o back-end e o front-end da plataforma de torneios.")
    ap.add_argument("--only", choices=["back", "front"], help="sobe só uma das partes")
    ap.add_argument("--status", action="store_true", help="apenas verifica se API e site estão no ar")
    ap.add_argument("--api-port", type=int, default=8000)
    ap.add_argument("--web-port", type=int, default=5173)
    ap.add_argument("--no-reload", action="store_true", help="API sem recarga automática")
    ap.add_argument("--install", action="store_true", help="roda `npm install` antes de subir o front")
    ap.add_argument("--open", action="store_true", help="abre o navegador ao ficar pronto")
    args = ap.parse_args()

    api_url = f"http://localhost:{args.api_port}"
    web_url = f"http://localhost:{args.web_port}"

    if args.status:
        api_ok, web_ok = is_up(f"{api_url}/health"), is_up(web_url)
        log("main", f"API   {api_url}  -> {'no ar' if api_ok else 'fora do ar'}")
        log("main", f"Site  {web_url}  -> {'no ar' if web_ok else 'fora do ar'}")
        return 0 if (api_ok and web_ok) else 1

    procs: list[tuple[str, subprocess.Popen]] = []
    want_back, want_front = args.only != "front", args.only != "back"

    if want_back:
        py = venv_python()
        if py is None:
            log("main", "Venv do back-end não encontrado. Rode em backend/: py -m venv .venv ; .venv\\Scripts\\pip install -r requirements.txt")
            return 2
        if not (BACKEND / ".env").exists():
            log("main", "Falta backend/.env (DATABASE_URL e JWT_SECRET). Veja o CLAUDE.md.")
            return 2
        if is_up(f"{api_url}/health"):
            log("main", f"A API já está respondendo em {api_url}; não vou subir outra.")
        else:
            cmd = [str(py), "-m", "uvicorn", "app.main:app", "--port", str(args.api_port)]
            if not args.no_reload:
                cmd.append("--reload")
            procs.append(("api", spawn("api", cmd, BACKEND)))

    if want_front:
        npm = shutil.which("npm.cmd" if IS_WIN else "npm")
        if npm is None:
            log("main", "Node.js/npm não encontrado. Instale o Node 20+ (https://nodejs.org).")
            return 2
        if args.install or not (FRONTEND / "node_modules").exists():
            log("main", "Instalando dependências do front (npm install)…")
            if subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND).returncode != 0:
                return 2
        if is_up(web_url):
            log("main", f"O site já está respondendo em {web_url}; não vou subir outro.")
        else:
            procs.append((
                "web",
                spawn("web", [npm, "run", "dev", "--", "--port", str(args.web_port)], FRONTEND, {"VITE_API_URL": api_url}),
            ))

    try:
        ready = True
        if want_back:
            ok = wait_for(f"{api_url}/health", 40)
            log("main", f"API   {api_url}  (docs em {api_url}/docs) -> {'pronta' if ok else 'NÃO respondeu a tempo'}")
            ready &= ok
        if want_front:
            ok = wait_for(web_url, 40)
            log("main", f"Site  {web_url} -> {'pronto' if ok else 'NÃO respondeu a tempo'}")
            ready &= ok
        if ready and args.open and want_front:
            webbrowser.open(web_url)
        if not procs:
            return 0 if ready else 1
        log("main", "Tudo ligado. Pressione Ctrl+C para encerrar.")
        while True:
            for tag, p in procs:
                if p.poll() is not None:
                    log("main", f"O processo '{tag}' terminou (código {p.returncode}). Encerrando o restante.")
                    return 1
            time.sleep(1)
    except KeyboardInterrupt:
        log("main", "Encerrando…")
        return 0
    finally:
        for _, p in procs:
            stop(p)


if __name__ == "__main__":
    sys.exit(main())
