"""Tablas que solo van a la carpeta (plan §5): fotos de los domingos y registros nocturnos.

Nunca se envían a la API ni a MySQL: este módulo no importa el cliente de la
API. Dos fases, como el resto del robot:

- FASE 1, con VPN: `Archivo.__call__(conn, empresa)` lee de HANA (es el gancho
  `extra` de extraccion.extraer o el paso de extraccion.sesion). Solo lee: la
  marca de agua de cada registro sale de los CSV que ya están en la carpeta.
- FASE 2, sin VPN: `Archivo.escribir()` guarda los CSV y aplica la retención.

Fotos: la tabla completa en `<CARPETA>\\<EMPRESA>\\<TABLA>\\aaaa-mm-dd.csv`, 52 semanas.
Registros: los días completos después de la marca de agua y antes de hoy, sumados
a `<CARPETA>\\<EMPRESA>\\<TABLA>\\aaaa-mm.csv` según el mes de la fila; no se borran.

Una tabla que falla queda en el log y en los fallos (etapa ARCHIVO, va en el
correo a TI) y las demás siguen. Los valores se guardan tal cual vienen de SAP,
como texto (carpeta.texto_crudo).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

import consultas
import hana
from carpeta import Carpeta, texto_crudo
from config import Config
from extraccion import mensaje_seguro
from registro import obtener

log = obtener("archivo")

ModoTabla = Literal["foto", "registro"]
CONFIGURACION = "CONFIGURACION"
HBT_TABLAS = "archivo/hbt_tablas.sql"
HBT_COLUMNAS = "archivo/hbt_columnas.sql"
RE_NOMBRE_HBT = re.compile(r"^@HBT\w*$", re.IGNORECASE)
# Columnas que parecen claves: nunca se leen de una tabla @HBT_*.
RE_CLAVE = re.compile(r"PASS|PWD|CLAVE|CONTRASE", re.IGNORECASE)
AVISO_GRANDE = (
    "omitida hasta que TI confirme su tamaño en el catálogo "
    "(BASES_SAP_ARCHIVO_HISTORIAL_DOCUMENTOS)"
)


@dataclass(frozen=True)
class TablaArchivo:
    carpeta: str
    tabla: str
    consulta: str  # relativa a robot/queries
    modo: ModoTabla
    columna_fecha: str | None = None  # solo registros: columna del día de la fila
    grande: bool = False  # historial de documentos y asientos: apagado por defecto


def _foto(carpeta: str, tabla: str, consulta: str | None = None) -> TablaArchivo:
    return TablaArchivo(carpeta, tabla, consulta or f"archivo/{carpeta}/{tabla}.sql", "foto")


def _registro(carpeta: str, tabla: str, columna: str, grande: bool = False) -> TablaArchivo:
    return TablaArchivo(carpeta, tabla, f"archivo/{carpeta}/{tabla}.sql", "registro", columna, grande)


_A, _U, _C, _B = "AUDITORIA", "USUARIOS_Y_PERMISOS", "CONTABILIDAD", "BANCOS"
_I, _O, _V = "INVENTARIO", "ORGANIZACION", "VENTAS_Y_CRM"

# Plan §5. LICENCIAS es manual (TI la exporta); las tablas @HBT_* se descubren al correr.
TABLAS: tuple[TablaArchivo, ...] = (
    _registro(_A, "USR5", "Date"),
    _registro(_A, "OSUL", "Date"),
    _registro(_A, "ACRD", "UpdateDate"),
    _registro(_A, "ACR1", "UpdateDate"),
    _registro(_A, "AITM", "UpdateDate"),
    _registro(_A, "AUSR", "UpdateDate"),
    _registro(_A, "ADOC", "UpdateDate", grande=True),
    _registro(_A, "ADO1", "UpdateDate", grande=True),
    _registro(_A, "AJDT", "UpdateDate", grande=True),
    _registro(_A, "AJD1", "UpdateDate", grande=True),
    _registro(_A, "OWDD", "CreateDate"),
    _registro(_A, "WDD1", "UpdateDate"),
    *(_foto(_U, t) for t in ("OUSR", "USR3", "UGR1", "OUPT", "UPT1")),
    *(_foto(_C, t) for t in ("OACT", "OPRC", "OOCR", "OPRJ", "OFPR", "OCRN", "OSTC", "OWHT")),
    _registro(_C, "ORTT", "RateDate"),
    *(_foto(_B, t) for t in ("ODSC", "DSC1", "OPYM")),
    *(_foto(_I, t) for t in ("OWHS", "OUOM", "OUGP", "OITT", "ITT1", "OSPP", "SPP1")),
    *(_foto(_O, t) for t in ("OADM", "OBPL", "OUDP", "OHPS", "OTER", "OIND", "OHEM")),
    *(_foto(_V, t) for t in ("OCLG", "OOPR", "OPR1", "OSHP", "OCRY", "OCST")),
    _foto(CONFIGURACION, "NNM1"),
    _foto(CONFIGURACION, "CUFD", "catalogo/campos_usuario.sql"),  # la misma del catálogo
    _foto(CONFIGURACION, "UFD1"),
    _foto(CONFIGURACION, "OUTB", "catalogo/tablas_usuario.sql"),  # la misma del catálogo
    *(_foto(CONFIGURACION, t) for t in ("OUDO", "OUQR", "OQCN", "OALT")),
)

CARPETAS_CON_FOTOS = tuple(sorted({t.carpeta for t in TABLAS if t.modo == "foto"}))


def seleccionar(modo: str, historial_documentos: bool) -> list[TablaArchivo]:
    """Tablas de `modo` ("fotos" o "registros"). Las grandes solo con el historial activo."""
    if modo not in ("fotos", "registros"):
        raise ValueError(f"Modo de archivo desconocido: {modo!r} (fotos o registros).")
    tipo = "foto" if modo == "fotos" else "registro"
    elegidas: list[TablaArchivo] = []
    for tabla in TABLAS:
        if tabla.modo != tipo:
            continue
        if tabla.grande and not historial_documentos:
            log.info("%s/%s: %s.", tabla.carpeta, tabla.tabla, AVISO_GRANDE)
            continue
        elegidas.append(tabla)
    return elegidas


def _envolver(sql: str, condicion: str) -> str:
    # Igual que consultas.py: el X.* solo proyecta las columnas que el archivo
    # lista una por una, y el salto de línea protege de un comentario final.
    return f"SELECT X.* FROM (\n{sql}\n) X WHERE {condicion}"


def sql_registro(sql: str, columna: str, desde: date | None) -> str:
    """Filas de días completos: `desde` <= día < hoy (o solo < hoy la primera vez).

    `>=` y `<` sirven igual si la columna es DATE o TIMESTAMP.
    """
    col = 'X."' + columna.replace('"', '""') + '"'
    if desde is None:
        return _envolver(sql, f"{col} < ?")
    return _envolver(sql, f"{col} >= ? AND {col} < ?")


def es_clave(columna: str) -> bool:
    return bool(RE_CLAVE.search(columna))


def sql_hbt(tabla: str, columnas: list[str]) -> str:
    """SELECT de una tabla @HBT_* con cada columna entre comillas (nunca todas con *)."""
    if not RE_NOMBRE_HBT.match(tabla):
        raise ValueError(f"Nombre de tabla HBT inesperado: {tabla!r}.")
    if not columnas:
        raise ValueError(f"La tabla {tabla} no tiene columnas que se puedan leer.")
    lista = ",\n".join('    T0."' + c.replace('"', '""') + '"' for c in columnas)
    return f'SELECT\n{lista}\nFROM "{tabla}" T0'


@dataclass
class Lectura:
    empresa: str
    carpeta: str
    tabla: str
    modo: ModoTabla
    columna_fecha: str | None
    columnas: list[str]
    filas: list[tuple]


@dataclass
class Archivo:
    """Lee en la fase 1 (llamándolo con conn y empresa) y escribe en la fase 2."""

    cfg: Config
    modo: str  # fotos | registros
    hoy: date  # Bogotá: nombre de las fotos y fin (excluido) de los registros
    carpeta: Carpeta | None = None
    tablas: list[TablaArchivo] = field(default_factory=list)
    lecturas: list[Lectura] = field(default_factory=list)
    fallos: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.carpeta = self.carpeta or Carpeta(self.cfg.csv_dir)
        self.tablas = seleccionar(self.modo, self.cfg.historial_documentos)

    # --- FASE 1 -----------------------------------------------------------

    def __call__(self, conn: Any, empresa: str) -> None:
        esquema_db = self.cfg.hana.empresas[empresa].esquema
        for tabla in self.tablas:
            try:
                self._leer(conn, empresa, esquema_db, tabla)
            except Exception as exc:
                self._fallo(empresa, tabla.carpeta, tabla.tabla, exc)
        if self.modo == "fotos":
            self._leer_hbt(conn, empresa, esquema_db)

    def _fallo(self, empresa: str, carpeta: str, tabla: str, exc: BaseException) -> None:
        log.error("Archivo %s %s/%s: %s", empresa, carpeta, tabla, exc)
        self.fallos.append(("ARCHIVO", f"{empresa} {carpeta}/{tabla}: {mensaje_seguro(exc)}"))

    def _leer(self, conn: Any, empresa: str, esquema_db: str, tabla: TablaArchivo) -> None:
        etiqueta = f"{empresa} {tabla.carpeta}/{tabla.tabla}"
        sql = consultas.leer(tabla.consulta, esquema_db)
        if tabla.modo == "foto":
            columnas, filas = hana.ejecutar(conn, sql, etiqueta, esquema_db)
        else:
            assert tabla.columna_fecha is not None
            ultimo = self.carpeta.ultimo_registro(tabla.carpeta, empresa, tabla.tabla, tabla.columna_fecha)
            desde = ultimo + timedelta(days=1) if ultimo is not None else None
            if desde is not None and desde >= self.hoy:
                log.info("Archivo %s: al día (último día guardado %s).", etiqueta, ultimo)
                return
            params: list[Any] = [self.hoy] if desde is None else [desde, self.hoy]
            columnas, filas = hana.ejecutar(
                conn, sql_registro(sql, tabla.columna_fecha, desde), etiqueta, esquema_db, params
            )
            if tabla.columna_fecha not in columnas:
                raise ValueError(f"La consulta no trae la columna {tabla.columna_fecha}.")
        self.lecturas.append(Lectura(
            empresa, tabla.carpeta, tabla.tabla, tabla.modo, tabla.columna_fecha, columnas, filas,
        ))

    def _leer_hbt(self, conn: Any, empresa: str, esquema_db: str) -> None:
        """Descubre las tablas @HBT_* y las lee con una lista explícita de columnas."""
        try:
            _, filas_t = hana.ejecutar(
                conn, consultas.leer(HBT_TABLAS, esquema_db), f"{empresa} tablas @HBT", esquema_db
            )
            nombres_c, filas_c = hana.ejecutar(
                conn, consultas.leer(HBT_COLUMNAS, esquema_db), f"{empresa} columnas @HBT", esquema_db
            )
            por_tabla = columnas_hbt(nombres_c, filas_c)
        except Exception as exc:
            self._fallo(empresa, CONFIGURACION, "@HBT_*", exc)
            return
        for nombre in (str(f[0]) for f in filas_t):
            try:
                sql = sql_hbt(nombre, por_tabla.get(nombre, []))
                columnas, filas = hana.ejecutar(conn, sql, f"{empresa} {CONFIGURACION}/{nombre}", esquema_db)
            except Exception as exc:
                self._fallo(empresa, CONFIGURACION, nombre, exc)
                continue
            self.lecturas.append(Lectura(empresa, CONFIGURACION, nombre, "foto", None, columnas, filas))

    # --- FASE 2 -----------------------------------------------------------

    def escribir(self) -> list[tuple[str, str]]:
        """Guarda lo leído (VPN abajo) y aplica la retención de las fotos. Devuelve todos los fallos."""
        for lectura in self.lecturas:
            try:
                self._escribir(lectura)
            except Exception as exc:
                self._fallo(lectura.empresa, lectura.carpeta, lectura.tabla, exc)
        if self.modo == "fotos":
            try:
                self.carpeta.purgar_fotos(self.hoy, CARPETAS_CON_FOTOS)
            except OSError as exc:
                log.error("Falló la retención de las fotos del archivo: %s", exc)
                self.fallos.append(("CARPETA", f"Falló la retención de las fotos del archivo: {exc}"))
        return list(self.fallos)

    def _escribir(self, lectura: Lectura) -> None:
        filas = [[texto_crudo(v) for v in f] for f in lectura.filas]
        if lectura.modo == "foto":
            self.carpeta.guardar_foto(
                lectura.carpeta, lectura.empresa, lectura.tabla, lectura.columnas, filas, self.hoy
            )
            log.info("Archivo %s %s/%s: foto con %d filas.",
                     lectura.empresa, lectura.carpeta, lectura.tabla, len(filas))
            return
        posicion = lectura.columnas.index(lectura.columna_fecha)
        por_mes: dict[str, list[list[str]]] = {}
        for fila in filas:
            mes = fila[posicion][:7]
            if not re.match(r"^\d{4}-\d{2}$", mes):
                raise ValueError(f"Una fila no trae fecha válida en {lectura.columna_fecha}.")
            por_mes.setdefault(mes, []).append(fila)
        for mes in sorted(por_mes):  # del más viejo al más nuevo: la marca de agua queda bien
            self.carpeta.anexar_registro(
                lectura.carpeta, lectura.empresa, lectura.tabla, mes, lectura.columnas, por_mes[mes]
            )
        log.info("Archivo %s %s/%s: %d filas nuevas en %s.", lectura.empresa, lectura.carpeta,
                 lectura.tabla, len(filas), ", ".join(sorted(por_mes)) or "ningún mes")


def columnas_hbt(nombres: list[str], filas: list[tuple]) -> dict[str, list[str]]:
    """Columnas de cada tabla @HBT_* en orden de POSITION, sin las que parecen claves."""
    i_tabla, i_columna, i_posicion = (nombres.index(n) for n in ("TABLE_NAME", "COLUMN_NAME", "POSITION"))
    por_tabla: dict[str, list[tuple[int, str]]] = {}
    for fila in filas:
        columna = str(fila[i_columna])
        if es_clave(columna):
            log.info("Tabla %s: se salta la columna %s (parece una clave).", fila[i_tabla], columna)
            continue
        por_tabla.setdefault(str(fila[i_tabla]), []).append((int(fila[i_posicion]), columna))
    return {t: [c for _, c in sorted(cs)] for t, cs in por_tabla.items()}
