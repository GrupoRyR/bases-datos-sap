"""FASE 1, con VPN: todas las lecturas de SAP de una ejecución.

Una sola sesión de VPN para todos los trabajos, una conexión de HANA por
empresa, y la VPN abajo en `finally`. Aquí no se escribe ningún CSV ni se
llama a la API: eso es la fase 2 (envio.py), con la VPN ya abajo.

Un error dentro de un trabajo hace fallar solo ese trabajo; un error al
conectar a HANA, solo los trabajos de esa empresa; un error de la VPN, todos.
Los mensajes de error no llevan valores de SAP: van a la API (/fallar) y al
correo de TI (contrato §4.4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

import config
import consultas
import esquema
import hana
from config import Config, ConfigError, EmpresaHana
from registro import obtener
from trabajos import Trabajo
from vpn import RobotVPN, VpnError

log = obtener("extraccion")

Extra = Callable[[Any, str], None]


@dataclass
class Resultado:
    trabajo: Trabajo
    columnas: dict[str, list[str]] = field(default_factory=dict)  # nombres del contrato
    filas: dict[str, list[list[Any]]] = field(default_factory=dict)  # ya serializadas
    conteo_sap: dict[str, int] | None = None  # solo en una corrida completa
    extraida_en: str = ""  # hora de Bogotá con zona, al terminar la última consulta
    # Solo VENTAS: primer día de la ventana (AAAA-MM-DD), calculado por HANA (contrato §10.1).
    # Si la extracción falla, queda el último que dio HANA: con él se abre y se falla la
    # corrida; sin él (la VPN o la conexión fallaron antes) la corrida no se puede abrir.
    ventana_desde: str | None = None
    error: str | None = None
    etapa: str | None = None

    def fallar(self, etapa: str, error: str) -> None:
        self.etapa = etapa
        self.error = error
        self.columnas, self.filas, self.conteo_sap = {}, {}, None


class FalloTrabajo(RuntimeError):
    def __init__(self, etapa: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.etapa = etapa


INTENTOS_VENTANA = 2  # la extracción de VENTAS se repite una vez si la ventana cambió


def leer_ventana(conn: Any, empresa: str) -> str:
    """Primer día de la ventana de VENTAS según HANA, en esta conexión (contrato §10.1).

    Nunca se calcula con el reloj del PC: la consulta filtra con CURRENT_DATE del
    servidor HANA y la ventana debe ser exactamente esa.
    """
    _, filas = hana.ejecutar(conn, consultas.SQL_VENTANA, f"{empresa} ventana de ventas")
    if len(filas) != 1 or len(filas[0]) != 1:
        raise hana.HanaError(
            f"La consulta de la ventana de ventas de {empresa} debía devolver una fila con una "
            f"columna y devolvió {len(filas)} filas."
        )
    dia = esquema.serializar(filas[0][0], esquema.FECHA, "ventana_desde")
    if dia is None:
        raise esquema.ValorInvalido(f"La ventana de ventas de {empresa} llegó vacía de HANA.")
    return dia


def revisar_ventana(parte: esquema.Parte, filas: list[list[Any]], ventana_desde: str) -> None:
    """Falla si alguna fila trae fecha_contabilizacion anterior a ventana_desde.

    La API rechazaría el lote (contrato §10.1); se corta antes de abrir la corrida.
    Las fechas ya están serializadas (AAAA-MM-DD), así que se comparan como texto.
    """
    posicion = parte.nombres.index(esquema.COLUMNA_VENTANA)
    antes = sum(1 for fila in filas if fila[posicion] < ventana_desde)
    if antes:
        raise FalloTrabajo(
            "VALIDACION",
            f"Parte {parte.nombre}: {antes} filas con {esquema.COLUMNA_VENTANA} anterior a "
            f"ventana_desde {ventana_desde}; la API las rechazaría.",
        )


_RE_LLAVES = re.compile(r"^(Parte \w+: \d+ llaves repetidas \([^)]*\))")
_RE_TABLA = re.compile(r"^Consulta '([^']*)': HANA no encuentra una tabla")
_RE_ETIQUETA = re.compile(r"^(.*?'[^']*'): ")
_RE_CONEXION = re.compile(r"^(No se pudo conectar a HANA \(\w+\) tras \d+ intentos): ")
_VER_LOG = "revisa robot/logs/robot.log."


def _hana_seguro(texto: str) -> str:
    """Corta el texto del driver de un HanaError: puede citar valores de SAP.

    Queda solo el prefijo propio (la etiqueta de la consulta o la empresa); el
    texto completo sigue en el log local.
    """
    m = _RE_TABLA.match(texto)
    if m:
        return (f"Consulta '{m.group(1)}': HANA no encuentra una tabla; revisa "
                "HANA_SGX_SCHEMA / HANA_SDC_SCHEMA y robot/logs/robot.log.")
    m = _RE_ETIQUETA.match(texto) or _RE_CONEXION.match(texto)
    if m:
        return f"{m.group(1)}; {_VER_LOG}"
    return texto


def mensaje_seguro(exc: BaseException) -> str:
    """Texto del error sin valores de SAP: parte, columna, fila y texto propio."""
    if isinstance(exc, esquema.LlaveRepetida):
        m = _RE_LLAVES.match(str(exc))
        return m.group(1) if m else "Hay llaves repetidas."
    if isinstance(exc, esquema.ValorInvalido):
        # serializar() termina el mensaje con " (tipo valor)": se quita el valor.
        return str(exc).split(" (", 1)[0]
    if isinstance(exc, hana.HanaError):
        return _hana_seguro(str(exc).strip())
    if isinstance(exc, (esquema.ColumnasInesperadas, VpnError, FalloTrabajo, ConfigError)):
        return str(exc).strip()
    return f"Error inesperado ({type(exc).__name__}); revisa robot/logs/robot.log."


def _etapa(exc: BaseException) -> str:
    if isinstance(exc, FalloTrabajo):
        return exc.etapa
    if isinstance(exc, ConfigError):
        return "CONFIGURACION"
    if isinstance(exc, (esquema.LlaveRepetida, esquema.ValorInvalido, esquema.ColumnasInesperadas)):
        return "VALIDACION"
    if isinstance(exc, hana.HanaError):
        return "HANA"
    return "EXTRACCION"


def _leer(conn: Any, esquema_db: str, empresa: str, parte: esquema.Parte, sql: str,
          params: list[Any] | None = None) -> tuple[list[str], list[tuple]]:
    return hana.ejecutar(conn, sql, f"{empresa} {parte.nombre}", esquema_db, params)


def _hijas(conn: Any, esquema_db: str, trabajo: Trabajo, parte: esquema.Parte, sql: str,
           codigos: list[str]) -> tuple[list[str] | None, list[tuple]]:
    """Direcciones o contactos de los socios extraídos en este trabajo (contrato §5.1)."""
    if not codigos:
        return None, []
    socios = [p for p in trabajo.partes if p in esquema.SOCIOS]
    if all(trabajo.partes[p] == "todo" for p in socios):
        # Todos los socios vinieron completos: una sola consulta y el filtro en Python.
        columnas, datos = _leer(conn, esquema_db, trabajo.empresa, parte, sql)
        [posicion] = esquema.indices(columnas, [c for c in parte.columnas if c.nombre == "codigo_socio"])
        enviados = set(codigos)
        return columnas, [
            f for f in datos if esquema.serializar(f[posicion], esquema.TEXTO) in enviados
        ]
    columnas: list[str] | None = None
    filas: list[tuple] = []
    for trozo in consultas.trozos(codigos):
        columnas, datos = _leer(
            conn, esquema_db, trabajo.empresa, parte, consultas.sql_por_socios(sql, len(trozo)), trozo
        )
        filas.extend(datos)
    return columnas, filas


def resultado_fallido(trabajo: Trabajo, exc: BaseException) -> Resultado:
    """Resultado de un trabajo que ya se sabe que falla, sin consultar HANA (envio lo reporta)."""
    r = Resultado(trabajo)
    r.fallar(_etapa(exc), mensaje_seguro(exc))
    return r


def _extraer_trabajo(conn: Any, empresa_cfg: EmpresaHana, r: Resultado, ahora: Callable[[], datetime]) -> None:
    t = r.trabajo
    if t.conjunto == "VENTAS":
        _extraer_en_ventana(conn, empresa_cfg, r)
    else:
        _extraer_partes(conn, empresa_cfg, r)
    r.extraida_en = ahora().isoformat(timespec="seconds")
    log.info(
        "%s extraído: %s%s.", t.nombre,
        ", ".join(f"{p} {len(f)}" for p, f in r.filas.items()),
        f"; ventana desde {r.ventana_desde}" if r.ventana_desde else "",
    )


def _extraer_en_ventana(conn: Any, empresa_cfg: EmpresaHana, r: Resultado) -> None:
    """VENTAS: la ventana se pide a HANA antes y después de la consulta (contrato §10.1).

    Si cambió (la extracción cruzó la medianoche del servidor HANA), se repite la
    extracción una vez; si vuelve a cambiar, el trabajo falla. El conteo de la
    completa va dentro, en la misma conexión, así que cuenta la misma ventana.
    """
    t = r.trabajo
    for intento in range(1, INTENTOS_VENTANA + 1):
        antes = r.ventana_desde = leer_ventana(conn, t.empresa)
        _extraer_partes(conn, empresa_cfg, r)
        despues = r.ventana_desde = leer_ventana(conn, t.empresa)
        if antes == despues:
            break
        log.warning(
            "%s: la ventana cambió de %s a %s durante la extracción (cruzó la medianoche); "
            "intento %d de %d.", t.nombre, antes, despues, intento, INTENTOS_VENTANA,
        )
    else:
        raise FalloTrabajo(
            "VALIDACION",
            f"La ventana de {t.nombre} cambió durante la extracción en {INTENTOS_VENTANA} intentos "
            f"(la última vez de {antes} a {despues}); no se envía.",
        )
    for nombre in t.partes:
        revisar_ventana(esquema.PARTES[nombre], r.filas[nombre], despues)


def _extraer_partes(conn: Any, empresa_cfg: EmpresaHana, r: Resultado) -> None:
    t = r.trabajo
    esquema_db = empresa_cfg.esquema
    completa = t.tipo == "completa"
    r.columnas, r.filas = {}, {}
    r.conteo_sap = {} if completa else None
    codigos: list[str] = []  # códigos de los socios extraídos, en orden

    for nombre, modo in t.partes.items():
        parte = esquema.PARTES[nombre]
        sql = consultas.leer_parte(parte, empresa_cfg)
        if nombre in esquema.HIJAS_DE_SOCIO:
            columnas, datos = _hijas(conn, esquema_db, t, parte, sql, codigos)
        elif modo == "cambios" and t.desde.get(nombre) is not None:
            desde = consultas.desde_a_parametro(t.desde[nombre])
            columnas, datos = _leer(conn, esquema_db, t.empresa, parte, consultas.sql_cambios(sql), [desde])
        else:
            columnas, datos = _leer(conn, esquema_db, t.empresa, parte, sql)

        filas = esquema.preparar_filas(parte, columnas, datos) if columnas is not None else []
        if completa:
            # COUNT(*) del archivo sin filtro, en la misma conexión (contrato §4.3).
            r.conteo_sap[nombre] = hana.contar(
                conn, consultas.sql_contar(sql), f"{t.empresa} {nombre} (conteo)"
            )
        if modo == "todo" and not filas:
            raise FalloTrabajo(
                "VALIDACION",
                f"La parte {nombre} llegó con 0 filas de SAP; no se envía para no vaciar la tabla.",
            )
        r.columnas[nombre] = parte.nombres
        r.filas[nombre] = filas
        if nombre in esquema.SOCIOS:
            posicion = parte.nombres.index("codigo")
            vistos = set(codigos)
            for f in filas:
                if f[posicion] not in vistos:
                    vistos.add(f[posicion])
                    codigos.append(f[posicion])


def _extraer_empresa(
    cfg: Config, empresa: str, resultados: list[Resultado], conectar: Callable[..., Any],
    ahora: Callable[[], datetime], extra: Extra | None,
) -> None:
    empresa_cfg = cfg.hana.empresas.get(empresa)
    if empresa_cfg is None:
        for r in resultados:
            r.fallar("CONFIGURACION", f"Empresa sin configuración de HANA: {empresa}.")
        return
    try:
        with conectar(cfg.hana, empresa_cfg) as conn:
            for r in resultados:
                try:
                    _extraer_trabajo(conn, empresa_cfg, r, ahora)
                except Exception as exc:
                    r.fallar(_etapa(exc), mensaje_seguro(exc))
                    log.error("Falló la extracción de %s: %s", r.trabajo.nombre, exc)
            if extra is not None:
                try:
                    extra(conn, empresa)
                except Exception:
                    log.exception("Falló el paso adicional de %s (no afecta las corridas).", empresa)
    except Exception as exc:
        etapa = "HANA" if isinstance(exc, hana.HanaError) else "EXTRACCION"
        for r in resultados:
            if r.error is None and not r.extraida_en:
                r.fallar(etapa, mensaje_seguro(exc))
        log.error("No se pudo leer HANA de %s: %s", empresa, exc)


def sesion(
    cfg: Config,
    empresas: list[str],
    paso: Extra,
    *,
    robot_vpn: Any = None,
    conectar: Callable[..., Any] = hana.conectar,
    sin_vpn: bool = False,
) -> list[tuple[str, str]]:
    """Una sesión de VPN sin trabajos de la API (archivo, catálogo, diagnóstico).

    Sube la VPN, abre una conexión de HANA por empresa, corre `paso(conn, empresa)`
    y baja la VPN en `finally`. `paso` solo lee: escribir es de la fase 2. Devuelve
    los fallos de VPN y de conexión como (etapa, mensaje); los de cada tabla los
    lleva el propio paso.
    """
    fallos: list[tuple[str, str]] = []
    if not empresas:
        return fallos
    robot = None if sin_vpn else (robot_vpn or RobotVPN(cfg.vpn))
    try:
        if robot is None:
            log.info("Se omite la gestión de la VPN (--sin-vpn).")
        else:
            try:
                robot.conectar()
            except VpnError as exc:
                log.error("FALLO en la etapa VPN: %s", exc)
                return [("VPN", mensaje_seguro(exc))]
        for empresa in empresas:
            empresa_cfg = cfg.hana.empresas.get(empresa)
            if empresa_cfg is None:
                fallos.append(("CONFIGURACION", f"Empresa sin configuración de HANA: {empresa}."))
                continue
            try:
                with conectar(cfg.hana, empresa_cfg) as conn:
                    paso(conn, empresa)
            except Exception as exc:
                etapa = "HANA" if isinstance(exc, hana.HanaError) else "EXTRACCION"
                log.error("Falló la lectura de HANA de %s: %s", empresa, exc)
                fallos.append((etapa, f"{empresa}: {mensaje_seguro(exc)}"))
    finally:
        if robot is not None:
            try:
                robot.desconectar()
            except Exception:
                log.exception("Falló al desconectar la VPN (se ignora).")
    return fallos


def extraer(
    cfg: Config,
    trabajos: list[Trabajo],
    *,
    robot_vpn: Any = None,
    conectar: Callable[..., Any] = hana.conectar,
    sin_vpn: bool = False,
    extra: Extra | None = None,
    ahora: Callable[[], datetime] = config.ahora,
) -> list[Resultado]:
    """Extrae todos los trabajos con una sola sesión de VPN. Nunca lanza por un trabajo.

    `extra(conn, empresa)` corre una vez por conexión de empresa después de sus
    trabajos (lo usa el archivo); sus errores quedan en el log.
    """
    resultados = [Resultado(t) for t in trabajos]
    if not resultados:
        return resultados

    robot = None if sin_vpn else (robot_vpn or RobotVPN(cfg.vpn))
    try:
        if robot is None:
            log.info("Se omite la gestión de la VPN (--sin-vpn).")
        else:
            try:
                robot.conectar()
            except VpnError as exc:
                log.error("FALLO en la etapa VPN: %s", exc)
                for r in resultados:
                    r.fallar("VPN", mensaje_seguro(exc))
                return resultados

        por_empresa: dict[str, list[Resultado]] = {}
        for r in resultados:
            por_empresa.setdefault(r.trabajo.empresa, []).append(r)
        for empresa, grupo in por_empresa.items():
            _extraer_empresa(cfg, empresa, grupo, conectar, ahora, extra)
    finally:
        if robot is not None:
            try:
                robot.desconectar()
            except Exception:
                log.exception("Falló al desconectar la VPN (se ignora).")
    return resultados
