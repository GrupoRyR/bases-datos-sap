from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
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


def test_cartera_es_un_solo_archivo_para_cualquier_esquema():
    comun = _escribir(config.QUERIES_DIR / "cartera" / "cartera.sql", "SELECT 1")
    _escribir(config.QUERIES_DIR / "cartera" / "SEGUREX" / "cartera.sql", "SELECT 2")
    for esquema in ("SEGUREX", "HBT_SDERIVADOS", "SEGUREX_PRUEBA"):
        assert consultas.ruta_consulta("cartera/cartera.sql", esquema) == comun


def test_fuera_de_maestros_no_hay_archivo_por_esquema():
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


def test_sql_cuentas():
    assert consultas.sql_cuentas(SQL, ("13050505", "13051005")) == (
        f'SELECT X.* FROM (\n{SQL}\n) X WHERE X."Cuenta visible" IN (\'13050505\', \'13051005\')'
    )


def _empresa(
    lista: int | None, esquema: str = "SEGUREX", cuentas: tuple[str, ...] = ("13050505",)
) -> EmpresaHana:
    return EmpresaHana("SGX", "usuario", "clave", esquema, lista_precios=lista, cuentas_cartera=cuentas)


def test_leer_parte_de_precios_filtra_por_el_numero_de_lista():
    _escribir(config.QUERIES_DIR / "maestros" / "precios.sql", "SELECT 1 FROM DUMMY")
    assert consultas.leer_parte(PARTES["precios"], _empresa(7)) == (
        'SELECT X.* FROM (\nSELECT 1 FROM DUMMY\n) X WHERE X."lista_codigo" = 7'
    )


def test_leer_parte_de_precios_sin_lista_falla_diciendo_que_variable_poner():
    _escribir(config.QUERIES_DIR / "maestros" / "precios.sql", "SELECT 1 FROM DUMMY")
    with pytest.raises(ConfigError, match="HANA_SGX_LISTA_PRECIOS"):
        consultas.leer_parte(PARTES["precios"], _empresa(None))


def test_leer_parte_de_cartera_filtra_por_las_cuentas_de_la_empresa():
    _escribir(config.QUERIES_DIR / "cartera" / "cartera.sql", "SELECT 1 FROM DUMMY")
    assert consultas.leer_parte(PARTES["cartera"], _empresa(None, cuentas=("1", "2"))) == (
        'SELECT X.* FROM (\nSELECT 1 FROM DUMMY\n) X WHERE X."Cuenta visible" IN (\'1\', \'2\')'
    )


def test_leer_parte_de_cartera_sin_cuentas_falla_diciendo_que_variable_poner():
    _escribir(config.QUERIES_DIR / "cartera" / "cartera.sql", "SELECT 1 FROM DUMMY")
    with pytest.raises(ConfigError, match="HANA_SGX_CUENTAS_CARTERA"):
        consultas.leer_parte(PARTES["cartera"], _empresa(None, cuentas=()))


def test_leer_parte_de_las_demas_partes_queda_igual():
    _escribir(config.QUERIES_DIR / "maestros" / "marcas.sql", "SELECT 1 FROM DUMMY")
    assert consultas.leer_parte(PARTES["marcas"], _empresa(None)) == "SELECT 1 FROM DUMMY"


VENTAS_REAL = Path(__file__).resolve().parent.parent / "queries" / "ventas" / "ventas.sql"
EXPRESION_SGX = 'CAST(T0."U_SGX_IdPedidoApp" AS NVARCHAR(254))'
# «Tot KG» de «AnálisisVentas-1» (Derivados), adaptada a ventas.sql (contrato §10).
EXPRESION_KILOS = 'CAST(X."Quantity" * T4."NumInSale" * X."Signo" AS DECIMAL(19, 6))'
KILOS_NULO = "CAST(NULL AS DECIMAL(19, 6))"


