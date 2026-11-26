"""Complemento de VENTAS (orden 016): llena `kilos` y `codigo_envio` en los meses que ya
tiene la app, a mano.

Va como el histórico (historico.py): un tramo por mes, de --desde a --hasta, hasta el día
antes de la ventana nocturna, con la misma planeación y las mismas dos fases
(historico.dos_fases):
    FASE 1 - con VPN:  por empresa, la ventana de HANA, los tramos y, por tramo, la
                       consulta del complemento (consultas.sql_complemento: la llave, la
                       fecha, los kilos y el código de envío) y su COUNT(*) en la misma conexión
    FASE 2 - sin VPN:  por tramo, del más viejo al más nuevo y empresa por empresa, una
                       corrida `complemento` en la API
Corre en las dos empresas: el código de envío (ShipToCode) es de verdad en las dos; los
kilos solo en consultas.EMPRESAS_CON_KILOS (Derivados), y en las demás la consulta los trae
en NULL (consultas.sql_ventas), así que Segurex los manda en null. Un tramo sin ventas en
SAP no se envía (`vacío`); uno que falla (`falló`) no frena a los demás. Repetir un mes no
hace daño: la API vuelve a escribir los mismos valores (no hay 409 por un rango ya cargado,
como en el histórico).

No escribe CSV: los tramos quedan en memoria hasta que baja la VPN, como en el histórico,
y el respaldo de esas ventas ya es el CSV del histórico (VENTAS\\<EMPRESA>\\historico). Si
un tramo falla, se vuelve a correr el comando.

Los kilos son una columna de queries/ventas/ventas.sql, la expresión de «Tot KG» de
«AnálisisVentas-1» (consultas.KILOS_VENTAS). Si la consulta no la trae, el modo no corre:
run_robot llama a revisar_consulta() antes de esperar el candado o subir la VPN, y cada
tramo la vuelve a exigir (consultas.sql_ventas y consultas.sql_complemento).
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
from api import ApiCliente, ApiRechazo
from config import Config, EmpresaHana
from historico import FALLO, VACIO, Tramo
from registro import obtener
from trabajos import Trabajo

log = obtener("complemento")

# Estimación de la fase con VPN, para no cruzarse con las franjas de los otros robots. Sale
# del histórico real del 2026-11-24 (robot.log, 13:01:00 a 13:02:18): 44 tramos (22 meses de
# dos empresas) en 78 s con la VPN arriba; unos 14 s para conectar la VPN y esperar la ruta
# a HANA, y 1 a 2 s por tramo (SGX 22 tramos en 42 s, SDC 22 en 22 s). La consulta del
# complemento es la misma de ventas con menos columnas, así que no debería tardar más. Va con
# holgura: 2 minutos fijos (unas 8 veces lo medido, por si la VPN reintenta) y 10 s por tramo
# de cada empresa (unas 5 veces el tramo más lento). Desde enero de 2025, con las dos
# empresas, da unos 9 minutos.
SEGUNDOS_FIJOS = 120
SEGUNDOS_POR_TRAMO = 10

LLENO = "lleno"

# --- La corrida `complemento` (contrato §4.1 a §4.3 y §10.5) -------------------------------
# Su forma vive solo aquí:
# - conjunto VENTAS, tipo "complemento", la parte ventas en modo todo, sin solicitudes y sin
#   fecha_corte;
# - ventana_desde es el día 1 del mes, desde PRIMER_MES, y ventana_hasta un día de ese mes
#   anterior a la ventana nocturna, como el histórico (envio._iniciar); si no, 422;
# - lotes de la parte ventas con exactamente las columnas de consultas.columnas_complemento():
#   la llave, fecha_contabilizacion, kilos y codigo_envio. kilos y codigo_envio pueden ir
#   null en una fila, nunca faltar; el cierre los escribe también cuando son null;
# - cierre con conteo_sap {"ventas": N}, el COUNT(*) del tramo (el tipo está en
#   trabajos.TIPOS_CON_CONTEO por eso). Si N no es lo recibido, 422 en conteo_sap.ventas;
#   si las llaves no cuadran con MySQL, 422 en filas.ventas con los conteos `sobran` y
#   `faltan` (motivo_de_rechazo los pone en el motivo del tramo). La corrida queda fallida;
# - no hay 409 por un rango ya cargado: un 409 es un fallo del tramo como cualquier otro.
TIPO = "complemento"
PRIMER_MES = date(2025, 1, 1)
_VENTAS = esquema.PARTES["ventas"]
PARTE_COMPLEMENTO = esquema.Parte(
    _VENTAS.nombre, _VENTAS.conjunto, _VENTAS.consulta, consultas.columnas_complemento(),
    _VENTAS.llave, "todo", False, _VENTAS.columna_ventana,
)


def trabajo_complemento_ventas(empresa: str, desde: date, hasta: date) -> Trabajo:
    """Un tramo del complemento: la corrida `complemento` de VENTAS de una empresa, de
    `desde` a `hasta`."""
    return Trabajo(
        empresa=empresa,
        conjunto=_VENTAS.conjunto,
        tipo=TIPO,
        partes={_VENTAS.nombre: "todo"},
        ventana_fija=desde.isoformat(),
        ventana_hasta=hasta.isoformat(),
    )


def revisar_desde(desde_mes: date) -> None:
    """Lanza historico.RangoInvalido si --desde es anterior a PRIMER_MES (la API daría 422)."""
    if desde_mes < PRIMER_MES:
        raise historico.RangoInvalido(
            f"--complemento-ventas va desde {PRIMER_MES:%Y-%m} (contrato §10.5); llegó --desde "
            f"{desde_mes:%Y-%m}."
        )


def motivo_de_rechazo(exc: BaseException) -> str:
    """El motivo de un tramo que falló al enviarse, con los conteos `sobran` y `faltan` si la
    API los dio al cerrar (líneas que no cuadran con MySQL). Son conteos, no valores de SAP."""
    motivo = str(exc)
    causa = exc.__cause__
    while causa is not None and not isinstance(causa, ApiRechazo):
        causa = causa.__cause__
    datos = causa.datos if isinstance(causa, ApiRechazo) and isinstance(causa.datos, dict) else {}
    sobran, faltan = datos.get("sobran"), datos.get("faltan")
    if all(isinstance(n, int) and not isinstance(n, bool) for n in (sobran, faltan)):
        motivo = f"{motivo.rstrip('.')} (sobran {sobran} y faltan {faltan} líneas)."
    return motivo
# --- fin de la forma de la corrida `complemento` ---------------------------------------------


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
    """FASE 1, un tramo: la consulta del complemento con su rango y su COUNT(*), en esta
    conexión.

    Las filas se validan como las de una corrida (tipos, obligatorias, llave repetida) y
    contra el rango del tramo; un error lo atrapa extraccion.extraer_resultados.
    """
    t = r.trabajo
    desde, hasta = date.fromisoformat(t.ventana_fija or ""), date.fromisoformat(t.ventana_hasta or "")
    sql = consultas.sql_complemento(consultas.leer_parte(_VENTAS, empresa_cfg), desde, hasta)
    columnas, datos = hana.ejecutar(conn, sql, f"{t.empresa} complemento", empresa_cfg.esquema)
    filas = esquema.preparar_filas(PARTE_COMPLEMENTO, columnas, datos)
    conteo = hana.contar(conn, consultas.sql_contar(sql), f"{t.empresa} complemento (conteo)")
    extraccion.revisar_ventana(PARTE_COMPLEMENTO, filas, t.ventana_fija or "", t.ventana_hasta)
    r.ventana_desde = t.ventana_fija
    r.columnas = {_VENTAS.nombre: PARTE_COMPLEMENTO.nombres}
    r.filas = {_VENTAS.nombre: filas}
    r.conteo_sap = {_VENTAS.nombre: conteo}
    r.extraida_en = ahora().isoformat(timespec="seconds")
    log.info("Complemento de VENTAS %s de %s a %s extraído: %d filas.", t.empresa, desde, hasta, len(filas))


def _enviar_tramo(api: ApiCliente, r: extraccion.Resultado) -> tuple[Tramo, list[tuple[str, str]]]:
    """FASE 2, un tramo: la corrida `complemento` en la API. Nunca lanza por un fallo del
    tramo."""
    tramo, fallos, terminado = historico.revisar_extraido(r)
    if terminado:
        return tramo, fallos
    try:
        envio.enviar_resultado(api, r)
    except envio.FalloEnvio as exc:
        tramo.motivo = motivo_de_rechazo(exc)
        fallos.append((exc.etapa, f"{tramo.nombre}: {tramo.motivo}"))
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
    """Las dos fases del complemento. Devuelve los tramos y los fallos como (etapa, mensaje).

    `renovar()` corre después de cada tramo extraído y enviado: run_robot renueva ahí el
    candado, como en el histórico.
    """
    lista, fallos = historico.dos_fases(
        cfg, empresas, desde_mes, hasta_mes, trabajo=trabajo_complemento_ventas,
        enviar=lambda r: _enviar_tramo(api, r), extraer=_extraer_tramo, etapa="COMPLEMENTO",
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
        prefijo = f"Complemento de VENTAS {empresa}"
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
