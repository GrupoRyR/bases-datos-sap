"""Cliente de la API del robot (docs/contrato-robot.md §2, §3, §4 y §7.3).

Cada petición es un POST JSON firmado con HMAC (firma.py), comprimido con gzip
por defecto. El gzip usa mtime=0 para que un lote reenviado tenga los mismos
bytes y el mismo SHA-256: así la API lo reconoce como duplicado (contrato §4.2).

Reintentos dentro de una llamada, siempre con el mismo cuerpo y firma nueva:
- error de red o 5xx: hasta 3 reenvíos, con esperas de 2, 4 y 8 s;
- 429: espera Retry-After (30 s si no viene, máximo 120) y gasta un intento;
- 401 y 413: sin reintento.
- iniciar, cerrar y fallar: si un intento se quedó sin respuesta y el reintento
  da 409, la API ya lo había aplicado y se toma como éxito (`recuperada`).
- 3xx: no se sigue (urllib haría un GET sin cuerpo); se pide corregir la URL.

En el log solo van ruta, estado e intento: nunca el secreto, la firma ni el
cuerpo, que puede llevar datos de SAP.
"""
from __future__ import annotations

import gzip
import http.client
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

import firma
from config import ApiConfig
from registro import obtener, registrar_secreto

log = obtener("api")

RUTA_BASE = "/api/robot/v1"
LIMITE_BYTES = 10 * 1000 * 1000  # tal como viaja (contrato §2)
LIMITE_DESCOMPRIMIDO = 40 * 1000 * 1000
MAX_INTENTOS = 4  # el primero y 3 reenvíos
ESPERAS_S = (2, 4, 8)
RETRY_AFTER_POR_DEFECTO = 30
RETRY_AFTER_MAXIMO = 120
MAX_ERROR = 1000
USER_AGENT = "bases-sap-robot/1"


@dataclass(frozen=True)
class Respuesta:
    status: int
    headers: dict[str, str]  # llaves en minúscula
    cuerpo: bytes


Transporte = Callable[[str, dict[str, str], bytes, float], Respuesta]


class ApiError(RuntimeError):
    """La API no respondió como se esperaba."""

    def __init__(self, mensaje: str, *, status: int | None = None, datos: Any = None) -> None:
        super().__init__(mensaje)
        self.status = status
        self.datos = datos if datos is not None else {}


class ErrorRed(ApiError):
    """No hubo respuesta: sin conexión, DNS o tiempo agotado."""


class FirmaRechazada(ApiError):
    """401: la API no aceptó la firma."""


class ApiRechazo(ApiError):
    """4xx con mensaje de la API (409, 422...)."""

    def __init__(self, mensaje: str, *, status: int | None = None, datos: Any = None) -> None:
        super().__init__(mensaje, status=status, datos=datos)
        cuerpo = self.datos if isinstance(self.datos, dict) else {}
        self.message: str = str(cuerpo.get("message") or "")
        self.errors: dict[str, Any] = cuerpo.get("errors") or {}


class CorridaAbierta(ApiRechazo):
    """409 al iniciar: ya hay una corrida abierta de ese conjunto y empresa."""

    def __init__(self, mensaje: str, *, status: int | None = None, datos: Any = None) -> None:
        super().__init__(mensaje, status=status, datos=datos)
        self.run_id: int | None = self.datos.get("run_id") if isinstance(self.datos, dict) else None


