import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.security import MIN_PASSWORD_LENGTH

_NAME_RE = re.compile(r"^[\w .\-]{3,32}$", re.UNICODE)

Role = Literal["admin", "organizer", "player"]


def _clean_name(v: str) -> str:
    v = " ".join(v.split())
    if not _NAME_RE.match(v):
        raise ValueError("Nome deve ter de 3 a 32 caracteres (letras, números, espaço, ponto, hífen, _).")
    return v


def _check_password(v: str) -> str:
    if len(v) < MIN_PASSWORD_LENGTH or len(v) > 128:
        raise ValueError(f"A senha deve ter de {MIN_PASSWORD_LENGTH} a 128 caracteres.")
    return v


class RegisterIn(BaseModel):
    name: str
    password: str
    captcha_token: str | None = Field(None, max_length=4096)  # comprovante do Turnstile, quando a verificação está ativa

    _n = field_validator("name")(_clean_name)
    _p = field_validator("password")(_check_password)


class AuthOptions(BaseModel):
    """Como o cadastro está configurado (o site usa para mostrar ou esconder "Criar conta" e a caixinha anti-robô)."""

    registration_open: bool
    turnstile_site_key: str | None = None


class LoginIn(BaseModel):
    name: str
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: Role
    is_active: bool
    created_at: datetime
    must_change_password: bool = False


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str

    _p = field_validator("new_password")(_check_password)


class ResetPasswordIn(BaseModel):
    new_password: str | None = None  # se omitido, o servidor gera uma senha temporária

    @field_validator("new_password")
    @classmethod
    def _p(cls, v):
        return None if v is None else _check_password(v)


class ResetPasswordOut(BaseModel):
    user_id: int
    temporary_password: str | None = None


class AdminCreateUserIn(BaseModel):
    """Criação de conta por um admin. Sem senha, o servidor gera uma temporária."""

    name: str
    password: str | None = None
    role: Role = "player"

    _n = field_validator("name")(_clean_name)

    @field_validator("password")
    @classmethod
    def _p(cls, v):
        return None if v is None else _check_password(v)


class AdminCreateUserOut(BaseModel):
    user: UserOut
    temporary_password: str | None = None


class RoleIn(BaseModel):
    role: Role


class ActiveIn(BaseModel):
    is_active: bool
