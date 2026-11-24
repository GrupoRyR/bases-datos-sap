"""Histórico de VENTAS (contrato §10.4): los tramos de un mes y la ventana estimada."""
from __future__ import annotations

from datetime import date

import pytest

import esquema
import extraccion
import historico
from historico import RangoInvalido, inicio_ventana_estimado, mes, tramos
from trabajos import Trabajo, trabajo_historico_ventas

VENTANA = date(2026, 10, 25)  # la ventana nocturna del 24/11/2026


def _mes(anio: int, numero: int) -> date:
    return date(anio, numero, 1)


# --- La ventana estimada (contrato §10.1) ----------------------------------------------


@pytest.mark.parametrize("hoy, inicio", [
    (date(2026, 11, 24), date(2026, 10, 25)),
    (date(2026, 10, 16), date(2026, 9, 24)),
    (date(2026, 10, 1), date(2026, 9, 24)),
    (date(2026, 3, 1), date(2026, 2, 22)),
    (date(2025, 1, 31), date(2024, 12, 25)),
])
def test_inicio_ventana_estimado_es_la_formula_del_contrato(hoy: date, inicio: date):
    assert inicio_ventana_estimado(hoy) == inicio


# --- mes: AAAA-MM -------------------------------------------------------------------


def test_mes_da_el_primer_dia():
    assert mes("2025-01") == date(2025, 1, 1)
    assert mes("2026-12") == date(2026, 12, 1)


@pytest.mark.parametrize("texto", ["2025-1", "2025-13", "2025-00", "2025-01-01", "enero", "", " 2025-01"])
def test_mes_invalido(texto: str):
    with pytest.raises(RangoInvalido, match="AAAA-MM"):
        mes(texto)


# --- tramos -----------------------------------------------------------------------


def test_meses_completos_antes_de_la_ventana():
    assert tramos(_mes(2025, 1), _mes(2025, 3), VENTANA) == [
        (date(2025, 1, 1), date(2025, 1, 31)),
        (date(2025, 2, 1), date(2025, 2, 28)),
        (date(2025, 3, 1), date(2025, 3, 31)),
    ]


def test_sin_hasta_llega_al_dia_antes_de_la_ventana():
    # El 24/11 la ventana empieza el 25/10: octubre va del 1 al 24 y noviembre no tiene tramo.
    assert tramos(_mes(2026, 9), None, VENTANA) == [
        (date(2026, 9, 1), date(2026, 9, 30)),
        (date(2026, 10, 1), date(2026, 10, 24)),
    ]


def test_hasta_el_mes_de_la_ventana_tambien_corta_el_dia_antes():
    assert tramos(_mes(2026, 10), _mes(2026, 10), VENTANA) == [(date(2026, 10, 1), date(2026, 10, 24))]


def test_hasta_antes_del_mes_de_la_ventana_da_solo_meses_completos():
    assert tramos(_mes(2026, 7), _mes(2026, 9), VENTANA) == [
        (date(2026, 7, 1), date(2026, 7, 31)),
        (date(2026, 8, 1), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 30)),
    ]


def test_febrero_bisiesto():
    assert tramos(_mes(2024, 2), _mes(2024, 2), VENTANA) == [(date(2024, 2, 1), date(2024, 2, 29))]
    assert tramos(_mes(2025, 2), _mes(2025, 2), VENTANA) == [(date(2025, 2, 1), date(2025, 2, 28))]


def test_cambio_de_anio():
    assert tramos(_mes(2025, 11), _mes(2026, 2), VENTANA) == [
        (date(2025, 11, 1), date(2025, 11, 30)),
        (date(2025, 12, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
    ]


def test_desde_enero_de_2025_hasta_la_ventana():
    lista = tramos(_mes(2025, 1), None, VENTANA)
    assert len(lista) == 22  # enero de 2025 a octubre de 2026
    assert lista[0] == (date(2025, 1, 1), date(2025, 1, 31))
    assert lista[-1] == (date(2026, 10, 1), date(2026, 10, 24))
    # Seguidos, sin huecos ni días repetidos.
    for (_, fin), (inicio, _) in zip(lista, lista[1:]):
        assert (inicio - fin).days == 1


def test_meses_anteriores_a_2025_se_permiten():
    # El contrato no fija un primer mes: enero de 2025 es el inicio previsto, no un límite.
    assert tramos(_mes(2024, 12), _mes(2025, 1), VENTANA) == [
        (date(2024, 12, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 1, 31)),
    ]


def test_ventana_que_empieza_el_primero_deja_ese_mes_sin_tramo():
    # Con la fórmula de §10.1 no pasa (cae entre el 22 y el 25), pero se maneja.
    primero = date(2026, 10, 1)
    assert tramos(_mes(2026, 8), None, primero) == [
        (date(2026, 8, 1), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 30)),
    ]
    assert tramos(_mes(2026, 9), _mes(2026, 10), primero) == [(date(2026, 9, 1), date(2026, 9, 30))]
    with pytest.raises(RangoInvalido, match="ventana nocturna"):
        tramos(_mes(2026, 10), None, primero)


@pytest.mark.parametrize("desde, hasta, texto", [
    (_mes(2026, 3), _mes(2026, 2), "--hasta"),          # al revés
    (_mes(2026, 9), _mes(2026, 11), "--hasta"),         # después del mes de la ventana
    (_mes(2026, 11), None, "ventana nocturna"),         # todo dentro de la ventana
    (_mes(2026, 11), _mes(2026, 11), "--hasta"),
    (_mes(2027, 1), None, "ventana nocturna"),
])
def test_rangos_invalidos(desde: date, hasta: date | None, texto: str):
    with pytest.raises(RangoInvalido, match=texto):
        tramos(desde, hasta, VENTANA)


def test_los_meses_van_por_su_primer_dia():
    with pytest.raises(ValueError, match="primer día"):
        tramos(date(2025, 1, 15), None, VENTANA)
    with pytest.raises(ValueError, match="primer día"):
        tramos(_mes(2025, 1), date(2025, 3, 2), VENTANA)


def test_rango_invalido_es_un_value_error():
    assert issubclass(historico.RangoInvalido, ValueError)


# --- El trabajo de un tramo y la revisión del rango -----------------------------------


def test_trabajo_de_un_tramo_es_una_corrida_historico_de_ventas_con_su_rango():
    assert trabajo_historico_ventas("SDC", date(2025, 1, 1), date(2025, 1, 31)) == Trabajo(
        empresa="SDC", conjunto="VENTAS", tipo="historico", partes={"ventas": "todo"},
        ventana_fija="2025-01-01", ventana_hasta="2025-01-31",
    )


def test_una_fila_fuera_del_rango_falla_antes_de_enviar():
    parte = esquema.PARTES["ventas"]
    posicion = parte.nombres.index("fecha_contabilizacion")

    def filas(*dias: str) -> list[list]:
        vacia = [None] * len(parte.nombres)
        return [vacia[:posicion] + [d] + vacia[posicion + 1:] for d in dias]

    extraccion.revisar_ventana(parte, filas("2025-01-01", "2025-01-31"), "2025-01-01", "2025-01-31")
    with pytest.raises(extraccion.FalloTrabajo, match="posterior a ventana_hasta 2025-01-31"):
        extraccion.revisar_ventana(parte, filas("2025-01-31", "2025-02-01"), "2025-01-01", "2025-01-31")
    with pytest.raises(extraccion.FalloTrabajo, match="anterior a ventana_desde 2025-01-01"):
        extraccion.revisar_ventana(parte, filas("2024-12-31"), "2025-01-01", "2025-01-31")
