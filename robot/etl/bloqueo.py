"""Franjas bloqueadas y candado: el robot nunca usa la VPN a la vez que otro.

El perfil VPN de Sophos es de túnel completo y lo comparten varios robots: si
dos se solapan, uno le baja el túnel al otro.

- `en_franja()`: mientras existan los otros robots, usan la VPN a las horas de
  BASES_SAP_FRANJAS_BLOQUEADAS (00:00, 05:00, 06:00, 12:00 y 12:30 en Bogotá).
  A 15 minutos o menos de esas horas, antes o después, este robot no corre
  (contrato §7.2, regla 5). `inicio_hueco()` busca cuándo cabe una ejecución larga
  (el histórico de ventas) entre una franja y la siguiente.
- `Bloqueo`: un solo proceso de este robot a la vez (la revisión de cada minuto,
  la nocturna, la del domingo o una manual), con el archivo robot/state/robot.lock.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

import config
from config import BOGOTA
from registro import obtener

log = obtener("bloqueo")

MINUTOS_DIA = 24 * 60


def _minutos(franja: str) -> int | None:
    try:
        hora, minuto = (int(p) for p in franja.strip().split(":"))
    except ValueError:
        return None
    if not (0 <= hora < 24 and 0 <= minuto < 60):
        return None
    return hora * 60 + minuto


def en_franja(momento: datetime, franjas: Iterable[str], margen_min: int = 15) -> str | None:
    """La hora bloqueada ("12:00") si `momento` está a `margen_min` minutos o menos de ella.

    Cuenta la hora de Bogotá (sin zona, se toma como de Bogotá) y cruza la
    medianoche: las 23:50 están a 10 minutos de las 00:00. Las horas inválidas
    se ignoran (Config.validar ya las reporta).
    """
    if momento.tzinfo is not None:
        momento = momento.astimezone(BOGOTA)
    actual = momento.hour * 60 + momento.minute + (momento.second + momento.microsecond / 1e6) / 60
    for franja in franjas:
        centro = _minutos(franja)
        if centro is None:
            continue
        distancia = abs(actual - centro) % MINUTOS_DIA
        if min(distancia, MINUTOS_DIA - distancia) <= margen_min:
            return f"{centro // 60:02d}:{centro % 60:02d}"
    return None



def fin_de_franja(momento: datetime, franjas: Iterable[str], margen_min: int = 15) -> datetime:
    """Primer minuto en que `momento` ya no está en ninguna franja (él mismo si no lo está).

    Salta franjas seguidas: a las 11:50, con las 12:00 y las 12:30, da las 12:46.
    """
    if en_franja(momento, franjas, margen_min) is None:
        return momento
    siguiente = momento.replace(second=0, microsecond=0)
    for _ in range(MINUTOS_DIA):
        siguiente += timedelta(minutes=1)
        if en_franja(siguiente, franjas, margen_min) is None:
            return siguiente
    raise ValueError("Todas las horas del día están bloqueadas: revisa BASES_SAP_FRANJAS_BLOQUEADAS.")


def proxima_franja(momento: datetime, franjas: Iterable[str], margen_min: int = 15) -> datetime | None:
    """Primer minuto entero, desde `momento` (incluido), que está en una franja.

    Es la hora de la franja menos el margen: con las 05:00 y 15 minutos, las 04:45. None
    si no hay ninguna franja en las 24 horas siguientes (BASES_SAP_FRANJAS_BLOQUEADAS vacía).
    """
    franjas = list(franjas)
    minuto = momento.replace(second=0, microsecond=0)
    if minuto < momento:
        minuto += timedelta(minutes=1)
    for _ in range(MINUTOS_DIA + 1):
        if en_franja(minuto, franjas, margen_min) is not None:
            return minuto
        minuto += timedelta(minutes=1)
    return None


def inicio_hueco(
    momento: datetime, duracion: timedelta, franjas: Iterable[str], margen_min: int = 15
) -> datetime:
    """Primer momento, desde `momento`, en que algo que dura `duracion` termina antes de la
    siguiente franja. `momento` mismo si ya cabe.

    Lo usa el histórico de ventas, que tiene la VPN arriba mucho tiempo: si no alcanza a
    terminar antes de la siguiente franja, espera a que esa franja pase y vuelve a probar.
    Lanza ValueError si ningún hueco del día es tan largo.
    """
    franjas = list(franjas)
    inicio = fin_de_franja(momento, franjas, margen_min)
    while inicio - momento <= timedelta(days=1):
        siguiente = proxima_franja(inicio, franjas, margen_min)
        if siguiente is None or inicio + duracion < siguiente:
            return inicio
        inicio = fin_de_franja(siguiente, franjas, margen_min)
    raise ValueError(
        f"Ningún hueco entre las franjas bloqueadas ({', '.join(franjas)}, ±{margen_min} minutos) "
        f"dura {int(duracion.total_seconds() // 60)} minutos."
    )


class Bloqueo:
    """Candado de archivo: se crea en exclusiva con el pid y la hora de Bogotá.

    Un candado con más de `vigencia` (por la hora que tiene escrita o, si no se
    puede leer, por la del archivo) es de un proceso que murió sin soltarlo: se
    avisa en el log, se borra y se toma.

    Como contexto, `with Bloqueo() as tomado:` intenta tomarlo sin esperar y
    lo suelta al salir si lo tomó.
    """

    def __init__(
        self,
        ruta: Path | None = None,
        *,
        vigencia: timedelta = timedelta(hours=3),
        reloj: Callable[[], datetime] = config.ahora,
    ) -> None:
        # config.STATE_DIR se lee aquí (no al importar) para que las pruebas lo cambien.
        self.ruta = Path(ruta) if ruta is not None else config.STATE_DIR / "robot.lock"
        self.vigencia = vigencia
        self.reloj = reloj
        self._marca: dict[str, Any] | None = None  # lo que escribimos, si lo tenemos

    def __enter__(self) -> bool:
        return self.tomar()

    def __exit__(self, *exc: object) -> None:
        self.soltar()

    def tomar(
        self,
        esperar: timedelta = timedelta(0),
        intervalo_s: float = 10,
        dormir: Callable[[float], None] = time.sleep,
    ) -> bool:
        """True si lo tomó. Si está ocupado, revisa cada `intervalo_s` hasta `esperar`."""
        limite = esperar.total_seconds()
        esperado = 0.0
        while True:
            if self._crear():
                return True
            if self._vencido():
                continue  # se borró: se intenta crear otra vez enseguida
            if esperado >= limite:
                return False
            pausa = min(intervalo_s, limite - esperado)
            dormir(pausa)
            esperado += pausa

    def soltar(self) -> None:
        """Borra el candado solo si sigue siendo nuestro (mismo pid y hora)."""
        if self._marca is None:
            return
        if self.dueno() == self._marca:
            try:
                self.ruta.unlink()
            except FileNotFoundError:
                pass
        else:
            log.warning("El candado %s ya no era de este proceso; no se borra.", self.ruta)
        self._marca = None

    def renovar(self) -> bool:
        """Pone la hora actual en el candado, si sigue siendo nuestro. True si lo renovó.

        Para una ejecución que puede pasar de la `vigencia` (el histórico de ventas): sin
        renovarlo, otro proceso lo daría por vencido y correría a la vez. Se escribe en un
        temporal que se renombra, así que nadie lee un candado a medias; si no se puede
        (en Windows, otro proceso lo tiene abierto en ese instante), queda en el log y se
        sigue con la marca anterior.
        """
        if self._marca is None or self.dueno() != self._marca:
            return False
        marca = {"pid": self._marca["pid"], "tomado_en": self.reloj().isoformat()}
        temporal = self.ruta.with_name(f".{self.ruta.name}.{os.getpid()}.tmp")
        try:
            temporal.write_text(json.dumps(marca), encoding="utf-8", newline="\n")
            os.replace(temporal, self.ruta)
        except OSError as exc:
            log.warning("No se pudo renovar el candado %s: %s", self.ruta, exc)
            try:
                temporal.unlink()
            except OSError:
                pass
            return False
        self._marca = marca
        return True

    def dueno(self) -> dict[str, Any] | None:
        """Contenido del candado (pid y tomado_en), o None si no existe o no se puede leer."""
        try:
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return datos if isinstance(datos, dict) else None

    def quien(self) -> str:
        """Quién tiene el candado, para los mensajes: "pid 4242 desde 2026-10-26T02:00:05-05:00"."""
        datos = self.dueno() or {}
        return f"pid {datos.get('pid', '?')} desde {datos.get('tomado_en', '?')}"

    # ---------------------------------------------------------------- interno
    def _crear(self) -> bool:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        marca = {"pid": os.getpid(), "tomado_en": self.reloj().isoformat()}
        try:
            fd = os.open(self.ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        except PermissionError:
            # En Windows, un archivo que otro proceso está borrando da PermissionError.
            if self.ruta.exists():
                return False
            raise
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as archivo:
            json.dump(marca, archivo)
        self._marca = marca
        return True

    def _tomado_en(self, datos: dict[str, Any] | None) -> datetime | None:
        try:
            momento = datetime.fromisoformat(str((datos or {})["tomado_en"]))
            return momento if momento.tzinfo else momento.replace(tzinfo=BOGOTA)
        except (KeyError, ValueError):
            pass
        try:
            return datetime.fromtimestamp(self.ruta.stat().st_mtime, BOGOTA)
        except OSError:
            # Ya no está, o en Windows otro proceso lo está borrando (PermissionError).
            return None

    def _vencido(self) -> bool:
        """True si había un candado vencido y se borró (o si ya no estaba)."""
        datos = self.dueno()
        tomado_en = self._tomado_en(datos)
        if tomado_en is None:
            return True  # lo soltaron mientras tanto
        edad = self.reloj() - tomado_en
        if edad <= self.vigencia:
            return False
        log.warning(
            "Candado vencido en %s (pid %s, tomado hace %s): se borra y se toma.",
            self.ruta, (datos or {}).get("pid", "?"), str(edad).split(".")[0],
        )
        # Se relee justo antes de borrar para no llevarse uno que otro proceso acaba de crear.
        if self.dueno() == datos:
            try:
                self.ruta.unlink()
            except FileNotFoundError:
                pass
        return True
