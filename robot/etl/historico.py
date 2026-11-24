"""Histórico de VENTAS (contrato §10.4): los meses anteriores a la ventana nocturna.

Se carga una vez, a mano, mes por mes: cada mes es un tramo y cada tramo, una corrida
`historico` con su rango (`ventana_desde` el día 1, `ventana_hasta` el último día del
mes). El mes en que empieza la ventana nocturna solo llega hasta el día antes, para no
cruzarse nunca con la corrida de las 02:00.

La planeación va sin red: los tramos y la ventana estimada con el reloj del PC. La
ventana de verdad la da HANA (consultas.SQL_VENTANA) cuando la VPN ya está arriba; la
estimada solo sirve para calcular cuánto va a durar la fase con VPN.

La ejecución (`ejecutar`) sigue las dos fases de siempre:
    FASE 1 - con VPN:  por empresa, la ventana de HANA, los tramos y, por tramo, la
                       consulta con su rango y su COUNT(*) en la misma conexión
    FASE 2 - sin VPN:  por tramo, del más viejo al más nuevo y empresa por empresa: el
                       CSV en VENTAS\\<EMPRESA>\\historico y la corrida en la API
Un tramo sin ventas en SAP no se envía (`vacío`); uno que la app ya tiene responde 409
(`ya cargado`); uno que falla (`falló`) no frena a los demás.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable

import config
import envio
import extraccion
import hana
from api import ApiCliente
from carpeta import Carpeta
from config import Config
from registro import obtener
from trabajos import trabajo_historico_ventas

log = obtener("historico")

# Estimación de la fase con VPN, para no cruzarse con las franjas de los otros robots:
# subir y bajar la VPN y conectar a HANA, más la consulta y el conteo de un mes de una
# empresa. Es holgada a propósito; si se queda corta, súbela (LEEME, «Histórico de ventas»).
MINUTOS_FIJOS = 5
MINUTOS_POR_TRAMO = 2

CARGADO = "cargado"
YA_CARGADO = "ya cargado"
VACIO = "vacío"
FALLO = "falló"

_RE_MES = re.compile(r"^(\d{4})-(\d{2})$")


class RangoInvalido(ValueError):
    """Un --desde o --hasta que no deja ningún mes por cargar o va al revés."""


def inicio_ventana_estimado(hoy: date) -> date:
    """Primer día de la ventana nocturna con la fórmula del contrato §10.1, con `hoy` del PC.

    `ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))`: el día 1 del mes en curso
    menos 7 días. Solo estima cuántos tramos hay antes de subir la VPN; los tramos que se
    cargan salen de la ventana que da HANA.
    """
    return hoy - timedelta(days=6 + hoy.day)


def mes(texto: str) -> date:
    """`AAAA-MM` -> el primer día de ese mes."""
    m = _RE_MES.match(texto or "")
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise RangoInvalido(f"El mes debe ser AAAA-MM (por ejemplo 2025-01); llegó {texto!r}.")
    return date(int(m.group(1)), int(m.group(2)), 1)


def _mes_siguiente(dia: date) -> date:
    return date(dia.year + dia.month // 12, dia.month % 12 + 1, 1)


def tramos(desde_mes: date, hasta_mes: date | None, inicio_ventana: date) -> list[tuple[date, date]]:
    """Un tramo (primer día, último día) por mes, de `desde_mes` a `hasta_mes`.

    Sin `hasta_mes`, el último es el mes en que empieza la ventana nocturna. Ese mes va
    solo hasta el día antes de `inicio_ventana`; si la ventana empieza el día 1, ese mes
    no tiene tramo. Los meses van por su primer día. Lanza RangoInvalido si `hasta_mes`
    es posterior al mes de la ventana, si va antes de `desde_mes` o si no queda ningún
    día por cargar.
    """
    for dia in (desde_mes, hasta_mes):
        if dia is not None and dia.day != 1:
            raise ValueError(f"Los meses del histórico van por su primer día; llegó {dia}.")
    ultimo_dia = inicio_ventana - timedelta(days=1)
    mes_ventana = inicio_ventana.replace(day=1)
    if hasta_mes is not None and hasta_mes > mes_ventana:
        raise RangoInvalido(
            f"--hasta {hasta_mes:%Y-%m} es posterior al mes en que empieza la ventana nocturna "
            f"({inicio_ventana}): esos días los carga la corrida de las 02:00."
        )
    if hasta_mes is not None and desde_mes > hasta_mes:
        raise RangoInvalido(f"--desde {desde_mes:%Y-%m} es posterior a --hasta {hasta_mes:%Y-%m}.")
    if desde_mes > ultimo_dia:
        raise RangoInvalido(
            f"--desde {desde_mes:%Y-%m} ya está dentro de la ventana nocturna (empieza el "
            f"{inicio_ventana}): no hay días por cargar."
        )
    ultimo_mes = hasta_mes or mes_ventana
    lista: list[tuple[date, date]] = []
    actual = desde_mes
    while actual <= ultimo_mes:
        siguiente = _mes_siguiente(actual)
        fin = min(siguiente - timedelta(days=1), ultimo_dia)
        if fin >= actual:
            lista.append((actual, fin))
        actual = siguiente
    return lista


def duracion_estimada(cantidad_tramos: int, empresas: int) -> timedelta:
    """Cuánto estará la VPN arriba: lo fijo más cada tramo de cada empresa (una estimación)."""
    return timedelta(minutes=MINUTOS_FIJOS + MINUTOS_POR_TRAMO * cantidad_tramos * empresas)


@dataclass
class Tramo:
    """Cómo terminó un tramo: cargado, ya cargado, vacío o falló."""

    empresa: str
    desde: date
    hasta: date
    estado: str = FALLO
    motivo: str | None = None  # solo si falló: texto seguro, sin valores de SAP
    primera: str | None = None  # primera y última fecha_contabilizacion cargadas
    ultima: str | None = None

    @property
    def rango(self) -> str:
        return f"{self.desde.isoformat()} a {self.hasta.isoformat()}"

    @property
    def nombre(self) -> str:
        return f"VENTAS {self.empresa} {self.rango}"

    def para_estado(self) -> dict[str, Any]:
        """Lo que va a robot/state/ultima_ejecucion.json: sin datos de SAP."""
        return {"empresa": self.empresa, "desde": self.desde.isoformat(), "hasta": self.hasta.isoformat(),
                "estado": self.estado, "motivo": self.motivo}


def ejecutar(
    cfg: Config,
    empresas: list[str],
    desde_mes: date,
    hasta_mes: date | None,
    *,
    api: ApiCliente,
    carpeta: Carpeta,
    robot_vpn: Any = None,
    conectar: Callable[..., Any] = hana.conectar,
    sin_vpn: bool = False,
    ahora: Callable[[], datetime] = config.ahora,
    renovar: Callable[[], Any] = lambda: None,
) -> tuple[list[Tramo], list[tuple[str, str]]]:
    """Las dos fases del histórico. Devuelve los tramos y los fallos como (etapa, mensaje).

    `renovar()` corre después de cada tramo extraído y enviado: run_robot renueva ahí el
    candado, porque el histórico puede durar más que su vigencia.
    """
    por_empresa: dict[str, list[extraccion.Resultado]] = {}
    fallos: list[tuple[str, str]] = []

    def leer(conn: Any, empresa: str) -> None:
        # La ventana de verdad es la de HANA, en esta conexión (contrato §10.1 y §10.4).
        inicio = date.fromisoformat(extraccion.leer_ventana(conn, empresa))
        try:
            plan = tramos(desde_mes, hasta_mes, inicio)
        except RangoInvalido as exc:
            log.error("VENTAS %s: %s", empresa, exc)
            fallos.append(("HISTORICO", f"VENTAS {empresa}: {exc}"))
            return
        log.info("VENTAS %s: la ventana nocturna empieza el %s; %d tramos, de %s a %s.",
                 empresa, inicio, len(plan), plan[0][0], plan[-1][1])
        resultados = por_empresa[empresa] = [
            extraccion.Resultado(trabajo_historico_ventas(empresa, desde, hasta)) for desde, hasta in plan
        ]
        for r in resultados:
            extraccion.extraer_resultados(conn, cfg.hana.empresas[empresa], [r], ahora)
            renovar()

    # FASE 1: con VPN. sesion() la baja en finally.
    fallos += extraccion.sesion(cfg, empresas, leer, robot_vpn=robot_vpn, conectar=conectar, sin_vpn=sin_vpn)

    # FASE 2: sin VPN, empresa por empresa y del mes más viejo al más nuevo.
    lista: list[Tramo] = []
    for empresa in empresas:
        for r in por_empresa.get(empresa, []):
            tramo, fallos_tramo = _enviar_tramo(api, carpeta, r)
            lista.append(tramo)
            fallos += fallos_tramo
            r.columnas, r.filas = {}, {}  # ya está en el CSV y en la app: se suelta la memoria
            renovar()
    resumir(lista, empresas)
    return lista, fallos


def _enviar_tramo(
    api: ApiCliente, carpeta: Carpeta, r: extraccion.Resultado
) -> tuple[Tramo, list[tuple[str, str]]]:
    t = r.trabajo
    desde, hasta = date.fromisoformat(t.ventana_fija or ""), date.fromisoformat(t.ventana_hasta or "")
    tramo = Tramo(t.empresa, desde, hasta)
    if r.error is not None:
        tramo.motivo = r.error
        return tramo, [(r.etapa or "EXTRACCION", f"{tramo.nombre}: {r.error}")]

    filas = r.filas.get("ventas", [])
    if not filas:
        conteo = (r.conteo_sap or {}).get("ventas", 0)
        if conteo:
            # No debería pasar: la consulta y el conteo son la misma, en la misma conexión.
            tramo.motivo = f"La consulta trajo 0 filas y el conteo de SAP da {conteo}; no se envía."
            log.error("%s: %s", tramo.nombre, tramo.motivo)
            return tramo, [("VALIDACION", f"{tramo.nombre}: {tramo.motivo}")]
        log.info("%s: sin ventas en SAP; no se envía.", tramo.nombre)
        tramo.estado = VACIO
        return tramo, []

    fallos: list[tuple[str, str]] = []
    try:
        carpeta.guardar_historico_ventas(t.empresa, tramo.desde, tramo.hasta, r.columnas["ventas"], filas)
    except OSError as exc:
        # La carpeta es respaldo: si falla, la app igual recibe el tramo y TI recibe el aviso.
        log.error("%s: no se pudo guardar el CSV: %s", tramo.nombre, exc)
        fallos.append(("CARPETA", f"{tramo.nombre}: No se pudo guardar el CSV: {exc}"))

    try:
        envio.enviar_resultado(api, r)
    except envio.RangoYaCargado:
        log.info("%s: la app ya tiene ventas en ese rango (409); no se vuelve a cargar.", tramo.nombre)
        tramo.estado = YA_CARGADO
    except envio.FalloEnvio as exc:
        tramo.motivo = str(exc)
        fallos.append((exc.etapa, f"{tramo.nombre}: {exc}"))
    else:
        tramo.estado = CARGADO
        posicion = r.columnas["ventas"].index("fecha_contabilizacion")
        fechas = [fila[posicion] for fila in filas]
        tramo.primera, tramo.ultima = min(fechas), max(fechas)
    return tramo, fallos


_TITULOS = (
    (VACIO, "vacíos (sin ventas en SAP)"),
    (YA_CARGADO, "ya cargados (la app ya tenía ventas)"),
    (FALLO, "fallidos"),
)


def resumir(lista: list[Tramo], empresas: list[str]) -> None:
    """Resumen en el log, por empresa: del primer al último día cargado y los tramos
    vacíos, ya cargados y fallidos."""
    for empresa in empresas:
        propios = [t for t in lista if t.empresa == empresa]
        prefijo = f"Histórico de VENTAS {empresa}"
        cargados = [t for t in propios if t.estado == CARGADO]
        if cargados:
            log.info("%s: cargado del %s al %s.", prefijo,
                     min(t.primera or "" for t in cargados), max(t.ultima or "" for t in cargados))
        else:
            log.info("%s: no se cargó ningún tramo.", prefijo)
        cuenta = {
            estado: sum(1 for t in propios if t.estado == estado)
            for estado in (CARGADO, YA_CARGADO, VACIO, FALLO)
        }
        log.info("%s: %d tramos; %d cargados, %d ya cargados, %d vacíos y %d fallidos.", prefijo,
                 len(propios), cuenta[CARGADO], cuenta[YA_CARGADO], cuenta[VACIO], cuenta[FALLO])
        for estado, titulo in _TITULOS:
            de_estado = [t for t in propios if t.estado == estado]
            if not de_estado:
                continue
            texto = ", ".join(
                t.rango + (f" ({t.motivo})" if estado == FALLO and t.motivo else "") for t in de_estado
            )
            nivel = logging.WARNING if estado == FALLO else logging.INFO
            log.log(nivel, "%s: %s: %s.", prefijo, titulo, texto)
