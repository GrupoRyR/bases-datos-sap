"""Revisión de robot/queries/produccion (contrato §12): columnas, ventana y lógica.

Las consultas de movimiento se corren en SQLite, con las funciones de HANA que usan
(ADD_DAYS, DAYOFMONTH) como funciones propias y `CAST(x AS DATE)` cambiado por
`DATE(x)`, para probar los filtros, la ventana, los conceptos y los redondeos.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

import consultas

PRODUCCION = Path(__file__).resolve().parent.parent / "queries" / "produccion"
VALIDAR = "VALIDAR CON DATOS REALES"
# Expresión del primer día de la ventana: la misma de VENTAS (consultas.SQL_VENTANA).
VENTANA = "ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))"

# Columnas de cada parte en el orden del contrato §12.
COLUMNAS = {
    "produccion_terminado": [
        "doc_entry", "numero_documento", "linea", "fecha", "grupo", "familia",
        "codigo_articulo", "articulo", "nro_ot", "posicion", "cantidad", "valor",
    ],
    "produccion_carga_planta": [
        "fecha", "area", "linea_producto", "linea_negocio", "etapa", "puesto_trabajo",
        "nro_ot", "posicion", "operacion", "codigo_articulo", "nombre_articulo", "unidad",
        "unidades", "unidades_no_conformes", "horas", "almacen", "estado_ot",
    ],
    "produccion_costos": [
        "fecha", "concepto", "area", "linea_producto", "linea_negocio", "etapa",
        "material_consumido", "grupo_material", "codigo_material", "nro_ot", "posicion",
        "codigo_articulo", "nombre_articulo", "puesto_trabajo", "costo",
    ],
    "produccion_despiece": ["padre", "hijo", "cantidad", "merma"],
    "produccion_rutas": [
        "codigo_articulo", "operacion", "area", "puesto", "tiempo", "cantidad_base",
        "factor_merma",
    ],
    "produccion_costeo_teorico": [
        "codigo_articulo", "articulo", "familia", "posiciones", "cantidad", "material_soll",
        "fabricacion_soll", "total_soll", "total_ist",
    ],
}
MOVIMIENTO = ("produccion_terminado", "produccion_carga_planta", "produccion_costos")
MAESTROS = ("produccion_despiece", "produccion_rutas", "produccion_costeo_teorico")
MONTOS = {
    "produccion_terminado": ("valor",),
    "produccion_costeo_teorico": ("material_soll", "fabricacion_soll", "total_soll", "total_ist"),
}


def _texto(parte: str) -> str:
    return (PRODUCCION / f"{parte}.sql").read_text(encoding="utf-8")


def _codigo(parte: str) -> str:
    return re.sub(r"--[^\n]*", "", _texto(parte))


def _alias_externos(parte: str) -> list[str]:
    """Alias del SELECT de afuera: sin las subconsultas entre paréntesis."""
    codigo = _codigo(parte)
    nivel, afuera = 0, []
    for caracter in codigo:
        if caracter == "(":
            nivel += 1
        elif caracter == ")":
            nivel -= 1
        elif nivel == 0:
            afuera.append(caracter)
    texto = "".join(afuera)
    select = re.search(r"\bSELECT\b(.*?)\bFROM\b", texto, flags=re.DOTALL)
    assert select, parte
    return re.findall(r'\bAS\s+"([^"]+)"', select.group(1))


def test_hay_una_consulta_por_parte():
    assert sorted(p.stem for p in PRODUCCION.glob("*.sql")) == sorted(COLUMNAS)


@pytest.mark.parametrize("parte", list(COLUMNAS))
def test_alias_son_las_columnas_del_contrato_en_su_orden(parte: str):
    assert _alias_externos(parte) == COLUMNAS[parte]


@pytest.mark.parametrize("parte", list(COLUMNAS))
def test_sin_with_ni_textos_vacios_ni_quien_reporto(parte: str):
    codigo = _codigo(parte)
    # El robot la envuelve en SELECT COUNT(*) FROM (...): un WITH ahí no es seguro.
    assert not re.match(r"\s*WITH\b", codigo, re.IGNORECASE)
    # Los textos vacíos de las originales llegan NULL (contrato §12).
    assert not re.search(r"''\s+AS\b", codigo)
    assert "DisplayName" not in codigo and "Reporto" not in codigo


@pytest.mark.parametrize("parte", MOVIMIENTO)
def test_movimiento_usa_la_ventana_de_ventas_y_no_un_rango_fijo(parte: str):
    codigo = _codigo(parte)
    assert VENTANA in consultas.SQL_VENTANA
    assert codigo.count(f">= {VENTANA}") == codigo.count("<= CURRENT_DATE") >= 1
    assert "BETWEEN" not in codigo.upper()
    assert not re.search(r"'\d{4}-\d{2}-\d{2}'", codigo), "sin fechas escritas"


@pytest.mark.parametrize("parte", MAESTROS)
def test_maestros_no_filtran_por_fecha(parte: str):
    assert "CURRENT_DATE" not in _codigo(parte)


@pytest.mark.parametrize("parte, montos", MONTOS.items())
def test_montos_redondeados_a_dos_decimales(parte: str, montos: tuple[str, ...]):
    codigo = _codigo(parte)
    for monto in montos:
        assert re.search(rf'ROUND\([^\n]*, 2\)\s+AS "{monto}"', codigo), monto


def test_linea_producto_es_la_misma_regla_en_carga_de_planta_y_costos():
    def regla(parte: str) -> str:
        m = re.search(r"CASE\s+WHEN TRIM\(COALESCE\(I.*?END\s+AS \"linea_producto\"", _codigo(parte), re.DOTALL)
        assert m, parte
        return re.sub(r"\s+", " ", m.group(0))

    assert regla("produccion_carga_planta") == regla("produccion_costos")
    assert "'Componente comun'" in regla("produccion_costos")


def test_lo_no_confirmado_esta_marcado():
    for parte in ("produccion_terminado", "produccion_carga_planta", "produccion_costos",
                  "produccion_despiece", "produccion_rutas"):
        assert VALIDAR in _texto(parte), parte


# --- Las consultas de movimiento en SQLite -------------------------------------------


def _a_sqlite(sql: str) -> str:
    return re.sub(r"CAST\(([^()]*) AS DATE\)", r"DATE(\1)", sql)


def _conexion() -> tuple[sqlite3.Connection, date]:
    con = sqlite3.connect(":memory:")
    con.create_function("ADD_DAYS", 2, lambda d, n: (date.fromisoformat(d) + timedelta(days=n)).isoformat())
    con.create_function("DAYOFMONTH", 1, lambda d: date.fromisoformat(d).day)
    hoy = date.fromisoformat(con.execute("SELECT CURRENT_DATE").fetchone()[0])
    con.executescript("""
        CREATE TABLE "DUMMY" ("X" TEXT); INSERT INTO "DUMMY" VALUES ('X');
        CREATE TABLE "OITM" ("ItemCode" TEXT, "ItmsGrpCod" INT, "U_GSP_FAMILIA" TEXT);
        CREATE TABLE "OITB" ("ItmsGrpCod" INT, "ItmsGrpNam" TEXT);
        CREATE TABLE "OIGN" ("DocEntry" INT, "DocNum" INT, "DocDate" TEXT);
        CREATE TABLE "IGN1" ("DocEntry" INT, "LineNum" INT, "ItemCode" TEXT, "Dscription" TEXT,
            "U_beas_belnrid" INT, "U_beas_belposid" INT, "Quantity" REAL, "LineTotal" REAL);
        CREATE TABLE "OIGE" ("DocEntry" INT, "DocDate" TEXT);
        CREATE TABLE "IGE1" ("DocEntry" INT, "LineNum" INT, "ItemCode" TEXT, "Dscription" TEXT,
            "U_beas_belnrid" INT, "U_beas_belposid" INT, "LineTotal" REAL);
        CREATE TABLE "BEAS_APLATZ" ("APLATZ_ID" TEXT, "GRUPPE" TEXT, "BEZ" TEXT);
        CREATE TABLE "BEAS_FTPOS" ("BELNR_ID" INT, "BELPOS_ID" INT, "ItemCode" TEXT, "ItemName" TEXT,
            "GRUPPE" TEXT, "ME_VERBRAUCH" TEXT, "WhsCode" TEXT, "ABGKZ" TEXT);
        CREATE TABLE "BEAS_ARBZEIT" ("DocDate" TEXT, "APLATZ_ID" TEXT, "BELNR_ID" INT,
            "BELPOS_ID" INT, "POS_ID" INT, "MENGE_GUT" REAL, "MENGE_SCHLECHT" REAL, "ZEIT" REAL,
            "CANCEL" INT, "PCOSTVK" REAL, "KOSTEN_GK" REAL, "KOSTEN_VK" REAL, "DisplayName" TEXT);
        INSERT INTO "OITB" VALUES (1, 'PRODUCTO TERMINADO SEGUREX'), (2, 'PIEZAS'), (3, 'MATERIA PRIMA');
        INSERT INTO "OITM" VALUES ('PT1', 1, 'MEGA'), ('PT2', 1, ''), ('PZ1', 2, 'PIEZAS EN NEGRO'),
            ('MP1', 3, NULL);
        INSERT INTO "BEAS_APLATZ" VALUES ('P1', 'PRENSAS', 'PRENSA 1'), ('E1', 'ENSAMBLE', 'ENSAMBLE A');
        -- OT 10: la pieza PZ1 (nombre con JUPITER); OT 20: la cerradura PT1.
        INSERT INTO "BEAS_FTPOS" VALUES
            (10, 1, 'PZ1', 'MANIJA JUPITER OPEN', 'PIEZAS EN NEGRO', 'UN', 'PP', 'N'),
            (20, 1, 'PT1', 'CERRADURA MEGA IZQ', '', 'UN', 'PT', 'J');
    """)
    return con, hoy


def _filas(con: sqlite3.Connection, parte: str) -> list[dict]:
    cursor = con.execute(_a_sqlite(_texto(parte)))
    nombres = [d[0] for d in cursor.description]
    return [dict(zip(nombres, f)) for f in cursor.fetchall()]


def test_terminado_trae_una_fila_por_linea_dentro_de_la_ventana():
    con, hoy = _conexion()
    inicio = date.fromisoformat(con.execute(f"SELECT {VENTANA}").fetchone()[0])
    con.executemany('INSERT INTO "OIGN" VALUES (?, ?, ?)', [
        (1, 501, hoy.isoformat()), (2, 502, inicio.isoformat()),
        (3, 503, (inicio - timedelta(days=1)).isoformat()),  # antes de la ventana: no sale
    ])
    con.executemany('INSERT INTO "IGN1" VALUES (?, ?, ?, ?, ?, ?, ?, ?)', [
        (1, 0, "PT1", "Cerradura", 20, 1, 4, 1000.006),
        (1, 1, "PT1", "Cerradura", 20, 1, 6, 1500.0),   # misma OT y artículo: fila aparte
        (1, 2, "PZ1", "Pieza", 10, 1, 9, 50.0),         # no es producto terminado
        (1, 3, "PT2", "Otra", 0, 0, 1, 10.0),           # sin OT
        (2, 0, "PT2", "Otra", 21, 2, 2, 300.0),         # el primer día de la ventana sí
        (3, 0, "PT1", "Cerradura", 20, 1, 1, 99.0),
    ])
    filas = _filas(con, "produccion_terminado")
    assert [(f["doc_entry"], f["linea"]) for f in filas] == [(2, 0), (1, 0), (1, 1)]
    assert filas[1]["valor"] == 1000.01 and filas[1]["familia"] == "MEGA"
    assert (filas[0]["familia"], filas[0]["grupo"]) == ("Sin familia", "PRODUCTO TERMINADO SEGUREX")
    # La suma por artículo es la de la consulta agrupada original.
    assert sum(f["cantidad"] for f in filas if f["codigo_articulo"] == "PT1") == 10


def test_carga_de_planta_excluye_anulados_y_resuelve_la_linea():
    con, hoy = _conexion()
    con.executemany('INSERT INTO "BEAS_ARBZEIT" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?)', [
        (hoy.isoformat(), "P1", 10, 1, 10, 100, 2, 90, 0, "Ana"),
        (hoy.isoformat(), "E1", 20, 1, 20, 5, 0, 30, 0, "Ana"),
        (hoy.isoformat(), "P1", 10, 1, 10, 7, 0, 60, 1, "Ana"),  # anulado
    ])
    filas = _filas(con, "produccion_carga_planta")
    assert [(f["area"], f["linea_producto"], f["etapa"], f["horas"]) for f in filas] == [
        ("ENSAMBLE", "MEGA", "Sin etapa", 0.5), ("PRENSAS", "JUPITER", "PIEZAS EN NEGRO", 1.5),
    ]
    assert filas[1]["linea_negocio"] == "PIEZAS" and filas[0]["estado_ot"] == "J"


def test_costos_trae_los_conceptos_redondeados_sin_ceros_y_con_nulos():
    con, hoy = _conexion()
    dia = hoy.isoformat()
    con.executemany('INSERT INTO "BEAS_ARBZEIT" VALUES (?, ?, ?, ?, 10, 1, 0, 60, ?, ?, ?, ?, NULL)', [
        (dia, "P1", 10, 1, 0, 100.004, 30.0, 80.0),  # MOD 100, variable 30, fijo 50
        (dia, "P1", 10, 1, 0, 0.0, 0.0, 10.0),       # solo costo fijo: los ceros no salen
        (dia, "P1", 10, 1, 1, 999.0, 1.0, 2.0),      # anulado
    ])
    con.execute('INSERT INTO "OIGE" VALUES (7, ?)', (dia,))
    con.executemany('INSERT INTO "IGE1" VALUES (7, ?, ?, ?, ?, 1, ?)', [
        (0, "MP1", "Lamina", 20, 400.126),  # comprado
        (1, "PZ1", "Manija", 20, 250.0),    # la planta la fabrica: intermedio
        (2, "MP1", "Lamina", 20, 0.0),      # costo cero: no sale
        (3, "MP1", "Lamina", 99, 50.0),     # OT que no existe: no sale (INNER JOIN)
    ])
    filas = _filas(con, "produccion_costos")
    por_concepto = {}
    for f in filas:
        por_concepto.setdefault(f["concepto"], []).append(f)
    assert sorted((c, sorted(x["costo"] for x in fs)) for c, fs in por_concepto.items()) == [
        ("Costo fijo", [10.0, 50.0]), ("Costo variable", [30.0]),
        ("Mano de obra directa", [100.0]), ("Material comprado", [400.13]),
        ("Material intermedio", [250.0]),
    ]
    transformacion = por_concepto["Mano de obra directa"][0]
    assert (transformacion["grupo_material"], transformacion["codigo_material"]) == (None, None)
    assert transformacion["material_consumido"] == "Transformacion (no es material)"
    assert (transformacion["area"], transformacion["puesto_trabajo"]) == ("PRENSAS", "PRENSA 1")
    comprado = por_concepto["Material comprado"][0]
    assert (comprado["area"], comprado["puesto_trabajo"]) == ("Material comprado (sin area)", None)
    assert (comprado["grupo_material"], comprado["codigo_material"]) == ("MATERIA PRIMA", "MP1")
    # El artículo que se fabrica es el de la posición de la OT, no el material.
    assert {(f["codigo_articulo"], f["linea_producto"]) for f in filas} == {("PZ1", "JUPITER"), ("PT1", "MEGA")}
