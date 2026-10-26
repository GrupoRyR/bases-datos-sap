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
