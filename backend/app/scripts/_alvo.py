"""Escolhe o banco usado pelos scripts de manutenção (backup, restauração, remoção de usuários).

Sem `--prod`: o banco do backend/.env (o de testes). Com `--prod`: a URL da produção é pedida no terminal, sem aparecer
na tela, e só vale para esta execução (não é gravada em lugar nenhum). Precisa rodar ANTES de importar app.db.session.
"""
import getpass
import os
import re
import sys


def escolher_banco(prod: bool) -> str:
    """Configura o banco e devolve uma descrição sem senha (ex.: 'projeto abcd1234 (PRODUÇÃO)')."""
    if prod:
        url = getpass.getpass("Cole a DATABASE_URL da PRODUÇÃO (não aparece na tela) e tecle Enter: ").strip().strip("\"'")
        if not url:
            sys.exit("Nenhuma URL informada. Nada foi feito.")
        os.environ["DATABASE_URL"] = url
    from app.core.config import get_settings

    return f"{descrever(get_settings().database_url)} ({'PRODUÇÃO' if prod else 'banco do .env / testes'})"


def descrever(url: str) -> str:
    """Identifica o banco sem mostrar a senha: no Supabase, o usuário é 'postgres.<id-do-projeto>'."""
    m = re.search(r"//([^:/@]+)(?::[^@]*)?@([^:/?]+)", url)
    if not m:
        return "banco local"
    user, host = m.groups()
    return f"projeto {user.split('.', 1)[1]}" if "." in user else f"servidor {host}"


def confirmar(palavra: str, aviso: str) -> None:
    print(aviso)
    if input(f"Para continuar, digite {palavra}: ").strip() != palavra:
        sys.exit("Cancelado. Nada foi feito.")
