import secrets

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.deps import AdminUser, SessionDep
from app.core.security import hash_password
from app.models import AuditLog, User
from app.schemas.user import (
    ActiveIn,
    ResetPasswordIn,
    ResetPasswordOut,
    RoleIn,
    UserOut,
    UserPublic,
)

router = APIRouter(prefix="/users", tags=["users"])


async def _get_or_404(session, user_id: int) -> User:
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    return user


@router.get("", response_model=list[UserPublic])
async def list_users(session: SessionDep, q: str | None = None, limit: int = 100, offset: int = 0):
    """Lista pública (somente id e nome), usada para busca ao inscrever jogadores."""
    stmt = select(User).where(User.is_active.is_(True)).order_by(User.name)
    if q:
        stmt = stmt.where(User.name.ilike(f"%{q}%"))
    result = await session.scalars(stmt.limit(min(limit, 200)).offset(offset))
    return result.all()


@router.get("/admin", response_model=list[UserOut])
async def list_users_admin(_: AdminUser, session: SessionDep):
    return (await session.scalars(select(User).order_by(User.name))).all()


@router.post("/{user_id}/reset-password", response_model=ResetPasswordOut)
async def reset_password(user_id: int, data: ResetPasswordIn, admin: AdminUser, session: SessionDep):
    user = await _get_or_404(session, user_id)
    temp = data.new_password or secrets.token_urlsafe(9)
    user.password_hash = hash_password(temp)
    session.add(AuditLog(actor_id=admin.id, action="user.reset_password", entity="user", entity_id=user.id))
    await session.commit()
    return ResetPasswordOut(user_id=user.id, temporary_password=None if data.new_password else temp)


@router.patch("/{user_id}/role", response_model=UserOut)
async def set_role(user_id: int, data: RoleIn, admin: AdminUser, session: SessionDep):
    user = await _get_or_404(session, user_id)
    if user.id == admin.id and data.role != "admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Você não pode remover seu próprio acesso de admin.")
    old = user.role
    user.role = data.role
    session.add(
        AuditLog(actor_id=admin.id, action="user.set_role", entity="user", entity_id=user.id, data={"from": old, "to": data.role})
    )
    await session.commit()
    return user


@router.patch("/{user_id}/active", response_model=UserOut)
async def set_active(user_id: int, data: ActiveIn, admin: AdminUser, session: SessionDep):
    user = await _get_or_404(session, user_id)
    if user.id == admin.id and not data.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Você não pode desativar a própria conta.")
    user.is_active = data.is_active
    session.add(
        AuditLog(actor_id=admin.id, action="user.set_active", entity="user", entity_id=user.id, data={"is_active": data.is_active})
    )
    await session.commit()
    return user
