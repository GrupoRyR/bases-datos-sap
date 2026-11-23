"""Vigilante del robot (`run_robot.py --vigilar`): Bases SAP con la completa de hoy.

Lo corre la tarea BasesSAP-Vigilante a las 03:45 y a las 07:00, en este orden:

1. Red: prueba que la API (y el panel, si está VIGILANTE_PANEL_URL) respondan por
   HTTPS, hasta 3 veces con un minuto entre intentos. Sin salida a internet no
   corre nada más: avisa (etapa RED).
   - VPN pegada (solo con VIGILANTE_REINICIAR_VPN, apagado por defecto): si no hay
     red y la VPN Sophos sigue conectada, fuera de las franjas bloqueadas, la baja
     con sccli, espera 30 segundos y vuelve a probar la red.
2. Completa de hoy: si ya hay una completa buena de hoy (registro propio,
   robot/state/ultima_completa.json), no hace nada. Si no, corre la completa
   una vez, dentro del mismo candado.
3. Aviso: si la completa de reparación falla, avisa una sola vez (etapa
   COMPLETA); run_robot guarda el estado y manda el correo.

- `guardar_completa()` / `completa_buena_de_hoy()`: registro propio de la última
  completa. `ultima_ejecucion.json` no sirve para esto: lo sobrescribe cada
  revisión de solicitudes.

Este módulo nunca importa run_robot (run_robot lo importa a él).
"""
from __future__ import annotations

import http.client
import json
import socket
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

import bloqueo
import config
from config import Config
from registro import obtener
from vpn import VpnError

ARCHIVO_COMPLETA = "ultima_completa.json"
INTENTOS_RED = 3
ESPERA_RED_S = 60
ESPERA_VPN_S = 30  # tras bajar la VPN, antes de volver a probar la red
TIMEOUT_RED_S = 15
AGENTE = "bases-sap-robot/1"

log = obtener("vigilante")


# --- Registro de la última completa -----------------------------------------------------


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


def _por_que_no_hay_completa(datos: dict[str, Any] | None, hoy: date) -> str:
    """Motivo corto, para el log, de que no haya una completa buena de hoy."""
    if datos is None:
        return "no hay registro de ninguna completa"
    if datos.get("fecha") != hoy.isoformat():
        return f"la última es del {datos.get('fecha', '?')}"
    if datos.get("estado") != "OK":
        return "la de hoy terminó con fallos"
    return "la de hoy no trajo todas las empresas"


# --- Prueba de la red ---------------------------------------------------------------------


def _abrir(url: str, timeout: float) -> None:
    """HEAD por HTTPS. Una respuesta HTTP de error llega como urllib.error.HTTPError."""
    peticion = urllib.request.Request(url, method="HEAD", headers={"User-Agent": AGENTE})
    with urllib.request.urlopen(peticion, timeout=timeout):
        pass


def probar_url(
    url: str,
    *,
    resolver: Callable[..., Any] = socket.getaddrinfo,
    abrir: Callable[[str, float], None] = _abrir,
    timeout: float = TIMEOUT_RED_S,
) -> str | None:
    """None si el servidor de `url` responde por HTTPS; si no, un motivo corto.

    Primero resuelve el nombre y luego hace un HEAD a la raíz del servidor: el
    motivo nunca lleva la ruta ni la consulta de la URL. Cualquier respuesta HTTP,
    aunque sea un error (404, 401, 503), prueba que hay salida a internet.
    """
    try:
        host = urlsplit(url).hostname
    except ValueError:
        host = None
    if not host:
        return "URL sin servidor: revisa BASES_SAP_API_URL y VIGILANTE_PANEL_URL"
    try:
        resolver(host, 443)
    except OSError as exc:
        return f"DNS de {host}: {exc}"
    try:
        abrir(f"https://{host}/", timeout)
    except urllib.error.HTTPError:
        return None  # el servidor contestó
    except urllib.error.URLError as exc:
        return f"HTTPS de {host}: {exc.reason}"
    except (OSError, http.client.HTTPException, ValueError) as exc:
        return f"HTTPS de {host}: {exc}"
    return None


def probar_red(
    urls: Iterable[str],
    *,
    probar: Callable[[str], str | None] = probar_url,
    dormir: Callable[[float], None] = time.sleep,
    intentos: int = INTENTOS_RED,
    espera: float = ESPERA_RED_S,
) -> list[str]:
    """[] en cuanto todas las URL responden; si no, los motivos del último intento.

    Espera `espera` segundos entre intentos (no después del último).
    """
    urls = list(urls)
    errores: list[str] = []
    for intento in range(1, intentos + 1):
        errores = [motivo for motivo in (probar(url) for url in urls) if motivo is not None]
        if not errores:
            return []
        log.warning("Sin salida a internet (intento %s de %s): %s.", intento, intentos, "; ".join(errores))
        if intento < intentos:
            dormir(espera)
    return errores


