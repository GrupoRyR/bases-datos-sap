from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

import esquema
from fake_hana import fila
from esquema import (
    BOOL,
    CANTIDAD,
    ENTERO,
    FECHA,
    HORA,
    MONTO,
    PARTES,
    TEXTO,
    ColumnasInesperadas,
    LlaveRepetida,
    ValorInvalido,
    indices,
    preparar_filas,
    serializar,
)

# Columnas del contrato (docs/contrato-robot.md §5.2, §6 y §10), en su orden.
SOCIO = [
    "codigo", "nombre", "nombre_extranjero", "nit", "grupo_codigo", "vendedor_codigo",
    "condicion_pago_codigo", "lista_precios_codigo", "telefono", "telefono_2", "celular",
    "correo", "ciudad", "limite_credito", "socio_vinculado", "activo",
    "actualizado_en_sap", "creado_en_sap",
]
COLUMNAS = {
    "clientes": SOCIO,
    "proveedores": SOCIO,
    "direcciones": [
        "codigo_socio", "tipo", "nombre", "calle", "barrio", "ciudad", "municipio_codigo",
        "departamento", "pais", "codigo_postal",
    ],
    "contactos": [
        "contacto_id", "codigo_socio", "nombre", "nombres", "apellidos", "cargo", "telefono",
        "celular", "correo", "activo",
    ],
    "articulos": [
        "codigo", "nombre", "nombre_extranjero", "grupo_codigo", "marca_codigo",
        "unidad_venta", "codigo_barras", "inventariable", "de_venta", "de_compra", "activo",
        "actualizado_en_sap", "creado_en_sap",
    ],
    "grupos_articulos": ["codigo", "nombre", "activo"],
    "marcas": ["codigo", "nombre", "activo"],
    "precios": ["articulo_codigo", "lista_codigo", "lista_nombre", "precio", "moneda", "activo"],
    "vendedores": ["codigo", "nombre", "correo", "celular", "activo"],
    "grupos_clientes": ["codigo", "nombre", "activo"],
    "condiciones_pago": ["codigo", "nombre", "dias_extra", "meses_extra", "activo"],
    "municipios": ["codigo", "nombre", "activo"],
    "cartera": [
        "codigo_sn", "slp_code", "email_asesor", "nombre_sn", "nit", "grupo", "municipio",
        "cuenta_visible", "tipo_doc", "documento", "documento_base", "referencia_1",
        "no_referencia", "asesor", "total_plazos", "no_plazo", "condicion_pago",
        "fecha_contabilizacion", "fecha_vencimiento", "fecha_documento", "dias",
        "limite_credito", "importe_original", "base_gravable", "saldo_base", "saldo_vencido",
        "valor_abonado", "sin_vencer", "valor_cheques", "d_0_30", "d_31_60", "d_61_90",
        "d_91_120", "d_121_150", "d_151_180", "d_mas_180", "saldo", "rango",
    ],
    "ventas": [
        "tipo_objeto", "doc_entry", "numero_documento", "linea", "clase_documento",
        "estado_documento", "fecha_documento", "fecha_contabilizacion", "slp_code", "vendedor",
        "canal", "codigo_cliente", "cliente", "nit", "ciudad", "pedido", "id_pedido_app",
        "oc_cliente", "ciudad_envio", "direccion_envio", "marca", "familia", "codigo_articulo",
        "descripcion", "cantidad", "costo_unitario", "costo_total", "precio_lista",
        "precio_unitario", "total", "iva", "moneda", "trm", "comentarios",
    ],
}
REQUERIDAS = {
    "clientes": {"codigo", "nombre", "activo", "actualizado_en_sap"},
    "proveedores": {"codigo", "nombre", "activo", "actualizado_en_sap"},
    "direcciones": {"codigo_socio", "tipo", "nombre"},
    "contactos": {"contacto_id", "codigo_socio", "nombre", "activo"},
    "articulos": {"codigo", "nombre", "activo", "actualizado_en_sap"},
    "grupos_articulos": {"codigo", "nombre", "activo"},
    "marcas": {"codigo", "nombre", "activo"},
    "precios": {"articulo_codigo", "lista_codigo", "lista_nombre", "activo"},
    "vendedores": {"codigo", "nombre", "activo"},
    "grupos_clientes": {"codigo", "nombre", "activo"},
    "condiciones_pago": {"codigo", "nombre", "activo"},
    "municipios": {"codigo", "nombre", "activo"},
    "cartera": {"codigo_sn", "documento", "fecha_vencimiento", "dias", "saldo"},
    "ventas": {
        "tipo_objeto", "doc_entry", "numero_documento", "linea", "clase_documento",
        "estado_documento", "fecha_documento", "fecha_contabilizacion", "slp_code",
        "codigo_cliente", "cantidad", "total",
    },
}
LLAVES = {
    "clientes": ("codigo",),
    "proveedores": ("codigo",),
    "direcciones": ("codigo_socio", "tipo", "nombre"),
    "contactos": ("contacto_id",),
    "articulos": ("codigo",),
    "grupos_articulos": ("codigo",),
    "marcas": ("codigo",),
    "precios": ("articulo_codigo",),
    "vendedores": ("codigo",),
    "grupos_clientes": ("codigo",),
    "condiciones_pago": ("codigo",),
    "municipios": ("codigo",),
    "cartera": (),
    "ventas": ("tipo_objeto", "doc_entry", "linea"),
}
MODOS = {
    "clientes": "cambios", "proveedores": "cambios", "articulos": "cambios",
    "direcciones": "socio", "contactos": "socio",
    "grupos_articulos": "todo", "marcas": "todo", "precios": "todo", "vendedores": "todo",
    "grupos_clientes": "todo", "condiciones_pago": "todo", "municipios": "todo",
    "cartera": "todo", "ventas": "todo",
}
CONJUNTOS = {"cartera": "CARTERA", "ventas": "VENTAS"}
MAESTROS = [p for p in COLUMNAS if p not in CONJUNTOS]


