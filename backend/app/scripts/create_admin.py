"""Cria (ou promove) o primeiro administrador.

Uso:  python -m app.scripts.create_admin "Nome"
A senha é pedida no terminal (não aparece na tela).
"""
import asyncio
import getpass
import sys

from sqlalchemy import func, select

from app.core.security import hash_password, now_utc
from app.db.session import SessionLocal, engine
from app.models import User
from app.schemas.user import _check_password, _clean_name


async def main(name: str, password: str) -> None:
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(func.lower(User.name) == name.lower()))
        if user:
            user.role = "admin"
            user.password_hash = hash_password(password)
            user.password_changed_at = now_utc()  # sessões abertas com a senha antiga são encerradas
            print(f"Usuário '{user.name}' promovido a admin e senha atualizada.")
        else:
            session.add(User(name=name, password_hash=hash_password(password), role="admin"))
            print(f"Admin '{name}' criado.")
        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit('Uso: python -m app.scripts.create_admin "Nome"')
    n = _clean_name(sys.argv[1])
    p = _check_password(getpass.getpass("Senha: "))
    if getpass.getpass("Repita a senha: ") != p:
        sys.exit("As senhas não conferem.")
    asyncio.run(main(n, p))
