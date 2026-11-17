"""Revisión estática de robot/queries: reglas del plan §5 y columnas del contrato."""
from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import date, timedelta
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
    "SGX": ("13050505", "13050510", "13051005"),
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


# Lo único propio que lleva la consulta sobre la copia del gestor: la ganancia bruta.
NOTA_GANANCIA = (
    "--\n"
    '-- "Ganancia bruta" (GrssProfit de INV1/RIN1, con signo) es la unica columna\n'
    "-- propia que se agrega a la copia de la consulta del gestor de cartera. Cuadra\n"
    "-- con la «Ganancia bruta» del Analisis de ventas de SAP al peso; el costo de\n"
    "-- inventario (StockPrice) se desvia cerca de 0,5 %.\n"
)
COLUMNA_GANANCIA = (
    '    ROUND(X."GrssProfit", 2) * X."Signo"                       AS "Ganancia bruta",\n'
)
SUBCONSULTA_GANANCIA = 'T1."VatSum", T1."GrssProfit",\n'


def test_ventas_es_la_consulta_del_gestor_mas_la_ganancia_bruta():
    texto = _texto(VENTAS)
    # Cada adición aparece donde debe y una sola vez (la columna, la nota y las dos subconsultas).
    assert texto.count(NOTA_GANANCIA) == 1
    assert texto.count(COLUMNA_GANANCIA) == 1
    assert texto.count(SUBCONSULTA_GANANCIA) == 2
    # Quitadas esas adiciones, queda exactamente la consulta del gestor.
    gestor = (
        texto.replace(NOTA_GANANCIA, "")
        .replace(COLUMNA_GANANCIA, "")
        .replace(SUBCONSULTA_GANANCIA, 'T1."VatSum",\n')
        .encode("utf-8")
    )
    blob = hashlib.sha1(b"blob %d\0" % len(gestor) + gestor).hexdigest()
    assert blob == BLOB_VENTAS_GESTOR
    assert sorted(p.name for p in (QUERIES / "ventas").iterdir()) == ["ventas.sql"]


def test_ventas_ganancia_bruta_va_despues_del_iva_y_con_signo():
    codigo = _sin_comentarios(_texto(VENTAS))
    alias = _alias(codigo)
    assert alias.index("Ganancia bruta") == alias.index("IVA") + 1
    # Las notas crédito restan: el signo (-1 en RIN1) multiplica la ganancia, como el IVA.
    assert 'ROUND(X."GrssProfit", 2) * X."Signo"' in codigo
    assert 'ROUND(X."VatSum", 2) * X."Signo"' in codigo
    assert codigo.count('13 AS "ObjType", 1 AS "Signo"') == 1
    assert codigo.count('14 AS "ObjType", -1 AS "Signo"') == 1


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
    "pedidos/pedidos.sql",
    "diagnostico/listas_precios.sql",
])
def test_lo_no_confirmado_esta_marcado(archivo: str):
    assert VALIDAR in _texto(QUERIES / archivo)


def test_catalogo_y_diagnostico_existen():
    for archivo in ("catalogo/tablas.sql", "catalogo/campos_usuario.sql",
                    "catalogo/tablas_usuario.sql", "catalogo/columnas.sql",
                    "diagnostico/listas_precios.sql"):
        assert (QUERIES / archivo).is_file(), archivo


# --- Pedidos: líneas abiertas de pedidos de clientes (contrato §11) --------------------

PEDIDOS = QUERIES / "pedidos" / "pedidos.sql"
TABLAS_PROHIBIDAS_EN_PEDIDOS = ("CRD1", "OITW", "ITM1", "OPLN", "RDR12")


def test_pedidos_es_una_sola_consulta_con_los_alias_del_contrato(monkeypatch):
    monkeypatch.setattr(config, "QUERIES_DIR", QUERIES)
    assert sorted(p.name for p in (QUERIES / "pedidos").iterdir()) == ["pedidos.sql"]
    for esquema in ESQUEMAS:
        assert consultas.ruta_consulta(PARTES["pedidos"].consulta, esquema) == PEDIDOS
    # El orden del SELECT es el del contrato §11.3 (el CSV y el lote salen en ese orden).
    assert _alias(_texto(PEDIDOS)) == PARTES["pedidos"].nombres


