"""Revisión estática de robot/queries: reglas del plan §5 y columnas del contrato."""
from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import date
from pathlib import Path

import pytest

import config
import consultas
from esquema import PARTES, PARTES_POR_CONJUNTO

QUERIES = Path(__file__).resolve().parent.parent / "queries"
ARCHIVOS = sorted(QUERIES.rglob("*.sql"))
ESQUEMAS = ("SEGUREX", "HBT_SDERIVADOS")
VALIDAR = "VALIDAR CON DATOS REALES"


def _id(ruta: Path) -> str:
    return ruta.relative_to(QUERIES).as_posix()


def _texto(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _sin_comentarios(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _alias(sql: str) -> list[str]:
    return re.findall(r'\bAS\s+"([^"]+)"', _sin_comentarios(sql), flags=re.IGNORECASE)


def test_hay_consultas():
    assert len(ARCHIVOS) >= 19


@pytest.mark.parametrize("ruta", ARCHIVOS, ids=_id)
def test_reglas_de_cada_archivo(ruta: Path):
    sql = _texto(ruta)
    codigo = _sin_comentarios(sql)
    assert not re.search(r"SELECT\s+(\w+\s*\.\s*)?\*", sql, re.IGNORECASE), "SELECT *"
    assert not re.search(r"\.\s*\*", sql), "columna.* en vez de columnas listadas"
    assert "?" not in sql, "sin parámetros: debe correr tal cual en el Query Manager"
    assert not re.search(r"\bOCRB\b", sql, re.IGNORECASE)
    assert not re.search(r"password", sql, re.IGNORECASE)
    for esquema in ESQUEMAS:
        assert f'"{esquema}".' not in codigo and f"{esquema}." not in codigo, (
            "tablas sin esquema: lo pone la conexión"
        )


def _parte_de(ruta: Path) -> str:
    return ruta.stem


MAESTROS = sorted((QUERIES / "maestros").rglob("*.sql"))


@pytest.mark.parametrize("ruta", MAESTROS, ids=_id)
def test_alias_de_maestros_son_las_columnas_del_contrato(ruta: Path):
    parte = PARTES[_parte_de(ruta)]
    alias = _alias(_texto(ruta))
    assert len(alias) == len(set(alias)), "alias repetido"
    assert set(alias) == set(parte.nombres)


def test_cada_parte_de_maestros_tiene_consulta_en_cada_esquema(monkeypatch):
    monkeypatch.setattr(config, "QUERIES_DIR", QUERIES)
    for nombre in PARTES_POR_CONJUNTO["MAESTROS"]:
        for esquema in ESQUEMAS:
            assert consultas.leer(PARTES[nombre].consulta, esquema)
    for esquema in ESQUEMAS:
        ruta = consultas.ruta_consulta("maestros/precios.sql", esquema)
        assert ruta == QUERIES / "maestros" / "precios.sql"
        assert not (QUERIES / "maestros" / esquema / "precios.sql").exists()


def test_precios_trae_todas_las_listas_y_no_filtra_por_nombre():
    # La lista pública se elige por número desde el robot (consultas.leer_parte).
    sql = _sin_comentarios(_texto(QUERIES / "maestros" / "precios.sql"))
    assert "WHERE" not in sql.upper()
    assert "ListName" in sql  # solo como columna lista_nombre


CARTERA = QUERIES / "cartera" / "cartera.sql"
CUENTAS_DE_CARTERA = {
    "SGX": ("13050505", "13051005"),
    "SDC": ("13050501", "13051005"),
}


def test_cartera_es_una_sola_consulta_para_todos_los_esquemas(monkeypatch):
    monkeypatch.setattr(config, "QUERIES_DIR", QUERIES)
    assert sorted(p.name for p in (QUERIES / "cartera").iterdir()) == ["cartera.sql"]
    for esquema in ESQUEMAS:
        assert consultas.ruta_consulta(PARTES["cartera"].consulta, esquema) == CARTERA


def test_cartera_trae_todas_las_etiquetas():
    sql = _texto(CARTERA)
    for columna in PARTES["cartera"].columnas:
        assert f'"{columna.hana}"' in sql, columna.hana
    assert "GESTOR_CARTERA/etl/queries/cartera.sql" in sql


def test_cartera_no_filtra_por_cuenta_y_trae_la_etiqueta_para_filtrar_afuera():
    codigo = _sin_comentarios(_texto(CARTERA))
    assert not re.search(r'"Account"\s+(IN|=)', codigo), "el filtro por cuenta lo pone el robot"
    assert 'T0."Account"                                      AS "Cuenta visible"' in codigo


# --- Cartera: filtrar por cuenta afuera da lo mismo que dentro ---------------------------
#
# La consulta única trae todas las cuentas y el robot se queda con las de la empresa
# (consultas.sql_cuentas). Se prueba contra los datos de un SQLite en memoria, con
# DAYS_BETWEEN de HANA como función propia, que la consulta de antes (con el
# `AND T0."Account" IN (...)` dentro del WHERE) y la de ahora dan las mismas filas.

_FILTRO_DE_ANTES = 'WHERE T1."CardType" = \'C\'\n'


def _sqlite_con_cartera() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.create_function(
        "DAYS_BETWEEN", 2, lambda a, b: (date.fromisoformat(b) - date.fromisoformat(a)).days
    )
    con.executescript("""
        CREATE TABLE "JDT1" ("TransId" INT, "Line_ID" INT, "Account" TEXT, "ShortName" TEXT,
            "TransType" INT, "BaseRef" TEXT, "Ref1" TEXT, "Ref2" TEXT, "RefDate" TEXT,
            "DueDate" TEXT, "TaxDate" TEXT, "Debit" REAL, "Credit" REAL,
            "BalDueDeb" REAL, "BalDueCred" REAL);
        CREATE TABLE "OCRD" ("CardCode" TEXT, "CardName" TEXT, "LicTradNum" TEXT, "CardType" TEXT,
            "GroupCode" INT, "SlpCode" INT, "City" TEXT, "CreditLine" REAL, "GroupNum" INT);
        CREATE TABLE "OCRG" ("GroupCode" INT, "GroupName" TEXT);
        CREATE TABLE "OSLP" ("SlpCode" INT, "SlpName" TEXT, "Email" TEXT);
        CREATE TABLE "OCTG" ("GroupNum" INT, "PymntGroup" TEXT);
        CREATE TABLE "OINV" ("TransId" INT, "DocTotal" REAL, "VatSum" REAL);
        CREATE TABLE "ORIN" ("TransId" INT, "DocTotal" REAL, "VatSum" REAL);
        INSERT INTO "OCRG" VALUES (1, 'Mayoristas');
        INSERT INTO "OSLP" VALUES (7, 'Ana', 'ANA@PRUEBA.TEST');
        INSERT INTO "OCTG" VALUES (1, 'Neto 30');
        INSERT INTO "OCRD" VALUES ('C1', 'Cliente uno', '900', 'C', 1, 7, 'Bogotá', 1000, 1);
        INSERT INTO "OCRD" VALUES ('C2', 'Cliente dos', '901', 'C', 1, NULL, 'Cali', 0, 1);
        INSERT INTO "OCRD" VALUES ('P1', 'Proveedor', '902', 'S', 1, NULL, 'Cali', 0, 1);
        INSERT INTO "OINV" VALUES (100, 119, 19);
        INSERT INTO "ORIN" VALUES (101, 119, 19);
    """)
    # (TransId, cuenta, socio, debe, haber, saldo debe, saldo haber, vence)
    asientos = [
        (100, "13050505", "C1", 119, 0, 119, 0, "2026-08-01"),  # solo Segurex
        (101, "13050505", "C2", 0, 119, 0, 119, "2026-09-15"),  # nota crédito, solo Segurex
        (102, "13050501", "C1", 50, 0, 50, 0, "2026-07-01"),    # solo Derivados
        (103, "13050501", "C2", 70, 0, 20, 0, "2026-10-30"),
        (104, "13051005", "C1", 30, 0, 30, 0, "2026-06-01"),    # las dos empresas
        (105, "13051005", "C2", 40, 0, 0, 0, "2026-06-01"),     # sin saldo: no sale
        (106, "13059999", "C1", 10, 0, 10, 0, "2026-06-01"),    # otra cuenta por cobrar
        (107, "13050505", "P1", 10, 0, 10, 0, "2026-06-01"),    # de un proveedor: no sale
    ]
    for linea, (trans, cuenta, socio, debe, haber, saldo_debe, saldo_haber, vence) in enumerate(asientos):
        con.execute(
            'INSERT INTO "JDT1" VALUES (?, ?, ?, ?, 13, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (trans, linea, cuenta, socio, f"B{trans}", f"R{trans}", f"X{trans}", "2026-05-01",
             vence, "2026-05-01", debe, haber, saldo_debe, saldo_haber),
        )
    return con


def _filas(con: sqlite3.Connection, sql: str) -> list[tuple]:
    return sorted(con.execute(sql).fetchall(), key=repr)


@pytest.mark.parametrize("empresa, cuentas", CUENTAS_DE_CARTERA.items())
def test_filtrar_las_cuentas_afuera_da_lo_mismo_que_dentro(empresa: str, cuentas: tuple[str, ...]):
    sql = _texto(CARTERA).rstrip()
    lista = ", ".join(f"'{c}'" for c in cuentas)
    assert _FILTRO_DE_ANTES in sql
    de_antes = sql.replace(_FILTRO_DE_ANTES, f'{_FILTRO_DE_ANTES}      AND T0."Account" IN ({lista})\n')
    con = _sqlite_con_cartera()

    de_ahora = _filas(con, consultas.sql_cuentas(sql, cuentas))

    assert de_ahora == _filas(con, de_antes)
    assert de_ahora, "la prueba necesita filas"
    posicion = [d[0] for d in con.execute(de_antes).description].index("Cuenta visible")
    assert {fila[posicion] for fila in de_ahora} <= set(cuentas)


def test_las_dos_empresas_ven_cuentas_distintas_en_la_misma_consulta():
    sql, con = _texto(CARTERA).rstrip(), _sqlite_con_cartera()
    sgx = _filas(con, consultas.sql_cuentas(sql, CUENTAS_DE_CARTERA["SGX"]))
    sdc = _filas(con, consultas.sql_cuentas(sql, CUENTAS_DE_CARTERA["SDC"]))
    assert len(sgx) == 3 and len(sdc) == 3  # SGX: 100, 101, 104; SDC: 102, 103, 104
    assert set(sgx) & set(sdc) == {fila for fila in sgx if "13051005" in fila}


# --- Ventas: la consulta del gestor, copiada tal cual (contrato §10) ---------------------

VENTAS = QUERIES / "ventas" / "ventas.sql"
# Id del blob de etl/queries/ventas.sql en el gestor de cartera, main 9e2f877:
#   git -C GESTOR_CARTERA rev-parse 9e2f877:etl/queries/ventas.sql
BLOB_VENTAS_GESTOR = "c768a24e9a66cda617be8be6381ce26478e3bcd0"


def test_ventas_es_la_consulta_del_gestor_sin_cambios():
    contenido = VENTAS.read_bytes()
    blob = hashlib.sha1(b"blob %d\0" % len(contenido) + contenido).hexdigest()
    assert blob == BLOB_VENTAS_GESTOR
    assert sorted(p.name for p in (QUERIES / "ventas").iterdir()) == ["ventas.sql"]


def test_ventas_trae_las_etiquetas_del_esquema_y_un_solo_marcador():
    sql = _texto(VENTAS)
    alias = _alias(sql)
    for columna in PARTES["ventas"].columnas:
        assert columna.hana in alias, columna.hana
    assert sql.count("-- @id_pedido_app") == 1
    assert 'CAST(T0."U_SGX_IdPedidoApp" AS NVARCHAR(254)) AS "IdPedidoApp" -- @id_pedido_app' in sql


def test_ventas_filtra_la_ventana_con_la_expresion_que_usa_el_robot():
    codigo = _sin_comentarios(_texto(VENTAS))
    expresion = consultas.SQL_VENTANA.removeprefix("SELECT ").removesuffix(" FROM DUMMY")
    assert codigo.count(f'T0."DocDate" >= {expresion}') == 2  # facturas y notas crédito


@pytest.mark.parametrize("archivo", [
    "ventas/ventas.sql",
    "maestros/articulos.sql",
    "maestros/precios.sql",
    "maestros/municipios.sql",
    "maestros/direcciones.sql",
    "maestros/contactos.sql",
    "maestros/clientes.sql",
    "maestros/proveedores.sql",
    "cartera/cartera.sql",
    "diagnostico/listas_precios.sql",
])
def test_lo_no_confirmado_esta_marcado(archivo: str):
    assert VALIDAR in _texto(QUERIES / archivo)


def test_catalogo_y_diagnostico_existen():
    for archivo in ("catalogo/tablas.sql", "catalogo/campos_usuario.sql",
                    "catalogo/tablas_usuario.sql", "catalogo/columnas.sql",
                    "diagnostico/listas_precios.sql"):
        assert (QUERIES / archivo).is_file(), archivo


# --- Archivo (plan §5) --------------------------------------------------------------

ARCHIVO = sorted((QUERIES / "archivo").rglob("*.sql"))
TABLAS_ARCHIVO = [r for r in ARCHIVO if r.parent != QUERIES / "archivo"]
CABECERA_ARCHIVO = (
    "VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; "
    r"confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción"
)
OHEM_PERMITIDAS = {"empID", "firstName", "middleName", "lastName", "jobTitle", "position", "dept", "email"}
RE_CLAVE = re.compile(r"PASS|PWD|CLAVE", re.IGNORECASE)


def _columnas(sql: str) -> list[str]:
    """Columnas T0."X" / T1."X" del SELECT (sin comentarios)."""
    seleccion = re.search(r"\bSELECT\b(.*?)\bFROM\b", _sin_comentarios(sql), re.DOTALL | re.IGNORECASE)
    assert seleccion
    return re.findall(r'\bT\d\."([^"]+)"', seleccion.group(1))


def test_hay_consultas_de_archivo():
    assert len(TABLAS_ARCHIVO) == 55
    assert {r.name for r in ARCHIVO if r.parent == QUERIES / "archivo"} == {
        "hbt_tablas.sql", "hbt_columnas.sql",
    }


@pytest.mark.parametrize("ruta", TABLAS_ARCHIVO, ids=_id)
def test_cada_archivo_lee_su_tabla_con_columnas_listadas(ruta: Path):
    sql = _texto(ruta)
    assert CABECERA_ARCHIVO in sql
    codigo = _sin_comentarios(sql)
    assert re.search(rf'FROM "{re.escape(ruta.stem)}" T0\b', codigo)
    columnas = _columnas(sql)
    assert columnas and len(columnas) == len(set(columnas)), "columnas repetidas"
    assert "ORDER BY" in codigo


@pytest.mark.parametrize("tabla", ["OUSR", "AUSR"])
def test_usuarios_sin_columnas_de_claves(tabla: str):
    [ruta] = [r for r in TABLAS_ARCHIVO if r.stem == tabla]
    for columna in _columnas(_texto(ruta)):
        assert not RE_CLAVE.search(columna), columna


def test_ohem_solo_nombre_cargo_area_y_correo():
    sql = _texto(QUERIES / "archivo" / "ORGANIZACION" / "OHEM.sql")
    assert set(_columnas(sql)) == OHEM_PERMITIDAS


def test_hbt_descubre_tablas_y_columnas_sin_parametros():
    for nombre in ("hbt_tablas.sql", "hbt_columnas.sql"):
        codigo = _sin_comentarios(_texto(QUERIES / "archivo" / nombre))
        assert "CURRENT_SCHEMA" in codigo
        assert "LIKE '@HBT%'" in codigo
    assert '"POSITION"' in _texto(QUERIES / "archivo" / "hbt_columnas.sql")
