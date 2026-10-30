"""Carpeta de CSV (BASES_SAP_CSV_DIR): respaldo de cada corrida y retención.

Estructura (plan §5):
    MAESTROS\\<SGX|SDC>\\<parte>\\aaaa-mm-dd_hhmm.csv     una por corrida, 90 días
    CARTERA\\<SGX|SDC>\\cartera\\aaaa-mm-dd_hhmm.csv      una por corrida, 90 días
    CARTERA\\<SGX|SDC>\\historico\\aaaa-mm-dd.csv         foto diaria, no se borra
    VENTAS\\<SGX|SDC>\\aaaa-mm-dd_hhmm.csv                una por corrida, 90 días
    <CARPETA>\\<SGX|SDC>\\<TABLA>\\aaaa-mm-dd.csv         foto del archivo, 52 semanas
    <CARPETA>\\<SGX|SDC>\\<TABLA>\\aaaa-mm.csv            registro del archivo, no se borra
    _CATALOGO\\<SGX|SDC>\\<consulta>\\aaaa-mm-dd.csv      foto del catálogo, 52 semanas
    _DIAGNOSTICO\\<SGX|SDC>\\<parte>\\aaaa-mm-dd_hhmm.csv y
    _DIAGNOSTICO\\resumen\\aaaa-mm-dd_hhmm.csv               una por ejecución, 90 días

CSV: UTF-8 con BOM (Excel lo abre bien), separador `;`, encabezado con los
nombres del contrato. Se escribe a un temporal en la misma carpeta y se
renombra: nunca queda un archivo a medias.
"""
from __future__ import annotations

import csv
import os
import re
import shutil
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence

from config import BOGOTA
from registro import obtener

log = obtener("carpeta")

RETENCION_DIAS = 90
RETENCION_FOTOS_DIAS = 364  # 52 semanas
PATRON_CORRIDA = re.compile(r"^(\d{4}-\d{2}-\d{2})_\d{4}(?:-\d+)?\.csv$")
PATRON_FOTO = re.compile(r"^(\d{4}-\d{2}-\d{2})\.csv$")
PATRON_MES = re.compile(r"^(\d{4}-\d{2})\.csv$")
DIAGNOSTICO = "_DIAGNOSTICO"
# Conjuntos de una sola parte: su CSV va directo en <CONJUNTO>\<EMPRESA> (contrato §10.3).
CONJUNTOS_SIN_CARPETA_DE_PARTE = ("VENTAS",)


def texto_crudo(valor: Any) -> str:
    """Valor de SAP tal cual, como texto: fechas AAAA-MM-DD, horas ISO, decimales
    sin notación científica, None vacío. Lo usan el archivo, el catálogo y el diagnóstico."""
    if valor is None:
        return ""
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return format(valor, "f")
    if isinstance(valor, (bytes, bytearray, memoryview)):
        return bytes(valor).hex()
    return str(valor)


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