def test_pedidos_filtra_las_lineas_abiertas_y_solo_une_las_tablas_permitidas():
    codigo = _sin_comentarios(_texto(PEDIDOS))
    for condicion in ('T0."DocStatus" = \'O\'', 'T0."CANCELED" = \'N\'',
                      'T1."LineStatus" = \'O\'', 'T1."OpenCreQty" > 0'):
        assert condicion in codigo, condicion
    assert re.search(
        r'FROM\s+"ORDR"\s+T0\s+INNER\s+JOIN\s+"RDR1"\s+T1\s+ON\s+T1\."DocEntry"\s*=\s*T0\."DocEntry"', codigo
    )
    unidas = re.findall(r'\bLEFT\s+JOIN\s+"(\w+)"', codigo)
    assert sorted(unidas) == ["OCRD", "OCRG", "OITB", "OITM", "OMRC", "OSLP"]
    assert len(re.findall(r"\bJOIN\b", codigo)) == 7  # RDR1 y las seis de arriba
    for tabla in TABLAS_PROHIBIDAS_EN_PEDIDOS:
        assert not re.search(rf"\b{tabla}\b", codigo), tabla
    # OpenInvQty va en unidades de inventario: nunca sirve para valorar (§11.2).
    assert "OpenInvQty" not in codigo


def test_pedidos_marca_una_vez_el_id_de_la_app_y_la_familia():
    sql = _texto(PEDIDOS)
    assert sql.count("@id_pedido_app") == 1 and sql.count("@familia") == 1
    assert re.search(r'CAST\(T0\."U_SGX_IdPedidoApp" AS NVARCHAR\(254\)\)\s+AS "id_pedido_app",'
                     r'[ \t]*--[ \t]*@id_pedido_app\n', sql)
    assert re.search(r'CAST\(T4\."U_GSP_FAMILIA" AS NVARCHAR\(100\)\)\s+AS "familia",'
                     r'[ \t]*--[ \t]*@familia\n', sql)


def test_pedidos_deja_marcado_lo_que_se_valida_con_sap():
    # Contrato §11.5: cada punto lleva su VALIDAR CON DATOS REALES en un comentario.
    sql = _texto(PEDIDOS)
    assert sql.count(VALIDAR) >= 4
    comentarios = " ".join(re.findall(r"--([^\n]*)", sql))
    for dato in ("U_SGX_IdPedidoApp", "U_GSP_FAMILIA", "GrssProfit", "unitMsr"):
        assert dato in comentarios, dato


