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
from config import Config
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


_RE_LLAVES = re.compile(r"^(Parte \w+: \d+ llaves repetidas \([^)]*\))")


def mensaje_seguro(exc: BaseException) -> str:
    """Texto del error sin valores de SAP: parte, columna, fila y texto propio."""
    if isinstance(exc, esquema.LlaveRepetida):
        m = _RE_LLAVES.match(str(exc))
        return m.group(1) if m else "Hay llaves repetidas."
    if isinstance(exc, esquema.ValorInvalido):
        # serializar() termina el mensaje con " (tipo valor)": se quita el valor.
        return str(exc).split(" (", 1)[0]
    if isinstance(exc, (esquema.ColumnasInesperadas, hana.HanaError, VpnError, FalloTrabajo)):
        return str(exc).strip()
    return f"Error inesperado ({type(exc).__name__}); revisa robot/logs/robot.log."


def _etapa(exc: BaseException) -> str:
    if isinstance(exc, FalloTrabajo):
        return exc.etapa
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


def _extraer_trabajo(conn: Any, esquema_db: str, r: Resultado, ahora: Callable[[], datetime]) -> None:
    t = r.trabajo
    completa = t.tipo == "completa"
    if completa:
        r.conteo_sap = {}
    codigos: list[str] = []  # códigos de los socios extraídos, en orden

    for nombre, modo in t.partes.items():
        parte = esquema.PARTES[nombre]
        sql = consultas.leer(parte.consulta, esquema_db)
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

    r.extraida_en = ahora().isoformat(timespec="seconds")
    log.info(
        "%s extraído: %s.", t.nombre,
        ", ".join(f"{p} {len(f)}" for p, f in r.filas.items()),
    )


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
                    _extraer_trabajo(conn, empresa_cfg.esquema, r, ahora)
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
