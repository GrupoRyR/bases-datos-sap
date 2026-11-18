"""Carga inicial de PRODUCCION (contrato §12): una corrida a mano con ventana_desde fija."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import config
import consultas
import esquema
from config import ConfigError
from fake_hana import fila, revisar_fases
from test_run_robot import _estado, _main
from trabajos import Trabajo, TrabajoInvalido, trabajo_carga_produccion

HOY = date(2026, 10, 26)
PRODUCCION = Path(__file__).resolve().parent.parent / "queries" / "produccion"
PARTES = esquema.PARTES_POR_CONJUNTO["PRODUCCION"]
MOVIMIENTO = [p for p in PARTES if esquema.PARTES[p].columna_ventana]


# --- consultas.sql_desde_fecha -------------------------------------------------------


@pytest.mark.parametrize("parte, veces", [
    ("produccion_terminado", 1), ("produccion_carga_planta", 1), ("produccion_costos", 2),
])
def test_cambia_la_ventana_de_la_consulta_por_la_fecha_pedida(parte: str, veces: int):
    sql = (PRODUCCION / f"{parte}.sql").read_text(encoding="utf-8")
    cambiada = consultas.sql_desde_fecha(sql, "2026-08-01")
    assert consultas.EXPRESION_VENTANA not in cambiada
    assert cambiada.count(">= TO_DATE('2026-08-01', 'YYYY-MM-DD')") == veces
    # Solo cambia el primer día: el resto del archivo queda igual.
    assert cambiada == sql.replace(consultas.EXPRESION_VENTANA, "TO_DATE('2026-08-01', 'YYYY-MM-DD')")


def test_la_expresion_es_la_misma_con_que_hana_calcula_la_ventana():
    assert consultas.SQL_VENTANA == f"SELECT {consultas.EXPRESION_VENTANA} FROM DUMMY"


def test_consulta_sin_la_expresion_de_la_ventana_no_corre():
    with pytest.raises(ConfigError, match="ventana"):
        consultas.sql_desde_fecha("SELECT 1 FROM DUMMY", "2026-08-01")


@pytest.mark.parametrize("dia", ["2026-8-1", "2026-08-01'; --", "ayer"])
def test_fecha_invalida_no_entra_a_la_consulta(dia: str):
    with pytest.raises(ValueError):
        consultas.sql_desde_fecha(f"SELECT {consultas.EXPRESION_VENTANA} FROM DUMMY", dia)


# --- trabajos.trabajo_carga_produccion ------------------------------------------------


def test_trabajo_de_la_carga_es_la_completa_de_produccion_de_segurex_con_fecha_fija():
    assert trabajo_carga_produccion("2026-08-01", HOY) == Trabajo(
        empresa="SGX", conjunto="PRODUCCION", tipo="completa",
        partes={p: "todo" for p in PARTES}, ventana_fija="2026-08-01",
    )


@pytest.mark.parametrize("desde", ["2025-12-31", "2026-10-27", "2026-13-01", "01/08/2026", ""])
def test_desde_fuera_de_lo_que_acepta_la_api_falla(desde: str):
    # La API acepta ventana_desde de PRODUCCION entre 2026-01-01 y mañana (contrato §12);
    # el robot no deja pedir días que todavía no pasaron.
    with pytest.raises(TrabajoInvalido, match="--desde"):
        trabajo_carga_produccion(desde, HOY)


# --- run_robot.py --carga-produccion ------------------------------------------------


def test_carga_inicial_envia_produccion_desde_la_fecha_pedida(entorno, correos):
    e = entorno
    # Una fila anterior a la ventana de HANA (24/09) pero dentro de la pedida.
    e.hana.datos["SGX"]["produccion_costos"].append(fila("produccion_costos", 3, fecha=date(2026, 8, 15)))
    assert _main(e, "--carga-produccion", "--desde", "2026-08-01") == 0
    revisar_fases(e.linea)
    [corrida] = e.servidor.corridas.values()
    assert (corrida.conjunto, corrida.empresa, corrida.tipo, corrida.estado) == (
        "PRODUCCION", "SGX", "completa", "cerrada")
    assert corrida.ventana_desde == "2026-08-01"
    assert corrida.conteo_sap == corrida.total_filas() == {
        p: 3 if p == "produccion_costos" else 2 for p in PARTES
    }
    # La fecha no se pide a HANA: va en la consulta, y el conteo usa la misma consulta.
    assert not e.hana.de("SGX", "ventana")
    for parte in MOVIMIENTO:
        for paso in e.hana.de("SGX", parte=parte):
            assert "TO_DATE('2026-08-01', 'YYYY-MM-DD')" in paso.sql
            assert consultas.EXPRESION_VENTANA not in paso.sql
    assert not e.hana.de("SDC")
    assert correos == []
    estado = _estado()
    assert (estado["estado"], estado["modo"], estado["trabajos"]) == ("OK", "carga produccion", ["PRODUCCION SGX"])
    assert (e.csv_dir / "PRODUCCION" / "SGX" / "produccion_costos" / "2026-10-26_0200.csv").is_file()


def test_carga_inicial_con_una_fila_anterior_a_la_fecha_pedida_no_envia(entorno, correos):
    e = entorno
    e.hana.datos["SGX"]["produccion_terminado"].append(fila("produccion_terminado", 3, fecha=date(2026, 7, 31)))
    assert _main(e, "--carga-produccion", "--desde", "2026-08-01") == 1
    [corrida] = e.servidor.corridas.values()
    assert (corrida.estado, corrida.lotes) == ("fallida", {})
    assert "anterior a ventana_desde 2026-08-01" in correos[0][0][1]


@pytest.mark.parametrize("argumentos", [
    ["--carga-produccion"],
    ["--completa", "--desde", "2026-08-01"],
    ["--carga-produccion", "--desde", "2026-08-01", "--empresa", "SDC"],
    ["--carga-produccion", "--desde", "2025-12-31"],
])
def test_argumentos_invalidos_no_corren(entorno, argumentos):
    with pytest.raises(SystemExit) as exc:
        _main(entorno, *argumentos)
    assert exc.value.code == 2
    assert entorno.servidor.corridas == {} and entorno.hana.ejecutadas == []
    assert not (config.STATE_DIR / "ultima_ejecucion.json").exists()
