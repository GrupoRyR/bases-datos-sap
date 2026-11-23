"""Tareas programadas de Windows de los otros robots: lanzarlas y esperar a que terminen.

El vigilante las usa para la cadena de los otros robots («SAP HANA - todo» y el
publicador del panel). Solo las lanza por nombre con los cmdlets del módulo
ScheduledTasks de PowerShell; nunca toca sus scripts ni su programación.

    Start-ScheduledTask   -TaskName '<n>'                   -> lanzar
    (Get-ScheduledTask     -TaskName '<n>').State           -> Running / Queued mientras corre
    (Get-ScheduledTaskInfo -TaskName '<n>').LastTaskResult  -> 0 si terminó bien

Los nombres del estado (Ready, Running, Queued, Disabled) son los del enum, no se
traducen con el idioma de Windows.
"""
from __future__ import annotations

import subprocess
import time
from datetime import timedelta
from typing import Callable

from registro import obtener

log = obtener("tareas")

CORRIENDO = frozenset({"Running", "Queued"})
TIMEOUT_POWERSHELL_S = 120


def _literal(texto: str) -> str:
    """Cadena literal de PowerShell entre comillas simples (una ' se escribe '')."""
    return "'" + texto.replace("'", "''") + "'"


def _corto(texto: str | None) -> str:
    """Primera línea con texto de la salida de error de PowerShell, para los mensajes."""
    for linea in (texto or "").splitlines():
        if linea.strip():
            return linea.strip()[:200]
    return "sin detalle"


class TareasWindows:
    """Lanza una tarea programada y espera, revisando cada `intervalo_s`, a que termine."""

    def __init__(
        self,
        *,
        ejecutar: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.monotonic,
        intervalo_s: float = 30,
    ) -> None:
        self.ejecutar = ejecutar
        self.dormir = dormir
        self.reloj = reloj
        self.intervalo_s = intervalo_s

    def _powershell(self, comando: str) -> subprocess.CompletedProcess:
        """Corre un comando de PowerShell sin shell ni ventana; cualquier error sale con código 1."""
        return self.ejecutar(
            [
                "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                f"$ErrorActionPreference = 'Stop'; {comando}",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_POWERSHELL_S,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _consultar(self, comando: str) -> tuple[str | None, str | None]:
        """(salida, None) si el comando terminó bien; (None, motivo) si no."""
        try:
            res = self._powershell(comando)
        except (OSError, subprocess.SubprocessError) as exc:
            return None, str(exc) or type(exc).__name__
        if res.returncode != 0:
            return None, _corto(res.stderr)
        return (res.stdout or "").strip(), None

    def correr(self, nombre: str, limite: timedelta) -> str | None:
        """Lanza la tarea `nombre` y espera a que termine. None si terminó bien; si no, el motivo.

        Nunca lanza excepciones: un fallo de PowerShell también es un motivo.
        """
        tarea = _literal(nombre)
        _, error = self._consultar(f"Start-ScheduledTask -TaskName {tarea}")
        if error is not None:
            return f"No se pudo lanzar la tarea {nombre}: {error}"
        log.info("Tarea %s lanzada; espero a que termine.", nombre)

        inicio = self.reloj()
        while True:
            # Se espera antes de la primera revisión para dar tiempo a que arranque.
            self.dormir(self.intervalo_s)
            estado, error = self._consultar(f"(Get-ScheduledTask -TaskName {tarea}).State")
            if error is not None:
                return f"No se pudo revisar la tarea {nombre}: {error}"
            if estado not in CORRIENDO:
                break
            if self.reloj() - inicio >= limite.total_seconds():
                minutos = int(limite.total_seconds() // 60)
                return f"La tarea {nombre} sigue corriendo después de {minutos} minutos"

        resultado, error = self._consultar(f"(Get-ScheduledTaskInfo -TaskName {tarea}).LastTaskResult")
        if error is not None:
            return f"No se pudo leer el resultado de la tarea {nombre}: {error}"
        if resultado != "0":
            return f"La tarea {nombre} terminó con código {resultado or '?'}"
        log.info("La tarea %s terminó bien.", nombre)
        return None
