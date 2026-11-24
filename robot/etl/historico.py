"""Histórico de VENTAS (contrato §10.4): los meses anteriores a la ventana nocturna.

Se carga una vez, a mano, mes por mes: cada mes es un tramo y cada tramo, una corrida
`historico` con su rango (`ventana_desde` el día 1, `ventana_hasta` el último día del
mes). El mes en que empieza la ventana nocturna solo llega hasta el día antes, para no
cruzarse nunca con la corrida de las 02:00.

Aquí va la planeación, sin red: los tramos y la ventana estimada con el reloj del PC.
La ventana de verdad la da HANA (consultas.SQL_VENTANA) cuando la VPN ya está arriba;
la estimada solo sirve para calcular cuánto va a durar la fase con VPN.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

_RE_MES = re.compile(r"^(\d{4})-(\d{2})$")


class RangoInvalido(ValueError):
    """Un --desde o --hasta que no deja ningún mes por cargar o va al revés."""


def inicio_ventana_estimado(hoy: date) -> date:
    """Primer día de la ventana nocturna con la fórmula del contrato §10.1, con `hoy` del PC.

    `ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))`: el día 1 del mes en curso
    menos 7 días. Solo estima cuántos tramos hay antes de subir la VPN; los tramos que se
    cargan salen de la ventana que da HANA.
    """
    return hoy - timedelta(days=6 + hoy.day)


def mes(texto: str) -> date:
    """`AAAA-MM` -> el primer día de ese mes."""
    m = _RE_MES.match(texto or "")
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise RangoInvalido(f"El mes debe ser AAAA-MM (por ejemplo 2025-01); llegó {texto!r}.")
    return date(int(m.group(1)), int(m.group(2)), 1)


def _mes_siguiente(dia: date) -> date:
    return date(dia.year + dia.month // 12, dia.month % 12 + 1, 1)


def tramos(desde_mes: date, hasta_mes: date | None, inicio_ventana: date) -> list[tuple[date, date]]:
    """Un tramo (primer día, último día) por mes, de `desde_mes` a `hasta_mes`.

    Sin `hasta_mes`, el último es el mes en que empieza la ventana nocturna. Ese mes va
    solo hasta el día antes de `inicio_ventana`; si la ventana empieza el día 1, ese mes
    no tiene tramo. Los meses van por su primer día. Lanza RangoInvalido si `hasta_mes`
    es posterior al mes de la ventana, si va antes de `desde_mes` o si no queda ningún
    día por cargar.
    """
    for dia in (desde_mes, hasta_mes):
        if dia is not None and dia.day != 1:
            raise ValueError(f"Los meses del histórico van por su primer día; llegó {dia}.")
    ultimo_dia = inicio_ventana - timedelta(days=1)
    mes_ventana = inicio_ventana.replace(day=1)
    if hasta_mes is not None and hasta_mes > mes_ventana:
        raise RangoInvalido(
            f"--hasta {hasta_mes:%Y-%m} es posterior al mes en que empieza la ventana nocturna "
            f"({inicio_ventana}): esos días los carga la corrida de las 02:00."
        )
    if hasta_mes is not None and desde_mes > hasta_mes:
        raise RangoInvalido(f"--desde {desde_mes:%Y-%m} es posterior a --hasta {hasta_mes:%Y-%m}.")
    if desde_mes > ultimo_dia:
        raise RangoInvalido(
            f"--desde {desde_mes:%Y-%m} ya está dentro de la ventana nocturna (empieza el "
            f"{inicio_ventana}): no hay días por cargar."
        )
    ultimo_mes = hasta_mes or mes_ventana
    lista: list[tuple[date, date]] = []
    actual = desde_mes
    while actual <= ultimo_mes:
        siguiente = _mes_siguiente(actual)
        fin = min(siguiente - timedelta(days=1), ultimo_dia)
        if fin >= actual:
            lista.append((actual, fin))
        actual = siguiente
    return lista
