"""Comparación con SAP (--comparar, contrato §13.2 y §13.3): solo lee.

Por empresa y conjunto (MAESTROS, CARTERA y VENTAS) calcula en SAP los mismos totales que
da la API en /totales, le pide los suyos, compara y guarda el resultado en /comparaciones.
Nunca escribe en SAP ni abre una corrida (/corridas). Dos fases, como siempre:
    FASE 1 - con VPN:  por empresa, las consultas de cada conjunto (extraccion.sesion)
    FASE 2 - sin VPN:  por conjunto y empresa, /totales y una /comparaciones

Los totales de SAP salen de las mismas consultas y la misma conversión del envío
(extraccion.extraer_resultados y esquema.serializar), así que el signo de las notas crédito,
los kilos nulos de Segurex, el redondeo por línea y el texto vacío como null son los mismos
que guardó la app:
- MAESTROS: un grupo por parte (las doce, en el orden de §1) con las filas que la completa
  envía con `activo = true`; en una parte sin columna `activo` (direcciones), todas. Una
  empresa sin lista de precios pública no envía precios: su grupo va en 0.
- CARTERA: un grupo `actual` con las filas de la cartera y la suma de `saldo`.
- VENTAS: de 2025-01-01 a hoy, mes por mes con el filtro del histórico (consultas.sql_rango);
  un grupo por mes con líneas: filas, `sumas.total`, `sumas.cantidad`, `nulos.kilos` y
  `nulos.codigo_envio`. Cada tramo se suelta apenas se suma.
Las sumas van exactas en Decimal y se redondean al final, la mitad lejos del cero (como cada
línea ya va redondeada, no cambian), y se comparan como texto.

Un conjunto que falla en SAP o en /totales no se compara: queda en el log y en los fallos, y
los demás siguen. El resumen va al log sin valores de SAP más allá de la clave y el campo.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Callable

import complemento
import config
import esquema
import extraccion
import hana
import historico
from api import ApiCliente, ApiError, ApiRechazo
from config import Config, EmpresaHana
from registro import obtener
from trabajos import trabajo_historico_ventas, trabajos_completos

log = obtener("comparar")

CONJUNTOS = ("MAESTROS", "CARTERA", "VENTAS")  # orden de §1; PEDIDOS y PRODUCCION no tienen totales
PRIMER_DIA = complemento.PRIMER_MES  # VENTAS desde 2025-01-01, como el complemento
TIPO = "comparar"  # tipo de los trabajos de MAESTROS y CARTERA: sin COUNT(*) (trabajos.TIPOS_CON_CONTEO)
CLAVE_CARTERA = "actual"
DECIMALES = {"total": 2, "cantidad": 6, "saldo": 2}
NULOS_VENTAS = ("kilos", "codigo_envio")
# Contrato §13.3: hasta 500 diferencias; clave de 1 a 20, campo de 1 a 40, valores hasta 40.
MAX_DIFERENCIAS = 500
MAX_CLAVE, MAX_CAMPO, MAX_VALOR = 20, 40, 40
GRUPOS_EN_EL_RESUMEN = 10
ETAPA = "COMPARAR"
_SIN_SESION = "SIN_SESION"  # la VPN o la conexión fallaron: el fallo ya lo da extraccion.sesion

# Estimación de la fase con VPN: la del complemento de ventas (complemento.duracion_estimada:
# 2 minutos fijos y 10 s por mes de cada empresa) por VENTAS, que es el mismo recorrido mes a
# mes pero con la consulta completa del histórico (que en el histórico real del 2026-11-24 tardó
# 1 a 2 s por tramo con su COUNT(*)), más 60 s por empresa para MAESTROS y CARTERA, que son
# una consulta por parte como en la nocturna. Sin medir todavía con SAP: va con holgura. Desde
# enero de 2025, con las dos empresas, da unos 11 minutos.
SEGUNDOS_POR_EMPRESA = 60


@dataclass
class Grupo:
    filas: int
    sumas: dict[str, str] = field(default_factory=dict)
    nulos: dict[str, int] = field(default_factory=dict)


@dataclass
class Comparacion:
    """Una empresa y un conjunto: sus totales de SAP, los de la API y las diferencias."""

    conjunto: str
    empresa: str
    desde: str | None = None  # solo VENTAS
    hasta: str | None = None
    sap: dict[str, Grupo] | None = None
    mysql: dict[str, Grupo] | None = None
    diferencias: list[dict[str, str | None]] = field(default_factory=list)
    error: str | None = None  # texto seguro, sin valores de SAP
    etapa: str | None = None
    sin_guardar: str | None = None  # /comparaciones falló

    @property
    def nombre(self) -> str:
        return f"{self.conjunto} {self.empresa}"

    @property
    def resultado(self) -> str:
        if self.error is not None or self.mysql is None:
            return "error"
        return "no_cuadra" if self.diferencias else "cuadra"

    @property
    def claves_con_diferencias(self) -> list[str]:
        return list(dict.fromkeys(d["clave"] or "" for d in self.diferencias))

    def fallar(self, etapa: str, error: str) -> None:
        self.etapa, self.error = etapa, error

    def para_estado(self) -> dict[str, Any]:
        """Lo que va a robot/state/ultima_ejecucion.json: sin datos de SAP."""
        return {"conjunto": self.conjunto, "empresa": self.empresa, "resultado": self.resultado,
                "grupos_con_diferencias": len(self.claves_con_diferencias)}


def duracion_estimada(empresas: int, hoy: date) -> timedelta:
    """Cuánto estará la VPN arriba (una estimación; ver SEGUNDOS_POR_EMPRESA)."""
    return (complemento.duracion_estimada(len(tramos_ventas(hoy)), empresas)
            + timedelta(seconds=SEGUNDOS_POR_EMPRESA * empresas))


def tramos_ventas(hoy: date) -> list[tuple[date, date]]:
    """Un tramo por mes de PRIMER_DIA a hoy (el último, hasta hoy)."""
    return historico.tramos(PRIMER_DIA, None, hoy + timedelta(days=1))


def formatear(valor: Decimal, decimales: int) -> str:
    """Texto de §4.2 con exactamente esos decimales, la mitad lejos del cero, sin "-0.00"."""
    redondeado = valor.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    if redondeado == 0:
        redondeado = abs(redondeado)
    return f"{redondeado:f}"


# --- FASE 1: los totales de SAP ---------------------------------------------------------------


def _extraer(conn: Any, empresa_cfg: EmpresaHana, trabajo: Any, ahora: Callable[[], datetime]) -> extraccion.Resultado:
    r = extraccion.Resultado(trabajo)
    extraccion.extraer_resultados(conn, empresa_cfg, [r], ahora)
    if r.error is not None:
        raise extraccion.FalloTrabajo(r.etapa or "EXTRACCION", r.error)
    return r


def _trabajo_completo(cfg: Config, conjunto: str, empresa: str, hoy: date) -> Any:
    """El trabajo de la nocturna de ese conjunto (las mismas partes), sin su COUNT(*)."""
    [t] = [t for t in trabajos_completos([empresa], hoy, [], cfg.hana.sin_precios()) if t.conjunto == conjunto]
    return dataclasses.replace(t, tipo=TIPO)


def _maestros(cfg: Config, conn: Any, empresa_cfg: EmpresaHana, hoy: date,
              ahora: Callable[[], datetime], renovar: Callable[[], Any]) -> dict[str, Grupo]:
    r = _extraer(conn, empresa_cfg, _trabajo_completo(cfg, "MAESTROS", empresa_cfg.codigo, hoy), ahora)
    grupos: dict[str, Grupo] = {}
    for nombre in esquema.PARTES_POR_CONJUNTO["MAESTROS"]:
        filas = r.filas.get(nombre, [])  # precios no va si la empresa no tiene lista pública
        columnas = r.columnas.get(nombre, esquema.PARTES[nombre].nombres)
        if "activo" in columnas:
            posicion = columnas.index("activo")
            grupos[nombre] = Grupo(sum(1 for f in filas if f[posicion] is True))
        else:
            grupos[nombre] = Grupo(len(filas))
    return grupos


def _cartera(cfg: Config, conn: Any, empresa_cfg: EmpresaHana, hoy: date,
             ahora: Callable[[], datetime], renovar: Callable[[], Any]) -> dict[str, Grupo]:
    r = _extraer(conn, empresa_cfg, _trabajo_completo(cfg, "CARTERA", empresa_cfg.codigo, hoy), ahora)
    filas = r.filas["cartera"]
    posicion = r.columnas["cartera"].index("saldo")
    saldo = sum((Decimal(f[posicion]) for f in filas), Decimal(0))
    return {CLAVE_CARTERA: Grupo(len(filas), {"saldo": formatear(saldo, DECIMALES["saldo"])})}


def agregar_ventas(acumulado: dict[str, dict[str, Any]], columnas: list[str], filas: list[list[Any]]) -> None:
    """Suma filas de VENTAS ya convertidas (esquema.preparar_filas) por mes de fecha_contabilizacion."""
    i_fecha = columnas.index("fecha_contabilizacion")
    sumas = [(nombre, columnas.index(nombre)) for nombre in ("total", "cantidad")]
    nulos = [(nombre, columnas.index(nombre)) for nombre in NULOS_VENTAS]
    for fila in filas:
        mes = acumulado.setdefault(fila[i_fecha][:7], {
            "filas": 0, **{n: Decimal(0) for n, _ in sumas}, **{f"nulos.{n}": 0 for n, _ in nulos}})
        mes["filas"] += 1
        for nombre, posicion in sumas:
            mes[nombre] += Decimal(fila[posicion])
        for nombre, posicion in nulos:
            mes[f"nulos.{nombre}"] += fila[posicion] is None


def grupos_ventas(acumulado: dict[str, dict[str, Any]]) -> dict[str, Grupo]:
    return {
        mes: Grupo(
            a["filas"],
            {n: formatear(a[n], DECIMALES[n]) for n in ("total", "cantidad")},
            {n: a[f"nulos.{n}"] for n in NULOS_VENTAS},
        )
        for mes, a in sorted(acumulado.items())
    }


def _ventas(cfg: Config, conn: Any, empresa_cfg: EmpresaHana, hoy: date,
            ahora: Callable[[], datetime], renovar: Callable[[], Any]) -> dict[str, Grupo]:
    acumulado: dict[str, dict[str, Any]] = {}
    for desde, hasta in tramos_ventas(hoy):
        # El tramo del histórico (la misma consulta, el mismo rango y la misma validación); se
        # suma y se suelta antes del siguiente.
        r = _extraer(conn, empresa_cfg, trabajo_historico_ventas(empresa_cfg.codigo, desde, hasta), ahora)
        agregar_ventas(acumulado, r.columnas["ventas"], r.filas["ventas"])
        r.columnas, r.filas = {}, {}
        renovar()
    return grupos_ventas(acumulado)


_LECTORES = {"MAESTROS": _maestros, "CARTERA": _cartera, "VENTAS": _ventas}


def _etapa(exc: BaseException) -> str:
    if isinstance(exc, extraccion.FalloTrabajo):
        return exc.etapa
    if isinstance(exc, hana.HanaError):
        return "HANA"
    if isinstance(exc, config.ConfigError):
        return "CONFIGURACION"
    return "EXTRACCION"


def leer_sap(
    cfg: Config,
    empresas: list[str],
    hoy: date,
    *,
    robot_vpn: Any = None,
    conectar: Callable[..., Any] = hana.conectar,
    sin_vpn: bool = False,
    ahora: Callable[[], datetime] = config.ahora,
    renovar: Callable[[], Any] = lambda: None,
) -> tuple[list[Comparacion], list[tuple[str, str]]]:
    """FASE 1: los totales de SAP de cada empresa y conjunto, en una sesión de VPN. Un conjunto
    que falla no frena a los demás. Devuelve las comparaciones y los fallos."""
    comparaciones = [
        Comparacion(conjunto, empresa, *((PRIMER_DIA.isoformat(), hoy.isoformat()) if conjunto == "VENTAS" else ()))
        for empresa in empresas for conjunto in CONJUNTOS if esquema.es_de_la_empresa(conjunto, empresa)
    ]

    def leer(conn: Any, empresa: str) -> None:
        empresa_cfg = cfg.hana.empresas[empresa]
        for c in comparaciones:
            if c.empresa != empresa:
                continue
            try:
                c.sap = _LECTORES[c.conjunto](cfg, conn, empresa_cfg, hoy, ahora, renovar)
            except Exception as exc:
                c.fallar(_etapa(exc), extraccion.mensaje_seguro(exc))
                log.error("Comparación %s: falló la lectura de SAP: %s", c.nombre, exc)
            renovar()

    fallos = extraccion.sesion(cfg, empresas, leer, robot_vpn=robot_vpn, conectar=conectar, sin_vpn=sin_vpn)
    for c in comparaciones:
        if c.sap is None and c.error is None:
            c.fallar(_SIN_SESION, "No se leyó SAP (falló la VPN o la conexión a HANA).")
    fallos += [(c.etapa or ETAPA, f"Comparación {c.nombre}: {c.error}")
               for c in comparaciones if c.error is not None and c.etapa != _SIN_SESION]
    return comparaciones, fallos


# --- FASE 2: /totales y /comparaciones ----------------------------------------------------------


def _texto(valor: Any) -> str | None:
    return None if valor is None else str(valor)[:MAX_VALOR]


def _diferencia(clave: str, campo: str, sap: Any, mysql: Any) -> dict[str, str | None]:
    return {"clave": clave[:MAX_CLAVE], "campo": campo[:MAX_CAMPO], "sap": _texto(sap), "mysql": _texto(mysql)}


def diferencias(sap: dict[str, Grupo], mysql: dict[str, Grupo], ordenar: bool = False) -> list[dict[str, str | None]]:
    """Regla de §13.2: por clave, filas y cada número de nulos iguales y cada suma igual como
    texto. Una clave de un solo lado es una diferencia en `filas` con el otro lado en null.
    Solo se comparan las sumas y los nulos que el robot calcula. Con `ordenar`, las claves van
    de menor a mayor (los meses de VENTAS); si no, primero las de SAP."""
    claves = list(sap) + [k for k in mysql if k not in sap]
    if ordenar:
        claves.sort()
    salida: list[dict[str, str | None]] = []
    for clave in claves:
        s, m = sap.get(clave), mysql.get(clave)
        if s is None or m is None:
            salida.append(_diferencia(clave, "filas", None if s is None else s.filas, None if m is None else m.filas))
            continue
        if s.filas != m.filas:
            salida.append(_diferencia(clave, "filas", s.filas, m.filas))
        for nombre, valor in s.sumas.items():
            if m.sumas.get(nombre) != valor:
                salida.append(_diferencia(clave, f"sumas.{nombre}", valor, m.sumas.get(nombre)))
        for nombre, numero in s.nulos.items():
            if m.nulos.get(nombre) != numero:
                salida.append(_diferencia(clave, f"nulos.{nombre}", numero, m.nulos.get(nombre)))
    return salida


def _mensaje_api(exc: BaseException) -> str:
    """Texto seguro de un error de la API: de un rechazo, el estado y los campos."""
    if isinstance(exc, ApiRechazo):
        campos = list(exc.errors)[:5]
        detalle = f" en {', '.join(campos)}" if campos else ""
        return f"La API rechazó la petición ({exc.status}){detalle}."
    if isinstance(exc, ApiError):
        return str(exc)
    return extraccion.mensaje_seguro(exc)


def _resumen_claves(c: Comparacion) -> str:
    por_clave: dict[str, list[str]] = {}
    for d in c.diferencias:
        por_clave.setdefault(d["clave"] or "", []).append(d["campo"] or "")
    partes = [f"{clave} ({', '.join(campos)})" for clave, campos in list(por_clave.items())[:GRUPOS_EN_EL_RESUMEN]]
    resto = len(por_clave) - GRUPOS_EN_EL_RESUMEN
    return ", ".join(partes) + (f" y {resto} más" if resto > 0 else "")


def comparar_con_api(
    api: ApiCliente,
    comparaciones: list[Comparacion],
    ahora: Callable[[], datetime] = config.ahora,
    renovar: Callable[[], Any] = lambda: None,
) -> list[tuple[str, str]]:
    """FASE 2, con la VPN abajo: por cada conjunto leído de SAP, /totales, las diferencias y
    una /comparaciones. Un fallo de la API en uno no frena a los demás. Devuelve los fallos."""
    fallos: list[tuple[str, str]] = []
    for c in comparaciones:
        if c.error is not None or c.sap is None:
            continue
        try:
            c.mysql = {g["clave"]: Grupo(g["filas"], g["sumas"], g["nulos"])
                       for g in api.totales(c.conjunto, c.empresa, c.desde, c.hasta)}
        except Exception as exc:
            c.fallar("API", _mensaje_api(exc))
            log.error("Comparación %s: falló /totales: %s", c.nombre, c.error)
            fallos.append(("API", f"Comparación {c.nombre}: {c.error}"))
            renovar()
            continue
        c.diferencias = diferencias(c.sap, c.mysql, ordenar=c.conjunto == "VENTAS")
        try:
            api.guardar_comparacion(
                conjunto=c.conjunto, empresa=c.empresa, comparada_en=ahora().isoformat(timespec="seconds"),
                desde=c.desde, hasta=c.hasta, cuadra=not c.diferencias,
                diferencias=c.diferencias[:MAX_DIFERENCIAS],
            )
        except Exception as exc:
            c.sin_guardar = _mensaje_api(exc)
            log.error("Comparación %s: no se pudo guardar en la API: %s", c.nombre, c.sin_guardar)
            fallos.append(("API", f"Comparación {c.nombre}: no se pudo guardar en la API: {c.sin_guardar}"))
        if c.diferencias:
            fallos.append((ETAPA, f"Comparación {c.nombre}: no cuadra en {len(c.claves_con_diferencias)} "
                                  f"grupos: {_resumen_claves(c)}."))
        renovar()
    return fallos


def resumir(comparaciones: list[Comparacion]) -> None:
    """Una línea por empresa y conjunto: cuadra, no cuadra (con clave y campo) o error."""
    for c in comparaciones:
        if c.resultado == "error":
            log.error("Comparación %s: error: %s", c.nombre, c.error)
        elif c.diferencias:
            log.warning("Comparación %s: no cuadra en %d grupos: %s.", c.nombre,
                        len(c.claves_con_diferencias), _resumen_claves(c))
        else:
            log.info("Comparación %s: cuadra.", c.nombre)


def ejecutar(
    cfg: Config,
    empresas: list[str],
    *,
    api: ApiCliente,
    robot_vpn: Any = None,
    conectar: Callable[..., Any] = hana.conectar,
    sin_vpn: bool = False,
    ahora: Callable[[], datetime] = config.ahora,
    renovar: Callable[[], Any] = lambda: None,
) -> tuple[list[Comparacion], list[tuple[str, str]]]:
    """Las dos fases de la comparación. Devuelve las comparaciones y los fallos (etapa, mensaje):
    sin fallos, todo cuadró y quedó guardado."""
    comparaciones, fallos = leer_sap(cfg, empresas, ahora().date(), robot_vpn=robot_vpn, conectar=conectar,
                                     sin_vpn=sin_vpn, ahora=ahora, renovar=renovar)
    fallos += comparar_con_api(api, comparaciones, ahora, renovar)
    resumir(comparaciones)
    if not fallos:
        log.info("Comparación con SAP: todo cuadra.")
    return comparaciones, fallos