def anexar_csv(ruta: Path, columnas: Sequence[str], filas: Iterable[Sequence[Any]]) -> Path:
    """Suma filas al final de un CSV; si no existe, lo crea con encabezado.

    También va por un temporal que se renombra: nunca queda un archivo a medias.
    Si el encabezado del archivo no es el de `columnas` (alguien cambió la
    consulta), lanza ValueError en vez de mezclar columnas.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        return escribir_csv(ruta, columnas, filas)
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        encabezado = next(csv.reader(archivo, delimiter=";"), [])
    if encabezado != list(columnas):
        raise ValueError(
            f"{ruta.name} tiene otras columnas ({len(encabezado)}) que la consulta "
            f"({len(columnas)}); no se suman filas. Revisa la consulta o mueve el archivo."
        )
    fd, temporal = tempfile.mkstemp(prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent)
    os.close(fd)
    try:
        shutil.copyfile(ruta, temporal)
        # utf-8 sin BOM: el BOM ya está al inicio del archivo.
        with open(temporal, "a", encoding="utf-8", newline="") as archivo:
            escritor = csv.writer(archivo, delimiter=";")
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
        """`<raiz>/<CONJUNTO>/<EMPRESA>/<parte>/aaaa-mm-dd_hhmm.csv`, con la hora de Bogotá.

        VENTAS no lleva la carpeta de la parte: `<raiz>/VENTAS/<EMPRESA>/aaaa-mm-dd_hhmm.csv`.
        """
        carpeta = self.raiz / conjunto / empresa
        if conjunto not in CONJUNTOS_SIN_CARPETA_DE_PARTE:
            carpeta = carpeta / parte
        return self._guardar_con_hora(carpeta, columnas, filas, momento)

    def guardar_resumen_diagnostico(
        self, columnas: Sequence[str], filas: Iterable[Sequence[Any]], momento: datetime
    ) -> Path:
        """`<raiz>/_DIAGNOSTICO/resumen/aaaa-mm-dd_hhmm.csv`."""
        return self._guardar_con_hora(self.raiz / DIAGNOSTICO / "resumen", columnas, filas, momento)

    def _guardar_con_hora(
        self, carpeta: Path, columnas: Sequence[str], filas: Iterable[Sequence[Any]], momento: datetime
    ) -> Path:
        if momento.tzinfo is not None:
            momento = momento.astimezone(BOGOTA)
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

    def guardar_foto(
        self, carpeta: str, empresa: str, tabla: str, columnas: Sequence[str],
        filas: Iterable[Sequence[Any]], dia: date,
    ) -> Path:
        """Foto `<raiz>/<CARPETA>/<EMPRESA>/<TABLA>/aaaa-mm-dd.csv`; reemplaza la del mismo día."""
        ruta = self.carpeta_tabla(carpeta, empresa, tabla) / f"{dia.isoformat()}.csv"
        return escribir_csv(ruta, columnas, filas)

    def carpeta_tabla(self, carpeta: str, empresa: str, tabla: str) -> Path:
        return self.raiz / carpeta / empresa / tabla

    def anexar_registro(
        self, carpeta: str, empresa: str, tabla: str, mes: str, columnas: Sequence[str],
        filas: Iterable[Sequence[Any]],
    ) -> Path:
        """Suma filas a `<raiz>/<CARPETA>/<EMPRESA>/<TABLA>/aaaa-mm.csv` (no se borra nunca)."""
        if not PATRON_MES.match(f"{mes}.csv"):
            raise ValueError(f"Mes inválido para un registro: {mes!r} (usa AAAA-MM).")
        return anexar_csv(self.carpeta_tabla(carpeta, empresa, tabla) / f"{mes}.csv", columnas, filas)

    def ultimo_registro(self, carpeta: str, empresa: str, tabla: str, columna: str) -> date | None:
        """Último día ya guardado de un registro: la fecha mayor de `columna` en el
        `aaaa-mm.csv` más nuevo. None si todavía no hay archivos (primera vez).

        Lanza ValueError si el archivo no tiene esa columna o ninguna fecha: así
        no se vuelve a traer todo el historial ni se duplican filas.
        """
        carpeta_tabla = self.carpeta_tabla(carpeta, empresa, tabla)
        if not carpeta_tabla.is_dir():
            return None
        meses = sorted(r for r in carpeta_tabla.iterdir() if r.is_file() and PATRON_MES.match(r.name))
        if not meses:
            return None
        ruta = meses[-1]
        ultimo: date | None = None
        with open(ruta, encoding="utf-8-sig", newline="") as archivo:
            lector = csv.reader(archivo, delimiter=";")
            encabezado = next(lector, [])
            if columna not in encabezado:
                raise ValueError(f"{ruta.name} no tiene la columna {columna}; revisa el archivo.")
            posicion = encabezado.index(columna)
            for fila in lector:
                if posicion >= len(fila) or not fila[posicion].strip():
                    continue
                try:
                    dia = date.fromisoformat(fila[posicion].strip()[:10])
                except ValueError:
                    raise ValueError(
                        f"{ruta.name}: la columna {columna} tiene un valor que no es fecha."
                    ) from None
                if ultimo is None or dia > ultimo:
                    ultimo = dia
        if ultimo is None:
            raise ValueError(f"{ruta.name} no tiene fechas en la columna {columna}; revisa el archivo.")
        return ultimo

    def purgar_fotos(
        self, hoy: date, carpetas: Iterable[str], dias: int = RETENCION_FOTOS_DIAS
    ) -> list[Path]:
        """Borra las fotos `aaaa-mm-dd.csv` de `<CARPETA>/<EMPRESA>/<TABLA>/` con fecha
        anterior a hoy - `dias`. Los registros `aaaa-mm.csv` no coinciden: nunca se tocan."""
        limite = hoy - timedelta(days=dias)
        borrados: list[Path] = []
        for nombre in sorted(set(carpetas)):
            for carpeta in sorted(c for c in self.raiz.glob(f"{nombre}/*/*") if c.is_dir()):
                borrados.extend(purgar_por_fecha(carpeta, PATRON_FOTO, limite))
        if borrados:
            log.info("Retención: %d fotos con más de %d días borradas.", len(borrados), dias)
        return borrados

    def purgar_diagnostico(self, hoy: date, dias: int = RETENCION_DIAS) -> list[Path]:
        """Borra los CSV de `_DIAGNOSTICO` con fecha anterior a hoy - `dias`."""
        limite = hoy - timedelta(days=dias)
        carpetas = [self.raiz / DIAGNOSTICO / "resumen", *self.raiz.glob(f"{DIAGNOSTICO}/*/*")]
        borrados: list[Path] = []
        for carpeta in sorted(c for c in carpetas if c.is_dir()):
            borrados.extend(purgar_por_fecha(carpeta, PATRON_CORRIDA, limite))
        if borrados:
            log.info("Retención: %d CSV de diagnóstico con más de %d días borrados.", len(borrados), dias)
        return borrados

    def purgar_corridas(self, hoy: date, dias: int = RETENCION_DIAS) -> list[Path]:
        """Borra los CSV de corridas con fecha anterior a hoy - `dias`. Nunca toca `historico`."""
        limite = hoy - timedelta(days=dias)
        carpetas = [
            *self.raiz.glob("MAESTROS/*/*"),
            *self.raiz.glob("CARTERA/*/cartera"),
            *(c for conjunto in CONJUNTOS_SIN_CARPETA_DE_PARTE for c in self.raiz.glob(f"{conjunto}/*")),
        ]
        borrados: list[Path] = []
        for carpeta in sorted(c for c in carpetas if c.is_dir()):
            borrados.extend(purgar_por_fecha(carpeta, PATRON_CORRIDA, limite))
        if borrados:
            log.info("Retención: %d CSV de corridas con más de %d días borrados.", len(borrados), dias)
        return borrados
