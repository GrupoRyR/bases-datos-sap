"""Carpeta de CSV (BASES_SAP_CSV_DIR): respaldo de cada corrida y retención.

Estructura (plan §5):
    MAESTROS\\<SGX|SDC>\\<parte>\\aaaa-mm-dd_hhmm.csv     una por corrida, 90 días
    CARTERA\\<SGX|SDC>\\cartera\\aaaa-mm-dd_hhmm.csv      una por corrida, 90 días
    CARTERA\\<SGX|SDC>\\historico\\aaaa-mm-dd.csv         foto diaria, no se borra

CSV: UTF-8 con BOM (Excel lo abre bien), separador `;`, encabezado con los
nombres del contrato. Se escribe a un temporal en la misma carpeta y se
renombra: nunca queda un archivo a medias.
"""
from __future__ import annotations

import csv
import os
import re
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

from config import BOGOTA
from registro import obtener

log = obtener("carpeta")

RETENCION_DIAS = 90
PATRON_CORRIDA = re.compile(r"^(\d{4}-\d{2}-\d{2})_\d{4}(?:-\d+)?\.csv$")


def _celda(valor: Any) -> Any:
    if valor is True:
        return "true"
    if valor is False:
        return "false"
    if valor is None:
        return ""
    return valor


def escribir_csv(ruta: Path, columnas: Sequence[str], filas: Iterable[Sequence[Any]]) -> Path:
    """Escribe el CSV completo o nada (temporal + renombrar). Crea las carpetas."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as archivo:
            escritor = csv.writer(archivo, delimiter=";")
            escritor.writerow(list(columnas))
            for fila in filas:
                escritor.writerow([_celda(v) for v in fila])
        os.replace(temporal, ruta)
    except BaseException:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        raise
    return ruta


def purgar_por_fecha(carpeta: Path, patron: re.Pattern[str], limite: date) -> list[Path]:
    """Borra los archivos de `carpeta` (sin bajar a subcarpetas) cuyo nombre
    coincide con `patron` y cuya fecha (grupo 1, AAAA-MM-DD) es anterior a `limite`.

    Un archivo que no se puede borrar queda en el log y no detiene a los demás.
    """
    borrados: list[Path] = []
    if not carpeta.is_dir():
        return borrados
    for ruta in sorted(carpeta.iterdir()):
        m = patron.match(ruta.name)
        if not m or not ruta.is_file():
            continue
        try:
            fecha = date.fromisoformat(m.group(1))
        except ValueError:
            continue
        if fecha >= limite:
            continue
        try:
            ruta.unlink()
            borrados.append(ruta)
        except OSError as exc:
            log.warning("No se pudo borrar %s: %s", ruta, exc)
    return borrados


class Carpeta:
    def __init__(self, raiz: Path) -> None:
        self.raiz = Path(raiz)

    def guardar_corrida(
        self,
        conjunto: str,
        empresa: str,
        parte: str,
        columnas: Sequence[str],
        filas: Iterable[Sequence[Any]],
        momento: datetime,
    ) -> Path:
        """`<raiz>/<CONJUNTO>/<EMPRESA>/<parte>/aaaa-mm-dd_hhmm.csv`, con la hora de Bogotá."""
        if momento.tzinfo is not None:
            momento = momento.astimezone(BOGOTA)
        carpeta = self.raiz / conjunto / empresa / parte
        base = f"{momento:%Y-%m-%d_%H%M}"
        ruta = carpeta / f"{base}.csv"
        numero = 2
        while ruta.exists():
            ruta = carpeta / f"{base}-{numero}.csv"
            numero += 1
        return escribir_csv(ruta, columnas, filas)

    def guardar_historico_cartera(
        self, empresa: str, fecha: str, columnas: Sequence[str], filas: Iterable[Sequence[Any]]
    ) -> Path:
        """Foto diaria `<raiz>/CARTERA/<EMPRESA>/historico/<fecha>.csv`; reemplaza la del mismo día."""
        dia = date.fromisoformat(fecha)  # ValueError si no es AAAA-MM-DD
        ruta = self.raiz / "CARTERA" / empresa / "historico" / f"{dia.isoformat()}.csv"
        return escribir_csv(ruta, columnas, filas)

    def purgar_corridas(self, hoy: date, dias: int = RETENCION_DIAS) -> list[Path]:
        """Borra los CSV de corridas con fecha anterior a hoy - `dias`. Nunca toca `historico`."""
        limite = hoy - timedelta(days=dias)
        carpetas = [
            *self.raiz.glob("MAESTROS/*/*"),
            *self.raiz.glob("CARTERA/*/cartera"),
        ]
        borrados: list[Path] = []
        for carpeta in sorted(c for c in carpetas if c.is_dir()):
            borrados.extend(purgar_por_fecha(carpeta, PATRON_CORRIDA, limite))
        if borrados:
            log.info("Retención: %d CSV de corridas con más de %d días borrados.", len(borrados), dias)
        return borrados
