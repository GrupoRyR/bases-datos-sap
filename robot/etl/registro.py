"""Logging del robot: consola + archivo rotativo, con redacción de secretos."""
from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

import config

_SECRETOS: list[str] = []


class _RedactarSecretos(logging.Filter):
    """Evita que una contraseña o el secreto HMAC terminen escritos en el log."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            mensaje = record.getMessage()
        except Exception:
            return True
        record.msg = _redactar(mensaje)
        record.args = ()
        # La traza de log.exception() se formatea después del filtro; se arma aquí
        # para redactarla, y el Formatter reutiliza exc_text en vez de rehacerla.
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = _redactar(record.exc_text)
        return True


def _redactar(texto: str) -> str:
    # Cualquier secreto registrado: claves de VPN, HANA y SMTP, y el secreto
    # de la llave del robot (BASES_SAP_ROBOT_SECRET).
    for secreto in _SECRETOS:
        if secreto and secreto in texto:
            texto = texto.replace(secreto, "***")
    # Cubre también el patrón  -p <algo>  de la línea de comandos
    return re.sub(r"(-p|--password)\s+\S+", r"\1 ***", texto)


def registrar_secreto(valor: str | None) -> None:
    """Marca un valor para que nunca aparezca en los logs."""
    if valor and len(valor) >= 4 and valor not in _SECRETOS:
        _SECRETOS.append(valor)


def configurar(nivel: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("bases_sap")
    if logger.handlers:
        return logger

    logger.setLevel(nivel)
    formato = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    filtro = _RedactarSecretos()

    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(formato)
    consola.addFilter(filtro)
    logger.addHandler(consola)

    # config.LOGS_DIR se lee aquí (no al importar) para que las pruebas lo cambien.
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    archivo = RotatingFileHandler(
        config.LOGS_DIR / "robot.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    archivo.setFormatter(formato)
    archivo.addFilter(filtro)
    logger.addHandler(archivo)

    return logger


def obtener(nombre: str) -> logging.Logger:
    return logging.getLogger(f"bases_sap.{nombre}")
