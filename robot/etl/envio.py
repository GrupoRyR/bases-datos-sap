"""FASE 2, sin VPN: CSV en la carpeta y corridas en la API (contrato §4).

Por cada resultado bueno: guarda el CSV de cada parte (y la foto diaria en la
cartera completa), inicia la corrida, manda lotes de hasta 1.000 filas de una
sola parte, numerados desde 1, y cierra. Cualquier error después de abrir la
corrida la marca fallida en la API.

Por cada resultado con error de extracción que atiende solicitudes o es la
completa: abre la corrida y la falla de inmediato, para que sus solicitudes
pasen a `fallida` con el motivo (contrato §4.4).

Devuelve los fallos como (etapa, mensaje), sin valores de SAP ni secretos.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

import config
from api import ApiCliente, ApiError, ApiRechazo, CorridaAbierta, LotesFaltantes
from carpeta import Carpeta
from extraccion import Resultado, mensaje_seguro
from registro import obtener
from trabajos import Trabajo

log = obtener("envio")

FILAS_POR_LOTE = 1000
MOTIVO_REEMPLAZO = "Corrida anterior sin terminar; la reemplaza una nueva."

Lote = tuple[int, str, list[str], list[list[Any]]]  # batch, parte, columns, rows


class FalloEnvio(RuntimeError):
    def __init__(self, etapa: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.etapa = etapa


def _mensaje(exc: BaseException) -> str:
    """Texto para /fallar y el correo. De un rechazo de la API solo van el estado
    y los campos (rows.12.codigo), no su texto, que podría repetir un valor de SAP."""
    if isinstance(exc, FalloEnvio):
        return str(exc)
    if isinstance(exc, ApiRechazo):
        campos = list(exc.errors)[:5]
        detalle = f" en {', '.join(campos)}" if campos else ""
        return f"La API rechazó la petición ({exc.status}){detalle}."
    if isinstance(exc, ApiError):
        return str(exc)
    return mensaje_seguro(exc)


def armar_lotes(trabajo: Trabajo, resultado: Resultado) -> list[Lote]:
    lotes: list[Lote] = []
    for parte in trabajo.partes:
        filas = resultado.filas[parte]
        for inicio in range(0, len(filas), FILAS_POR_LOTE):
            lotes.append((len(lotes) + 1, parte, resultado.columnas[parte], filas[inicio:inicio + FILAS_POR_LOTE]))
    return lotes


def _iniciar(api: ApiCliente, trabajo: Trabajo, extraida_en: str) -> int:
    datos = {
        "conjunto": trabajo.conjunto,
        "empresa": trabajo.empresa,
        "tipo": trabajo.tipo,
        "partes": dict(trabajo.partes),
        "solicitudes": list(trabajo.solicitudes),
        "fecha_corte": trabajo.fecha_corte,
        "extraida_en": extraida_en,
    }
    try:
        return int(api.iniciar_corrida(**datos)["run_id"])
    except CorridaAbierta as exc:
        if exc.run_id is None:
            raise
        # El bloqueo garantiza un solo robot: la abierta es de una ejecución que se cortó.
        log.warning("%s: la corrida %s quedó abierta; se marca fallida.", trabajo.nombre, exc.run_id)
        api.fallar_corrida(exc.run_id, MOTIVO_REEMPLAZO)
        return int(api.iniciar_corrida(**datos)["run_id"])


def _fallar(api: ApiCliente, run_id: int, mensaje: str) -> None:
    try:
        api.fallar_corrida(run_id, mensaje)
        log.info("Corrida %s marcada fallida.", run_id)
    except Exception as exc:
        log.error("No se pudo marcar fallida la corrida %s: %s", run_id, exc)


def _guardar_csv(carpeta: Carpeta, r: Resultado, momento: datetime) -> None:
    t = r.trabajo
    for parte in t.partes:
        carpeta.guardar_corrida(t.conjunto, t.empresa, parte, r.columnas[parte], r.filas[parte], momento)
    if t.conjunto == "CARTERA" and t.tipo == "completa" and t.fecha_corte:
        carpeta.guardar_historico_cartera(t.empresa, t.fecha_corte, r.columnas["cartera"], r.filas["cartera"])


def _cerrar(api: ApiCliente, run_id: int, r: Resultado, lotes: list[Lote]) -> dict[str, Any]:
    t = r.trabajo
    filas = {p: len(r.filas[p]) for p in t.partes}
    conteo = dict(r.conteo_sap or {}) if t.tipo == "completa" else None
    try:
        return api.cerrar_corrida(run_id, batches=len(lotes), filas=filas, conteo_sap=conteo)
    except LotesFaltantes as exc:
        if not exc.faltan:
            raise FalloEnvio("API", "Las filas no cuadran al cerrar la corrida (409 sin lotes faltantes).") from exc
        if any(not 1 <= n <= len(lotes) for n in exc.faltan):
            raise FalloEnvio("API", f"La API pide lotes que no existen: {exc.faltan}.") from exc
        log.warning("Corrida %s: faltan los lotes %s; se reenvían.", run_id, exc.faltan)
        for n in exc.faltan:
            _enviar_lote(api, run_id, lotes[n - 1])
        return api.cerrar_corrida(run_id, batches=len(lotes), filas=filas, conteo_sap=conteo)


def _enviar_lote(api: ApiCliente, run_id: int, lote: Lote) -> None:
    batch, parte, columnas, filas = lote
    api.enviar_lote(run_id, batch=batch, parte=parte, columns=columnas, rows=filas)


def _enviar_resultado(api: ApiCliente, r: Resultado) -> None:
    t = r.trabajo
    run_id: int | None = None
    try:
        run_id = _iniciar(api, t, r.extraida_en)
        lotes = armar_lotes(t, r)
        for lote in lotes:
            _enviar_lote(api, run_id, lote)
        respuesta = _cerrar(api, run_id, r, lotes)
    except Exception as exc:
        mensaje = _mensaje(exc)
        log.error("%s: falló el envío (corrida %s): %s", t.nombre, run_id, exc)
        if run_id is not None:
            _fallar(api, run_id, mensaje)
        etapa = exc.etapa if isinstance(exc, FalloEnvio) else "API"
        raise FalloEnvio(etapa, mensaje) from exc

    filas = {p: len(r.filas[p]) for p in t.partes}
    log.info("%s: corrida %s cerrada; %d lotes; filas %s.", t.nombre, run_id, len(lotes), filas)
    if respuesta.get("conteo"):
        log.info("%s: conteo de la API %s.", t.nombre, respuesta["conteo"])


def _abrir_y_fallar(api: ApiCliente, r: Resultado, ahora: Callable[[], datetime]) -> None:
    t = r.trabajo
    try:
        run_id = _iniciar(api, t, ahora().isoformat(timespec="seconds"))
    except Exception as exc:
        log.error("%s: no se pudo abrir la corrida para reportar el fallo: %s", t.nombre, exc)
        return
    _fallar(api, run_id, r.error or "Falló la extracción.")


def enviar(
    api: ApiCliente,
    carpeta: Carpeta,
    resultados: list[Resultado],
    *,
    momento: datetime,
    ahora: Callable[[], datetime] = config.ahora,
) -> list[tuple[str, str]]:
    """Guarda y envía cada resultado; un fallo no detiene a los demás."""
    fallos: list[tuple[str, str]] = []
    for r in resultados:
        t = r.trabajo
        if r.error is not None:
            fallos.append((r.etapa or "EXTRACCION", f"{t.nombre}: {r.error}"))
            if t.solicitudes or t.tipo == "completa":
                _abrir_y_fallar(api, r, ahora)
            continue

        try:
            _guardar_csv(carpeta, r, momento)
        except OSError as exc:
            # La carpeta es respaldo: si falla, la app igual recibe los datos y TI recibe el aviso.
            log.error("%s: no se pudo guardar el CSV: %s", t.nombre, exc)
            fallos.append(("CARPETA", f"{t.nombre}: No se pudo guardar el CSV: {exc}"))

        try:
            _enviar_resultado(api, r)
        except FalloEnvio as exc:
            fallos.append((exc.etapa, f"{t.nombre}: {exc}"))
    return fallos
