from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core import login_guard
from app.core.config import get_settings
from app.core.deps import CurrentUserAnyState, SessionDep
from app.core.security import (
    MIN_PASSWORD_LENGTH,
    create_access_token,
    hash_password,
    hash_password_async,
    needs_rehash,
    now_utc,
    verify_password_async,
)
from app.models import User
from app.schemas.user import AuthOptions, ChangePasswordIn, LoginIn, RegisterIn, TokenOut, UserOut
from app.services import captcha

router = APIRouter(prefix="/auth", tags=["auth"])

# Hash de uma senha qualquer, usado para gastar o mesmo tempo quando o usuário não existe.
_DUMMY_HASH = hash_password("dummy-password")


@router.get("/options", response_model=AuthOptions)
async def options():
    """Público: se o cadastro está aberto e a chave pública da verificação anti-robô (se houver)."""
    s = get_settings()
    return AuthOptions(
        registration_open=s.allow_registration,
        turnstile_site_key=s.turnstile_site_key.strip() if s.allow_registration and s.turnstile_enabled else None,
    )


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterIn, session: SessionDep):
    s = get_settings()
    if not s.allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "O cadastro está fechado. Peça a um admin para criar a sua conta.")
    if s.turnstile_enabled:
        if not data.captcha_token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Conclua a verificação anti-robô antes de criar a conta.")
        try:
            # O IP do visitante não é enviado: no Render a API só enxerga o IP do proxy (o campo é opcional).
            ok = await captcha.verify(data.captcha_token)
        except captcha.CaptchaUnavailable:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Não foi possível fazer a verificação anti-robô agora. Tente de novo em instantes."
            )
        if not ok:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "A verificação anti-robô falhou ou expirou. Tente de novo.")
    exists = await session.scalar(select(User.id).where(func.lower(User.name) == data.name.lower()))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um usuário com esse nome.")
    user = User(name=data.name, password_hash=await hash_password_async(data.password), role="player")
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
    wait = login_guard.locked_for(name)
    if wait:
        minutes = (wait + 59) // 60
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Muitas tentativas erradas. O login desta conta está bloqueado; tente de novo em {minutes} minuto(s).",
            headers={"Retry-After": str(wait)},
        )
    user = await session.scalar(select(User).where(func.lower(User.name) == name.lower()))
    ok = await verify_password_async(data.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok or not user.is_active:
        login_guard.failure(name)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nome ou senha inválidos.")
    login_guard.success(name)
    changed = False
    if len(data.password) < MIN_PASSWORD_LENGTH and not user.must_change_password:
        # Senha criada antes do mínimo atual: entra, mas precisa trocar antes de usar a plataforma.
        user.must_change_password = changed = True
    if needs_rehash(user.password_hash):
        # Hash feito com parâmetros antigos (mais pesados): refaz com os atuais, sem a pessoa perceber.
        user.password_hash = await hash_password_async(data.password)
        changed = True
    if changed:
        await session.commit()
    return TokenOut(access_token=create_access_token(user.id, user.role), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUserAnyState):
    return user


@router.post("/change-password", response_model=TokenOut)
async def change_password(data: ChangePasswordIn, user: CurrentUserAnyState, session: SessionDep):
    """Troca a própria senha. Também libera a conta de quem estava com senha temporária.

    Todos os crachás emitidos antes deixam de valer (outros aparelhos saem); devolve um crachá novo para quem trocou.
    """
    if not await verify_password_async(data.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha atual incorreta.")
    if data.new_password == data.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A nova senha precisa ser diferente da senha atual.")
    user.password_hash = await hash_password_async(data.new_password)
    user.must_change_password = False
    user.password_changed_at = now_utc()
    await session.commit()
    return TokenOut(access_token=create_access_token(user.id, user.role), user=UserOut.model_validate(user))
