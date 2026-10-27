"""Diagnóstico (--diagnostico): lo corre el usuario para ver cifras antes de cargar.

Por empresa extrae cada parte de MAESTROS (completa) y CARTERA con su
COUNT(*), y la lista de listas de precios (OPLN). Nunca envía nada a la API:
este módulo no importa el cliente de la API y no necesita su configuración.

    _DIAGNOSTICO\\<EMPRESA>\\<parte>\\aaaa-mm-dd_hhmm.csv
    _DIAGNOSTICO\\<EMPRESA>\\listas_precios\\aaaa-mm-dd_hhmm.csv
    _DIAGNOSTICO\\resumen\\aaaa-mm-dd_hhmm.csv
        empresa;conjunto;parte;filas;conteo_sap;activos;inactivos;error

Una parte que falla no detiene a las demás: su error (corto y sin valores de
SAP) queda en el resumen. Retención: 90 días. Dos fases: `Diagnostico.__call__`
lee con la VPN arriba y `Diagnostico.escribir()` guarda con la VPN abajo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import consultas
import esquema
import hana
from carpeta import DIAGNOSTICO, Carpeta, texto_crudo
from config import Config, EmpresaHana
from extraccion import mensaje_seguro
from registro import obtener

log = obtener("diagnostico")

LISTAS_PRECIOS = "listas_precios"
CONSULTA_LISTAS = "diagnostico/listas_precios.sql"
COLUMNAS_RESUMEN = ["empresa", "conjunto", "parte", "filas", "conteo_sap", "activos", "inactivos", "error"]


@dataclass
class ParteDiagnostico:
    empresa: str
    conjunto: str
    parte: str
    columnas: list[str] = field(default_factory=list)
    filas: list[list[Any]] | None = None  # None: la consulta no llegó a traer filas
    conteo_sap: int | None = None
    activos: int | None = None
    inactivos: int | None = None
    error: str | None = None

    def resumen(self) -> list[Any]:
        return [
            self.empresa, self.conjunto, self.parte,
            "" if self.filas is None else len(self.filas),
            "" if self.conteo_sap is None else self.conteo_sap,
            "" if self.activos is None else self.activos,
            "" if self.inactivos is None else self.inactivos,
            self.error or "",
        ]


@dataclass
class Diagnostico:
    cfg: Config
    momento: datetime  # hora de Bogotá de la ejecución: nombre de los CSV
    carpeta: Carpeta | None = None
    partes: list[ParteDiagnostico] = field(default_factory=list)
    fallos: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.carpeta = self.carpeta or Carpeta(self.cfg.csv_dir)

    # --- FASE 1 -----------------------------------------------------------

    def __call__(self, conn: Any, empresa: str) -> None:
        empresa_cfg = self.cfg.hana.empresas[empresa]
        esquema_db = empresa_cfg.esquema
        for parte in esquema.PARTES.values():
            p = ParteDiagnostico(empresa, parte.conjunto, parte.nombre)
            self.partes.append(p)
            if parte.nombre == esquema.PRECIOS and empresa_cfg.sin_precios:
                # Como en la corrida real (contrato §4.1): no se pide y no es un fallo.
                p.error = (f"Omitida: {empresa} no tiene lista de precios pública "
                           f"({empresa_cfg.variable_lista_precios}).")
                continue
            try:
                self._leer_parte(conn, empresa_cfg, parte, p)
            except Exception as exc:
                self._fallo(p, exc)
        p = ParteDiagnostico(empresa, "DIAGNOSTICO", LISTAS_PRECIOS)
        self.partes.append(p)
        try:
            columnas, datos = hana.ejecutar(
                conn, consultas.leer(CONSULTA_LISTAS, esquema_db), f"{empresa} {LISTAS_PRECIOS}", esquema_db
            )
            p.columnas, p.filas = columnas, [[texto_crudo(v) for v in f] for f in datos]
        except Exception as exc:
            self._fallo(p, exc)

    def _leer_parte(self, conn: Any, empresa_cfg: EmpresaHana, parte: esquema.Parte, p: ParteDiagnostico) -> None:
        etiqueta = f"{p.empresa} {parte.nombre} (diagnóstico)"
        sql = consultas.leer_parte(parte, empresa_cfg)
        columnas, datos = hana.ejecutar(conn, sql, etiqueta, empresa_cfg.esquema)
        # Si la validación falla, igual se guardan las filas crudas para revisarlas.
        p.columnas, p.filas = columnas, [[texto_crudo(v) for v in f] for f in datos]
        p.conteo_sap = hana.contar(conn, consultas.sql_contar(sql), f"{etiqueta} conteo")
        filas = esquema.preparar_filas(parte, columnas, datos)
        p.columnas, p.filas = parte.nombres, filas
        if "activo" in parte.nombres:
            posicion = parte.nombres.index("activo")
            p.activos = sum(1 for f in filas if f[posicion] is True)
            p.inactivos = sum(1 for f in filas if f[posicion] is False)

    def _fallo(self, p: ParteDiagnostico, exc: BaseException) -> None:
        p.error = mensaje_seguro(exc)
        log.error("Diagnóstico %s %s: %s", p.empresa, p.parte, exc)
        self.fallos.append(("DIAGNOSTICO", f"{p.empresa} {p.parte}: {p.error}"))

    # --- FASE 2 -----------------------------------------------------------

    def escribir(self) -> list[tuple[str, str]]:
        """Guarda los datos y el resumen, lo muestra en el log y aplica la retención."""
        for p in self.partes:
            if p.filas is None:
                continue
            try:
                self.carpeta.guardar_corrida(DIAGNOSTICO, p.empresa, p.parte, p.columnas, p.filas, self.momento)
            except OSError as exc:
                log.error("Diagnóstico %s %s: no se pudo guardar el CSV: %s", p.empresa, p.parte, exc)
                self.fallos.append(("CARPETA", f"{p.empresa} {p.parte}: No se pudo guardar el CSV: {exc}"))
        if self.partes:
            filas = [p.resumen() for p in self.partes]
            try:
                ruta = self.carpeta.guardar_resumen_diagnostico(COLUMNAS_RESUMEN, filas, self.momento)
                log.info("Resumen del diagnóstico: %s", ruta)
            except OSError as exc:
                log.error("No se pudo guardar el resumen del diagnóstico: %s", exc)
                self.fallos.append(("CARPETA", f"No se pudo guardar el resumen del diagnóstico: {exc}"))
            self._mostrar(filas)
        try:
            self.carpeta.purgar_diagnostico(self.momento.date())
        except OSError as exc:
            log.error("Falló la retención del diagnóstico: %s", exc)
            self.fallos.append(("CARPETA", f"Falló la retención del diagnóstico: {exc}"))
        return list(self.fallos)

    @staticmethod
    def _mostrar(filas: list[list[Any]]) -> None:
        log.info("%-4s %-11s %-17s %8s %10s %8s %9s  %s", *COLUMNAS_RESUMEN)
        for f in filas:
            log.info("%-4s %-11s %-17s %8s %10s %8s %9s  %s", *f)
