"""Revisión de solicitudes: la corre el Programador de tareas cada minuto.

Pasos (contrato §7.3):
    1. Dentro de una franja bloqueada (±15 minutos de las horas de los otros
       robots) termina sin preguntar nada: no toma solicitudes ni usa la VPN.
    2. Toma el candado sin esperar; si lo tiene otro proceso del robot (la
       nocturna, la del domingo o la revisión del minuto anterior), termina.
    3. Se actualiza (autoactualizar.py): pregunta a /version qué commit está
       desplegado y, si es otro, lleva la copia del robot a ese commit con un
       avance rápido. Si se actualizó, o si hay complementos pendientes en
       robot/complementos.toml que caben antes de la siguiente franja, suelta
       el candado, lanza run_robot.py --tras-despliegue en un proceso nuevo
       (con el código nuevo) y termina. Si la actualización falla, avisa (una
       vez por hora) y sigue con el código de hoy.
    4. Pide hasta 20 solicitudes a /solicitudes/tomar, sin VPN. Si no hay,
       termina sin subir la VPN.
    5. Si hay, arma una corrida por empresa y conjunto y las corre con las dos
       fases de run_robot (VPN solo mientras consulta SAP).

Para no llenar robot/logs/robot.log, una revisión sin trabajo no escribe nada
(solo DEBUG). Los avisos por correo que se repetirían cada minuto tienen
límite: la configuración incompleta, uno al día; un error al tomar las
solicitudes, uno inesperado, una actualización que falla o un complemento
inválido, uno por hora. Un error al preguntar /version solo va al log en DEBUG:
la ruta puede no existir todavía en el servidor. Los fallos de una corrida avisan
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
from pathlib import Path
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterator

import autoactualizar
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
def _sin_info(nombre: str, nivel: int = logging.WARNING) -> Iterator[None]:
    """Calla el INFO de un logger del robot (el de la API anota cada POST que sale bien)."""
    logger = registro.obtener(nombre)
    previo = logger.level
    logger.setLevel(nivel)
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


def _commit_desplegado(api: ApiCliente) -> str | None:
    """El commit que la API dice desplegado, o None. Un error no frena la revisión y solo va
    al log en DEBUG (también el de la API): la ruta es provisional y puede no existir aún."""
    try:
        with _sin_info("api", logging.CRITICAL + 1):
            return api.version()
    except Exception as exc:
        log.debug("No se pudo preguntar a la API qué commit está desplegado: %s", exc)
        return None


def _hay_complementos(cfg: Config, ahora: Callable[[], datetime], git: autoactualizar.Ejecutor | None) -> bool:
    """True si hay complementos pendientes y caben antes de la siguiente franja.

    Si no caben, no se lanza nada: un proceso que se queda esperando el hueco dejaría que
    cada minuto lanzara otro. Lo retoma la revisión del minuto en que quepan.
    """
    planes, problemas = run_robot.complementos_pendientes(ahora, git)
    if problemas:
        for problema in problemas:
            log.error("%s", problema)
        _avisar_con_limite(cfg, "complementos", AVISO_REPETIDO, ahora(),
                           [("COMPLEMENTOS", problema) for problema in problemas])
    if not planes:
        return False
    estimado = sum((plan.estimado for _, plan in planes), timedelta())
    momento = ahora()
    try:
        inicio = bloqueo.inicio_hueco(momento, estimado, cfg.franjas, cfg.margen_franja_min)
    except ValueError as exc:
        mensaje = f"Los complementos pendientes no caben en ningún hueco: {exc}"
        log.error(mensaje)
        _avisar_con_limite(cfg, "complementos", AVISO_REPETIDO, momento, [("COMPLEMENTOS", mensaje)])
        return False
    if inicio > momento:
        log.debug("Hay complementos pendientes, pero no caben antes de la siguiente franja; se lanzan "
                  "desde las %s.", f"{inicio:%H:%M}")
        return False
    log.info("Complementos pendientes: %s.", ", ".join(c.id for c, _ in planes))
    return True


def _autoactualizar(
    cfg: Config,
    api: ApiCliente,
    *,
    ahora: Callable[[], datetime],
    git: autoactualizar.Ejecutor | None,
    comando: autoactualizar.Ejecutor | None,
) -> bool:
    """Paso 3, con el candado tomado. True si hay que lanzar run_robot.py --tras-despliegue.

    Nunca lanza: un fallo avisa (una vez por hora) y la revisión sigue con el código de hoy.
    """
    commit: str | None = None
    try:
        commit = _commit_desplegado(api)
        resultado = autoactualizar.actualizar(commit, git=git, comando=comando)
        if resultado.estado == autoactualizar.FALLO:
            mensaje = (f"No se pudo actualizar el robot al commit desplegado {(commit or '?')[:12]}: "
                       f"{resultado.motivo} Sigue con el código de hoy.")
            log.error(mensaje)
            _avisar_con_limite(cfg, "autoactualizar", AVISO_REPETIDO, ahora(), [("AUTOACTUALIZAR", mensaje)])
            return False
        if resultado.estado == autoactualizar.ACTUALIZADO:
            log.info("Robot actualizado de %s a %s%s.", (resultado.antes or "?")[:12], (resultado.despues or "?")[:12],
                     " (con los paquetes nuevos de requirements.txt)" if resultado.requisitos else "")
            return True
        return _hay_complementos(cfg, ahora, git)
    except Exception as exc:  # la actualización nunca deja sin atender las solicitudes
        log.exception("Error inesperado al revisar la actualización del robot.")
        mensaje = f"Error al revisar la actualización del robot: {extraccion.mensaje_seguro(exc)}"
        _avisar_con_limite(cfg, "autoactualizar", AVISO_REPETIDO, ahora(), [("AUTOACTUALIZAR", mensaje)])
        return False


def _lanzar_tras_despliegue(
    cfg: Config, lanzar: autoactualizar.Lanzador, ahora: Callable[[], datetime]
) -> int:
    """El proceso nuevo, ya sin el candado: él lo toma (y espera) como los modos programados."""
    cmd = autoactualizar.comando_tras_despliegue()
    try:
        lanzar(cmd, Path(config.BASE_DIR))
    except OSError as exc:
        mensaje = f"No se pudo lanzar run_robot.py --tras-despliegue: {exc.__class__.__name__}."
        log.error(mensaje)
        _avisar_con_limite(cfg, "autoactualizar", AVISO_REPETIDO, ahora(), [("AUTOACTUALIZAR", mensaje)])
        return 1
    log.info("Lanzado run_robot.py --tras-despliegue; esta revisión no toma solicitudes.")
    return 0


def _revisar(
    cfg: Config,
    api: ApiCliente,
    *,
    fabrica_vpn: Callable[..., Any],
    conectar: Callable[..., Any],
    ahora: Callable[[], datetime],
) -> int:
    """Pasos 4 y 5, con el candado ya tomado."""
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
    git: autoactualizar.Ejecutor | None = None,
    comando: autoactualizar.Ejecutor | None = None,
    lanzar: autoactualizar.Lanzador | None = None,
) -> int:
    argparse.ArgumentParser(
        description="Revisa las solicitudes de la app y las corre (Programador de tareas, cada minuto)."
    ).parse_args(argv)
    registro.configurar()

    cfg: Config | None = None
    try:
        cfg = cargar_config()
        registro.registrar_secretos(cfg)
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
        api = fabrica_api(cfg.api)
        if _autoactualizar(cfg, api, ahora=ahora, git=git, comando=comando):
            candado.soltar()  # el proceso nuevo lo toma; soltar() otra vez en el finally no hace nada
            return _lanzar_tras_despliegue(cfg, lanzar or autoactualizar.lanzador_por_defecto, ahora)
        return _revisar(cfg, api, fabrica_vpn=fabrica_vpn, conectar=conectar, ahora=ahora)
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