def test_estan_todas_las_partes_del_contrato():
    assert list(PARTES) == list(COLUMNAS)
    assert esquema.PARTES_POR_CONJUNTO == {
        "MAESTROS": tuple(MAESTROS), "CARTERA": ("cartera",), "VENTAS": ("ventas",),
    }
    assert esquema.SOCIOS == ("clientes", "proveedores")
    assert esquema.HIJAS_DE_SOCIO == ("direcciones", "contactos")


@pytest.mark.parametrize("nombre", list(COLUMNAS))
def test_columnas_llave_obligatorias_y_modo(nombre):
    parte = PARTES[nombre]
    assert parte.nombre == nombre
    assert parte.nombres == COLUMNAS[nombre]
    assert {c.nombre for c in parte.columnas if c.requerida} == REQUERIDAS[nombre]
    assert parte.llave == LLAVES[nombre]
    assert parte.modo_solicitud == MODOS[nombre]
    assert parte.incremental == (nombre in {"clientes", "proveedores", "articulos"})
    assert parte.conjunto == CONJUNTOS.get(nombre, "MAESTROS")


@pytest.mark.parametrize("nombre", MAESTROS)
def test_en_maestros_el_alias_es_el_nombre_del_contrato(nombre):
    assert all(c.hana == c.nombre for c in PARTES[nombre].columnas)
    assert PARTES[nombre].consulta == f"maestros/{nombre}.sql"


def test_cartera_usa_las_etiquetas_del_gestor():
    cartera = PARTES["cartera"]
    assert cartera.consulta == "cartera/cartera.sql"
    hana = {c.nombre: c.hana for c in cartera.columnas}
    assert hana["codigo_sn"] == "Código SN"
    assert hana["asesor"] == "Empleado ventas / compras"
    assert hana["valor_cheques"] == "Valor cheques aplicados"
    assert hana["d_mas_180"] == "> 180"
    assert len(set(hana.values())) == len(hana)