def _sqlite_con_pedidos(hoy: date) -> sqlite3.Connection:
    """ORDR/RDR1 y sus tablas de nombres en SQLite, con DAYS_BETWEEN de HANA como función.

    `hoy` debe ser el CURRENT_DATE de SQLite (fecha UTC): los días se arman contra él.
    """
    def dia(dias_atras: int) -> str:
        return (hoy - timedelta(days=dias_atras)).isoformat()

    con = sqlite3.connect(":memory:")
    con.create_function(
        "DAYS_BETWEEN", 2, lambda a, b: (date.fromisoformat(b) - date.fromisoformat(a)).days
    )
    con.executescript("""
        CREATE TABLE "ORDR" ("DocEntry" INT, "DocNum" INT, "DocDate" TEXT, "DocDueDate" TEXT,
            "DocStatus" TEXT, "CANCELED" TEXT, "SlpCode" INT, "CardCode" TEXT, "CardName" TEXT,
            "U_SGX_IdPedidoApp" TEXT, "NumAtCard" TEXT, "Address2" TEXT, "Comments" TEXT,
            "DiscPrcnt" REAL, "DocCur" TEXT, "DocRate" REAL);
        CREATE TABLE "RDR1" ("DocEntry" INT, "LineNum" INT, "LineStatus" TEXT, "ShipDate" TEXT,
            "ItemCode" TEXT, "Dscription" TEXT, "WhsCode" TEXT, "unitMsr" TEXT, "Quantity" REAL,
            "OpenCreQty" REAL, "OpenQty" REAL, "OpenInvQty" REAL, "PriceBefDi" REAL, "Price" REAL,
            "LineTotal" REAL, "GrssProfit" REAL, "TaxOnly" TEXT);
        CREATE TABLE "OCRD" ("CardCode" TEXT, "LicTradNum" TEXT, "City" TEXT, "GroupCode" INT);
        CREATE TABLE "OCRG" ("GroupCode" INT, "GroupName" TEXT);
        CREATE TABLE "OSLP" ("SlpCode" INT, "SlpName" TEXT);
        CREATE TABLE "OITM" ("ItemCode" TEXT, "ItmsGrpCod" INT, "FirmCode" INT, "U_GSP_FAMILIA" TEXT);
        CREATE TABLE "OITB" ("ItmsGrpCod" INT, "ItmsGrpNam" TEXT);
        CREATE TABLE "OMRC" ("FirmCode" INT, "FirmName" TEXT);
        INSERT INTO "OCRG" VALUES (1, 'Distribuidores');
        INSERT INTO "OSLP" VALUES (7, 'Ana');
        INSERT INTO "OCRD" VALUES ('C1', '900', 'Bogotá', 1);
        INSERT INTO "OITM" VALUES ('A1', 10, 3, 'GUANTES');
        INSERT INTO "OITB" VALUES (10, 'Proteccion manos');
        INSERT INTO "OMRC" VALUES (3, 'Marca uno');
    """)
    # (DocEntry, días desde el pedido, días desde el compromiso, estado, anulado, descuento %)
    pedidos = [
        (1, 30, -5, "O", "N", 10.0),   # Hasta 30 dias, aún no vence
        (2, 31, 1, "O", "N", None),    # De 31 a 60 dias, descuento NULL
        (3, 61, 20, "O", "N", 0.0),    # De 61 a 90 dias
        (4, 91, 60, "O", "N", 0.0),    # Mas de 90 dias, sin vendedor
        (5, 5, 0, "C", "N", 0.0),      # cerrado: no sale
        (6, 5, 0, "O", "Y", 0.0),      # anulado: no sale
    ]
    for entry, dias, atraso, estado, anulado, descuento in pedidos:
        con.execute(
            'INSERT INTO "ORDR" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (entry, 3800 + entry, dia(dias), dia(atraso), estado, anulado, None if entry == 4 else 7,
             "C1", "Cliente uno", f"APP-{entry}", f"OC{entry}", "Calle 1", None, descuento, "COP", 1.0),
        )
    # (DocEntry, LineNum, estado, cantidad, abierta, total de la línea, ganancia, solo impuesto)
    lineas = [
        (1, 0, "O", 400, 100, 1000.0, 300.0, "N"),   # una cuarta parte abierta, 10 % de descuento
        (1, 1, "C", 10, 0, 50.0, 5.0, "N"),          # línea cerrada: no sale
        (1, 2, "O", 10, 0, 50.0, 5.0, "N"),          # abierta sin cantidad pendiente: no sale
        (2, 0, "O", 3, 3, 90.0, 30.0, "N"),
        (3, 0, "O", 2, 1, 80.0, 20.0, "Y"),          # solo impuesto: total y ganancia en 0
        (4, 0, "O", 0, 1, 80.0, 20.0, "N"),          # cantidad 0: total y ganancia en 0
        (5, 0, "O", 1, 1, 10.0, 1.0, "N"),
        (6, 0, "O", 1, 1, 10.0, 1.0, "N"),
    ]
    for entry, numero, estado, cantidad, abierta, total, ganancia, solo_impuesto in lineas:
        con.execute(
            'INSERT INTO "RDR1" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (entry, numero, estado, dia(0), "A1", "Guante", "PT", "Caja", cantidad, abierta,
             abierta, abierta * 25, 12.5, 10.0, total, ganancia, solo_impuesto),
        )
    return con


def _pedidos_en_sqlite(sql: str) -> list[dict]:
    con = sqlite3.connect(":memory:")
    hoy = date.fromisoformat(con.execute("SELECT CURRENT_DATE").fetchone()[0])
    con = _sqlite_con_pedidos(hoy)
    cursor = con.execute(sql)
    nombres = [d[0] for d in cursor.description]
    return [dict(zip(nombres, fila)) for fila in cursor.fetchall()]


def test_pedidos_trae_solo_las_lineas_abiertas_con_cantidad_pendiente():
    sql = _texto(PEDIDOS).rstrip()
    filas = _pedidos_en_sqlite(sql)
    assert [(f["doc_entry"], f["linea"]) for f in filas] == [(1, 0), (2, 0), (3, 0), (4, 0)]
    # conteo_sap: el COUNT(*) de la misma consulta (contrato §11.4).
    [conteo] = _pedidos_en_sqlite(consultas.sql_contar(sql))
    assert list(conteo.values()) == [len(filas)]