def _ventas_real() -> str:
    return VENTAS_REAL.read_text(encoding="utf-8")


def test_ventas_de_segurex_queda_tal_cual():
    sql = _ventas_real()
    assert consultas.sql_id_pedido_app(sql, "SGX") == sql


def test_ventas_de_derivados_cambia_el_id_del_pedido_de_la_app_por_null():
    sql = _ventas_real()
    cambiada = consultas.sql_id_pedido_app(sql, "SDC")
    assert 'CAST(NULL AS NVARCHAR(254)) AS "IdPedidoApp" -- @id_pedido_app' in cambiada
    # El campo solo queda nombrado en un comentario: HANA no lo pide en Derivados.
    assert "U_SGX_IdPedidoApp" not in re.sub(r"--[^\n]*", "", cambiada)
    assert EXPRESION_SGX not in cambiada
    # Solo cambia esa expresión: el resto del archivo queda igual.
    assert cambiada == sql.replace(EXPRESION_SGX, "CAST(NULL AS NVARCHAR(254))")


@pytest.mark.parametrize("empresa", ["SGX", "SDC"])
@pytest.mark.parametrize("texto", [
    'SELECT CAST(T0."U_SGX_IdPedidoApp" AS NVARCHAR(254)) AS "IdPedidoApp" FROM "OINV" T0',
    'SELECT CAST(T0."U" AS NVARCHAR(254)) AS "IdPedidoApp" -- @id_pedido_app\n'
    'UNION ALL SELECT CAST(T0."U" AS NVARCHAR(254)) AS "IdPedidoApp" -- @id_pedido_app',
    'SELECT T0."U" AS "IdPedidoApp" -- @id_pedido_app',
    'SELECT CAST(T0."U" AS NVARCHAR(254)) AS "Otro" -- @id_pedido_app',
])
def test_ventas_sin_un_solo_marcador_reconocible_falla(texto: str, empresa: str):
    with pytest.raises(ConfigError, match="@id_pedido_app"):
        consultas.sql_id_pedido_app(texto, empresa)


def test_ventas_de_derivados_trae_los_kilos_y_el_id_de_la_app_en_null():
    sql = _ventas_real()
    cambiada = consultas.sql_ventas(sql, "SDC")
    assert f'{EXPRESION_KILOS} AS "Kilos" -- @kilos' in cambiada
    # Solo cambia el id del pedido de la app: los kilos son de verdad en Derivados.
    assert cambiada == consultas.sql_id_pedido_app(sql, "SDC")


def test_ventas_de_segurex_trae_el_id_de_la_app_y_los_kilos_en_null():
    sql = _ventas_real()
    cambiada = consultas.sql_ventas(sql, "SGX")
    assert f'{KILOS_NULO} AS "Kilos" -- @kilos' in cambiada
    # NumInSale solo queda nombrado en comentarios: en Segurex no se lee.
    assert "NumInSale" not in re.sub(r"--[^\n]*", "", cambiada)
    assert EXPRESION_SGX in cambiada
    # Solo cambia esa expresión: el resto del archivo queda igual.
    assert cambiada == sql.replace(EXPRESION_KILOS, KILOS_NULO)


def test_las_empresas_con_kilos_son_las_de_la_consulta_de_ventas():
    assert consultas.EMPRESAS_CON_KILOS == ("SDC",)
    assert consultas.KILOS_NULO == KILOS_NULO


_ID_VENTAS = 'CAST(T0."U" AS NVARCHAR(254)) AS "IdPedidoApp" -- @id_pedido_app\n'


