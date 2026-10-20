import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

_NAME_RE = re.compile(r"^[\w .\-]{3,32}$", re.UNICODE)

Role = Literal["admin", "organizer", "player"]


def _clean_name(v: str) -> str:
    v = " ".join(v.split())
    if not _NAME_RE.match(v):
        raise ValueError("Nome deve ter de 3 a 32 caracteres (letras, números, espaço, ponto, hífen, _).")
    return v


def _check_password(v: str) -> str:
    if len(v) < 6 or len(v) > 128:
        raise ValueError("A senha deve ter de 6 a 128 caracteres.")
    return v


class RegisterIn(BaseModel):
    name: str
    password: str

    _n = field_validator("name")(_clean_name)
    _p = field_validator("password")(_check_password)


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


class RoleIn(BaseModel):
    role: Role


class ActiveIn(BaseModel):
    is_active: bool
