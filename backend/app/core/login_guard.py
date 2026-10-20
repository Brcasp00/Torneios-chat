"""Bloqueio de login por tentativas erradas (proteção contra quem tenta adivinhar a senha).

Depois de MAX_FAILURES senhas erradas seguidas para o mesmo nome (dentro de LOCK_SECONDS), o login desse nome fica
bloqueado por LOCK_SECONDS, mesmo com a senha certa. Quem já está logado continua usando a plataforma normalmente.
Um login certo zera a contagem; o admin desbloqueia ao redefinir a senha.

O estado fica na memória do servidor (um único processo no Render): reiniciar o servidor zera os bloqueios.
Nomes que não existem são tratados igual, para não revelar quais contas existem.
"""
import time

MAX_FAILURES = 3
LOCK_SECONDS = 10 * 60
_MAX_ENTRIES = 10_000

# nome normalizado -> [falhas, momento da 1ª falha, bloqueado até]
_state: dict[str, list[float]] = {}


def _clock() -> float:
    return time.monotonic()


def _key(name: str) -> str:
    return " ".join(name.split()).lower()


def locked_for(name: str) -> int:
    """Segundos que faltam para o desbloqueio (0 = liberado)."""
    entry = _state.get(_key(name))
    if not entry:
        return 0
    return max(0, int(entry[2] - _clock() + 0.999))


def failure(name: str) -> None:
    now = _clock()
    key = _key(name)
    entry = _state.get(key)
    if entry is None or now - entry[1] > LOCK_SECONDS:
        entry = [0, now, 0]  # falhas antigas (fora da janela) não contam mais
    entry[0] += 1
    if entry[0] >= MAX_FAILURES:
        entry = [0, now, now + LOCK_SECONDS]
    _state[key] = entry
    if len(_state) > _MAX_ENTRIES:
        _prune(now)


def success(name: str) -> None:
    _state.pop(_key(name), None)


clear = success  # admin redefiniu a senha: desbloqueia


def _prune(now: float) -> None:
    for key in [k for k, (_, first, until) in _state.items() if until <= now and now - first > LOCK_SECONDS]:
        del _state[key]


def reset() -> None:
    """Zera tudo (usado nos testes)."""
    _state.clear()