def test_ventas_usa_las_etiquetas_del_gestor():
    ventas = PARTES["ventas"]
    assert ventas.consulta == "ventas/ventas.sql"
    hana = {c.nombre: c.hana for c in ventas.columnas}
    assert hana == {
        "tipo_objeto": "Tipo objeto", "doc_entry": "DocEntry", "numero_documento": "Número documento",
        "linea": "Línea", "clase_documento": "Clase documento", "estado_documento": "Estado documento",
        "fecha_documento": "Fecha documento", "fecha_contabilizacion": "Fecha contabilización",
        "slp_code": "SlpCode", "vendedor": "Vendedor", "canal": "Canal",
        "codigo_cliente": "Código cliente", "cliente": "Cliente", "nit": "Nit", "ciudad": "Ciudad",
        "pedido": "Pedido", "id_pedido_app": "Id pedido app", "oc_cliente": "OC cliente",
        "ciudad_envio": "Ciudad envío", "direccion_envio": "Dirección envío", "marca": "Marca",
        "familia": "Familia", "codigo_articulo": "Código artículo", "descripcion": "Descripción",
        "cantidad": "Cantidad", "costo_unitario": "Costo unitario", "costo_total": "Costo total",
        "precio_lista": "Precio lista", "precio_unitario": "Precio unitario", "total": "Total",
        "iva": "IVA", "moneda": "Moneda", "trm": "TRM", "comentarios": "Comentarios",
    }


def _tipos(nombre: str) -> dict[str, str]:
    return {c.nombre: c.tipo for c in PARTES[nombre].columnas}


def test_tipos_de_maestros():
    socio = _tipos("clientes")
    for columna in ("grupo_codigo", "vendedor_codigo", "condicion_pago_codigo",
                    "lista_precios_codigo"):
        assert socio[columna] == ENTERO
    assert socio["limite_credito"] == MONTO
    assert socio["activo"] == BOOL
    assert socio["actualizado_en_sap"] == HORA
    assert socio["creado_en_sap"] == FECHA
    assert socio["codigo"] == TEXTO and socio["socio_vinculado"] == TEXTO
    assert _tipos("proveedores") == socio

    articulo = _tipos("articulos")
    assert articulo["grupo_codigo"] == ENTERO and articulo["marca_codigo"] == ENTERO
    for columna in ("inventariable", "de_venta", "de_compra", "activo"):
        assert articulo[columna] == BOOL
    assert articulo["actualizado_en_sap"] == HORA and articulo["creado_en_sap"] == FECHA

    for nombre in ("grupos_articulos", "marcas", "vendedores", "grupos_clientes",
                   "condiciones_pago"):
        assert _tipos(nombre)["codigo"] == ENTERO
        assert _tipos(nombre)["activo"] == BOOL
    assert _tipos("municipios")["codigo"] == TEXTO
    assert _tipos("contactos")["contacto_id"] == ENTERO
    assert _tipos("contactos")["activo"] == BOOL
    assert _tipos("precios")["lista_codigo"] == ENTERO
    assert _tipos("precios")["precio"] == MONTO
    assert _tipos("condiciones_pago")["dias_extra"] == ENTERO
    assert _tipos("condiciones_pago")["meses_extra"] == ENTERO
    assert set(_tipos("direcciones").values()) == {TEXTO}


def test_tipos_de_cartera():
    tipos = _tipos("cartera")
    enteros = {"slp_code", "total_plazos", "no_plazo", "dias"}
    fechas = {"fecha_contabilizacion", "fecha_vencimiento", "fecha_documento"}
    nombres = COLUMNAS["cartera"]
    montos = set(nombres[nombres.index("limite_credito"):nombres.index("saldo") + 1])
    assert {"d_0_30", "d_mas_180", "valor_cheques"} <= montos
    for nombre, tipo in tipos.items():
        if nombre in enteros:
            assert tipo == ENTERO, nombre
        elif nombre in fechas:
            assert tipo == FECHA, nombre
        elif nombre in montos:
            assert tipo == MONTO, nombre
        else:
            assert tipo == TEXTO, nombre
    assert tipos["tipo_doc"] == TEXTO and tipos["documento"] == TEXTO


def test_tipos_de_ventas():
    tipos = _tipos("ventas")
    enteros = {"tipo_objeto", "doc_entry", "numero_documento", "linea", "slp_code"}
    fechas = {"fecha_documento", "fecha_contabilizacion"}
    cantidades = {"cantidad", "trm"}
    montos = {"costo_unitario", "costo_total", "precio_lista", "precio_unitario", "total", "iva"}
    for nombre, tipo in tipos.items():
        if nombre in enteros:
            assert tipo == ENTERO, nombre
        elif nombre in fechas:
            assert tipo == FECHA, nombre
        elif nombre in cantidades:
            assert tipo == CANTIDAD, nombre
        elif nombre in montos:
            assert tipo == MONTO, nombre
        else:
            assert tipo == TEXTO, nombre


