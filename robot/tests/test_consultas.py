from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import config
import consultas
from config import ConfigError, EmpresaHana
from esquema import PARTES


def _escribir(ruta: Path, texto: str) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def test_el_archivo_del_esquema_gana_sobre_el_comun():
    base = config.QUERIES_DIR  # tmp_path/queries (conftest)
    comun = _escribir(base / "maestros" / "precios.sql", "SELECT 1 FROM DUMMY")
    propio = _escribir(base / "maestros" / "SEGUREX" / "precios.sql", "SELECT 2 FROM DUMMY")
    assert consultas.ruta_consulta("maestros/precios.sql", "SEGUREX") == propio
    assert consultas.ruta_consulta("maestros/precios.sql", "HBT_SDERIVADOS") == comun


def test_solo_hay_archivo_del_esquema():
    propio = _escribir(config.QUERIES_DIR / "maestros" / "SEGUREX" / "precios.sql", "SELECT 2")
    assert consultas.ruta_consulta("maestros/precios.sql", "SEGUREX") == propio
    with pytest.raises(ConfigError, match="precios.sql"):
        consultas.ruta_consulta("maestros/precios.sql", "HBT_SDERIVADOS")


def test_cartera_tambien_tiene_archivo_por_esquema():
    propio = _escribir(config.QUERIES_DIR / "cartera" / "SEGUREX" / "cartera.sql", "SELECT 2")
    otro = _escribir(config.QUERIES_DIR / "cartera" / "HBT_SDERIVADOS" / "cartera.sql", "SELECT 3")
    assert consultas.ruta_consulta("cartera/cartera.sql", "SEGUREX") == propio
    assert consultas.ruta_consulta("cartera/cartera.sql", "HBT_SDERIVADOS") == otro


def test_cartera_de_un_esquema_sin_consulta_falla_claro_aunque_haya_otra_comun():
    _escribir(config.QUERIES_DIR / "cartera" / "cartera.sql", "SELECT 1")
    _escribir(config.QUERIES_DIR / "cartera" / "SEGUREX" / "cartera.sql", "SELECT 2")
    with pytest.raises(ConfigError, match="No hay consulta de cartera para el esquema SEGUREX_PRUEBA") as exc:
        consultas.ruta_consulta("cartera/cartera.sql", "SEGUREX_PRUEBA")
    assert "robot/queries/cartera/SEGUREX_PRUEBA/cartera.sql" in str(exc.value)


def test_fuera_de_maestros_y_cartera_no_hay_archivo_por_esquema():
    _escribir(config.QUERIES_DIR / "diagnostico" / "SEGUREX" / "listas_precios.sql", "SELECT 2")
    comun = _escribir(config.QUERIES_DIR / "diagnostico" / "listas_precios.sql", "SELECT 1")
    assert consultas.ruta_consulta("diagnostico/listas_precios.sql", "SEGUREX") == comun


def test_falta_la_consulta():
    with pytest.raises(ConfigError, match="clientes.sql"):
        consultas.ruta_consulta("maestros/clientes.sql", "SEGUREX")


def test_leer_quita_el_punto_y_coma_final():
    _escribir(config.QUERIES_DIR / "maestros" / "marcas.sql",
              '﻿-- marcas\nSELECT T0."FirmCode" AS "codigo"\nFROM "OMRC" T0;\n\n  ')
    assert consultas.leer("maestros/marcas.sql", "SEGUREX") == (
        '-- marcas\nSELECT T0."FirmCode" AS "codigo"\nFROM "OMRC" T0'
    )


def test_leer_sin_punto_y_coma_queda_igual():
    _escribir(config.QUERIES_DIR / "maestros" / "marcas.sql", "SELECT 1 FROM DUMMY\n")
    assert consultas.leer("maestros/marcas.sql", "SEGUREX") == "SELECT 1 FROM DUMMY"


SQL = 'SELECT T0."CardCode" AS "codigo" FROM "OCRD" T0\nORDER BY T0."CardCode"'


def test_sql_cambios():
    assert consultas.sql_cambios(SQL) == (
        f'SELECT X.* FROM (\n{SQL}\n) X WHERE X."actualizado_en_sap" >= ?'
    )


def test_sql_por_socios():
    assert consultas.sql_por_socios(SQL, 3) == (
        f'SELECT X.* FROM (\n{SQL}\n) X WHERE X."codigo_socio" IN (?, ?, ?)'
    )
    with pytest.raises(ValueError):
        consultas.sql_por_socios(SQL, 0)


def test_sql_lista_precios():
    assert consultas.sql_lista_precios(SQL, 1) == (
        f'SELECT X.* FROM (\n{SQL}\n) X WHERE X."lista_codigo" = 1'
    )


def _empresa(lista: int | None, esquema: str = "SEGUREX") -> EmpresaHana:
    return EmpresaHana("SGX", "usuario", "clave", esquema, lista_precios=lista)


def test_leer_parte_de_precios_filtra_por_el_numero_de_lista():
    _escribir(config.QUERIES_DIR / "maestros" / "precios.sql", "SELECT 1 FROM DUMMY")
    assert consultas.leer_parte(PARTES["precios"], _empresa(7)) == (
        'SELECT X.* FROM (\nSELECT 1 FROM DUMMY\n) X WHERE X."lista_codigo" = 7'
    )


def test_leer_parte_de_precios_sin_lista_falla_diciendo_que_variable_poner():
    _escribir(config.QUERIES_DIR / "maestros" / "precios.sql", "SELECT 1 FROM DUMMY")
    with pytest.raises(ConfigError, match="HANA_SGX_LISTA_PRECIOS"):
        consultas.leer_parte(PARTES["precios"], _empresa(None))


def test_leer_parte_de_las_demas_partes_queda_igual():
    _escribir(config.QUERIES_DIR / "maestros" / "marcas.sql", "SELECT 1 FROM DUMMY")
    assert consultas.leer_parte(PARTES["marcas"], _empresa(None)) == "SELECT 1 FROM DUMMY"


def test_sql_contar():
    assert consultas.sql_contar(SQL) == f"SELECT COUNT(*) FROM (\n{SQL}\n) X"


def test_un_comentario_al_final_no_se_come_el_cierre():
    sql = "SELECT 1 FROM DUMMY\n-- fin"
    assert consultas.sql_contar(sql).endswith("-- fin\n) X")


@pytest.mark.parametrize("desde, esperado", [
    ("2026-10-23T09:58:00-05:00", datetime(2026, 10, 23, 9, 58, 0)),
    ("2026-10-23T14:58:00Z", datetime(2026, 10, 23, 9, 58, 0)),
    ("2026-10-23T14:58:00+00:00", datetime(2026, 10, 23, 9, 58, 0)),
    ("2026-10-24T02:30:15+00:00", datetime(2026, 10, 23, 21, 30, 15)),
    (None, None),
])
def test_desde_a_parametro(desde, esperado):
    resultado = consultas.desde_a_parametro(desde)
    assert resultado == esperado
    assert resultado is None or resultado.tzinfo is None


def test_desde_invalido():
    with pytest.raises(ValueError, match="desde"):
        consultas.desde_a_parametro("ayer")


def test_trozos():
    codigos = [f"C{i}" for i in range(1201)]
    partes = consultas.trozos(codigos)
    assert [len(p) for p in partes] == [500, 500, 201]
    assert [c for p in partes for c in p] == codigos
    assert consultas.trozos([]) == []
    assert consultas.trozos(["a", "b", "c"], 2) == [["a", "b"], ["c"]]
    with pytest.raises(ValueError):
        consultas.trozos(codigos, 0)