class LotesFaltantes(ApiRechazo):
    """409 al cerrar: faltan lotes o las filas no cuadran."""

    def __init__(self, mensaje: str, *, status: int | None = None, datos: Any = None) -> None:
        super().__init__(mensaje, status=status, datos=datos)
        self.faltan: list[int] = list(self.datos.get("faltan") or []) if isinstance(self.datos, dict) else []


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    """urllib convierte un POST redirigido en un GET sin cuerpo ni firma: mejor no seguirlo."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_ABRIDOR = urllib.request.build_opener(_SinRedirecciones)


def _abrir(peticion: urllib.request.Request, timeout: float) -> Any:
    return _ABRIDOR.open(peticion, timeout=timeout)


def transporte_urllib(url: str, headers: dict[str, str], cuerpo: bytes, timeout: float) -> Respuesta:
    """POST con urllib. Un 3xx/4xx/5xx también es una Respuesta; sin respuesta, ErrorRed."""
    peticion = urllib.request.Request(url, data=cuerpo, headers=headers, method="POST")
    try:
        with _abrir(peticion, timeout) as r:
            return Respuesta(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
    except urllib.error.HTTPError as e:
        return Respuesta(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read())
    except (urllib.error.URLError, OSError, http.client.HTTPException) as e:
        motivo = getattr(e, "reason", None) or e.__class__.__name__
        raise ErrorRed(f"Sin respuesta de la API: {motivo}") from e


def _leer_json(respuesta: Respuesta) -> Any:
    cuerpo = respuesta.cuerpo
    try:
        if respuesta.headers.get("content-encoding", "").lower() == "gzip":
            cuerpo = gzip.decompress(cuerpo)
        return json.loads(cuerpo.decode("utf-8")) if cuerpo else {}
    except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _retry_after(valor: str | None) -> int:
    try:
        segundos = int(float(str(valor).strip()))
    except (TypeError, ValueError):
        return RETRY_AFTER_POR_DEFECTO
    return min(max(segundos, 0), RETRY_AFTER_MAXIMO)


class ApiCliente:
    def __init__(
        self,
        cfg: ApiConfig,
        *,
        transporte: Transporte | None = None,
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.time,
        comprimir: bool = True,
        timeout: float = 60,
    ) -> None:
        self.cfg = cfg
        registrar_secreto(cfg.secret)
        self.transporte = transporte or transporte_urllib
        self.dormir = dormir
        self.reloj = reloj
        self.comprimir = comprimir
        self.timeout = timeout

    # ---------------------------------------------------------------- métodos
    def tomar_solicitudes(self, max_solicitudes: int = 20) -> list[dict[str, Any]]:
        datos = self._post("/solicitudes/tomar", {"max": max_solicitudes})
        return list(datos.get("solicitudes") or [])

    def iniciar_corrida(
        self,
        *,
        conjunto: str,
        empresa: str,
        tipo: str,
        partes: dict[str, str],
        solicitudes: list[int],
        fecha_corte: str | None,
        extraida_en: str,
        ventana_desde: str | None = None,
    ) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {
            "conjunto": conjunto,
            "empresa": empresa,
            "tipo": tipo,
            "partes": partes,
            "solicitudes": solicitudes,
            "fecha_corte": fecha_corte,
            "extraida_en": extraida_en,
        }
        if ventana_desde is not None:
            # Solo VENTAS (contrato §4.1): en los demás conjuntos la llave ni siquiera va.
            cuerpo["ventana_desde"] = ventana_desde
        def recuperar(datos: dict[str, Any]) -> dict[str, Any] | None:
            # La corrida abierta es la que creó el intento cuya respuesta se perdió.
            if datos.get("run_id") is None:
                return None
            return {"run_id": datos["run_id"], "estado": "abierta", "recuperada": True}

        return self._post("/corridas", cuerpo, conflicto=CorridaAbierta, recuperar=recuperar)

    def enviar_lote(
        self,
        run_id: int,
        *,
        batch: int,
        parte: str,
        columns: list[str],
        rows: list[list[Any]],
    ) -> dict[str, Any]:
        """201 (nuevo) o 200 con duplicate=true (reenvío idéntico) son éxito."""
        cuerpo = {"batch": batch, "parte": parte, "columns": columns, "rows": rows}
        return self._post(f"/corridas/{run_id}/lotes", cuerpo)

    def cerrar_corrida(
        self,
        run_id: int,
        *,
        batches: int,
        filas: dict[str, int],
        conteo_sap: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        cuerpo: dict[str, Any] = {"batches": batches, "filas": filas}
        if conteo_sap is not None:
            cuerpo["conteo_sap"] = conteo_sap

        def conflicto(mensaje: str, *, status: int | None = None, datos: Any = None) -> ApiRechazo:
            if isinstance(datos, dict) and "faltan" in datos:
                return LotesFaltantes(mensaje, status=status, datos=datos)
            return ApiRechazo(mensaje, status=status, datos=datos)

        def recuperar(datos: dict[str, Any]) -> dict[str, Any] | None:
            if datos.get("estado") != "cerrada":
                return None
            return {"run_id": run_id, "estado": "cerrada", "recuperada": True}

        return self._post(
            f"/corridas/{run_id}/cerrar", cuerpo, conflicto=conflicto, recuperar=recuperar
        )

    def fallar_corrida(self, run_id: int, error: str) -> dict[str, Any]:
        def recuperar(datos: dict[str, Any]) -> dict[str, Any] | None:
            if datos.get("estado") != "fallida":
                return None
            return {"run_id": run_id, "estado": "fallida", "recuperada": True}

        return self._post(
            f"/corridas/{run_id}/fallar", {"error": error.strip()[:MAX_ERROR]}, recuperar=recuperar
        )

    # ---------------------------------------------------------------- interno
    def cuerpo(self, datos: Any) -> bytes:
        """Bytes tal como viajan. Deterministas: el mismo dato da los mismos bytes."""
        crudo = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(crudo) > LIMITE_DESCOMPRIMIDO:
            raise ApiError(
                f"El cuerpo pesa {len(crudo):,} bytes sin comprimir; el límite es 40 MB (contrato §2)."
            )
        return gzip.compress(crudo, mtime=0) if self.comprimir else crudo

    def _post(
        self,
        relativa: str,
        datos: dict[str, Any],
        *,
        conflicto: Callable[..., ApiRechazo] = ApiRechazo,
        recuperar: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
    ) -> dict[str, Any]:
        """POST firmado con reintentos.

        `recuperar` cubre las rutas que no se pueden repetir (iniciar, cerrar, fallar):
        si un intento anterior se quedó sin respuesta (red o 5xx), la API pudo haberlo
        aplicado, y el 409 del reintento lo confirma en vez de ser un error.
        """
        # La ruta firmada va desde la raíz de la app: si BASES_SAP_API_URL tiene un
        # subdirectorio, va en la URL pero no en la firma (contrato §3).
        ruta = RUTA_BASE + relativa
        url = self.cfg.url + ruta
        cuerpo = self.cuerpo(datos)
        if len(cuerpo) > LIMITE_BYTES:
            raise ApiError(
                f"El cuerpo para {ruta} pesa {len(cuerpo):,} bytes; el límite es 10 MB (contrato §2)."
            )
        fijos = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if self.comprimir:
            fijos["Content-Encoding"] = "gzip"

        sin_respuesta = False  # algún intento anterior pudo aplicarse sin que lo supiéramos
        for intento in range(1, MAX_INTENTOS + 1):
            encabezados = {
                **fijos,
                **firma.encabezados(
                    self.cfg.key_id, self.cfg.secret, ruta, cuerpo, timestamp=int(self.reloj())
                ),
            }
            try:
                respuesta = self.transporte(url, encabezados, cuerpo, self.timeout)
            except ErrorRed as e:
                if intento == MAX_INTENTOS:
                    log.error(f"POST {ruta}: sin respuesta (intento {intento} de {MAX_INTENTOS}); me rindo")
                    raise
                espera = ESPERAS_S[intento - 1]
                log.warning(
                    f"POST {ruta}: sin respuesta (intento {intento} de {MAX_INTENTOS}): {e}; "
                    f"reintento en {espera} s"
                )
                sin_respuesta = True
                self.dormir(espera)
                continue

            status = respuesta.status
            contenido = _leer_json(respuesta)
            if 200 <= status < 300:
                log.info(f"POST {ruta} → {status} (intento {intento})")
                if not isinstance(contenido, dict):
                    raise ApiError(f"La API respondió {status} en {ruta} sin un objeto JSON.", status=status)
                return contenido

            if status == 409 and sin_respuesta and recuperar and isinstance(contenido, dict):
                recuperado = recuperar(contenido)
                if recuperado is not None:
                    log.warning(f"POST {ruta} → 409 tras un intento sin respuesta: ya estaba aplicado")
                    return recuperado

            if 300 <= status < 400:
                destino = respuesta.headers.get("location", "?")
                raise ApiError(
                    f"La API redirige {ruta} a {destino} ({status}). Corrige BASES_SAP_API_URL "
                    "en robot/.env con la dirección final (https y sin redirecciones).",
                    status=status,
                )

            reintentable = status >= 500 or status == 429
            if not reintentable or intento == MAX_INTENTOS:
                log.error(f"POST {ruta} → {status} (intento {intento} de {MAX_INTENTOS})")
                raise self._error(status, ruta, contenido, conflicto)

            if status == 429:
                espera = _retry_after(respuesta.headers.get("retry-after"))
            else:
                espera = ESPERAS_S[intento - 1]
                sin_respuesta = True
            log.warning(f"POST {ruta} → {status} (intento {intento} de {MAX_INTENTOS}); reintento en {espera} s")
            self.dormir(espera)

        raise AssertionError("inalcanzable")  # pragma: no cover

    @staticmethod
    def _error(
        status: int, ruta: str, contenido: Any, conflicto: Callable[..., ApiRechazo]
    ) -> ApiError:
        datos = contenido if contenido is not None else {}
        mensaje_api = datos.get("message") if isinstance(datos, dict) else None
        if status == 401:
            return FirmaRechazada(
                f"La API rechazó la firma (401) en {ruta}. Revisa BASES_SAP_ROBOT_KEY_ID y "
                "BASES_SAP_ROBOT_SECRET en robot/.env (deben coincidir con ROBOT_HMAC_KEYS del "
                "servidor) y que la hora del PC esté bien: la API tolera 5 minutos de diferencia.",
                status=status,
                datos=datos,
            )
        if status == 413:
            return ApiError(f"La API rechazó el cuerpo por tamaño (413) en {ruta}.", status=status, datos=datos)
        if 400 <= status < 500 and status != 429:
            clase = conflicto if status == 409 else ApiRechazo
            detalle = f": {mensaje_api}" if mensaje_api else ""
            errores = datos.get("errors") if isinstance(datos, dict) else None
            if isinstance(errores, dict) and errores:
                primeros = list(errores.items())[:5]
                detalle += " (" + "; ".join(
                    f"{campo}: {' '.join(map(str, m)) if isinstance(m, list) else m}"
                    for campo, m in primeros
                ) + ")"
            return clase(f"La API respondió {status} en {ruta}{detalle}", status=status, datos=datos)
        return ApiError(
            f"La API respondió {status} en {ruta} después de {MAX_INTENTOS} intentos.",
            status=status,
            datos=datos,
        )