def test_pedidos_calcula_dias_rango_atraso_y_valores_pendientes():
    filas = {f["doc_entry"]: f for f in _pedidos_en_sqlite(_texto(PEDIDOS))}
    assert [(filas[n]["dias"], filas[n]["rango"], filas[n]["dias_atraso"]) for n in (1, 2, 3, 4)] == [
        (30, "Hasta 30 dias", -5), (31, "De 31 a 60 dias", 1),
        (61, "De 61 a 90 dias", 20), (91, "Mas de 90 dias", 60),
    ]
    uno = filas[1]
    # 1.000 * 100 / 400 * (1 - 10 / 100) = 225; ganancia 300 * 100 / 400 = 75.
    assert (uno["total_pendiente"], uno["ganancia_bruta_pendiente"]) == (225.0, 75.0)
    assert (uno["cantidad_pedida"], uno["cantidad_pendiente"]) == (400, 100)
    assert (uno["slp_code"], uno["vendedor"], uno["canal"]) == (7, "Ana", "Distribuidores")
    assert (uno["linea_articulo"], uno["familia"], uno["marca"]) == ("Proteccion manos", "GUANTES", "Marca uno")
    assert (uno["id_pedido_app"], uno["numero_pedido"], uno["descuento_documento"]) == ("APP-1", 3801, 10.0)
    assert filas[2]["total_pendiente"] == 90.0  # descuento NULL = sin descuento
    for n in (3, 4):  # solo impuesto y cantidad 0
        assert (filas[n]["total_pendiente"], filas[n]["ganancia_bruta_pendiente"]) == (0, 0)
    assert (filas[4]["slp_code"], filas[4]["vendedor"]) == (-1, None)


def test_pedidos_de_derivados_corre_sin_los_campos_de_segurex():
    filas = _pedidos_en_sqlite(consultas.sql_pedidos(_texto(PEDIDOS), "SDC"))
    assert len(filas) == 4
    assert {(f["id_pedido_app"], f["familia"]) for f in filas} == {(None, None)}


# --- Archivo (plan §5) --------------------------------------------------------------

ARCHIVO = sorted((QUERIES / "archivo").rglob("*.sql"))
TABLAS_ARCHIVO = [r for r in ARCHIVO if r.parent != QUERIES / "archivo"]
CABECERA_ARCHIVO = (
    "VALIDAR CON DATOS REALES: columnas tomadas de la documentación de SAP B1; "
    r"confirmarlas con _CATALOGO\<empresa>\columnas antes de la primera extracción"
)
# Consultas ya confirmadas con el catálogo de Segurex (17/11/2026): llevan esa nota en
# vez de la cabecera de «VALIDAR CON DATOS REALES». Columnas exactas, en minúscula
# o mayúscula tal como las guarda HANA.
CONFIRMADAS_CON_CATALOGO = r"Columnas confirmadas con _CATALOGO\SEGUREX\columnas el 17/11/2026"
COLUMNAS_CONFIRMADAS = {
    "OSUL": ["ID", "RealName", "LogReason", "LogDetail", "Mac", "Machine",
             "StartDate", "StartTime", "EndDate", "EndTime"],
    "AUSR": ["logInstanc", "USERID", "USER_CODE", "U_NAME", "E_Mail", "SUPERUSER",
             "Locked", "updateDate"],
}
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
    if ruta.stem in COLUMNAS_CONFIRMADAS:
        assert CONFIRMADAS_CON_CATALOGO in sql
    else:
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


@pytest.mark.parametrize("tabla", list(COLUMNAS_CONFIRMADAS))
def test_osul_y_ausr_traen_solo_las_columnas_confirmadas(tabla: str):
    [ruta] = [r for r in TABLAS_ARCHIVO if r.stem == tabla]
    # Lista cerrada: una columna nueva (contraseñas, llaves, hashes como ChkHash) falla aquí.
    assert _columnas(_texto(ruta)) == COLUMNAS_CONFIRMADAS[tabla]


def test_la_columna_de_fecha_de_cada_registro_esta_en_su_consulta():
    import archivo

    for tabla in archivo.TABLAS:
        if tabla.modo == "registro":
            columnas = _columnas(_texto(QUERIES / tabla.consulta))
            assert tabla.columna_fecha in columnas, tabla.tabla


