"""Verificação anti-robô do cadastro (Cloudflare Turnstile).

O site mostra a caixinha da Cloudflare; quando a pessoa passa, ela recebe um comprovante (token) de uso único que é
enviado junto com o cadastro. A API pergunta à Cloudflare se o comprovante é válido antes de criar a conta.
Chaves de teste (sempre aprovam), úteis no ambiente local: site 1x00000000000000000000AA,
secreta 1x0000000000000000000000000000000AA.
"""
import logging

import httpx

from app.core.config import get_settings

log = logging.getLogger("captcha")
VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class CaptchaUnavailable(Exception):
    """Não foi possível falar com a Cloudflare (rede, instabilidade)."""


async def verify(token: str) -> bool:
    data = {"secret": get_settings().turnstile_secret.strip(), "response": token}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(VERIFY_URL, data=data)
            r.raise_for_status()
            result = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("Falha ao consultar o Turnstile: %s", e)
        raise CaptchaUnavailable from e
    if not result.get("success"):
        log.info("Turnstile recusou o comprovante: %s", result.get("error-codes"))
    return bool(result.get("success"))
