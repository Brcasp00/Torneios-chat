import secrets

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core import login_guard
from app.core.deps import AdminUser, SessionDep
from app.core.security import hash_password
from app.models import AuditLog, User
from app.schemas.user import (
    ActiveIn,
    AdminCreateUserIn,
    AdminCreateUserOut,
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
async def list_users(
    session: SessionDep, q: str | None = None, limit: int = Query(100, ge=1), offset: int = Query(0, ge=0)
):
    """Lista pública (somente id e nome), usada para busca ao inscrever jogadores."""
    stmt = select(User).where(User.is_active.is_(True)).order_by(User.name)
    if q:
        stmt = stmt.where(User.name.ilike(f"%{q}%"))
    result = await session.scalars(stmt.limit(min(limit, 200)).offset(offset))
    return result.all()


@router.get("/admin", response_model=list[UserOut])
async def list_users_admin(_: AdminUser, session: SessionDep):
    return (await session.scalars(select(User).order_by(User.name))).all()


@router.post("", response_model=AdminCreateUserOut, status_code=status.HTTP_201_CREATED)
async def create_user(data: AdminCreateUserIn, admin: AdminUser, session: SessionDep):
    """Admin cria uma conta (com o papel escolhido). Sem senha informada, devolve uma temporária uma única vez."""
    if await session.scalar(select(User.id).where(func.lower(User.name) == data.name.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um usuário com esse nome.")
    password = data.password or secrets.token_urlsafe(9)
    # Senha gerada pelo sistema é temporária: a pessoa é obrigada a trocá-la no primeiro acesso.
    user = User(name=data.name, password_hash=hash_password(password), role=data.role, must_change_password=data.password is None)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um usuário com esse nome.")
    session.add(
        AuditLog(actor_id=admin.id, action="user.create", entity="user", entity_id=user.id, data={"name": user.name, "role": user.role})
    )
    await session.commit()
    await session.refresh(user)
    return AdminCreateUserOut(user=UserOut.model_validate(user), temporary_password=None if data.password else password)


@router.post("/{user_id}/reset-password", response_model=ResetPasswordOut)
async def reset_password(user_id: int, data: ResetPasswordIn, admin: AdminUser, session: SessionDep):
    user = await _get_or_404(session, user_id)
    temp = data.new_password or secrets.token_urlsafe(9)
    user.password_hash = hash_password(temp)
    user.must_change_password = data.new_password is None  # senha gerada = temporária; definida pelo admin = definitiva
    login_guard.clear(user.name)  # redefinir a senha também desbloqueia o login
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