def test_ohem_solo_nombre_cargo_area_y_correo():
    sql = _texto(QUERIES / "archivo" / "ORGANIZACION" / "OHEM.sql")
    assert set(_columnas(sql)) == OHEM_PERMITIDAS


# --- Columnas sensibles de empleados y usuarios (plan §5) ----------------------------
#
# Lista negra sobre CUALQUIER consulta, no solo la del archivo: si una consulta lee
# OHEM (empleados) no puede traer cédula, pasaporte, salario, banco, teléfono o
# dirección de la casa ni fecha de nacimiento; si lee OUSR o AUSR, ninguna columna
# con PASSWORD en el nombre.
OHEM_PROHIBIDAS = (
    "govID", "passportNo", "salary", "salaryUnit", "bankCode", "bankBranch",
    "bankAcount", "homeTel", "homeStreet", "birthDate",
)
PROHIBIDAS_POR_TABLA: dict[str, re.Pattern[str]] = {
    "OHEM": re.compile(r"\b(?:" + "|".join(OHEM_PROHIBIDAS) + r")\b", re.IGNORECASE),
    "OUSR": re.compile(r"\w*PASSWORD\w*", re.IGNORECASE),
    "AUSR": re.compile(r"\w*PASSWORD\w*", re.IGNORECASE),
}


def _tablas_leidas(sql: str) -> set[str]:
    """Tablas de los FROM y JOIN (sin comentarios), en mayúsculas; con el esquema
    delante ("SEGUREX"."OHEM") cuenta la tabla."""
    return {
        t.upper()
        for t in re.findall(
            r'\b(?:FROM|JOIN)\s+(?:"?[\w@]+"?\.)?"?([\w@]+)"?', _sin_comentarios(sql), re.IGNORECASE
        )
    }


def columnas_sensibles(sql: str) -> list[str]:
    """Columnas prohibidas que trae la consulta según las tablas que lee."""
    codigo = _sin_comentarios(sql)
    encontradas: list[str] = []
    for tabla in sorted(_tablas_leidas(sql) & PROHIBIDAS_POR_TABLA.keys()):
        encontradas += PROHIBIDAS_POR_TABLA[tabla].findall(codigo)
    return encontradas


@pytest.mark.parametrize("ruta", ARCHIVOS, ids=_id)
def test_ninguna_consulta_trae_columnas_sensibles_de_empleados_o_usuarios(ruta: Path):
    assert columnas_sensibles(_texto(ruta)) == []


@pytest.mark.parametrize("sql, esperadas", [
    ('SELECT T0."empID", T0."govID", T0."salary"\nFROM "OHEM" T0', ["govID", "salary"]),
    ('SELECT T0."empID", T1."bankAcount"\nFROM "OUSR" T0\nJOIN "OHEM" T1 ON 1 = 1', ["bankAcount"]),
    ('SELECT T0."USERID", T0."PASSWORD4"\nFROM "OUSR" T0', ["PASSWORD4"]),
    ('SELECT T0."USERID", T0."U_Password"\nFROM "AUSR" T0', ["U_Password"]),
    # Sin falsos positivos: otra tabla, otra columna parecida o solo en un comentario.
    ('SELECT T0."salary"\nFROM "OCRD" T0', []),
    ('SELECT T0."salaryHistory", T0."birthDateText"\nFROM "OHEM" T0', []),
    ('-- nunca T0."govID" ni PASSWORD\nSELECT T0."empID"\nFROM "OHEM" T0', []),
    # Con el esquema delante también cuenta la tabla, no el esquema.
    ('SELECT T0."govID"\nFROM "SEGUREX"."OHEM" T0', ["govID"]),
])
def test_columnas_sensibles_detecta_solo_las_prohibidas(sql: str, esperadas: list[str]):
    assert columnas_sensibles(sql) == esperadas


def test_hbt_descubre_tablas_y_columnas_sin_parametros():
    for nombre in ("hbt_tablas.sql", "hbt_columnas.sql"):
        codigo = _sin_comentarios(_texto(QUERIES / "archivo" / nombre))
        assert "CURRENT_SCHEMA" in codigo
        assert "LIKE '@HBT%'" in codigo
    assert '"POSITION"' in _texto(QUERIES / "archivo" / "hbt_columnas.sql")
