"""Catálogo de cada empresa (--catalogo y la corrida de los domingos), plan §5.

`_CATALOGO\\<EMPRESA>\\{tablas,campos_usuario,tablas_usuario,columnas}\\aaaa-mm-dd.csv`,
con las consultas de robot/queries/catalogo. Fotos de 52 semanas. Nunca va a la
API: este módulo no importa el cliente de la API.

`columnas` se queda solo con las tablas que el robot lee (las de MAESTROS,
CARTERA, el archivo y las @HBT_*), para confirmar los nombres marcados
VALIDAR CON DATOS REALES en las consultas.

Dos fases: `Catalogo.__call__(conn, empresa)` lee con la VPN arriba y
`Catalogo.escribir()` guarda con la VPN abajo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import config
import consultas
import hana
from carpeta import Carpeta, texto_crudo
from config import Config
from extraccion import mensaje_seguro
from registro import obtener

log = obtener("catalogo")

CARPETA = "_CATALOGO"
CONSULTAS = {
    "tablas": "catalogo/tablas.sql",
    "campos_usuario": "catalogo/campos_usuario.sql",
    "tablas_usuario": "catalogo/tablas_usuario.sql",
    "columnas": "catalogo/columnas.sql",
}
PREFIJO_HBT = "@HBT"
# Tablas de SAP en FROM o JOIN: "OCRD" sí; "SYS"."TABLES" no (tiene esquema).
_RE_TABLA = re.compile(r'\b(?:FROM|JOIN)\s+"([^"]+)"(?!\s*\.)', re.IGNORECASE)


def tablas_leidas() -> frozenset[str]:
    """Tablas de SAP que leen las consultas del robot (todas las de robot/queries)."""
    tablas: set[str] = set()
    for ruta in sorted(config.QUERIES_DIR.rglob("*.sql")):
        sql = re.sub(r"--[^\n]*", "", ruta.read_text(encoding="utf-8-sig"))
        tablas.update(_RE_TABLA.findall(sql))
    return frozenset(tablas)


def es_tabla_del_robot(nombre: str, tablas: frozenset[str]) -> bool:
    return nombre in tablas or nombre.upper().startswith(PREFIJO_HBT)


@dataclass
class Catalogo:
    cfg: Config
    hoy: date
    carpeta: Carpeta | None = None
    lecturas: list[tuple[str, str, list[str], list[tuple]]] = field(default_factory=list)
    fallos: list[tuple[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.carpeta = self.carpeta or Carpeta(self.cfg.csv_dir)

    def __call__(self, conn: Any, empresa: str) -> None:
        """FASE 1: las cuatro consultas del catálogo; una que falla no detiene a las demás."""
        esquema_db = self.cfg.hana.empresas[empresa].esquema
        for nombre, archivo in CONSULTAS.items():
            try:
                columnas, filas = hana.ejecutar(
                    conn, consultas.leer(archivo, esquema_db), f"{empresa} catálogo {nombre}", esquema_db
                )
                if nombre == "columnas":
                    filas = self._solo_del_robot(columnas, filas)
            except Exception as exc:
                self._fallo(empresa, nombre, exc)
                continue
            self.lecturas.append((empresa, nombre, columnas, filas))

    @staticmethod
    def _solo_del_robot(columnas: list[str], filas: list[tuple]) -> list[tuple]:
        posicion = columnas.index("TABLE_NAME")
        tablas = tablas_leidas()
        return [f for f in filas if es_tabla_del_robot(str(f[posicion]), tablas)]

    def _fallo(self, empresa: str, nombre: str, exc: BaseException) -> None:
        log.error("Catálogo %s %s: %s", empresa, nombre, exc)
        self.fallos.append(("CATALOGO", f"{empresa} {nombre}: {mensaje_seguro(exc)}"))

    def escribir(self) -> list[tuple[str, str]]:
        """FASE 2: una foto por empresa y consulta, y la retención de 52 semanas."""
        for empresa, nombre, columnas, filas in self.lecturas:
            try:
                self.carpeta.guardar_foto(
                    CARPETA, empresa, nombre, columnas, [[texto_crudo(v) for v in f] for f in filas], self.hoy
                )
                log.info("Catálogo %s %s: %d filas.", empresa, nombre, len(filas))
            except Exception as exc:
                self._fallo(empresa, nombre, exc)
        try:
            self.carpeta.purgar_fotos(self.hoy, [CARPETA])
        except OSError as exc:
            log.error("Falló la retención del catálogo: %s", exc)
            self.fallos.append(("CARPETA", f"Falló la retención del catálogo: {exc}"))
        return list(self.fallos)