def test_partes_por_solicitud_segun_contrato_7_1():
    assert esquema.PARTES_POR_SOLICITUD == {
        ("CARTERA", None): ("cartera",),
        ("VENTAS", None): ("ventas",),
        ("MAESTROS", None): tuple(MAESTROS),
        ("MAESTROS", "clientes"): ("clientes", "direcciones", "contactos"),
        ("MAESTROS", "proveedores"): ("proveedores", "direcciones", "contactos"),
        ("MAESTROS", "articulos"): ("articulos", "grupos_articulos", "marcas"),
        ("MAESTROS", "precios"): ("precios",),
        ("MAESTROS", "vendedores"): ("vendedores",),
        ("MAESTROS", "catalogos"): ("grupos_clientes", "condiciones_pago", "municipios"),
    }


# --- serializar ---------------------------------------------------------------


@pytest.mark.parametrize("valor, esperado", [
    (5, 5), (-1, -1), (Decimal("12"), 12), (Decimal("7.00"), 7), ("42", 42), (" 3 ", 3),
    (8.0, 8), (None, None), ("", None), ("  ", None),
])
def test_entero(valor, esperado):
    resultado = serializar(valor, ENTERO)
    assert resultado == esperado
    assert resultado is None or type(resultado) is int


@pytest.mark.parametrize("valor", [Decimal("1.5"), "2.5", "abc", 1.25, True])
def test_entero_invalido(valor):
    with pytest.raises(ValorInvalido, match="grupo_codigo"):
        serializar(valor, ENTERO, "grupo_codigo")


@pytest.mark.parametrize("valor, esperado", [
    ("1234.565", "1234.57"), (Decimal("1234.565"), "1234.57"), (Decimal("-1234.565"), "-1234.57"),
    (Decimal("1234567.8"), "1234567.80"), (0, "0.00"), (15, "15.00"), (2.675, "2.68"),
    (Decimal("-0.001"), "0.00"), (Decimal("1E+3"), "1000.00"), (None, None), ("", None),
])
def test_monto(valor, esperado):
    assert serializar(valor, MONTO) == esperado


@pytest.mark.parametrize("valor, esperado", [
    (Decimal("2.5"), "2.500000"), (Decimal("-2.5"), "-2.500000"), (3, "3.000000"),
    ("4100.1234565", "4100.123457"), (Decimal("-4100.1234565"), "-4100.123457"),
    (2.675, "2.675000"), (0, "0.000000"), (Decimal("-0.0000001"), "0.000000"),
    (Decimal("1E+3"), "1000.000000"), (None, None), ("", None),
])
def test_cantidad_con_hasta_seis_decimales(valor, esperado):
    assert serializar(valor, CANTIDAD) == esperado


@pytest.mark.parametrize("valor", ["1,5", "abc", Decimal("NaN"), float("inf"), True])
def test_cantidad_invalida(valor):
    with pytest.raises(ValorInvalido, match="cantidad"):
        serializar(valor, CANTIDAD, "cantidad")


def test_ventas_con_llave_repetida_falla():
    filas = [fila("ventas", 1), fila("ventas", 2, tipo_objeto=1, doc_entry=1, linea=1)]
    alias = [c.hana for c in PARTES["ventas"].columnas]
    with pytest.raises(LlaveRepetida, match="tipo_objeto, doc_entry, linea"):
        preparar_filas(PARTES["ventas"], alias, [[f[a] for a in alias] for f in filas])


@pytest.mark.parametrize("valor", ["1,234.56", "abc", Decimal("NaN"), float("inf"), True])
def test_monto_invalido(valor):
    with pytest.raises(ValorInvalido, match="saldo"):
        serializar(valor, MONTO, "saldo")


