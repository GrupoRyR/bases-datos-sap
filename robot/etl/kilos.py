"""Kilos de VENTAS (orden 016): llena `kilos` en los meses que ya tiene la app, a mano.

Va como el histórico (historico.py): un tramo por mes, de --desde a --hasta, hasta el día
antes de la ventana nocturna, con la misma planeación y las mismas dos fases
(historico.dos_fases):
    FASE 1 - con VPN:  por empresa, la ventana de HANA, los tramos y, por tramo, la
                       consulta de kilos (consultas.sql_kilos: la llave, la fecha y los
                       kilos) y su COUNT(*) en la misma conexión
    FASE 2 - sin VPN:  por tramo, del más viejo al más nuevo y empresa por empresa, una
                       corrida `kilos` en la API
Un tramo sin ventas en SAP no se envía (`vacío`); uno que falla (`falló`) no frena a los
demás.

No escribe CSV: los tramos quedan en memoria hasta que baja la VPN, como en el histórico,
y el respaldo de esas ventas ya es el CSV del histórico (VENTAS\\<EMPRESA>\\historico). Si
un tramo falla, se vuelve a correr el comando.

Mientras queries/ventas/ventas.sql no traiga la columna de kilos (la expresión de «Tot KG»
de «AnálisisVentas-1»), el modo no corre: run_robot llama a revisar_consulta() antes de
esperar el candado o subir la VPN, y cada tramo la vuelve a exigir (consultas.sql_kilos).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable

import config
import consultas
import envio
import esquema
import extraccion
import hana
import historico
from api import ApiCliente
from config import Config, EmpresaHana
from historico import FALLO, VACIO, Tramo
from registro import obtener
from trabajos import Trabajo

log = obtener("kilos")

# Estimación de la fase con VPN, para no cruzarse con las franjas de los otros robots. Sale
# del histórico real del 2026-11-24 (robot.log, 13:01:00 a 13:02:18): 44 tramos (22 meses de
# dos empresas) en 78 s con la VPN arriba; unos 14 s para conectar la VPN y esperar la ruta
# a HANA, y 1 a 2 s por tramo (SGX 22 tramos en 42 s, SDC 22 en 22 s). La consulta de kilos
# es la misma de ventas con menos columnas, así que no debería tardar más. Va con holgura:
# 2 minutos fijos (unas 8 veces lo medido, por si la VPN reintenta) y 10 s por tramo de cada
# empresa (unas 5 veces el tramo más lento). Desde enero de 2025 da unos 9 minutos.
SEGUNDOS_FIJOS = 120
SEGUNDOS_POR_TRAMO = 10

LLENO = "lleno"

# --- PROVISIONAL (orden 015) -------------------------------------------------------------
# La corrida `kilos` aún no está en el contrato (docs/contrato-robot.md): la define la orden
# 015 de Datos y API. Hasta entonces su forma vive solo aquí, para alinearla en un solo lugar:
# - conjunto VENTAS, tipo "kilos", la parte ventas en modo todo y sin solicitudes;
# - ventana_desde y ventana_hasta del tramo, como el histórico (envio._iniciar);
# - lotes de la parte ventas con las columnas de consultas.columnas_kilos(): la llave,
#   fecha_contabilizacion y kilos, en ese orden;
# - cierre con conteo_sap {"ventas": N}, el COUNT(*) del tramo (el tipo está en
#   trabajos.TIPOS_CON_CONTEO por eso);
# - un 409 al iniciar es un fallo del tramo: no hay «ya cargado» como en el histórico.
TIPO = "kilos"
_VENTAS = esquema.PARTES["ventas"]
PARTE_KILOS = esquema.Parte(
    _VENTAS.nombre, _VENTAS.conjunto, _VENTAS.consulta, consultas.columnas_kilos(), _VENTAS.llave,
    "todo", False, _VENTAS.columna_ventana,
)


def trabajo_kilos_ventas(empresa: str, desde: date, hasta: date) -> Trabajo:
    """Un tramo de kilos: la corrida `kilos` de VENTAS de una empresa, de `desde` a `hasta`."""
    return Trabajo(
        empresa=empresa,
        conjunto=_VENTAS.conjunto,
        tipo=TIPO,
        partes={_VENTAS.nombre: "todo"},
        ventana_fija=desde.isoformat(),
        ventana_hasta=hasta.isoformat(),
    )
# --- fin de lo PROVISIONAL ---------------------------------------------------------------


def revisar_consulta() -> None:
    """Falla con ConfigError si ventas.sql no trae la columna de kilos (consultas.exigir_kilos).

    run_robot la llama antes de esperar la franja o el candado y de subir la VPN.
    """
    consultas.exigir_kilos(consultas.leer(_VENTAS.consulta, ""))


def duracion_estimada(cantidad_tramos: int, empresas: int) -> timedelta:
    """Cuánto estará la VPN arriba: lo fijo más cada tramo de cada empresa (una estimación)."""
    return timedelta(seconds=SEGUNDOS_FIJOS + SEGUNDOS_POR_TRAMO * cantidad_tramos * empresas)


def _extraer_tramo(
    conn: Any, empresa_cfg: EmpresaHana, r: extraccion.Resultado, ahora: Callable[[], datetime]
) -> None:
    """FASE 1, un tramo: la consulta de kilos con su rango y su COUNT(*), en esta conexión.

    Las filas se validan como las de una corrida (tipos, obligatorias, llave repetida) y
    contra el rango del tramo; un error lo atrapa extraccion.extraer_resultados.
    """
    t = r.trabajo
    desde, hasta = date.fromisoformat(t.ventana_fija or ""), date.fromisoformat(t.ventana_hasta or "")
    sql = consultas.sql_kilos(consultas.leer_parte(_VENTAS, empresa_cfg), desde, hasta)
    columnas, datos = hana.ejecutar(conn, sql, f"{t.empresa} kilos", empresa_cfg.esquema)
    filas = esquema.preparar_filas(PARTE_KILOS, columnas, datos)
    conteo = hana.contar(conn, consultas.sql_contar(sql), f"{t.empresa} kilos (conteo)")
    extraccion.revisar_ventana(PARTE_KILOS, filas, t.ventana_fija or "", t.ventana_hasta)
    r.ventana_desde = t.ventana_fija
    r.columnas = {_VENTAS.nombre: PARTE_KILOS.nombres}
    r.filas = {_VENTAS.nombre: filas}
    r.conteo_sap = {_VENTAS.nombre: conteo}
    r.extraida_en = ahora().isoformat(timespec="seconds")
    log.info("Kilos de VENTAS %s de %s a %s extraídos: %d filas.", t.empresa, desde, hasta, len(filas))


def _enviar_tramo(api: ApiCliente, r: extraccion.Resultado) -> tuple[Tramo, list[tuple[str, str]]]:
    """FASE 2, un tramo: la corrida `kilos` en la API. Nunca lanza por un fallo del tramo."""
    tramo, fallos, terminado = historico.revisar_extraido(r)
    if terminado:
        return tramo, fallos
    try:
        envio.enviar_resultado(api, r)
    except envio.FalloEnvio as exc:
        tramo.motivo = str(exc)
        fallos.append((exc.etapa, f"{tramo.nombre}: {exc}"))
    else:
        tramo.estado = LLENO
    return tramo, fallos


def ejecutar(
    cfg: Config,
    empresas: list[str],
    desde_mes: date,
    hasta_mes: date | None,
    *,
    api: ApiCliente,
    robot_vpn: Any = None,
    conectar: Callable[..., Any] = hana.conectar,
    sin_vpn: bool = False,
    ahora: Callable[[], datetime] = config.ahora,
    renovar: Callable[[], Any] = lambda: None,
) -> tuple[list[Tramo], list[tuple[str, str]]]:
    """Las dos fases de los kilos. Devuelve los tramos y los fallos como (etapa, mensaje).

    `renovar()` corre después de cada tramo extraído y enviado: run_robot renueva ahí el
    candado, como en el histórico.
    """
    lista, fallos = historico.dos_fases(
        cfg, empresas, desde_mes, hasta_mes, trabajo=trabajo_kilos_ventas,
        enviar=lambda r: _enviar_tramo(api, r), extraer=_extraer_tramo, etapa="KILOS",
        robot_vpn=robot_vpn, conectar=conectar, sin_vpn=sin_vpn, ahora=ahora, renovar=renovar,
    )
    resumir(lista, empresas)
    return lista, fallos


_TITULOS = (
    (LLENO, "llenos"),
    (VACIO, "vacíos (sin ventas en SAP)"),
    (FALLO, "fallidos"),
)


def resumir(lista: list[Tramo], empresas: list[str]) -> None:
    """Resumen en el log, por empresa: cuántos tramos llenos, vacíos y fallidos, y cuáles,
    con el motivo de los fallidos. Sin valores de SAP."""
    for empresa in empresas:
        propios = [t for t in lista if t.empresa == empresa]
        prefijo = f"Kilos de VENTAS {empresa}"
        cuenta = {estado: sum(1 for t in propios if t.estado == estado) for estado, _ in _TITULOS}
        log.info("%s: %d tramos; %d llenos, %d vacíos y %d fallidos.", prefijo,
                 len(propios), cuenta[LLENO], cuenta[VACIO], cuenta[FALLO])
        for estado, titulo in _TITULOS:
            de_estado = [t for t in propios if t.estado == estado]
            if not de_estado:
                continue
            texto = ", ".join(
                t.rango + (f" ({t.motivo})" if estado == FALLO and t.motivo else "") for t in de_estado
            )
            nivel = logging.WARNING if estado == FALLO else logging.INFO
            log.log(nivel, "%s: %s: %s.", prefijo, titulo, texto)