# --- VPN pegada -----------------------------------------------------------------------------


def _reiniciar_vpn(
    cfg: Config,
    errores: list[str],
    urls: list[str],
    *,
    fabrica_vpn: Callable[[Any], Any] | None,
    ahora: Callable[[], datetime],
    dormir: Callable[[float], None],
    probar: Callable[[str], str | None],
) -> str | None:
    """Sin salida a internet: si la VPN quedó conectada, la baja y vuelve a probar.

    None si la red volvió; si no, el mensaje del fallo RED. Solo con
    VIGILANTE_REINICIAR_VPN y con la VPN gestionada por el robot (sin --sin-vpn).
    Nunca dentro de una franja bloqueada: ahí el túnel puede ser de otro robot.
    El candado del robot ya está tomado (corre dentro de run_robot._ejecutar).
    """
    mensaje = "Sin salida a internet: " + "; ".join(errores)
    if not cfg.vigilante.reiniciar_vpn or fabrica_vpn is None:
        return mensaje

    robot_vpn = fabrica_vpn(cfg.vpn)
    try:
        conectada = robot_vpn.esta_conectado()
    except VpnError as exc:
        log.warning("No se pudo saber si la VPN está conectada; no se toca: %s", exc)
        conectada = False
    if not conectada:
        log.info("La VPN no está conectada: la falta de red no es por ella.")
        return mensaje

    franja = bloqueo.en_franja(ahora(), cfg.franjas, cfg.margen_franja_min)
    if franja:
        return (f"{mensaje}; la VPN quedó arriba porque estamos en la franja de las {franja}, "
                "en que la pueden estar usando los otros robots")

    log.warning("La VPN sigue conectada y no hay salida a internet: la bajo y vuelvo a probar.")
    try:
        robot_vpn.forzar_desconexion()
    except VpnError as exc:
        return f"{mensaje}; no se pudo bajar la VPN: {exc}"
    dormir(ESPERA_VPN_S)
    errores = probar_red(urls, probar=probar, dormir=dormir)
    if errores:
        return "Sin salida a internet: " + "; ".join(errores) + "; se bajó la VPN y la red no volvió"
    log.info("La red volvió después de bajar la VPN.")
    return None


# --- Vigilante ------------------------------------------------------------------------------


def vigilar(
    cfg: Config,
    *,
    correr_completa: Callable[[], int],
    ahora: Callable[[], datetime],
    dormir: Callable[[float], None],
    probar: Callable[[str], str | None] = probar_url,
    fabrica_vpn: Callable[[Any], Any] | None = None,
) -> list[tuple[str, str]]:
    """Red (-> VPN pegada) -> completa de hoy -> aviso. Devuelve los fallos (etapa, mensaje).

    `correr_completa()` corre la completa de las dos empresas, sin avisar, y
    devuelve su código de salida. Nunca se corre si ya hay una completa buena de
    hoy: así no hay dos completas buenas el mismo día.

    `fabrica_vpn(cfg.vpn)` da el RobotVPN con que se baja un túnel pegado (solo con
    VIGILANTE_REINICIAR_VPN); None cuando el robot corre con --sin-vpn.
    """
    urls = [cfg.api.url]
    if cfg.vigilante.panel_url:
        urls.append(cfg.vigilante.panel_url)
    errores = probar_red(urls, probar=probar, dormir=dormir)
    if errores:
        mensaje = _reiniciar_vpn(
            cfg, errores, urls, fabrica_vpn=fabrica_vpn, ahora=ahora, dormir=dormir, probar=probar,
        )
        if mensaje is not None:
            log.error("%s. No se corre la completa.", mensaje)
            return [("RED", mensaje)]
    log.info("Hay salida a internet.")

    hoy = ahora().date()
    if completa_buena_de_hoy(hoy):
        log.info("Bases SAP está al día: la completa de hoy (%s) terminó bien.", hoy.isoformat())
        return []

    log.warning("Bases SAP no tiene una completa buena de hoy (%s): corro la completa.",
                _por_que_no_hay_completa(leer_completa(), hoy))
    codigo = correr_completa()
    if codigo == 130:
        raise KeyboardInterrupt  # Ctrl+C durante la completa: se cancela todo, sin aviso
    if codigo != 0:
        datos = leer_completa() or {}
        etapas = datos.get("etapas") if datos.get("fecha") == hoy.isoformat() else None
        detalle = ", ".join(str(e) for e in etapas) if isinstance(etapas, list) and etapas else "sin detalle"
        mensaje = f"La completa de reparación terminó con fallos ({detalle}); el detalle está en el log."
        log.error(mensaje)
        return [("COMPLETA", mensaje)]
    log.info("La completa de reparación terminó bien: Bases SAP quedó al día.")
    return []
