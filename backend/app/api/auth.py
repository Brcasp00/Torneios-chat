from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.deps import CurrentUserAnyState, SessionDep
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas.user import ChangePasswordIn, LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash de uma senha qualquer, usado para gastar o mesmo tempo quando o usuário não existe.
_DUMMY_HASH = hash_password("dummy-password")


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterIn, session: SessionDep):
    exists = await session.scalar(select(User.id).where(func.lower(User.name) == data.name.lower()))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um usuário com esse nome.")
    user = User(name=data.name, password_hash=hash_password(data.password), role="player")
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um usuário com esse nome.")
    await session.refresh(user)
    return TokenOut(access_token=create_access_token(user.id, user.role), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
async def login(data: LoginIn, session: SessionDep):
    name = " ".join(data.name.split())
    user = await session.scalar(select(User).where(func.lower(User.name) == name.lower()))
    ok = verify_password(data.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nome ou senha inválidos.")
    return TokenOut(access_token=create_access_token(user.id, user.role), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUserAnyState):
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(data: ChangePasswordIn, user: CurrentUserAnyState, session: SessionDep):
    """Troca a própria senha. Também libera a conta de quem estava com senha temporária."""
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha atual incorreta.")
    if data.new_password == data.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A nova senha precisa ser diferente da senha atual.")
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    await session.commit()