@pytest.mark.parametrize("valor, esperado", [
    (date(2026, 10, 23), "2026-10-23"), (datetime(2026, 10, 23, 18, 30), "2026-10-23"),
    ("2026-10-23", "2026-10-23"), ("2026-10-23 00:00:00", "2026-10-23"), (None, None),
])
def test_fecha(valor, esperado):
    assert serializar(valor, FECHA) == esperado


def test_fecha_invalida():
    with pytest.raises(ValorInvalido, match="creado_en_sap"):
        serializar("23/10/2026", FECHA, "creado_en_sap")


def test_hora_naive_se_toma_como_bogota():
    assert serializar(datetime(2026, 10, 23, 9, 15, 2), HORA) == "2026-10-23T09:15:02-05:00"
    assert serializar(datetime(2026, 10, 23, 9, 15, 2, 500), HORA) == "2026-10-23T09:15:02-05:00"


def test_hora_con_zona_se_convierte_a_bogota():
    utc = datetime(2026, 10, 23, 14, 15, 2, tzinfo=timezone.utc)
    assert serializar(utc, HORA) == "2026-10-23T09:15:02-05:00"
    madrid = datetime(2026, 10, 23, 16, 15, 2, tzinfo=timezone(timedelta(hours=2)))
    assert serializar(madrid, HORA) == "2026-10-23T09:15:02-05:00"
    assert serializar("2026-10-23T14:15:02Z", HORA) == "2026-10-23T09:15:02-05:00"
    assert serializar(None, HORA) is None


def test_hora_invalida():
    with pytest.raises(ValorInvalido, match="actualizado_en_sap"):
        serializar("ayer", HORA, "actualizado_en_sap")


@pytest.mark.parametrize("valor, esperado", [
    ("Y", True), ("N", False), ("y", True), ("1", True), ("0", False), (1, True), (0, False),
    (True, True), (False, False), ("True", True), ("False", False), ("t", True), ("f", False),
    (None, None), ("", None),
])
def test_bool(valor, esperado):
    assert serializar(valor, BOOL) is esperado


@pytest.mark.parametrize("valor", ["S", "si", 2])
def test_bool_invalido(valor):
    with pytest.raises(ValorInvalido, match="activo"):
        serializar(valor, BOOL, "activo")


@pytest.mark.parametrize("valor, esperado", [
    ("  Ferretería  ", "Ferretería"), ("", None), ("   ", None), (None, None),
    (Decimal("13"), "13"), (Decimal("13.00"), "13"), (Decimal("13.50"), "13.50"), (18, "18"),
    (24.0, "24"),
])
def test_texto(valor, esperado):
    assert serializar(valor, TEXTO) == esperado


def test_texto_se_recorta_a_4000():
    assert serializar("a" * 4001, TEXTO) == "a" * 4000
    assert serializar(" " + "b" * 4000 + " ", TEXTO) == "b" * 4000


# --- indices y preparar_filas ------------------------------------------------


def test_indices_falla_si_falta_una_columna():
    columnas = PARTES["marcas"].columnas
    assert indices(["activo", "nombre", "codigo"], columnas) == [2, 1, 0]
    with pytest.raises(ColumnasInesperadas, match="nombre"):
        indices(["codigo", "activo"], columnas)


def test_preparar_filas_mapea_y_serializa():
    filas = preparar_filas(
        PARTES["marcas"], ["activo", "codigo", "nombre", "sobrante"],
        [("Y", 3, " Marca A ", "x"), ("N", Decimal("4"), "Marca B", "y")],
    )
    assert filas == [[3, "Marca A", True], [4, "Marca B", False]]


def test_preparar_filas_obligatoria_vacia():
    with pytest.raises(ValorInvalido) as error:
        preparar_filas(PARTES["marcas"], ["codigo", "nombre", "activo"],
                       [(1, "A", "Y"), (2, "   ", "Y")])
    mensaje = str(error.value)
    assert "marcas" in mensaje and "nombre" in mensaje and "fila 2" in mensaje


def _socio_sin_nombre(parte: str, nombre) -> list[list]:
    columnas = PARTES[parte].columnas
    datos = fila(parte, 1, codigo="PE1008RP", nombre=nombre)
    return preparar_filas(PARTES[parte], [c.hana for c in columnas], [tuple(datos[c.hana] for c in columnas)])


