from __future__ import annotations

from datetime import date
from pathlib import Path

import catalogo
import extraccion
from fake_hana import revisar_fases

HOY = date(2026, 10, 26)


def _correr(e, empresas=("SGX", "SDC")) -> list:
    c = catalogo.Catalogo(e.cfg, HOY)
    fallos = extraccion.sesion(e.cfg, list(empresas), c, robot_vpn=e.vpn, conectar=e.hana.conectar)
    return fallos + c.escribir()


def _lineas(ruta: Path) -> list[str]:
    return ruta.read_text(encoding="utf-8-sig").splitlines()


def test_salida_por_empresa_y_consulta(escenario):
    e = escenario
    assert _correr(e) == []
    for empresa in ("SGX", "SDC"):
        base = e.csv_dir / "_CATALOGO" / empresa
        assert sorted(p.name for p in base.iterdir()) == [
            "campos_usuario", "columnas", "tablas", "tablas_usuario",
        ]
        for nombre in ("campos_usuario", "columnas", "tablas", "tablas_usuario"):
            assert [p.name for p in (base / nombre).iterdir()] == ["2026-10-26.csv"]
    tablas = _lineas(e.csv_dir / "_CATALOGO" / "SGX" / "tablas" / "2026-10-26.csv")
    assert tablas == [
        "TABLE_NAME;RECORD_COUNT;TABLE_SIZE;IS_COLUMN_TABLE",
        "OCRD;120;4096;TRUE",
        "ADOC;9000000;2147483648;TRUE",
    ]
    revisar_fases(e.linea)


def test_columnas_solo_de_las_tablas_que_lee_el_robot(escenario):
    e = escenario
    assert _correr(e, ("SGX",)) == []
    lineas = _lineas(e.csv_dir / "_CATALOGO" / "SGX" / "columnas" / "2026-10-26.csv")
    assert lineas[0] == "TABLE_NAME;POSITION;COLUMN_NAME;DATA_TYPE_NAME;LENGTH;SCALE;IS_NULLABLE"
    assert [l.split(";")[0] for l in lineas[1:]] == ["OCRD", "OINV", "@HBT_CONFIG", "USR5"]


def test_tablas_leidas_salen_de_las_consultas(escenario):
    tablas = catalogo.tablas_leidas()
    # MAESTROS, CARTERA, diagnóstico, archivo y catálogo de SAP (CUFD, OUTB).
    for tabla in ("OCRD", "CRD1", "OCPR", "OITM", "OITB", "OMRC", "OPLN", "ITM1", "OSLP",
                  "OCRG", "OCTG", "@HBT_MUNICIPIO", "JDT1", "OINV", "ORIN",
                  "USR5", "ACR1", "ACRD", "ADOC", "OUSR", "OHEM", "ORTT", "NNM1", "CUFD", "OUTB"):
        assert tabla in tablas, tabla
    # Las vistas del diccionario de HANA van con esquema y no cuentan.
    assert not tablas & {"SYS", "TABLES", "TABLE_COLUMNS", "M_TABLES"}
    assert catalogo.es_tabla_del_robot("@HBT_LO_QUE_SEA", tablas)
    assert not catalogo.es_tabla_del_robot("ZZZ_AJENA", tablas)


def test_una_consulta_que_falla_no_detiene_las_demas(escenario):
    e = escenario
    e.hana.partes_que_fallan.add(("SGX", "catalogo/tablas"))
    fallos = _correr(e, ("SGX",))
    assert fallos == [("CATALOGO", "SGX tablas: Error ejecutando la consulta "
                                   "'SGX catálogo tablas'; revisa robot/logs/robot.log.")]
    base = e.csv_dir / "_CATALOGO" / "SGX"
    assert not (base / "tablas").exists()
    assert (base / "columnas" / "2026-10-26.csv").is_file()


def test_retencion_de_52_semanas(escenario):
    e = escenario
    vieja = e.csv_dir / "_CATALOGO" / "SGX" / "tablas" / "2025-10-01.csv"
    vieja.parent.mkdir(parents=True, exist_ok=True)
    vieja.write_text("x", encoding="utf-8")
    assert _correr(e, ("SGX",)) == []
    assert not vieja.exists()
