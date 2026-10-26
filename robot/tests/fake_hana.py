"""HANA y VPN falsas para probar la extracción y el robot completo sin red.

HanaFalsa.conectar tiene la firma de hana.conectar(cfg_hana, empresa). El
cursor reconoce la parte buscando dentro del SQL ejecutado el texto real de
cada archivo de robot/queries (vía consultas.leer), y aplica la semántica de
los envoltorios de consultas.py:

- `SELECT COUNT(*) FROM (...)`         -> una fila con el conteo;
- `X."actualizado_en_sap" >= ?`       -> filas con esa hora o posterior;
- `X."codigo_socio" IN (?, ...)`      -> filas de esos socios.

Las pruebas deben apuntar config.QUERIES_DIR a robot/queries (QUERIES), porque
conftest lo mueve a tmp.

La VPN falsa, la HANA falsa y ApiFalsa (fake_api.py) escriben en una misma
`linea` de tiempo; revisar_fases() comprueba con ella las dos fases.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

import consultas
import esquema
from config import (
    AlertaConfig,
    ApiConfig,
    Config,
    EmpresaHana,
    HanaConfig,
    VpnConfig,
)
from hana import HanaError
from vpn import VpnError

QUERIES = Path(__file__).resolve().parent.parent / "queries"
ESQUEMAS = {"SGX": "SEGUREX", "SDC": "HBT_SDERIVADOS"}


@dataclass(frozen=True)
class Ejecucion:
    empresa: str
    tipo: str  # todo | cambios | socios | contar
    parte: str
    params: tuple


# --- Datos de prueba ---------------------------------------------------------


def _valor(columna: esquema.Columna, i: int) -> Any:
    if columna.tipo == esquema.ENTERO:
        return i
    if columna.tipo == esquema.MONTO:
        return Decimal(f"{1000 * i}.50")
    if columna.tipo == esquema.FECHA:
        return date(2026, 10, 1)
    if columna.tipo == esquema.HORA:
        return datetime(2026, 10, 20, 8, 0, 0)
    if columna.tipo == esquema.BOOL:
        return "Y"
    return f"{columna.nombre}-{i}"


def fila(parte: str, i: int, **valores: Any) -> dict[str, Any]:
    """Fila de HANA (llaves = alias del SQL) con valores de ejemplo de cada tipo."""
    columnas = esquema.PARTES[parte].columnas
    datos = {c.hana: _valor(c, i) for c in columnas}
    por_nombre = {c.nombre: c.hana for c in columnas}
    for nombre, valor in valores.items():
        datos[por_nombre.get(nombre, nombre)] = valor
    return datos


def datos_empresa(empresa: str, clientes: int = 3, proveedores: int = 2) -> dict[str, list[dict]]:
    """Filas por parte de una empresa. Los códigos llevan la empresa (CSGX001...).

    El cliente i se actualizó el 10+i de octubre de 2026 a las 09:00 (naive, hora de Bogotá).
    """
    def socio(parte: str, letra: str, i: int) -> dict[str, Any]:
        return fila(
            parte, i,
            codigo=f"{letra}{empresa}{i:03d}",
            nombre=f"Socio {letra}{i}",
            limite_credito=Decimal("1500000.505"),
            activo="Y" if i % 2 else "N",
            actualizado_en_sap=datetime(2026, 10, min(10 + i, 28), 9, 0, 0),
        )

    datos: dict[str, list[dict]] = {
        "clientes": [socio("clientes", "C", i) for i in range(1, clientes + 1)],
        "proveedores": [socio("proveedores", "P", i) for i in range(1, proveedores + 1)],
    }
    codigos = [f["codigo"] for f in datos["clientes"] + datos["proveedores"]]
    datos["direcciones"] = [
        fila("direcciones", n, codigo_socio=codigo, tipo=tipo, nombre=nombre)
        for n, (codigo, tipo, nombre) in enumerate(
            ((c, t, nom) for c in codigos for t, nom in (("B", "Principal"), ("S", "Bodega"))),
            start=1,
        )
    ]
    datos["contactos"] = [
        fila("contactos", n, contacto_id=n, codigo_socio=codigo)
        for n, codigo in enumerate(codigos, start=1)
    ]
    for parte in esquema.PARTES:
        if parte not in datos:
            datos[parte] = [fila(parte, i) for i in (1, 2)]
    datos["cartera"] = [fila("cartera", i) for i in (1, 2, 3)]
    return datos


def config_de_prueba(csv_dir: Path) -> Config:
    return Config(
        vpn=VpnConfig(Path("sccli.exe"), "vpn-de-prueba", "u", "clave-vpn-prueba", 5, True),
        hana=HanaConfig(
            host="hana.prueba.local",
            port=30015,
            timeout=60,
            empresas={
                codigo: EmpresaHana(codigo, f"usuario-{codigo}", f"clave-{codigo}-prueba", esquema_db)
                for codigo, esquema_db in ESQUEMAS.items()
            },
        ),
        api=ApiConfig("https://bases.prueba.test", "r2026a", "secreto-robot-de-prueba"),
        csv_dir=csv_dir,
        franjas=["00:00"],
        margen_franja_min=15,
        historial_documentos=False,
        alertas=AlertaConfig("", 587, "", ""),
    )


# --- VPN ---------------------------------------------------------------------


class VpnFalsa:
    """Mismos métodos que RobotVPN: conectar() y desconectar()."""

    def __init__(self, linea: list, *, fallar: bool = False) -> None:
        self.linea = linea
        self.fallar = fallar
        self.arriba = False
        self.conexiones = 0

    def conectar(self) -> None:
        self.conexiones += 1
        self.linea.append(("vpn", "conectar"))
        if self.fallar:
            raise VpnError("No se pudo conectar la VPN tras 3 intentos.")
        self.arriba = True
        self.linea.append(("vpn", "arriba"))

    def desconectar(self) -> None:
        self.arriba = False
        self.linea.append(("vpn", "abajo"))


# --- HANA --------------------------------------------------------------------


class _Cursor:
    def __init__(self, hana: "HanaFalsa", empresa: str, esquema_db: str) -> None:
        self.hana = hana
        self.empresa = empresa
        self.esquema = esquema_db
        self.description: list[tuple] | None = None
        self._filas: list[tuple] = []

    def execute(self, sql: str, params: Any = None) -> None:
        h = self.hana
        if h.vpn is not None and not h.vpn.arriba:
            raise AssertionError("Consulta a HANA con la VPN abajo.")
        parte = h.identificar(sql, self.esquema)
        params = tuple(params or ())
        if sql.lstrip().upper().startswith("SELECT COUNT(*)"):
            tipo = "contar"
        elif 'X."actualizado_en_sap" >= ?' in sql:
            tipo = "cambios"
        elif 'X."codigo_socio" IN (' in sql:
            tipo = "socios"
        else:
            tipo = "todo"
        h.ejecutadas.append(Ejecucion(self.empresa, tipo, parte, params))
        h.linea.append(("hana", "consulta", self.empresa, parte, tipo))
        if (self.empresa, parte) in h.partes_que_fallan:
            raise RuntimeError(h.texto_de_falla)

        filas = list(h.datos.get(self.empresa, {}).get(parte, []))
        if 'X."actualizado_en_sap" >= ?' in sql:
            filas = [f for f in filas if f["actualizado_en_sap"] >= params[0]]
        if 'X."codigo_socio" IN (' in sql:
            codigos = set(params)
            filas = [f for f in filas if f["codigo_socio"] in codigos]

        if tipo == "contar":
            self.description = [("COUNT(*)",)]
            self._filas = [(len(filas),)]
            return
        quitar = h.columnas_que_faltan.get((self.empresa, parte), set())
        alias = [c.hana for c in esquema.PARTES[parte].columnas if c.nombre not in quitar]
        self.description = [(a,) for a in alias]
        self._filas = [tuple(f.get(a) for a in alias) for f in filas]

    def fetchmany(self, n: int) -> list[tuple]:
        lote, self._filas = self._filas[:n], self._filas[n:]
        return lote

    def close(self) -> None:
        pass


class ConexionFalsa:
    def __init__(self, hana: "HanaFalsa", empresa: str, esquema_db: str) -> None:
        self.hana = hana
        self.empresa = empresa
        self.esquema = esquema_db

    def cursor(self) -> _Cursor:
        return _Cursor(self.hana, self.empresa, self.esquema)


@dataclass
class HanaFalsa:
    datos: dict[str, dict[str, list[dict]]]  # empresa -> parte -> filas
    linea: list = field(default_factory=list)
    vpn: VpnFalsa | None = None  # si se da, consultar con la VPN abajo es un error
    ejecutadas: list[Ejecucion] = field(default_factory=list)
    empresas_que_fallan: set[str] = field(default_factory=set)
    partes_que_fallan: set[tuple[str, str]] = field(default_factory=set)
    texto_de_falla: str = "falla simulada de la consulta"  # texto del driver en una falla
    columnas_que_faltan: dict[tuple[str, str], set[str]] = field(default_factory=dict)
    _textos: dict[str, dict[str, str]] = field(default_factory=dict)

    @contextmanager
    def conectar(self, cfg_hana: HanaConfig, empresa: EmpresaHana) -> Iterator[ConexionFalsa]:
        if self.vpn is not None and not self.vpn.arriba:
            raise AssertionError("Conexión a HANA con la VPN abajo.")
        self.linea.append(("hana", "conectar", empresa.codigo))
        if empresa.codigo in self.empresas_que_fallan:
            raise HanaError(f"No se pudo conectar a HANA ({empresa.codigo}) tras 3 intentos: simulado")
        try:
            yield ConexionFalsa(self, empresa.codigo, empresa.esquema)
        finally:
            self.linea.append(("hana", "cerrar", empresa.codigo))

    def identificar(self, sql: str, esquema_db: str) -> str:
        if esquema_db not in self._textos:
            self._textos[esquema_db] = {
                nombre: consultas.leer(parte.consulta, esquema_db)
                for nombre, parte in esquema.PARTES.items()
            }
        encontradas = [n for n, texto in self._textos[esquema_db].items() if texto in sql]
        if not encontradas:
            raise AssertionError(f"SQL que no sale de ningún archivo de robot/queries: {sql[:80]!r}")
        return max(encontradas, key=lambda n: len(self._textos[esquema_db][n]))

    def de(self, empresa: str, tipo: str | None = None, parte: str | None = None) -> list[Ejecucion]:
        return [
            e for e in self.ejecutadas
            if e.empresa == empresa and (tipo is None or e.tipo == tipo) and (parte is None or e.parte == parte)
        ]


def revisar_fases(linea: list) -> None:
    """Con la VPN arriba solo hay HANA; con la VPN abajo, nunca HANA. Termina abajo."""
    arriba = False
    for evento in linea:
        if evento[0] == "vpn":
            if evento[1] == "arriba":
                arriba = True
            elif evento[1] == "abajo":
                arriba = False
        elif evento[0] in ("api", "csv"):
            assert not arriba, f"{evento} con la VPN arriba"
        elif evento[0] == "hana":
            assert arriba, f"{evento} con la VPN abajo"
    assert not arriba, "La VPN quedó arriba"