@pytest.mark.parametrize("parte", ["clientes", "proveedores"])
@pytest.mark.parametrize("nombre", [None, "", "   "])
def test_socio_sin_nombre_usa_el_codigo_y_avisa(parte: str, nombre, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="bases_sap.esquema"):
        [resultado] = _socio_sin_nombre(parte, nombre)

    nombres = PARTES[parte].nombres
    assert resultado[nombres.index("codigo")] == "PE1008RP"
    assert resultado[nombres.index("nombre")] == "PE1008RP"
    assert resultado[nombres.index("activo")] is True  # el resto de la fila queda igual
    [aviso] = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert parte in aviso.getMessage() and "fila 1" in aviso.getMessage()
    assert "PE1008RP llegó sin nombre; se usa codigo como nombre" in aviso.getMessage()


def test_socio_con_nombre_no_avisa(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING, logger="bases_sap.esquema"):
        [resultado] = _socio_sin_nombre("proveedores", " Proveedor Uno ")
    assert resultado[PARTES["proveedores"].nombres.index("nombre")] == "Proveedor Uno"
    assert caplog.records == []


def test_otras_obligatorias_vacias_siguen_fallando_sin_respaldo():
    # Solo el nombre de los socios tiene respaldo: un artículo sin nombre sigue frenando la parte.
    columnas = PARTES["articulos"].columnas
    datos = fila("articulos", 1, nombre=None)
    with pytest.raises(ValorInvalido, match="nombre"):
        preparar_filas(PARTES["articulos"], [c.hana for c in columnas], [tuple(datos[c.hana] for c in columnas)])


def test_preparar_filas_valor_invalido_dice_parte_y_fila():
    with pytest.raises(ValorInvalido) as error:
        preparar_filas(PARTES["marcas"], ["codigo", "nombre", "activo"],
                       [(1, "A", "Y"), (2, "B", "Y"), (3, "C", "talvez")])
    mensaje = str(error.value)
    assert "marcas" in mensaje and "activo" in mensaje and "fila 3" in mensaje


def test_preparar_filas_llave_repetida():
    columnas = ["codigo_socio", "tipo", "nombre", "calle", "barrio", "ciudad",
                "municipio_codigo", "departamento", "pais", "codigo_postal"]
    base = [None] * 7
    filas = [
        ("C1", "B", "Principal", *base),
        ("C1", "S", "Principal", *base),
        ("C1", "B", "Principal ", *base),
    ]
    with pytest.raises(LlaveRepetida) as error:
        preparar_filas(PARTES["direcciones"], columnas, filas)
    assert error.value.llaves == [("C1", "B", "Principal")]
    assert "C1" in str(error.value) and "direcciones" in str(error.value)


def test_llave_que_solo_cambia_en_mayusculas_es_repetida():
    # MySQL compara la llave sin distinguir mayúsculas: C001 y c001 chocarían allá.
    filas = [("C001", "Uno", "Y"), ("c001", "Otro", "Y")]
    columnas = ["codigo", "nombre", "activo"]
    with pytest.raises(LlaveRepetida):
        preparar_filas(PARTES["municipios"], columnas, filas)


def test_llave_repetida_muestra_hasta_cinco():
    filas = [(i % 7, f"M{i}", "Y") for i in range(20)]
    with pytest.raises(LlaveRepetida) as error:
        preparar_filas(PARTES["marcas"], ["codigo", "nombre", "activo"], filas)
    assert len(error.value.llaves) == 5
    assert "7 llaves" in str(error.value)


def test_cartera_admite_filas_repetidas():
    parte = PARTES["cartera"]
    columnas = [c.hana for c in parte.columnas]
    fila = []
    for c in parte.columnas:
        fila.append({TEXTO: "X", ENTERO: 0, MONTO: Decimal("10.5"), FECHA: date(2026, 1, 2)}[c.tipo])
    filas = preparar_filas(parte, columnas, [tuple(fila), tuple(fila)])
    assert len(filas) == 2
    assert filas[0] == filas[1]
    assert filas[0][parte.nombres.index("dias")] == 0
    assert filas[0][parte.nombres.index("saldo")] == "10.50"
