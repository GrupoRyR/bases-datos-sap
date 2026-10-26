"""Revisión estática de robot/queries: reglas del plan §5 y columnas del contrato."""
from __future__ import annotations

import re
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
        assert ruta == QUERIES / "maestros" / esquema / "precios.sql"
    assert not (QUERIES / "maestros" / "precios.sql").exists()


def test_precios_solo_lista_publica():
    for esquema in ESQUEMAS:
        sql = _sin_comentarios(_texto(QUERIES / "maestros" / esquema / "precios.sql"))
        assert "\"ListName\" = 'PÚBLICA'" in sql


def test_cartera_trae_todas_las_etiquetas_del_esquema():
    sql = _texto(QUERIES / PARTES["cartera"].consulta)
    for columna in PARTES["cartera"].columnas:
        assert f'"{columna.hana}"' in sql, columna.hana
    assert "GESTOR_CARTERA/etl/queries/cartera.sql" in sql


@pytest.mark.parametrize("archivo", [
    "maestros/articulos.sql",
    "maestros/SEGUREX/precios.sql",
    "maestros/HBT_SDERIVADOS/precios.sql",
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