@pytest.mark.parametrize("empresa", ["SGX", "SDC"])
@pytest.mark.parametrize("texto", [
    "SELECT " + _ID_VENTAS + 'FROM "OINV" T0',                                  # sin kilos
    "SELECT " + _ID_VENTAS + 'CAST(1 AS DECIMAL(19, 6)) AS "Kilos"\nFROM "OINV" T0',  # sin marcador
    "SELECT " + _ID_VENTAS + 'X."K" AS "Kilos" -- @kilos\nFROM "OINV" T0',      # sin CAST
    "SELECT " + _ID_VENTAS + 'CAST(1 AS DECIMAL(19, 6)) AS "Otro" -- @kilos\nFROM "OINV" T0',
    "SELECT " + _ID_VENTAS + 'CAST(1 AS DECIMAL(19, 6)) AS "Kilos" -- @kilos\n'
    'UNION ALL SELECT CAST(1 AS DECIMAL(19, 6)) AS "Kilos" -- @kilos\nFROM "OINV" T0',
])
def test_ventas_sin_un_solo_marcador_de_kilos_reconocible_falla(texto: str, empresa: str):
    with pytest.raises(ConfigError, match="@kilos"):
        consultas.sql_ventas(texto, empresa)


@pytest.mark.parametrize("codigo", ["SGX", "SDC"])
def test_leer_parte_de_ventas_pone_lo_de_cada_empresa(monkeypatch, codigo: str):
    monkeypatch.setattr(config, "QUERIES_DIR", VENTAS_REAL.parent.parent)
    empresa = EmpresaHana(codigo, "usuario", "clave", "ESQUEMA")
    sql = consultas.leer_parte(PARTES["ventas"], empresa)
    assert (EXPRESION_SGX in sql) == (codigo == "SGX")
    assert (EXPRESION_KILOS in sql) == (codigo == "SDC")
    assert sql == consultas.sql_ventas(_ventas_real().rstrip(), codigo)


def test_leer_parte_de_ventas_sin_marcador_no_corre():
    _escribir(config.QUERIES_DIR / "ventas" / "ventas.sql", "SELECT 1 FROM DUMMY")
    with pytest.raises(ConfigError, match="@id_pedido_app"):
        consultas.leer_parte(PARTES["ventas"], _empresa(None))


PEDIDOS_REAL = Path(__file__).resolve().parent.parent / "queries" / "pedidos" / "pedidos.sql"
ID_APP_SGX = 'CAST(T0."U_SGX_IdPedidoApp" AS NVARCHAR(254))'
FAMILIA_SGX = 'CAST(T4."U_GSP_FAMILIA" AS NVARCHAR(100))'


def _pedidos_real() -> str:
    return PEDIDOS_REAL.read_text(encoding="utf-8")


def test_pedidos_de_segurex_queda_tal_cual():
    sql = _pedidos_real()
    assert consultas.sql_pedidos(sql, "SGX") == sql


def test_pedidos_de_derivados_cambia_el_id_de_la_app_y_la_familia_por_null():
    sql = _pedidos_real()
    cambiada = consultas.sql_pedidos(sql, "SDC")
    assert re.search(r'CAST\(NULL AS NVARCHAR\(254\)\) +AS "id_pedido_app", -- @id_pedido_app\n', cambiada)
    assert re.search(r'CAST\(NULL AS NVARCHAR\(100\)\) +AS "familia", -- @familia\n', cambiada)
    # Los campos de Segurex solo quedan nombrados en comentarios: HANA no los pide en Derivados.
    codigo = re.sub(r"--[^\n]*", "", cambiada)
    assert "U_SGX_IdPedidoApp" not in codigo and "U_GSP_FAMILIA" not in codigo
    # Solo cambian esas dos expresiones: el resto del archivo queda igual.
    assert cambiada == sql.replace(ID_APP_SGX, "CAST(NULL AS NVARCHAR(254))").replace(
        FAMILIA_SGX, "CAST(NULL AS NVARCHAR(100))"
    )


_ID_APP = 'CAST(T0."U" AS NVARCHAR(254)) AS "id_pedido_app", -- @id_pedido_app\n'
_FAMILIA = 'CAST(T4."F" AS NVARCHAR(100)) AS "familia", -- @familia\n'


