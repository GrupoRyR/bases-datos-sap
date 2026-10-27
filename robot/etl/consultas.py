"""Carga de las consultas de robot/queries y los filtros que el robot les agrega.

Cada archivo .sql corre tal cual en el Query Manager de SAP B1 (sin
parámetros). El robot no lo edita: lo envuelve en una subconsulta y filtra por
fuera (cambios desde una hora, socios enviados, conteo). El `X.*` de los
envoltorios solo proyecta las columnas que el archivo ya lista una por una: no
es un SELECT de todas las columnas de una tabla de SAP. HANA admite un
ORDER BY dentro de una subconsulta, así que el orden del archivo se conserva.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePosixPath

import config
from config import BOGOTA, EmpresaHana
from esquema import PRECIOS, Parte

TROZO_SOCIOS = 500  # códigos por IN (...) en direcciones y contactos


def ruta_consulta(nombre_relativo: str, esquema: str) -> Path:
    """Ruta de una consulta relativa a robot/queries (ej: "maestros/precios.sql").

    Para un archivo directo bajo maestros/, `maestros/<ESQUEMA>/<archivo>` gana sobre
    `maestros/<archivo>` (ninguna parte lo usa hoy: las que cambian por empresa, como
    los precios y la cartera, se filtran afuera con la configuración de la empresa).
    """
    base = config.QUERIES_DIR  # se lee aquí: las pruebas lo cambian
    partes = PurePosixPath(nombre_relativo).parts
    candidatas: list[Path] = []
    if len(partes) == 2 and partes[0] == "maestros" and esquema:
        candidatas.append(base / "maestros" / esquema / partes[1])
    candidatas.append(base.joinpath(*partes))
    for ruta in candidatas:
        if ruta.is_file():
            return ruta
    raise config.ConfigError(
        "No existe la consulta "
        + " ni ".join(str(r) for r in candidatas)
        + f" (esquema {esquema or 'sin esquema'})."
    )


def leer(nombre_relativo: str, esquema: str) -> str:
    """Texto de la consulta sin el `;` final (sirve en el Query Manager, no en una subconsulta)."""
    texto = ruta_consulta(nombre_relativo, esquema).read_text(encoding="utf-8-sig")
    texto = texto.rstrip()
    while texto.endswith(";"):
        texto = texto[:-1].rstrip()
    return texto


def _envolver(sql: str, condicion: str) -> str:
    # El salto de línea antes de ")" evita que un comentario final (-- ...) se
    # coma el cierre de la subconsulta.
    return f"SELECT X.* FROM (\n{sql}\n) X WHERE {condicion}"


def sql_cambios(sql: str) -> str:
    """Filas con actualizado_en_sap >= ? (modo `cambios`, contrato §5.1)."""
    return _envolver(sql, 'X."actualizado_en_sap" >= ?')


def sql_por_socios(sql: str, n: int) -> str:
    """Filas de `n` socios (direcciones y contactos), con un ? por código."""
    if n < 1:
        raise ValueError("sql_por_socios necesita al menos un código de socio.")
    marcas = ", ".join("?" for _ in range(n))
    return _envolver(sql, f'X."codigo_socio" IN ({marcas})')


def sql_lista_precios(sql: str, lista: int) -> str:
    """Solo las filas de la lista de precios `lista` (parte precios, por número)."""
    return _envolver(sql, f'X."lista_codigo" = {int(lista)}')


def sql_cuentas(sql: str, cuentas: tuple[str, ...]) -> str:
    """Solo las filas de esas cuentas contables (parte cartera).

    Filtra por la etiqueta `Cuenta visible` (JDT1.Account), que la consulta ya trae. Las
    cuentas son solo dígitos (config._cuentas), así que van como texto sin riesgo.
    """
    lista = ", ".join(f"'{cuenta}'" for cuenta in cuentas)
    return _envolver(sql, f'X."Cuenta visible" IN ({lista})')


def leer_parte(parte: Parte, empresa: EmpresaHana) -> str:
    """Consulta de una parte para una empresa, con el filtro propio de la empresa.

    Dos partes cambian por empresa y lo hacen afuera del archivo, que es uno solo y
    corre tal cual en el Query Manager: `precios` trae todas las listas y el robot se
    queda con la pública, por número (HANA_<EMPRESA>_LISTA_PRECIOS); `cartera` trae
    todas las cuentas y se queda con las de la empresa (HANA_<EMPRESA>_CUENTAS_CARTERA).
    """
    sql = leer(parte.consulta, empresa.esquema)
    if parte.nombre == PRECIOS:
        if empresa.lista_precios is None:
            raise empresa.error_sin_precios()
        return sql_lista_precios(sql, empresa.lista_precios)
    if parte.conjunto == "CARTERA":
        if not empresa.cuentas_cartera:
            raise config.ConfigError(
                f"{empresa.codigo} no tiene cuentas de cartera: pon sus números separados por coma en "
                f"{empresa.variable_cuentas_cartera} (robot/.env)."
            )
        return sql_cuentas(sql, empresa.cuentas_cartera)
    return sql


def sql_contar(sql: str) -> str:
    """COUNT(*) con los mismos filtros de la extracción (conteo_sap, contrato §4.3)."""
    return f"SELECT COUNT(*) FROM (\n{sql}\n) X"


def desde_a_parametro(desde: str | None) -> datetime | None:
    """`desde` de la API (ISO 8601 con zona) -> hora local de Bogotá sin zona.

    actualizado_en_sap es un TIMESTAMP sin zona en hora de Bogotá, así que el
    parámetro debe ir igual. Una hora sin zona se toma como de Bogotá.
    """
    if desde is None:
        return None
    try:
        momento = datetime.fromisoformat(desde.strip())
    except (AttributeError, ValueError):
        raise ValueError(f"El desde de la API no es una hora ISO 8601: {desde!r}") from None
    if momento.tzinfo is not None:
        momento = momento.astimezone(BOGOTA).replace(tzinfo=None)
    return momento


def trozos(codigos: list[str], tamano: int = TROZO_SOCIOS) -> list[list[str]]:
    """Parte la lista en trozos de hasta `tamano` códigos, en el mismo orden."""
    if tamano < 1:
        raise ValueError("El tamaño del trozo debe ser al menos 1.")
    return [codigos[i:i + tamano] for i in range(0, len(codigos), tamano)]
