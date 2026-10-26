"""API falsa del lado del servidor, fiel a docs/contrato-robot.md.

Se usa como transporte de ApiCliente: `ApiCliente(cfg, transporte=ApiFalsa(...))`.
Verifica la firma con su propia copia del secreto (no usa firma.py, para no
repetir un error del cliente), descomprime, valida y guarda el estado de las
corridas para que las pruebas revisen qué llegó a la "API".
"""
from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from api import ErrorRed, Respuesta
from config import BOGOTA

RUTA_BASE = "/api/robot/v1"
HORA_INICIAL = 1_792_152_000.0
TOLERANCIA_S = 300
MAX_FILAS = 1000
LIMITE_BYTES = 10 * 1000 * 1000

PARTES = {
    "MAESTROS": (
        "clientes", "proveedores", "direcciones", "contactos", "articulos",
        "grupos_articulos", "marcas", "precios", "vendedores", "grupos_clientes",
        "condiciones_pago", "municipios",
    ),
    "CARTERA": ("cartera",),
}
# Contrato §7.1: partes que trae una corrida según la parte pedida.
PARTES_POR_SOLICITUD = {
    ("CARTERA", None): {"cartera"},
    ("MAESTROS", None): set(PARTES["MAESTROS"]),
    ("MAESTROS", "clientes"): {"clientes", "direcciones", "contactos"},
    ("MAESTROS", "proveedores"): {"proveedores", "direcciones", "contactos"},
    ("MAESTROS", "articulos"): {"articulos", "grupos_articulos", "marcas"},
    ("MAESTROS", "precios"): {"precios"},
    ("MAESTROS", "vendedores"): {"vendedores"},
    ("MAESTROS", "catalogos"): {"grupos_clientes", "condiciones_pago", "municipios"},
}

_RE_KEY = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_RE_NONCE = re.compile(r"^[0-9a-f]{32}$")
_RE_FIRMA = re.compile(r"^sha256=[0-9a-f]{64}$")
_RE_LOTES = re.compile(r"^/corridas/(\d+)/lotes$")
_RE_CERRAR = re.compile(r"^/corridas/(\d+)/cerrar$")
_RE_FALLAR = re.compile(r"^/corridas/(\d+)/fallar$")


@dataclass
class Peticion:
    nombre: str  # tomar, iniciar, lote, cerrar, fallar o desconocida
    ruta: str  # desde la raíz de la app: /api/robot/v1/...
    url: str
    headers: dict[str, str]
    cuerpo: bytes  # tal como viajó
    datos: Any  # JSON decodificado, o None si no se llegó a leer
    status: int = 0


@dataclass
class Lote:
    batch: int
    parte: str
    columns: list[str]
    rows: list[list[Any]]
    sha256: str


@dataclass
class Corrida:
    run_id: int
    conjunto: str
    empresa: str
    tipo: str
    partes: dict[str, str]
    solicitudes: list[int]
    fecha_corte: str | None
    extraida_en: str
    estado: str = "abierta"
    lotes: dict[int, Lote] = field(default_factory=dict)
    conteo_sap: dict[str, int] | None = None
    error: str | None = None

    def filas(self, parte: str) -> list[dict[str, Any]]:
        """Filas recibidas de una parte, como dicts columna -> valor, en orden de lote."""
        return [
            dict(zip(lote.columns, fila))
            for _, lote in sorted(self.lotes.items())
            if lote.parte == parte
            for fila in lote.rows
        ]

    def total_filas(self) -> dict[str, int]:
        totales = {parte: 0 for parte in self.partes}
        for lote in self.lotes.values():
            totales[lote.parte] = totales.get(lote.parte, 0) + len(lote.rows)
        return totales


@dataclass
class _Falla:
    status: int = 503
    headers: dict[str, str] = field(default_factory=dict)
    datos: Any = None
    red: bool = False
    # True: la API procesa la petición y luego se pierde la respuesta.
    despues: bool = False


