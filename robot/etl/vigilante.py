"""Vigilante del robot: comprueba que Bases SAP tenga la completa de hoy.

- `guardar_completa()` / `completa_buena_de_hoy()`: registro propio de la última
  completa (robot/state/ultima_completa.json). `ultima_ejecucion.json` no sirve
  para esto: lo sobrescribe cada revisión de solicitudes.

Este módulo nunca importa run_robot (run_robot lo importa a él).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import config
from registro import obtener

ARCHIVO_COMPLETA = "ultima_completa.json"

log = obtener("vigilante")


def _ruta_completa() -> Path:
    # config.STATE_DIR se lee al llamar (no al importar) para que las pruebas lo cambien.
    return config.STATE_DIR / ARCHIVO_COMPLETA


def guardar_completa(*, fecha: date, estado: str, empresas: list[str], etapas: list[str]) -> None:
    """Registra cómo terminó la completa del día `fecha` (Bogotá).

    `etapas` son solo los nombres de las etapas que fallaron, sin repetir: nunca
    mensajes ni datos de SAP. Si no se puede escribir, queda un aviso en el log.
    """
    datos = {
        "fecha": fecha.isoformat(),
        "estado": estado,
        "empresas": list(empresas),
        "etapas": list(dict.fromkeys(etapas)),
        "terminada_en": datetime.now(timezone.utc).isoformat(),
    }
    try:
        ruta = _ruta_completa()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        log.warning("No se pudo guardar el registro de la completa.", exc_info=True)


def leer_completa() -> dict[str, Any] | None:
    """El registro de la última completa, o None si no existe o no se puede leer."""
    try:
        datos = json.loads(_ruta_completa().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return datos if isinstance(datos, dict) else None


def completa_buena_de_hoy(hoy: date) -> bool:
    """True solo si la última completa es de `hoy`, terminó OK y trajo todas las empresas."""
    datos = leer_completa()
    if datos is None:
        return False
    empresas = datos.get("empresas")
    if not isinstance(empresas, list) or not all(isinstance(e, str) for e in empresas):
        return False
    return (
        datos.get("estado") == "OK"
        and datos.get("fecha") == hoy.isoformat()
        and set(config.EMPRESAS) <= set(empresas)
    )
