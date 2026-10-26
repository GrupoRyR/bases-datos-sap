"""Partes del contrato, sus columnas y la conversión de valores (docs/contrato-robot.md).

Este archivo replica §5 (MAESTROS), §6 (CARTERA) y §7.1 (qué trae cada
solicitud) del contrato. El contrato manda: si cambia, se cambia aquí también.

- En MAESTROS los alias del SQL ya son los nombres del contrato (`hana == nombre`).
- En CARTERA la consulta es la del gestor de cartera, con sus etiquetas
  ("Código SN"...), y `hana` es esa etiqueta.
- `indices()` falla ruidosamente si alguien edita el SQL y desaparece una
  columna (regla 7 del skill robot-sap-hana).
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Iterable, Literal, Sequence

from config import BOGOTA

TEXTO, ENTERO, MONTO, FECHA, HORA, BOOL = "texto", "entero", "monto", "fecha", "hora", "bool"

MAX_TEXTO = 4000  # contrato §4.2
MAX_LLAVES_EN_ERROR = 5
_CENTAVOS = Decimal("0.01")
_VERDADEROS = {"y", "1", "true", "t"}
_FALSOS = {"n", "0", "false", "f"}

Modo = Literal["cambios", "todo", "socio"]


@dataclass(frozen=True)
class Columna:
    hana: str       # alias exacto en la consulta HANA
    nombre: str     # columna del contrato (§5.2 y §6)
    tipo: str
    # Obligatoria: no puede llegar nula ni vacía (contrato §4.2).
    requerida: bool = False


@dataclass(frozen=True)
class Parte:
    nombre: str
    conjunto: str                   # MAESTROS o CARTERA
    consulta: str                   # archivo relativo a robot/queries
    columnas: tuple[Columna, ...]   # el ORDEN define el orden del CSV y del lote
    llave: tuple[str, ...]          # nombres del contrato; vacía = sin llave (cartera)
    # Modo en una solicitud (contrato §5.1): "cambios" usa actualizado_en_sap,
    # "socio" sigue a los socios enviados en la corrida, "todo" trae todo.
    modo_solicitud: Modo
    incremental: bool               # la consulta trae actualizado_en_sap

    @property
    def nombres(self) -> list[str]:
        return [c.nombre for c in self.columnas]


def _m(nombre: str, tipo: str = TEXTO, requerida: bool = False) -> Columna:
    """Columna de MAESTROS: el alias del SQL es el nombre del contrato."""
    return Columna(nombre, nombre, tipo, requerida)


_SOCIO = (
    _m("codigo", requerida=True),
    _m("nombre", requerida=True),
    _m("nombre_extranjero"),
    _m("nit"),
    _m("grupo_codigo", ENTERO),
    _m("vendedor_codigo", ENTERO),
    _m("condicion_pago_codigo", ENTERO),
    _m("lista_precios_codigo", ENTERO),
    _m("telefono"),
    _m("telefono_2"),
    _m("celular"),
    _m("correo"),
    _m("ciudad"),
    _m("limite_credito", MONTO),
    _m("socio_vinculado"),
    _m("activo", BOOL, requerida=True),
    _m("actualizado_en_sap", HORA, requerida=True),
    _m("creado_en_sap", FECHA),
)

_DIRECCIONES = (
    _m("codigo_socio", requerida=True),
    _m("tipo", requerida=True),
    _m("nombre", requerida=True),
    _m("calle"),
    _m("barrio"),
    _m("ciudad"),
    _m("municipio_codigo"),
    _m("departamento"),
    _m("pais"),
    _m("codigo_postal"),
)

_CONTACTOS = (
    _m("contacto_id", ENTERO, requerida=True),
    _m("codigo_socio", requerida=True),
    _m("nombre", requerida=True),
    _m("nombres"),
    _m("apellidos"),
    _m("cargo"),
    _m("telefono"),
    _m("celular"),
    _m("correo"),
    _m("activo", BOOL, requerida=True),
)

_ARTICULOS = (
    _m("codigo", requerida=True),
    _m("nombre", requerida=True),
    _m("nombre_extranjero"),
    _m("grupo_codigo", ENTERO),
    _m("marca_codigo", ENTERO),
    _m("unidad_venta"),
    _m("codigo_barras"),
    _m("inventariable", BOOL),
    _m("de_venta", BOOL),
    _m("de_compra", BOOL),
    _m("activo", BOOL, requerida=True),
    _m("actualizado_en_sap", HORA, requerida=True),
    _m("creado_en_sap", FECHA),
)


def _catalogo(tipo_codigo: str = ENTERO, *extra: Columna) -> tuple[Columna, ...]:
    return (
        _m("codigo", tipo_codigo, requerida=True),
        _m("nombre", requerida=True),
        *extra,
        _m("activo", BOOL, requerida=True),
    )


_PRECIOS = (
    _m("articulo_codigo", requerida=True),
    _m("lista_codigo", ENTERO, requerida=True),
    _m("lista_nombre", requerida=True),
    _m("precio", MONTO),
    _m("moneda"),
    _m("activo", BOOL, requerida=True),
)

_VENDEDORES = (
    _m("codigo", ENTERO, requerida=True),
    _m("nombre", requerida=True),
    _m("correo"),
    _m("celular"),
    _m("activo", BOOL, requerida=True),
)

# Orden del contrato §6; `hana` es la etiqueta de la consulta del gestor.
_CARTERA = (
    Columna("Código SN", "codigo_sn", TEXTO, requerida=True),
    Columna("SlpCode", "slp_code", ENTERO),
    Columna("Email asesor", "email_asesor", TEXTO),
    Columna("Nombre SN", "nombre_sn", TEXTO),
    Columna("Nit", "nit", TEXTO),
    Columna("Grupo", "grupo", TEXTO),
    Columna("Municipio", "municipio", TEXTO),
    Columna("Cuenta visible", "cuenta_visible", TEXTO),
    Columna("Tipo doc", "tipo_doc", TEXTO),
    Columna("Documento", "documento", TEXTO, requerida=True),
    Columna("Documento base", "documento_base", TEXTO),
    Columna("Referencia 1", "referencia_1", TEXTO),
    Columna("No. referencia", "no_referencia", TEXTO),
    Columna("Empleado ventas / compras", "asesor", TEXTO),
    Columna("Total plazos", "total_plazos", ENTERO),
    Columna("No. plazo", "no_plazo", ENTERO),
    Columna("Condicion pago documento", "condicion_pago", TEXTO),
    Columna("Fecha contabilización", "fecha_contabilizacion", FECHA),
    Columna("Fecha vencimiento", "fecha_vencimiento", FECHA, requerida=True),
    Columna("Fecha documento", "fecha_documento", FECHA),
    Columna("Días", "dias", ENTERO, requerida=True),
    Columna("Límite crédito", "limite_credito", MONTO),
    Columna("Importe original", "importe_original", MONTO),
    Columna("Base gravable", "base_gravable", MONTO),
    Columna("Saldo base", "saldo_base", MONTO),
    Columna("Saldo vencido", "saldo_vencido", MONTO),
    Columna("Valor abonado", "valor_abonado", MONTO),
    Columna("Sin vencer", "sin_vencer", MONTO),
    Columna("Valor cheques aplicados", "valor_cheques", MONTO),
    Columna("0-30", "d_0_30", MONTO),
    Columna("31-60", "d_31_60", MONTO),
    Columna("61-90", "d_61_90", MONTO),
    Columna("91-120", "d_91_120", MONTO),
    Columna("121-150", "d_121_150", MONTO),
    Columna("151-180", "d_151_180", MONTO),
    Columna("> 180", "d_mas_180", MONTO),
    Columna("Saldo", "saldo", MONTO, requerida=True),
    Columna("Rango", "rango", TEXTO),
)


def _maestro(
    nombre: str,
    columnas: tuple[Columna, ...],
    llave: tuple[str, ...] = ("codigo",),
    modo: Modo = "todo",
    incremental: bool = False,
) -> Parte:
    return Parte(nombre, "MAESTROS", f"maestros/{nombre}.sql", columnas, llave, modo, incremental)


# Orden de las partes: el del contrato §1. `precios` no tiene archivo común:
# cada esquema trae el suyo en maestros/<ESQUEMA>/precios.sql (consultas.py).
PARTES: dict[str, Parte] = {
    parte.nombre: parte
    for parte in (
        _maestro("clientes", _SOCIO, modo="cambios", incremental=True),
        _maestro("proveedores", _SOCIO, modo="cambios", incremental=True),
        _maestro("direcciones", _DIRECCIONES, ("codigo_socio", "tipo", "nombre"), "socio"),
        _maestro("contactos", _CONTACTOS, ("contacto_id",), "socio"),
        _maestro("articulos", _ARTICULOS, modo="cambios", incremental=True),
        _maestro("grupos_articulos", _catalogo()),
        _maestro("marcas", _catalogo()),
        _maestro("precios", _PRECIOS, ("articulo_codigo",)),
        _maestro("vendedores", _VENDEDORES),
        _maestro("grupos_clientes", _catalogo()),
        _maestro("condiciones_pago", _catalogo(
            ENTERO, _m("dias_extra", ENTERO), _m("meses_extra", ENTERO))),
        _maestro("municipios", _catalogo(TEXTO)),
        Parte("cartera", "CARTERA", "cartera/cartera.sql", _CARTERA, (), "todo", False),
    )
}

PARTES_POR_CONJUNTO: dict[str, tuple[str, ...]] = {
    conjunto: tuple(p.nombre for p in PARTES.values() if p.conjunto == conjunto)
    for conjunto in ("MAESTROS", "CARTERA")
}

SOCIOS = ("clientes", "proveedores")
HIJAS_DE_SOCIO = ("direcciones", "contactos")

# Contrato §7.1: (conjunto, parte pedida o None) -> partes que trae la corrida.
PARTES_POR_SOLICITUD: dict[tuple[str, str | None], tuple[str, ...]] = {
    ("CARTERA", None): ("cartera",),
    ("MAESTROS", None): PARTES_POR_CONJUNTO["MAESTROS"],
    ("MAESTROS", "clientes"): ("clientes", *HIJAS_DE_SOCIO),
    ("MAESTROS", "proveedores"): ("proveedores", *HIJAS_DE_SOCIO),
    ("MAESTROS", "articulos"): ("articulos", "grupos_articulos", "marcas"),
    ("MAESTROS", "precios"): ("precios",),
    ("MAESTROS", "vendedores"): ("vendedores",),
    ("MAESTROS", "catalogos"): ("grupos_clientes", "condiciones_pago", "municipios"),
}


class ColumnasInesperadas(RuntimeError):
    """La consulta HANA no devolvió las columnas que el robot espera."""


class ValorInvalido(ValueError):
    """Un valor no se puede convertir al tipo del contrato o falta siendo obligatorio."""


class LlaveRepetida(ValueError):
    """La llave de una parte se repite: la API respondería 422 (contrato §4.2)."""

    def __init__(self, mensaje: str, llaves: list[tuple]) -> None:
        super().__init__(mensaje)
        self.llaves = llaves


def indices(columnas_hana: Sequence[str], columnas: Iterable[Columna]) -> list[int]:
    """Posición de cada columna esperada dentro del resultado de HANA.

    Falla ruidosamente si alguien edita el SQL y rompe el contrato: es
    preferible a enviar datos desalineados.
    """
    columnas = list(columnas)
    recibidas = list(columnas_hana)
    faltantes = [c.hana for c in columnas if c.hana not in recibidas]
    if faltantes:
        raise ColumnasInesperadas(
            "La consulta no devolvió estas columnas esperadas: "
            + ", ".join(faltantes)
            + "\nColumnas recibidas: "
            + ", ".join(recibidas)
            + "\nRevisa el archivo .sql o actualiza robot/etl/esquema.py."
        )
    return [recibidas.index(c.hana) for c in columnas]


# --- Conversión de valores (contrato §4.2) ----------------------------------


def _invalido(columna: str, valor: Any, que: str) -> ValorInvalido:
    donde = f"columna {columna}: " if columna else ""
    return ValorInvalido(f"{donde}{que} ({type(valor).__name__} {valor!r:.60})")


def _decimal(valor: Any, columna: str, que: str) -> Decimal:
    if isinstance(valor, bool):
        raise _invalido(columna, valor, que)
    try:
        if isinstance(valor, float):
            # str() da la representación corta: 2.675 -> "2.675", no 2.67499...
            numero = Decimal(str(valor))
        elif isinstance(valor, str):
            numero = Decimal(valor.strip())
        else:
            numero = Decimal(valor)
    except (InvalidOperation, TypeError, ValueError):
        raise _invalido(columna, valor, que) from None
    if not numero.is_finite():
        raise _invalido(columna, valor, que)
    return numero


def _entero(valor: Any, columna: str) -> int:
    if isinstance(valor, int) and not isinstance(valor, bool):
        return valor
    numero = _decimal(valor, columna, "se esperaba un entero")
    if numero != numero.to_integral_value():
        raise _invalido(columna, valor, "se esperaba un entero")
    return int(numero)


def _monto(valor: Any, columna: str) -> str:
    numero = _decimal(valor, columna, "se esperaba un monto")
    redondeado = numero.quantize(_CENTAVOS, rounding=ROUND_HALF_UP)
    if redondeado == 0:
        redondeado = Decimal("0.00")  # sin "-0.00"
    return f"{redondeado:f}"


def _fecha(valor: Any, columna: str) -> str:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, str):
        texto = valor.strip()
        try:
            return date.fromisoformat(texto).isoformat()
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(texto).date().isoformat()
        except ValueError:
            pass
    raise _invalido(columna, valor, "se esperaba una fecha AAAA-MM-DD")


def _hora(valor: Any, columna: str) -> str:
    momento: datetime | None = None
    if isinstance(valor, datetime):
        momento = valor
    elif isinstance(valor, date):
        momento = datetime(valor.year, valor.month, valor.day)
    elif isinstance(valor, str):
        try:
            momento = datetime.fromisoformat(valor.strip())
        except ValueError:
            momento = None
    if momento is None:
        raise _invalido(columna, valor, "se esperaba una fecha y hora")
    # HANA devuelve TIMESTAMP sin zona: es hora local de Bogotá.
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=BOGOTA)
    else:
        momento = momento.astimezone(BOGOTA)
    return momento.isoformat(timespec="seconds")


def _bool(valor: Any, columna: str) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, int) and valor in (0, 1):
        return valor == 1
    if isinstance(valor, str):
        texto = valor.strip().lower()
        if texto in _VERDADEROS:
            return True
        if texto in _FALSOS:
            return False
    raise _invalido(columna, valor, "se esperaba Y/N, 1/0 o True/False")


def _texto(valor: Any) -> str | None:
    if isinstance(valor, Decimal) and valor.is_finite() and valor == valor.to_integral_value():
        texto = str(int(valor))
    elif isinstance(valor, float) and math.isfinite(valor) and valor.is_integer():
        texto = str(int(valor))
    elif isinstance(valor, Decimal):
        texto = f"{valor:f}"
    else:
        texto = str(valor)
    texto = texto.strip()[:MAX_TEXTO].strip()
    return texto or None


def serializar(valor: Any, tipo: str, columna: str = "") -> Any:
    """Convierte un valor de HANA al formato JSON del contrato (§4.2).

    None y el texto vacío quedan en None. Lanza ValorInvalido con el nombre de
    la columna si el valor no sirve para su tipo.
    """
    if valor is None:
        return None
    if isinstance(valor, str) and not valor.strip():
        return None
    if tipo == TEXTO:
        return _texto(valor)
    if tipo == ENTERO:
        return _entero(valor, columna)
    if tipo == MONTO:
        return _monto(valor, columna)
    if tipo == FECHA:
        return _fecha(valor, columna)
    if tipo == HORA:
        return _hora(valor, columna)
    if tipo == BOOL:
        return _bool(valor, columna)
    raise ValueError(f"Tipo desconocido: {tipo}")


def preparar_filas(
    parte: Parte, columnas_hana: Sequence[str], filas: Iterable[Sequence[Any]]
) -> list[list[Any]]:
    """Filas de HANA -> filas del lote, en el orden de `parte.columnas`.

    Falla antes de enviar nada si un valor no sirve, si una columna obligatoria
    llega vacía o si la llave se repite: la API respondería 422.
    """
    posiciones = indices(columnas_hana, parte.columnas)
    salida: list[list[Any]] = []
    for numero, fila in enumerate(filas, start=1):
        valores: list[Any] = []
        for columna, posicion in zip(parte.columnas, posiciones):
            try:
                valor = serializar(fila[posicion], columna.tipo, columna.nombre)
            except ValorInvalido as exc:
                raise ValorInvalido(f"Parte {parte.nombre}, fila {numero}: {exc}") from exc
            if valor is None and columna.requerida:
                raise ValorInvalido(
                    f"Parte {parte.nombre}, fila {numero}: la columna obligatoria "
                    f"{columna.nombre} llegó vacía."
                )
            valores.append(valor)
        salida.append(valores)

    if parte.llave:
        _revisar_llave(parte, salida)
    return salida


def _revisar_llave(parte: Parte, filas: list[list[Any]]) -> None:
    nombres = parte.nombres
    posiciones = [nombres.index(n) for n in parte.llave]
    conteo = Counter(tuple(fila[p] for p in posiciones) for fila in filas)
    repetidas = [llave for llave, veces in conteo.items() if veces > 1]
    if not repetidas:
        return
    muestra = repetidas[:MAX_LLAVES_EN_ERROR]
    raise LlaveRepetida(
        f"Parte {parte.nombre}: {len(repetidas)} llaves repetidas "
        f"({', '.join(parte.llave)}), por ejemplo: "
        + "; ".join(str(llave) for llave in muestra),
        muestra,
    )
