"""Carga de las consultas de robot/queries y los filtros que el robot les agrega.

Cada archivo .sql corre tal cual en el Query Manager de SAP B1 (sin
parámetros). El robot no lo edita: lo envuelve en una subconsulta y filtra por
fuera (cambios desde una hora, socios enviados, conteo). El `X.*` de los
envoltorios solo proyecta las columnas que el archivo ya lista una por una: no
es un SELECT de todas las columnas de una tabla de SAP. HANA admite un
ORDER BY dentro de una subconsulta, así que el orden del archivo se conserva.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath

import config
from config import BOGOTA, EmpresaHana
from esquema import PARTES, PRECIOS, Columna, Parte

TROZO_SOCIOS = 500  # códigos por IN (...) en direcciones y contactos

# Campos de usuario que solo existen en Segurex: el id del pedido de la app
# (U_SGX_IdPedidoApp) en VENTAS (contrato §10) y PEDIDOS (§11.2), y la familia del
# artículo (OITM.U_GSP_FAMILIA) en PEDIDOS. Cada consulta lleva la expresión de Segurex
# con su marcador al final de la línea (`-- @id_pedido_app`, `-- @familia`); en las demás
# empresas el robot la cambia por un NULL del mismo tipo. La expresión regular de VENTAS
# es la del gestor (etl/config.py, 9e2f877).
MARCADOR_ID_PEDIDO_APP = "@id_pedido_app"
EMPRESAS_CON_CAMPOS_SGX = ("SGX",)
ID_PEDIDO_APP_NULO = "CAST(NULL AS NVARCHAR(254))"
_RE_ID_PEDIDO_APP = re.compile(
    r'CAST\([^\n]*?\)(?=[ \t]+AS[ \t]+"IdPedidoApp"[ \t]*--[ \t]*@id_pedido_app)'
)


@dataclass(frozen=True)
class CampoMarcado:
    """Expresión `CAST(...) AS "<alias>"` de un campo que solo vale en algunas empresas
    (`empresas`; por defecto, los campos de Segurex), con su marcador al final de la línea;
    en las demás empresas se cambia por `nulo`."""

    marcador: str
    alias: str
    nulo: str
    patron: re.Pattern[str]
    empresas: tuple[str, ...] = EMPRESAS_CON_CAMPOS_SGX


def _campo_de_pedidos(marcador: str, alias: str, nulo: str) -> CampoMarcado:
    # En PEDIDOS los campos no van al final del SELECT: el alias lleva su coma.
    patron = re.compile(
        r'CAST\([^\n]*?\)(?=[ \t]+AS[ \t]+"' + re.escape(alias)
        + r'",[ \t]*--[ \t]*' + re.escape(marcador) + r")"
    )
    return CampoMarcado(marcador, alias, nulo, patron)


ID_PEDIDO_APP_VENTAS = CampoMarcado(
    MARCADOR_ID_PEDIDO_APP, "IdPedidoApp", ID_PEDIDO_APP_NULO, _RE_ID_PEDIDO_APP
)
# PEDIDOS (contrato §11.2): ORDR.U_SGX_IdPedidoApp y OITM.U_GSP_FAMILIA, solo en Segurex.
CAMPOS_SGX_PEDIDOS = (
    _campo_de_pedidos(MARCADOR_ID_PEDIDO_APP, "id_pedido_app", ID_PEDIDO_APP_NULO),
    _campo_de_pedidos("@familia", "familia", "CAST(NULL AS NVARCHAR(100))"),
)

# Primer día de la ventana de VENTAS y PRODUCCION (contrato §10.1 y §12): la misma
# expresión de las consultas, calculada por HANA. Nunca con el reloj del PC.
EXPRESION_VENTANA = "ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))"
SQL_VENTANA = f"SELECT {EXPRESION_VENTANA} FROM DUMMY"


def sql_desde_fecha(sql: str, dia: str) -> str:
    """La consulta con el primer día de su ventana fijado en `dia` (AAAA-MM-DD).

    Para la carga inicial de PRODUCCION (contrato §12): cambia cada aparición de la
    expresión de la ventana por esa fecha. La fecha se valida antes de escribirla en el
    SQL; si la consulta no tiene la expresión, falla en vez de traer otra ventana.
    """
    fecha = date.fromisoformat(dia)
    if fecha.isoformat() != dia:
        raise ValueError(f"La fecha de la ventana debe ser AAAA-MM-DD: {dia!r}.")
    if EXPRESION_VENTANA not in sql:
        raise config.ConfigError(
            f"La consulta no tiene la expresión de la ventana ({EXPRESION_VENTANA}); no se corre."
        )
    return sql.replace(EXPRESION_VENTANA, f"TO_DATE('{dia}', 'YYYY-MM-DD')")


# `<columna> >= <expresión de la ventana>`: la columna con su alias de tabla (T0."DocDate").
_RE_FILTRO_VENTANA = re.compile(
    r'(?P<columna>(?:[A-Za-z_]\w*\.)?(?:"[^"\n]+"|[A-Za-z_]\w*))(?P<espacio>\s*)>=\s*'
    + re.escape(EXPRESION_VENTANA)
)


def _partir_comentario(linea: str) -> tuple[str, str]:
    """(código, comentario) de una línea: el comentario empieza en el primer `--` que no
    está dentro de un texto ('...') ni de un nombre entre comillas ("...")."""
    comilla: str | None = None
    for i, caracter in enumerate(linea):
        if comilla:
            if caracter == comilla:
                comilla = None
        elif caracter in ("'", '"'):
            comilla = caracter
        elif linea.startswith("--", i):
            return linea[:i], linea[i:]
    return linea, ""


def _fecha_sql(dia: date) -> str:
    return f"TO_DATE('{dia.isoformat()}', 'YYYY-MM-DD')"


def sql_rango(sql: str, desde: date, hasta: date) -> str:
    """La consulta con su ventana cambiada por el rango cerrado de `desde` a `hasta`.

    Para el histórico de VENTAS (contrato §10.4): la consulta es la misma de la nocturna
    y solo cambia el filtro de la fecha. Cada `<columna> >= <expresión de la ventana>`
    del código pasa a `<columna> BETWEEN <desde> AND <hasta>` sobre la misma columna, así
    que las dos nunca se separan. Los comentarios no cuentan y no se tocan.

    Falla con ConfigError si el código no tiene la expresión o si una aparición no tiene
    esa forma: así nunca corre una consulta con otra ventana. Las fechas solo llegan
    como `date`, nunca como texto.
    """
    for dia in (desde, hasta):
        if not isinstance(dia, date) or isinstance(dia, datetime):
            raise TypeError(f"El rango de la consulta va con fechas (date), no {type(dia).__name__}.")
    if hasta < desde:
        raise ValueError(f"El rango de la consulta va al revés: {desde} a {hasta}.")
    rango = f"BETWEEN {_fecha_sql(desde)} AND {_fecha_sql(hasta)}"
    lineas = sql.split("\n")
    cambios = 0
    for i, linea in enumerate(lineas):
        codigo, comentario = _partir_comentario(linea)
        apariciones = codigo.count(EXPRESION_VENTANA)
        if not apariciones:
            continue
        nuevo, cambiadas = _RE_FILTRO_VENTANA.subn(
            lambda m: f"{m['columna']}{m['espacio']}{rango}", codigo
        )
        if cambiadas != apariciones:
            raise config.ConfigError(
                f"La consulta usa la expresión de la ventana ({EXPRESION_VENTANA}) fuera de un filtro "
                f"`<columna> >= ...` en la línea {i + 1}; no se corre con un rango."
            )
        lineas[i] = nuevo + comentario
        cambios += cambiadas
    if not cambios:
        raise config.ConfigError(
            f"La consulta no tiene la expresión de la ventana ({EXPRESION_VENTANA}); no se corre."
        )
    return "\n".join(lineas)


# Kilos de VENTAS (orden 016): la columna «Tot KG» de la consulta guardada «AnálisisVentas-1»
# de Derivados (INV1.Quantity * OITM.NumInSale, y por -1 en RIN1) es la última del SELECT de
# ventas.sql, con esta etiqueta, el signo de "Cantidad" y el marcador `-- @kilos` al final de
# la línea. Una línea sin artículo o sin NumInSale va en NULL: la API la guarda así (contrato
# §10 y §10.5). Si la consulta no trae la columna, todo lo que necesita kilos falla cerrado
# (exigir_kilos y sql_ventas): nunca se envían kilos inventados.
MARCADOR_KILOS = "@kilos"
ALIAS_KILOS = "Kilos"
# Empresas donde la expresión de kilos es de verdad: «AnálisisVentas-1» es de Derivados y en
# Segurex no está confirmado que OITM.NumInSale sean kilos. En las demás, la expresión marcada
# cambia por KILOS_NULO (sql_ventas), y el modo de kilos solo corre en estas.
EMPRESAS_CON_KILOS = ("SDC",)
KILOS_NULO = "CAST(NULL AS DECIMAL(19, 6))"
KILOS_VENTAS = CampoMarcado(
    MARCADOR_KILOS, ALIAS_KILOS, KILOS_NULO,
    re.compile(r'CAST\([^\n]*?\)(?=[ \t]+AS[ \t]+"Kilos"[ \t]*--[ \t]*@kilos)'),
    EMPRESAS_CON_KILOS,
)
# El envoltorio la nombra entre comillas (X."Kilos"): en HANA eso distingue mayúsculas, así
# que la etiqueta va exacta; solo AS puede ir en minúsculas.
_RE_ALIAS_KILOS = re.compile(r'\b(?i:AS)\s+"' + re.escape(ALIAS_KILOS) + '"')


def _sin_comentarios(sql: str) -> str:
    return "\n".join(_partir_comentario(linea)[0] for linea in sql.split("\n"))


def exigir_kilos(sql: str) -> None:
    """Falla con ConfigError si la consulta de ventas no trae la columna de kilos.

    Busca `AS "Kilos"` en el código; los comentarios no cuentan. El modo de kilos la llama
    antes de esperar el candado o subir la VPN: sin la expresión de «Tot KG» no corre.
    """
    if not _RE_ALIAS_KILOS.search(_sin_comentarios(sql)):
        raise config.ConfigError(
            f'La consulta de ventas no trae la columna de kilos (... AS "{ALIAS_KILOS}" al final del '
            f"SELECT, donde va el marcador -- {MARCADOR_KILOS}): falta la expresión de «Tot KG» de "
            "«AnálisisVentas-1» (orden 016). No se corre, para no enviar kilos inventados ni vacíos."
        )


def columnas_kilos() -> tuple[Columna, ...]:
    """Columnas de los kilos de VENTAS, las de la parte ventas, en su orden: la llave, su
    columna de la ventana (fecha_contabilizacion) y kilos, la última (contrato §10.5). La
    llave y la fecha son obligatorias; kilos puede llegar vacío si SAP no tiene peso."""
    ventas = PARTES["ventas"]
    return tuple(
        c for c in ventas.columnas
        if c.nombre in ventas.llave or c.nombre in (ventas.columna_ventana, "kilos")
    )


def sql_kilos(sql: str, desde: date, hasta: date) -> str:
    """La consulta de ventas de una empresa (sql_de_empresa) con el rango de `desde` a
    `hasta` (sql_rango), de la que solo salen la llave, la fecha y los kilos.

    Las columnas van una por una, con las etiquetas de la consulta. Falla con ConfigError si
    la consulta no trae kilos (exigir_kilos) o no tiene la expresión de la ventana. El
    conteo es sql_contar de esta misma consulta.
    """
    exigir_kilos(sql)
    lista = ", ".join(f'X."{c.hana}"' for c in columnas_kilos())
    return f"SELECT {lista} FROM (\n{sql_rango(sql, desde, hasta)}\n) X"


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


def sql_id_pedido_app(sql: str, empresa: str) -> str:
    """La consulta de ventas con solo el id del pedido de la app de la empresa: tal cual en
    Segurex; en las demás, con la expresión marcada `-- @id_pedido_app` cambiada por un NULL
    (contrato §10). Los kilos no cambian: la consulta de una empresa es sql_ventas.

    Si el marcador falta, se repite o la expresión no se reconoce, falla en vez de
    correr: sin él, Derivados pediría una columna que no tiene.
    """
    return _campos_de_empresa(sql, empresa, (ID_PEDIDO_APP_VENTAS,), "ventas")


def sql_ventas(sql: str, empresa: str) -> str:
    """La consulta de ventas para una empresa (contrato §10): el id del pedido de la app
    como en sql_id_pedido_app y los kilos tal cual en EMPRESAS_CON_KILOS; en las demás, la
    expresión marcada `-- @kilos` cambia por KILOS_NULO.

    Falla igual que sql_id_pedido_app si una de las dos marcas falta, se repite o su
    expresión no se reconoce: sin la de kilos, Segurex leería NumInSale como kilos.
    """
    return _campos_de_empresa(sql, empresa, (ID_PEDIDO_APP_VENTAS, KILOS_VENTAS), "ventas")


def sql_pedidos(sql: str, empresa: str) -> str:
    """La consulta de pedidos para una empresa: tal cual en Segurex; en las demás, con
    las expresiones marcadas `-- @id_pedido_app` y `-- @familia` cambiadas por un NULL
    (contrato §11.2). Falla igual que sql_id_pedido_app si una marca no se reconoce."""
    return _campos_de_empresa(sql, empresa, CAMPOS_SGX_PEDIDOS, "pedidos")


def sql_de_empresa(parte: Parte, sql: str, empresa: str) -> str:
    """El texto de la consulta de una parte para una empresa, sin filtros: en VENTAS y
    PEDIDOS, los campos que solo tiene Segurex cambian por NULL en las demás empresas, y en
    VENTAS los kilos, que solo son de verdad en Derivados, cambian por NULL en Segurex."""
    if parte.conjunto == "VENTAS":
        return sql_ventas(sql, empresa)
    if parte.conjunto == "PEDIDOS":
        return sql_pedidos(sql, empresa)
    return sql


def _campos_de_empresa(sql: str, empresa: str, campos: tuple[CampoMarcado, ...], que: str) -> str:
    """La consulta con cada campo marcado cambiado por su NULL si la empresa no está en las
    del campo. Todos los marcadores se revisan en todas las empresas."""
    cambiada = sql
    for campo in campos:
        marcadores = sql.count(campo.marcador)
        nula, expresiones = campo.patron.subn(campo.nulo, cambiada)
        if marcadores != 1 or expresiones != 1:
            raise config.ConfigError(
                f"La consulta de {que} debe tener exactamente una expresión "
                f'CAST(...) AS "{campo.alias}" marcada con \'-- {campo.marcador}\' en la misma '
                f"línea (marcadores: {marcadores}, expresiones: {expresiones}); no se corre."
            )
        if empresa not in campo.empresas:
            cambiada = nula
    return cambiada


def leer_parte(parte: Parte, empresa: EmpresaHana) -> str:
    """Consulta de una parte para una empresa, con el filtro propio de la empresa.

    Dos partes cambian por empresa y lo hacen afuera del archivo, que es uno solo y
    corre tal cual en el Query Manager: `precios` trae todas las listas y el robot se
    queda con la pública, por número (HANA_<EMPRESA>_LISTA_PRECIOS); `cartera` trae
    todas las cuentas y se queda con las de la empresa (HANA_<EMPRESA>_CUENTAS_CARTERA).
    `ventas` es la consulta del gestor: en Derivados cambia la expresión marcada del id
    del pedido de la app por un NULL y en Segurex la de los kilos (sql_ventas); `pedidos`
    cambia en Derivados el id del pedido de la app y la familia (sql_pedidos).
    """
    sql = sql_de_empresa(parte, leer(parte.consulta, empresa.esquema), empresa.codigo)
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
