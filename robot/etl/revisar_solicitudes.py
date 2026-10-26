"""Revisión de solicitudes: la corre el Programador de tareas cada minuto.

Pasos (contrato §7.3):
    1. Dentro de una franja bloqueada (±15 minutos de las horas de los otros
       robots) termina sin preguntar nada: no toma solicitudes ni usa la VPN.
    2. Toma el candado sin esperar; si lo tiene otro proceso del robot (la
       nocturna, la del domingo o la revisión del minuto anterior), termina.
    3. Pide hasta 20 solicitudes a /solicitudes/tomar, sin VPN. Si no hay,
       termina sin subir la VPN.
    4. Si hay, arma una corrida por empresa y conjunto y las corre con las dos
       fases de run_robot (VPN solo mientras consulta SAP).

Para no llenar robot/logs/robot.log, una revisión sin trabajo no escribe nada
(solo DEBUG). Los avisos por correo que se repetirían cada minuto tienen
límite: la configuración incompleta, uno al día; un error al tomar las
solicitudes o uno inesperado, uno por hora. Los fallos de una corrida avisan
siempre, una vez por revisión.

Uso (desde robot\\etl):
    python revisar_solicitudes.py

Salida: 0 sin trabajo o todo bien, 1 algún fallo, 2 configuración incompleta.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterator

import bloqueo
import config
import extraccion
import hana
import notificar
import registro
import run_robot
from api import ApiCliente
from config import Config, ConfigError, cargar_config
from trabajos import Trabajo, TrabajoInvalido, trabajos_de_solicitudes
from vpn import RobotVPN

MAX_SOLICITUDES = 20
AVISO_CONFIGURACION = timedelta(days=1)
AVISO_REPETIDO = timedelta(hours=1)

log = registro.obtener("solicitudes")


@contextmanager
def _sin_info(nombre: str) -> Iterator[None]:
    """Calla el INFO de un logger del robot (el de la API anota cada POST que sale bien)."""
    logger = registro.obtener(nombre)
    previo = logger.level
    logger.setLevel(logging.WARNING)
    try:
        yield
    finally:
        logger.setLevel(previo)


def _avisar_con_limite(
    cfg: Config, clave: str, cada: timedelta, momento: datetime, fallos: list[tuple[str, str]]
) -> None:
    """Avisa por correo si no se avisó lo mismo en el último `cada` (marca en robot/state)."""
    marca = config.STATE_DIR / f"aviso_{clave}.json"
    try:
        ultimo = datetime.fromisoformat(json.loads(marca.read_text(encoding="utf-8"))["avisado_en"])
        if momento - ultimo < cada:
            log.debug("Ya se avisó %s a las %s; no se repite el correo.", clave, ultimo)
            return
    except (OSError, ValueError, KeyError, TypeError):
        pass  # sin marca o ilegible: se avisa
    notificar.avisar_fallos(cfg.alertas, fallos)
    try:
        config.STATE_DIR.mkdir(parents=True, exist_ok=True)
        marca.write_text(json.dumps({"avisado_en": momento.isoformat()}), encoding="utf-8")
    except OSError:
        log.warning("No se pudo guardar la marca del aviso %s.", clave, exc_info=True)


def _validas(
    solicitudes: list[dict[str, Any]], hoy: date, sin_precios: frozenset[str] = frozenset()
) -> tuple[list[Trabajo], list[tuple[str, str]]]:
    """Trabajos de las solicitudes válidas; cada inválida va a los fallos y la API la vence."""
    validas: list[dict[str, Any]] = []
    fallos: list[tuple[str, str]] = []
    for solicitud in solicitudes:
        try:
            trabajos_de_solicitudes([solicitud], hoy)  # valida empresa, conjunto, parte y desde
        except TrabajoInvalido as exc:
            log.error("Solicitud inválida: %s", exc)
            fallos.append(("SOLICITUDES", str(exc)))
            continue
        validas.append(solicitud)
    return trabajos_de_solicitudes(validas, hoy, sin_precios), fallos


def _revisar(
    cfg: Config,
    *,
    fabrica_api: Callable[..., ApiCliente],
    fabrica_vpn: Callable[..., Any],
    conectar: Callable[..., Any],
    ahora: Callable[[], datetime],
) -> int:
    """Pasos 3 y 4, con el candado ya tomado."""
    api = fabrica_api(cfg.api)
    try:
        with _sin_info("api"):
            solicitudes = api.tomar_solicitudes(MAX_SOLICITUDES)
    except Exception as exc:
        mensaje = f"No se pudieron tomar las solicitudes: {exc}"
        log.error(mensaje)
        run_robot.guardar_estado(estado="ERROR", modo="solicitudes", etapa="SOLICITUDES", error=mensaje)
        _avisar_con_limite(cfg, "tomar", AVISO_REPETIDO, ahora(), [("SOLICITUDES", mensaje)])
        return 1
    if not solicitudes:
        log.debug("Sin solicitudes.")
        return 0

    inicio = time.monotonic()
    log.info("Solicitudes tomadas: %s.", ", ".join(str(s.get("id")) for s in solicitudes))
    trabajos, fallos = _validas(solicitudes, ahora().date(), cfg.hana.sin_precios())
    if trabajos:
        log.info("Trabajos: %s.", ", ".join(t.nombre for t in trabajos))
        fallos += run_robot.ejecutar_trabajos(
            cfg, trabajos, api=api, robot_vpn=fabrica_vpn(cfg.vpn), conectar=conectar, ahora=ahora,
        )
    duracion = round(time.monotonic() - inicio, 1)
    run_robot.guardar_estado(
        estado="ERROR" if fallos else "OK",
        modo="solicitudes",
        solicitudes=[s.get("id") for s in solicitudes],
        trabajos=[t.nombre for t in trabajos],
        fallos=[list(f) for f in fallos],
        duracion_seg=duracion,
    )
    if fallos:
        for etapa, mensaje in fallos:
            log.error("FALLO en la etapa %s: %s", etapa, mensaje)
        notificar.avisar_fallos(cfg.alertas, fallos)
        return 1
    log.info("Solicitudes terminadas sin fallos en %.1fs.", duracion)
    return 0


def main(
    argv: list[str] | None = None,
    *,
    fabrica_api: Callable[..., ApiCliente] = ApiCliente,
    fabrica_vpn: Callable[..., Any] = RobotVPN,
    conectar: Callable[..., Any] = hana.conectar,
    ahora: Callable[[], datetime] = config.ahora,
) -> int:
    argparse.ArgumentParser(
        description="Revisa las solicitudes de la app y las corre (Programador de tareas, cada minuto)."
    ).parse_args(argv)
    registro.configurar()

    cfg: Config | None = None
    try:
        cfg = cargar_config()
        cfg.validar(requiere_vpn=True, requiere_api=True)
    except ConfigError as exc:
        log.error("Configuración incompleta:\n%s", exc)
        if cfg is not None and cfg.alertas.habilitada:
            _avisar_con_limite(cfg, "configuracion", AVISO_CONFIGURACION, ahora(),
                               [("CONFIGURACION", str(exc))])
        return 2

    franja = bloqueo.en_franja(ahora(), cfg.franjas, cfg.margen_franja_min)
    if franja:
        log.debug("Franja bloqueada de las %s: no se revisan solicitudes.", franja)
        return 0

    candado = bloqueo.Bloqueo(reloj=ahora)
    if not candado.tomar():
        log.debug("Otro proceso del robot tiene el candado; esta revisión se salta.")
        return 0
    try:
        return _revisar(cfg, fabrica_api=fabrica_api, fabrica_vpn=fabrica_vpn, conectar=conectar, ahora=ahora)
    except Exception as exc:  # red de seguridad: nada sale sin registrar
        log.exception("Error inesperado al revisar las solicitudes.")
        mensaje = extraccion.mensaje_seguro(exc)
        run_robot.guardar_estado(estado="ERROR", modo="solicitudes", etapa="INESPERADO", error=mensaje)
        _avisar_con_limite(cfg, "inesperado", AVISO_REPETIDO, ahora(), [("INESPERADO", mensaje)])
        return 1
    finally:
        candado.soltar()


if __name__ == "__main__":
    sys.exit(main())