@pytest.mark.parametrize("empresa", ["SGX", "SDC"])
@pytest.mark.parametrize("texto, marcador", [
    ("SELECT " + _FAMILIA + 'FROM "ORDR" T0', "@id_pedido_app"),
    ("SELECT " + _ID_APP + 'FROM "ORDR" T0', "@familia"),
    ("SELECT " + _ID_APP + _ID_APP + _FAMILIA + 'FROM "ORDR" T0', "@id_pedido_app"),
    ("SELECT " + _ID_APP + _FAMILIA + _FAMILIA + 'FROM "ORDR" T0', "@familia"),
    ('SELECT T0."U" AS "id_pedido_app", -- @id_pedido_app\n' + _FAMILIA, "@id_pedido_app"),
    ("SELECT " + _ID_APP + 'CAST(T4."F" AS NVARCHAR(100)) AS "otra", -- @familia\n', "@familia"),
])
def test_pedidos_sin_un_solo_marcador_reconocible_de_cada_campo_falla(texto: str, marcador: str, empresa: str):
    with pytest.raises(ConfigError, match=marcador):
        consultas.sql_pedidos(texto, empresa)


@pytest.mark.parametrize("codigo", ["SGX", "SDC"])
def test_leer_parte_de_pedidos_pone_lo_de_cada_empresa(monkeypatch, codigo: str):
    monkeypatch.setattr(config, "QUERIES_DIR", PEDIDOS_REAL.parent.parent)
    empresa = EmpresaHana(codigo, "usuario", "clave", "ESQUEMA")
    sql = consultas.leer_parte(PARTES["pedidos"], empresa)
    assert (ID_APP_SGX in sql) == (FAMILIA_SGX in sql) == (codigo == "SGX")
    assert sql == consultas.sql_pedidos(_pedidos_real().rstrip(), codigo)


def test_leer_parte_de_pedidos_sin_marcadores_no_corre():
    _escribir(config.QUERIES_DIR / "pedidos" / "pedidos.sql", "SELECT 1 FROM DUMMY")
    with pytest.raises(ConfigError, match="@id_pedido_app"):
        consultas.leer_parte(PARTES["pedidos"], _empresa(None))


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


# --- sql_rango: el filtro de la ventana cambiado por un rango cerrado (contrato §10.4) ---

VENTAS_SQL = Path(__file__).resolve().parent.parent / "queries" / "ventas" / "ventas.sql"
ENERO = (date(2025, 1, 1), date(2025, 1, 31))
RANGO_ENERO = "BETWEEN TO_DATE('2025-01-01', 'YYYY-MM-DD') AND TO_DATE('2025-01-31', 'YYYY-MM-DD')"


def _ventas() -> str:
    return VENTAS_SQL.read_text(encoding="utf-8")


