from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import User

_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user_optional(
    session: SessionDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User | None:
    if creds is None:
        return None
    payload = decode_access_token(creds.credentials)
    if not payload:
        return None
    user = await session.get(User, int(payload["sub"]))
    return user if user and user.is_active else None


async def get_current_user_any_state(user: Annotated[User | None, Depends(get_current_user_optional)]) -> User:
    """Usuário autenticado, mesmo que ainda precise trocar a senha temporária (usado só em /auth/me e /auth/change-password)."""
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Não autenticado.", headers={"WWW-Authenticate": "Bearer"})
    return user


async def get_current_user(user: Annotated[User, Depends(get_current_user_any_state)]) -> User:
    if user.must_change_password:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Você está com uma senha temporária. Troque a senha em 'Minha conta' para continuar."
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserAnyState = Annotated[User, Depends(get_current_user_any_state)]
OptionalUser = Annotated[User | None, Depends(get_current_user_optional)]


def require_roles(*roles: str):
    async def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão para esta ação.")
        return user

    return checker


# O papel é lido do banco a cada requisição, então mudanças de role valem imediatamente.
AdminUser = Annotated[User, Depends(require_roles("admin"))]
StaffUser = Annotated[User, Depends(require_roles("admin", "organizer"))]
