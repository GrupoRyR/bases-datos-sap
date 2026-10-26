"""Firma HMAC-SHA256 de cada petición del robot (docs/contrato-robot.md §3).

Cadena canónica en UTF-8, campos unidos por "\\n" y sin salto final:

    {timestamp}
    {nonce}
    POST
    {ruta}                      p. ej. /api/robot/v1/corridas/42/lotes
    {sha256 del cuerpo tal como viaja (los bytes gzip si va comprimido)}
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

METODO = "POST"


def sha256_hex(cuerpo: bytes) -> str:
    return hashlib.sha256(cuerpo).hexdigest()


def cadena_canonica(timestamp: int, nonce: str, ruta: str, cuerpo: bytes) -> str:
    return "\n".join((str(int(timestamp)), nonce, METODO, ruta, sha256_hex(cuerpo)))


def firmar(secret: str, timestamp: int, nonce: str, ruta: str, cuerpo: bytes) -> str:
    """Devuelve "sha256=<hex>" para el encabezado X-Robot-Signature."""
    cadena = cadena_canonica(timestamp, nonce, ruta, cuerpo)
    digest = hmac.new(secret.encode("utf-8"), cadena.encode("utf-8"), hashlib.sha256)
    return f"sha256={digest.hexdigest()}"


def nuevo_nonce() -> str:
    """16 bytes al azar en 32 caracteres hexadecimales en minúscula."""
    return secrets.token_hex(16)


def encabezados(
    key_id: str,
    secret: str,
    ruta: str,
    cuerpo: bytes,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Encabezados X-Robot-* de una petición. Cada llamada usa hora y nonce nuevos."""
    ts = int(time.time()) if timestamp is None else int(timestamp)
    nonce = nonce or nuevo_nonce()
    return {
        "X-Robot-Key": key_id,
        "X-Robot-Timestamp": str(ts),
        "X-Robot-Nonce": nonce,
        "X-Robot-Signature": firmar(secret, ts, nonce, ruta, cuerpo),
    }