def _codigo(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def test_sql_rango_cambia_cada_filtro_de_la_ventana_de_ventas():
    sql = _ventas()
    cambiada = consultas.sql_rango(sql, *ENERO)
    # Facturas y notas crédito: los dos filtros, sobre la misma columna.
    assert cambiada.count(f'T0."DocDate" {RANGO_ENERO}') == 2
    assert consultas.EXPRESION_VENTANA not in _codigo(cambiada)
    # Solo cambian esas dos líneas: el resto (comentarios incluidos) queda igual.
    distintas = [(a, b) for a, b in zip(sql.split("\n"), cambiada.split("\n")) if a != b]
    assert [a.strip() for a, _ in distintas] == [
        f'WHERE T0."DocDate" >= {consultas.EXPRESION_VENTANA}',
    ] * 2
    assert cambiada.replace(RANGO_ENERO, f">= {consultas.EXPRESION_VENTANA}") == sql


def test_sql_rango_no_cambia_la_consulta_nocturna():
    sql = _ventas()
    consultas.sql_rango(sql, *ENERO)
    assert _ventas() == sql
    assert _codigo(sql).count(f'T0."DocDate" >= {consultas.EXPRESION_VENTANA}') == 2


def test_sql_rango_sirve_con_la_consulta_de_derivados():
    sql = consultas.sql_id_pedido_app(_ventas(), "SDC")
    assert consultas.sql_rango(sql, *ENERO).count(RANGO_ENERO) == 2


def test_sql_rango_sin_la_expresion_no_corre():
    with pytest.raises(ConfigError, match="ventana"):
        consultas.sql_rango('SELECT 1 FROM "OINV" T0 WHERE T0."DocDate" >= CURRENT_DATE', *ENERO)


def test_sql_rango_con_la_expresion_solo_en_un_comentario_no_corre():
    sql = f"-- {consultas.EXPRESION_VENTANA}\nSELECT 1 FROM DUMMY"
    with pytest.raises(ConfigError, match="ventana"):
        consultas.sql_rango(sql, *ENERO)


@pytest.mark.parametrize("filtro", [
    'T0."DocDate" > {e}',
    '{e} <= T0."DocDate"',
    'T0."DocDate" >= {e} AND T1."Otra" = {e}',
    "{e} IS NOT NULL",
])
def test_sql_rango_con_una_aparicion_que_no_es_columna_mayor_o_igual_no_corre(filtro: str):
    sql = 'SELECT 1 FROM "OINV" T0 WHERE ' + filtro.format(e=consultas.EXPRESION_VENTANA)
    with pytest.raises(ConfigError, match="ventana"):
        consultas.sql_rango(sql, *ENERO)


def test_sql_rango_no_toma_por_comentario_un_guion_doble_dentro_de_un_texto():
    sql = f"""SELECT 1 FROM "OINV" T0 WHERE T0."Comments" <> '--' AND T0."DocDate" >= {consultas.EXPRESION_VENTANA}"""
    assert consultas.sql_rango(sql, *ENERO).endswith(f'T0."DocDate" {RANGO_ENERO}')


@pytest.mark.parametrize("desde, hasta, error", [
    ("2025-01-01", date(2025, 1, 31), TypeError),
    (date(2025, 1, 1), datetime(2025, 1, 31, 0, 0), TypeError),
    (date(2025, 1, 31), date(2025, 1, 1), ValueError),
])
def test_sql_rango_solo_acepta_fechas_en_orden(desde, hasta, error):
    with pytest.raises(error):
        consultas.sql_rango(_ventas(), desde, hasta)


# --- La consulta de VENTAS con el rango, en SQLite ------------------------------------


def _sqlite_con_ventas() -> sqlite3.Connection:
    """Las tablas que lee ventas.sql, con las funciones de HANA que usa como propias."""
    con = sqlite3.connect(":memory:")
    con.create_function("ADD_DAYS", 2, lambda d, n: (date.fromisoformat(d) + timedelta(days=n)).isoformat())
    con.create_function("DAYOFMONTH", 1, lambda d: date.fromisoformat(d).day)
    con.create_function("TO_DATE", 2, lambda d, formato: date.fromisoformat(d).isoformat())
    encabezado = ('"DocEntry" INT, "DocNum" INT, "DocSubType" TEXT, "CANCELED" TEXT, "DocStatus" TEXT, '
                  '"DocDate" TEXT, "TaxDate" TEXT, "SlpCode" INT, "CardCode" TEXT, "CardName" TEXT, '
                  '"NumAtCard" TEXT, "Address2" TEXT, "DiscPrcnt" REAL, "DocCur" TEXT, "DocRate" REAL, '
                  '"Comments" TEXT')
    lineas = ('"DocEntry" INT, "LineNum" INT, "ItemCode" TEXT, "Dscription" TEXT, "Quantity" REAL, '
              '"Price" REAL, "PriceBefDi" REAL, "StockPrice" REAL, "LineTotal" REAL, "VatSum" REAL, '
              '"GrssProfit" REAL, "TaxOnly" TEXT, "BaseType" INT, "BaseRef" TEXT')
    con.executescript(f"""
        CREATE TABLE "OINV" ({encabezado}, "U_SGX_IdPedidoApp" TEXT);
        CREATE TABLE "ORIN" ({encabezado});
        CREATE TABLE "INV1" ({lineas});
        CREATE TABLE "RIN1" ({lineas});
        CREATE TABLE "OCRD" ("CardCode" TEXT, "LicTradNum" TEXT, "City" TEXT, "GroupCode" INT);
        CREATE TABLE "OSLP" ("SlpCode" INT, "SlpName" TEXT);
        CREATE TABLE "OITM" ("ItemCode" TEXT, "ItmsGrpCod" INT, "FirmCode" INT, "NumInSale" REAL);
        CREATE TABLE "OITB" ("ItmsGrpCod" INT, "ItmsGrpNam" TEXT);
        CREATE TABLE "OMRC" ("FirmCode" INT, "FirmName" TEXT);
        CREATE TABLE "OCRG" ("GroupCode" INT, "GroupName" TEXT);
    """)
    return con


def _documento(
    con: sqlite3.Connection, tabla: str, doc_entry: int, dia: date, *, cantidad: float = 1,
    articulo: str = "A1",
) -> None:
    lineas = {"OINV": "INV1", "ORIN": "RIN1"}[tabla]
    valores = [doc_entry, doc_entry, "--", "N", "O", dia.isoformat(), dia.isoformat(), 1, "C1", "Cliente",
               None, None, 0, "COP", 1]
    extra = [None] if tabla == "OINV" else []
    marcas = ", ".join("?" for _ in range(16 + len(extra)))
    con.execute(f'INSERT INTO "{tabla}" VALUES ({marcas})', valores + [None] + extra)
    con.execute(f'INSERT INTO "{lineas}" VALUES (?, 0, ?, \'Art\', ?, 10, 10, 5, 10, 1.9, 5, \'N\', -1, NULL)',
                (doc_entry, articulo, cantidad))


def test_la_consulta_con_el_rango_trae_solo_los_dias_del_rango_y_su_conteo_cuadra():
    con = _sqlite_con_ventas()
    desde, hasta = ENERO
    for doc_entry, dia in [
        (1, desde - timedelta(days=1)),  # el día antes: no sale
        (2, desde),
        (3, date(2025, 1, 15)),
        (4, hasta),
        (5, hasta + timedelta(days=1)),  # el día después: no sale
    ]:
        _documento(con, "OINV", doc_entry, dia)
    _documento(con, "ORIN", 6, date(2025, 1, 20))  # nota crédito en el rango
    _documento(con, "ORIN", 7, date(2024, 12, 31))  # nota crédito antes: no sale

    sql = consultas.sql_rango(_ventas(), desde, hasta)
    cursor = con.execute(sql)
    nombres = [d[0] for d in cursor.description]
    filas = [dict(zip(nombres, f)) for f in cursor.fetchall()]
    assert [(f["Tipo objeto"], f["DocEntry"]) for f in filas] == [(13, 2), (13, 3), (14, 6), (13, 4)]
    assert {f["Fecha contabilización"] for f in filas} <= {
        (desde + timedelta(days=n)).isoformat() for n in range(31)
    }
    [(conteo,)] = con.execute(consultas.sql_contar(sql)).fetchall()
    assert conteo == len(filas) == 4


# --- Kilos de VENTAS (orden 016): la columna y su consulta ----------------------------

CON_COMENTARIOS = '    X."Comments"                                               AS "Comentarios"\n'
# La columna de kilos con su coma y su nota, para armar una copia SIN kilos (falla cerrado).
_ADICION_KILOS = re.compile(r',\n(?:    --[^\n]*\n)*    CAST\([^\n]*\) AS "Kilos" -- @kilos(?=\n)')


def _alias_del_select(sql: str) -> list[str]:
    """Etiquetas del SELECT de afuera de ventas.sql (sin comentarios), en orden."""
    codigo = _codigo(sql)
    seleccion = codigo[codigo.index("SELECT"):codigo.index("\nFROM (")]
    return re.findall(r'AS "([^"]+)"', seleccion)


def _sin_kilos(sql: str) -> str:
    """ventas.sql SIN la columna de kilos, como estaba antes de la orden 016."""
    sin, cambios = _ADICION_KILOS.subn("", sql)
    assert cambios == 1 and sin.count(CON_COMENTARIOS) == 1
    return sin


def test_la_consulta_de_ventas_trae_kilos_al_final_del_select():
    sql = _ventas()
    consultas.exigir_kilos(sql)
    # La nocturna, las solicitudes y el histórico traen las columnas del esquema, en orden,
    # con kilos de último.
    assert _alias_del_select(sql) == [c.hana for c in PARTES["ventas"].columnas]
    assert _alias_del_select(sql)[-1] == consultas.ALIAS_KILOS


@pytest.mark.parametrize("empresa", ["SGX", "SDC"])
def test_exigir_kilos_acepta_la_consulta_de_cada_empresa(empresa: str):
    consultas.exigir_kilos(consultas.sql_ventas(_ventas(), empresa))


def test_sin_la_columna_de_kilos_exigir_kilos_falla():
    with pytest.raises(ConfigError, match="no trae la columna de kilos"):
        consultas.exigir_kilos(_sin_kilos(_ventas()))


@pytest.mark.parametrize("reemplazo", [
    CON_COMENTARIOS + '    -- X."Peso" AS "Kilos"\n',             # en una línea de comentario
    CON_COMENTARIOS[:-1] + ' -- , X."Peso" AS "Kilos"\n',          # al final de la última columna
])
def test_exigir_kilos_no_cuenta_los_kilos_de_un_comentario(reemplazo: str):
    sql = _sin_kilos(_ventas()).replace(CON_COMENTARIOS, reemplazo)
    assert 'AS "Kilos"' in sql
    with pytest.raises(ConfigError, match="kilos"):
        consultas.exigir_kilos(sql)


def test_exigir_kilos_pide_la_etiqueta_exacta():
    # El envoltorio la nombra entre comillas (X."Kilos"), y en HANA eso distingue mayúsculas.
    with pytest.raises(ConfigError, match="Kilos"):
        consultas.exigir_kilos(
            _sin_kilos(_ventas()).replace(CON_COMENTARIOS, CON_COMENTARIOS[:-1] + ',\n    1 AS "kilos"\n')
        )


def test_sql_kilos_sin_la_columna_no_corre():
    with pytest.raises(ConfigError, match="kilos"):
        consultas.sql_kilos(_sin_kilos(_ventas()), *ENERO)


def test_columnas_de_los_kilos_son_la_llave_la_fecha_y_kilos():
    columnas = consultas.columnas_kilos()
    assert [c.nombre for c in columnas] == ["tipo_objeto", "doc_entry", "linea", "fecha_contabilizacion", "kilos"]
    assert [c.hana for c in columnas] == ["Tipo objeto", "DocEntry", "Línea", "Fecha contabilización", "Kilos"]
    # La llave es la de VENTAS. La llave y la fecha son obligatorias; kilos no: una línea sin
    # peso en SAP va en null y la API lo guarda así (contrato §10.5).
    assert set(PARTES["ventas"].llave) < {c.nombre for c in columnas}
    assert [c.requerida for c in columnas] == [True, True, True, True, False]


def test_columnas_de_los_kilos_salen_del_esquema_de_ventas():
    ventas = {c.nombre: c for c in PARTES["ventas"].columnas}
    assert list(consultas.columnas_kilos()) == [ventas[c.nombre] for c in consultas.columnas_kilos()]


def test_sql_kilos_trae_solo_la_llave_la_fecha_y_kilos_con_el_rango():
    sql = consultas.sql_ventas(_ventas(), "SDC")
    kilos = consultas.sql_kilos(sql, *ENERO)
    assert kilos.startswith(
        'SELECT X."Tipo objeto", X."DocEntry", X."Línea", X."Fecha contabilización", X."Kilos" FROM (\n'
    )
    assert kilos.endswith("\n) X")
    assert kilos.count(RANGO_ENERO) == 2
    assert consultas.sql_rango(sql, *ENERO) in kilos
    assert "X.*" not in kilos


def _ventas_con_kilos_en_sqlite() -> sqlite3.Connection:
    """Una factura y una nota crédito de 2 unidades del artículo A1 (NumInSale 1,5), una
    factura de un artículo que no está en OITM y otra fuera del rango."""
    con = _sqlite_con_ventas()
    con.execute('INSERT INTO "OITM" VALUES (\'A1\', 10, 3, 1.5)')
    desde, hasta = ENERO
    _documento(con, "OINV", 1, desde - timedelta(days=1), cantidad=2)  # el día antes: no sale
    _documento(con, "OINV", 2, desde, cantidad=2)
    _documento(con, "ORIN", 3, date(2025, 1, 20), cantidad=2)  # nota crédito: kilos negativos
    _documento(con, "OINV", 4, date(2025, 1, 25), cantidad=2, articulo="ZZ")  # sin artículo en OITM
    _documento(con, "OINV", 5, hasta + timedelta(days=1), cantidad=2)  # el día después: no sale
    return con


def test_ventas_de_derivados_en_sqlite_trae_los_kilos_con_signo_y_sin_perder_lineas():
    con = _ventas_con_kilos_en_sqlite()
    cursor = con.execute(consultas.sql_rango(consultas.sql_ventas(_ventas(), "SDC"), *ENERO))
    nombres = [d[0] for d in cursor.description]
    filas = [dict(zip(nombres, f)) for f in cursor.fetchall()]
    assert nombres[-1] == "Kilos"
    # Cantidad 2 por NumInSale 1,5: 3 kilos, negativos en la nota crédito. La línea cuyo
    # artículo no está en OITM sale igual (LEFT JOIN), con kilos NULL.
    assert [(f["DocEntry"], f["Cantidad"], f["Kilos"]) for f in filas] == [
        (2, 2.0, 3.0), (3, -2.0, -3.0), (4, 2.0, None),
    ]


def test_ventas_de_segurex_en_sqlite_trae_las_mismas_lineas_con_kilos_null():
    con = _ventas_con_kilos_en_sqlite()
    cursor = con.execute(consultas.sql_rango(consultas.sql_ventas(_ventas(), "SGX"), *ENERO))
    nombres = [d[0] for d in cursor.description]
    filas = [dict(zip(nombres, f)) for f in cursor.fetchall()]
    assert [(f["DocEntry"], f["Kilos"]) for f in filas] == [(2, None), (3, None), (4, None)]


def test_sql_kilos_en_sqlite_trae_el_rango_con_signo_y_su_conteo_cuadra():
    con = _ventas_con_kilos_en_sqlite()
    sql = consultas.sql_kilos(consultas.sql_ventas(_ventas(), "SDC"), *ENERO)
    cursor = con.execute(sql)
    assert [d[0] for d in cursor.description] == [c.hana for c in consultas.columnas_kilos()]
    assert cursor.fetchall() == [
        (13, 2, 0, "2025-01-01", 3.0), (14, 3, 0, "2025-01-20", -3.0), (13, 4, 0, "2025-01-25", None),
    ]
    [(conteo,)] = con.execute(consultas.sql_contar(sql)).fetchall()
    assert conteo == 3