class _Error(Exception):
    def __init__(self, status: int, datos: dict[str, Any]) -> None:
        super().__init__(status)
        self.status = status
        self.datos = datos


def _hora_iso(segundos: float) -> str:
    return datetime.fromtimestamp(segundos, BOGOTA).isoformat(timespec="seconds")


def _rechazo(mensaje: str, campo: str = "datos") -> _Error:
    return _Error(422, {"message": mensaje, "errors": {campo: [mensaje]}})


class ApiFalsa:
    def __init__(
        self,
        *,
        base_url: str = "https://bases.prueba.test",
        key_id: str = "r2026a",
        secret: str = "secreto-robot-de-prueba",
        reloj: Callable[[], float] | None = None,
        columnas_por_parte: dict[str, list[str]] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.llaves = {key_id: secret}
        self.hora = HORA_INICIAL
        self._reloj = reloj
        # Si se da, los lotes deben traer exactamente esas columnas (contrato §4.2).
        self.columnas_por_parte = columnas_por_parte
        self.peticiones: list[Peticion] = []
        self.corridas: dict[int, Corrida] = {}
        self.siguiente_run_id = 1
        self.cola_solicitudes: list[dict[str, Any]] = []
        self.solicitudes: dict[int, dict[str, Any]] = {}  # tomadas, por id
        self.estado_solicitudes: dict[int, str] = {}
        self._nonces: set[tuple[str, str]] = set()
        self._fallas: dict[str, list[_Falla]] = {}

    # ------------------------------------------------------------ para pruebas
    def reloj(self) -> float:
        return self._reloj() if self._reloj else self.hora

    def encolar_solicitud(self, solicitud: dict[str, Any]) -> None:
        """Deja una solicitud lista para que `tomar` la entregue."""
        self.cola_solicitudes.append(solicitud)

    def programar_fallas(
        self,
        nombre: str,
        veces: int = 1,
        *,
        status: int = 503,
        headers: dict[str, str] | None = None,
        datos: Any = None,
        red: bool = False,
        despues: bool = False,
    ) -> None:
        """Las próximas `veces` llamadas a la ruta `nombre` responden `status` o, con red=True, lanzan ErrorRed.

        Con despues=True la API procesa la petición antes de fallar: la respuesta se pierde.
        """
        falla = _Falla(status, {k.lower(): v for k, v in (headers or {}).items()}, datos, red, despues)
        self._fallas.setdefault(nombre, []).extend([falla] * veces)

    def peticiones_a(self, nombre: str) -> list[Peticion]:
        return [p for p in self.peticiones if p.nombre == nombre]

    # ------------------------------------------------------------- transporte
    def __call__(
        self, url: str, headers: dict[str, str], cuerpo: bytes, timeout: float
    ) -> Respuesta:
        headers = {k.lower(): v for k, v in headers.items()}
        ruta = url[len(self.base_url):] if url.startswith(self.base_url + "/") else url
        relativa = ruta[len(RUTA_BASE):] if ruta.startswith(RUTA_BASE + "/") else None
        peticion = Peticion(self._nombre(relativa), ruta, url, headers, cuerpo, None)
        self.peticiones.append(peticion)

        fallas = self._fallas.get(peticion.nombre)
        if fallas:
            falla = fallas.pop(0)
            if falla.despues:
                self._procesar(peticion, ruta, relativa, headers, cuerpo)
            if falla.red:
                peticion.status = -1
                raise ErrorRed("Falla de red simulada.")
            return self._responder(peticion, falla.status, falla.datos or {"message": "Falla simulada."}, falla.headers)

        return self._procesar(peticion, ruta, relativa, headers, cuerpo)

    def _procesar(
        self, peticion: Peticion, ruta: str, relativa: str | None, headers: dict[str, str], cuerpo: bytes
    ) -> Respuesta:
        try:
            if len(cuerpo) > LIMITE_BYTES:
                raise _Error(413, {"message": "Cuerpo demasiado grande."})
            self._verificar_firma(ruta, headers, cuerpo)
            if relativa is None or peticion.nombre == "desconocida":
                raise _Error(404, {"message": "No encontrado."})
            peticion.datos = datos = self._decodificar(headers, cuerpo)
            status, respuesta = self._despachar(relativa, datos, cuerpo)
        except _Error as e:
            return self._responder(peticion, e.status, e.datos)
        return self._responder(peticion, status, respuesta)

    # ---------------------------------------------------------------- interno
    @staticmethod
    def _nombre(relativa: str | None) -> str:
        if relativa == "/solicitudes/tomar":
            return "tomar"
        if relativa == "/corridas":
            return "iniciar"
        for nombre, patron in (("lote", _RE_LOTES), ("cerrar", _RE_CERRAR), ("fallar", _RE_FALLAR)):
            if relativa and patron.match(relativa):
                return nombre
        return "desconocida"

    @staticmethod
    def _responder(
        peticion: Peticion, status: int, datos: Any, headers: dict[str, str] | None = None
    ) -> Respuesta:
        peticion.status = status
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        return Respuesta(status, {"content-type": "application/json", **(headers or {})}, cuerpo)

    def _verificar_firma(self, ruta: str, headers: dict[str, str], cuerpo: bytes) -> None:
        invalida = _Error(401, {"message": "Firma inválida."})
        key = headers.get("x-robot-key", "")
        ts = headers.get("x-robot-timestamp", "")
        nonce = headers.get("x-robot-nonce", "")
        firma = headers.get("x-robot-signature", "")
        if not (_RE_KEY.match(key) and ts.isdigit() and _RE_NONCE.match(nonce) and _RE_FIRMA.match(firma)):
            raise invalida
        secret = self.llaves.get(key)
        if secret is None or abs(int(ts) - self.reloj()) > TOLERANCIA_S:
            raise invalida
        cadena = "\n".join((ts, nonce, "POST", ruta, hashlib.sha256(cuerpo).hexdigest()))
        esperada = "sha256=" + hmac.new(secret.encode(), cadena.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(esperada, firma) or (key, nonce) in self._nonces:
            raise invalida
        self._nonces.add((key, nonce))

    @staticmethod
    def _decodificar(headers: dict[str, str], cuerpo: bytes) -> Any:
        try:
            if headers.get("content-encoding", "").lower() == "gzip":
                cuerpo = gzip.decompress(cuerpo)
            return json.loads(cuerpo.decode("utf-8"))
        except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise _Error(400, {"message": "Cuerpo JSON inválido."}) from e

    def _despachar(self, relativa: str, datos: Any, cuerpo: bytes) -> tuple[int, dict[str, Any]]:
        if not isinstance(datos, dict):
            raise _rechazo("El cuerpo debe ser un objeto JSON.")
        if relativa == "/solicitudes/tomar":
            return self._tomar(datos)
        if relativa == "/corridas":
            return self._iniciar(datos)
        for patron, accion in ((_RE_LOTES, self._lote), (_RE_CERRAR, self._cerrar), (_RE_FALLAR, self._fallar)):
            m = patron.match(relativa)
            if m:
                return accion(self._corrida_abierta(int(m.group(1))), datos, cuerpo)
        raise _Error(404, {"message": "No encontrado."})

    def _corrida_abierta(self, run_id: int) -> Corrida:
        corrida = self.corridas.get(run_id)
        if corrida is None:
            raise _Error(404, {"message": "Corrida no encontrada."})
        if corrida.estado != "abierta":
            raise _Error(409, {"message": "La corrida ya no está abierta.", "estado": corrida.estado})
        return corrida

    def _tomar(self, datos: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        maximo = datos.get("max")
        if not isinstance(maximo, int) or isinstance(maximo, bool) or maximo < 1:
            raise _rechazo("max debe ser un entero mayor que 0.", "max")
        tomadas, self.cola_solicitudes = self.cola_solicitudes[:maximo], self.cola_solicitudes[maximo:]
        for solicitud in tomadas:
            self.solicitudes[solicitud["id"]] = solicitud
            self.estado_solicitudes[solicitud["id"]] = "tomada"
        return 200, {"solicitudes": tomadas}

    def _iniciar(self, datos: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        conjunto, empresa, tipo = datos.get("conjunto"), datos.get("empresa"), datos.get("tipo")
        partes = datos.get("partes")
        solicitudes = datos.get("solicitudes")
        if conjunto not in PARTES:
            raise _rechazo("Conjunto desconocido.", "conjunto")
        if empresa not in ("SGX", "SDC"):
            raise _rechazo("Empresa desconocida.", "empresa")
        if tipo not in ("completa", "solicitud"):
            raise _rechazo("Tipo inválido.", "tipo")
        if not isinstance(partes, dict) or not partes:
            raise _rechazo("partes es obligatorio.", "partes")
        for parte, modo in partes.items():
            if parte not in PARTES[conjunto] or modo not in ("todo", "cambios"):
                raise _rechazo(f"Parte o modo inválido: {parte}.", f"partes.{parte}")
        if tipo == "completa" and (set(partes) != set(PARTES[conjunto]) or set(partes.values()) != {"todo"}):
            raise _rechazo("Una corrida completa lleva todas las partes en modo todo.", "partes")
        if not isinstance(solicitudes, list):
            raise _rechazo("solicitudes debe ser una lista.", "solicitudes")
        for sid in solicitudes:
            solicitud = self.solicitudes.get(sid)
            if (
                solicitud is None
                or self.estado_solicitudes.get(sid) != "tomada"
                or (solicitud["empresa"], solicitud["conjunto"]) != (empresa, conjunto)
                or not PARTES_POR_SOLICITUD[(conjunto, solicitud.get("parte"))] <= set(partes)
            ):
                raise _rechazo(f"La solicitud {sid} no corresponde a esta corrida.", "solicitudes")
        fecha_corte = datos.get("fecha_corte")
        if (conjunto == "CARTERA") != (fecha_corte is not None):
            raise _rechazo("fecha_corte va solo, y siempre, en CARTERA.", "fecha_corte")
        if not datos.get("extraida_en"):
            raise _rechazo("extraida_en es obligatorio.", "extraida_en")

        for corrida in self.corridas.values():
            if (corrida.conjunto, corrida.empresa, corrida.estado) == (conjunto, empresa, "abierta"):
                raise _Error(409, {"message": "Ya hay una corrida abierta.", "run_id": corrida.run_id})

        run_id = self.siguiente_run_id
        self.siguiente_run_id += 1
        self.corridas[run_id] = Corrida(
            run_id, conjunto, empresa, tipo, dict(partes), list(solicitudes),
            fecha_corte, datos["extraida_en"],
        )
        return 201, {"run_id": run_id, "estado": "abierta", "abierta_hasta": _hora_iso(self.reloj() + 1800)}

    def _lote(self, corrida: Corrida, datos: dict[str, Any], cuerpo: bytes) -> tuple[int, dict[str, Any]]:
        batch, parte = datos.get("batch"), datos.get("parte")
        columns, rows = datos.get("columns"), datos.get("rows")
        if not isinstance(batch, int) or isinstance(batch, bool) or batch < 1:
            raise _rechazo("batch debe ser un entero desde 1.", "batch")
        sha = hashlib.sha256(cuerpo).hexdigest()
        previo = corrida.lotes.get(batch)
        if previo is not None:
            if previo.sha256 == sha:
                return 200, {"batch": batch, "rows": len(previo.rows), "duplicate": True}
            raise _Error(409, {"message": "El lote ya llegó con otro cuerpo.", "estado": corrida.estado})
        if parte not in corrida.partes:
            raise _rechazo("La parte no está en la corrida.", "parte")
        if not isinstance(columns, list) or not columns or len(set(columns)) != len(columns):
            raise _rechazo("columns inválidas.", "columns")
        if self.columnas_por_parte and set(columns) != set(self.columnas_por_parte[parte]):
            raise _rechazo("columns no son las de la parte.", "columns")
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_FILAS:
            raise _rechazo(f"Un lote lleva de 1 a {MAX_FILAS} filas.", "rows")
        for i, fila in enumerate(rows):
            if not isinstance(fila, list) or len(fila) != len(columns):
                raise _rechazo("La fila no tiene un valor por columna.", f"rows.{i}")
        corrida.lotes[batch] = Lote(batch, parte, list(columns), rows, sha)
        return 201, {"batch": batch, "rows": len(rows)}

    def _cerrar(self, corrida: Corrida, datos: dict[str, Any], cuerpo: bytes) -> tuple[int, dict[str, Any]]:
        batches, filas = datos.get("batches"), datos.get("filas")
        if not isinstance(batches, int) or isinstance(batches, bool) or batches < 0:
            raise _rechazo("batches debe ser un entero.", "batches")
        if not isinstance(filas, dict) or not set(filas) <= set(corrida.partes):
            raise _rechazo("filas inválidas.", "filas")
        if corrida.tipo == "completa" and not isinstance(datos.get("conteo_sap"), dict):
            raise _rechazo("conteo_sap es obligatorio en una corrida completa.", "conteo_sap")
        if corrida.tipo != "completa" and "conteo_sap" in datos:
            raise _rechazo("conteo_sap solo va en una corrida completa.", "conteo_sap")

        faltan = [n for n in range(1, batches + 1) if n not in corrida.lotes]
        recibidas = corrida.total_filas()
        sobran = [n for n in corrida.lotes if n > batches]
        if faltan or sobran or any(recibidas.get(p, 0) != filas.get(p, 0) for p in corrida.partes):
            raise _Error(409, {"message": "Faltan lotes o las filas no cuadran.", "faltan": faltan})
        vacias = [p for p, modo in corrida.partes.items() if modo == "todo" and recibidas.get(p, 0) == 0]
        if vacias:
            self._terminar(corrida, "fallida", f"Parte todo sin filas: {', '.join(vacias)}")
            raise _rechazo("Una parte todo llegó sin filas.", f"filas.{vacias[0]}")

        corrida.conteo_sap = datos.get("conteo_sap")
        self._terminar(corrida, "cerrada")
        respuesta: dict[str, Any] = {
            "run_id": corrida.run_id,
            "estado": "cerrada",
            "aplicada_en": _hora_iso(self.reloj()),
        }
        if corrida.tipo == "completa":
            conteo_sap = corrida.conteo_sap or {}
            respuesta["conteo"] = {
                p: {
                    "sap": conteo_sap.get(p),
                    "recibidas": recibidas[p],
                    "activas_mysql": recibidas[p],
                    "cuadra": conteo_sap.get(p) == recibidas[p],
                }
                for p in corrida.partes
            }
        return 200, respuesta

    def _fallar(self, corrida: Corrida, datos: dict[str, Any], cuerpo: bytes) -> tuple[int, dict[str, Any]]:
        error = datos.get("error")
        if not isinstance(error, str) or not error or len(error) > 1000:
            raise _rechazo("error va de 1 a 1.000 caracteres.", "error")
        self._terminar(corrida, "fallida", error)
        return 200, {"run_id": corrida.run_id, "estado": "fallida"}

    def _terminar(self, corrida: Corrida, estado: str, error: str | None = None) -> None:
        corrida.estado = estado
        corrida.error = error
        for sid in corrida.solicitudes:
            self.estado_solicitudes[sid] = "terminada" if estado == "cerrada" else "fallida"
