"""Conexión y consultas a SAP HANA (SAP Business One), una conexión por empresa."""
from __future__ import annotations

import socket
import time
from contextlib import contextmanager
from typing import Any, Iterator, Sequence

from config import EmpresaHana, HanaConfig
from registro import obtener, registrar_secreto

log = obtener("hana")

LOTE = 5000  # filas por fetch, para no cargar todo en memoria de golpe

# Texto (en minúsculas) de los errores del driver que vienen del TLS.
_PISTAS_TLS = ("ssl", "tls", "certificate", "handshake")

AYUDA_TLS = (
    "El fallo parece del cifrado TLS con HANA. Para corregirlo, en robot/.env:\n"
    "  1. Solo como último recurso, HANA_SSL_VALIDATE=false (cifra, pero no "
    "comprueba el certificado).\n"
    "  2. Si el servidor no soporta TLS, HANA_ENCRYPT=false y avisa a TI.\n"
    "Después vuelve a correr: python run_robot.py --diagnostico"
)

# El modo TLS se anuncia una sola vez por ejecución, aunque se conecte a cada empresa.
_modo_tls_avisado = False


class HanaError(RuntimeError):
    """No se pudo conectar a HANA o ejecutar la consulta."""


def describir_cifrado(cfg: HanaConfig) -> str:
    """Modo TLS de la conexión, para el log y el resumen del diagnóstico."""
    validacion = cfg.encrypt and cfg.validar_certificado
    return (
        f"cifrado {'sí' if cfg.encrypt else 'no'}, "
        f"validación de certificado {'sí' if validacion else 'no'}"
    )


def _avisar_modo_tls(cfg: HanaConfig) -> None:
    global _modo_tls_avisado
    if _modo_tls_avisado:
        return
    _modo_tls_avisado = True
    if not cfg.encrypt:
        log.warning("Conexión a HANA sin cifrar (HANA_ENCRYPT=false): el tráfico "
                    "entre la VPN y HANA viaja en claro.")
        return
    log.info("Conexión a HANA cifrada (TLS), validación de certificado %s.",
             "sí" if cfg.validar_certificado else "no")
    if not cfg.validar_certificado:
        log.warning("No se valida el certificado de HANA (HANA_SSL_VALIDATE=false): "
                    "cifra, pero queda expuesta a un intermediario activo.")


def _opciones_tls(cfg: HanaConfig) -> dict[str, Any]:
    """Argumentos TLS de dbapi.connect; anuncia el modo elegido una vez por ejecución."""
    _avisar_modo_tls(cfg)
    if not cfg.encrypt:
        return {"encrypt": False, "sslValidateCertificate": False}
    return {"encrypt": True, "sslValidateCertificate": cfg.validar_certificado}


def _es_error_tls(exc: BaseException) -> bool:
    texto = str(exc).lower()
    return any(pista in texto for pista in _PISTAS_TLS)


def _esperar_puerto(host: str, port: int, espera_total: int = 60) -> bool:
    """Espera a que el puerto responda antes de invocar al driver.

    Sophos reporta el túnel como "conectado" unos segundos antes de terminar de
    instalar las rutas hacia la red interna, así que una comprobación inmediata
    da un falso negativo. Se sondea hasta `espera_total` segundos.
    """
    limite = time.monotonic() + espera_total
    primer_intento = True
    while True:
        try:
            with socket.create_connection((host, port), timeout=5):
                return True
        except OSError:
            if time.monotonic() >= limite:
                return False
            if primer_intento:
                log.info("Esperando a que la VPN termine de instalar la ruta "
                         "hacia %s:%s...", host, port)
                primer_intento = False
            time.sleep(2)


@contextmanager
def conectar(cfg: HanaConfig, empresa: EmpresaHana, intentos: int = 3) -> Iterator[Any]:
    """Abre una conexión a HANA con el usuario y el esquema de la empresa.

    Requiere que la VPN ya esté arriba.
    """
    try:
        from hdbcli import dbapi
    except ImportError as exc:
        raise HanaError(
            "Falta el driver de SAP HANA. Instálalo con:\n"
            "    pip install -r robot/requirements.txt"
        ) from exc

    registrar_secreto(empresa.password)
    codigo = empresa.codigo

    if not _esperar_puerto(cfg.host, cfg.port):
        raise HanaError(
            f"No hay ruta hasta {cfg.host}:{cfg.port} tras 60s de espera.\n"
            "Causas habituales:\n"
            "  - La VPN no está realmente conectada o no enruta esa subred.\n"
            "  - HANA_HOST / HANA_PORT están mal en robot/.env "
            "(SAP B1 suele usar 30013 para SYSTEMDB y 30015 para el tenant).\n"
            "  - El firewall del servidor bloquea el puerto."
        )

    conn = None
    ultimo: Exception | None = None
    tls = _opciones_tls(cfg)
    for intento in range(1, intentos + 1):
        try:
            log.info("Conectando a HANA %s:%s (%s, esquema %s), intento %d/%d...",
                     cfg.host, cfg.port, codigo, empresa.esquema, intento, intentos)
            extra = {"currentSchema": empresa.esquema} if empresa.esquema else {}
            extra.update(tls)
            conn = dbapi.connect(
                address=cfg.host,
                port=cfg.port,
                user=empresa.usuario,
                password=empresa.password,
                connectTimeout=30000,
                communicationTimeout=cfg.timeout * 1000,
                autocommit=True,
                **extra,
            )
            log.info("Conexión a HANA establecida (%s).", codigo)
            break
        except Exception as exc:  # dbapi.Error y derivados
            ultimo = exc
            texto = str(exc).lower()
            if "authentication failed" in texto or "invalid username" in texto:
                raise HanaError(
                    f"HANA rechazó el usuario o la contraseña de {codigo}. Revisa "
                    f"HANA_{codigo}_USER / HANA_{codigo}_PASSWORD en robot/.env. "
                    "(No se reintenta para no bloquear el usuario.)"
                ) from exc
            log.warning("Intento %d fallido: %s", intento, exc)
            if intento < intentos:
                time.sleep(5 * intento)

    if conn is None:
        mensaje = f"No se pudo conectar a HANA ({codigo}) tras {intentos} intentos: {ultimo}"
        if cfg.encrypt and ultimo is not None and _es_error_tls(ultimo):
            mensaje = f"{mensaje}\n{AYUDA_TLS}"
        raise HanaError(mensaje) from ultimo

    try:
        yield conn
    finally:
        try:
            conn.close()
            log.info("Conexión a HANA cerrada (%s).", codigo)
        except Exception:
            log.debug("Error al cerrar la conexión (se ignora).", exc_info=True)


def ejecutar(
    conn: Any,
    sql: str,
    etiqueta: str,
    esquema: str = "",
    params: Sequence[Any] | None = None,
) -> tuple[list[str], list[tuple]]:
    """Ejecuta una consulta y devuelve (nombres_de_columna, filas).

    0 filas no es un error aquí: una parte incremental puede no tener cambios.
    Quien llama decide si 0 filas invalida la corrida.
    """
    inicio = time.monotonic()
    cursor = conn.cursor()
    try:
        log.info("Ejecutando consulta '%s'...", etiqueta)
        if params is not None:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)

        if cursor.description is None:
            raise HanaError(f"La consulta '{etiqueta}' no devolvió resultados.")
        columnas = [d[0] for d in cursor.description]

        filas: list[tuple] = []
        while True:
            lote = cursor.fetchmany(LOTE)
            if not lote:
                break
            filas.extend(tuple(f) for f in lote)
            if len(filas) % (LOTE * 10) == 0:
                log.info("  ... %d filas leídas", len(filas))

        segundos = time.monotonic() - inicio
        log.info("Consulta '%s': %d filas en %.1fs.", etiqueta, len(filas), segundos)
        return columnas, filas
    except HanaError:
        raise
    except Exception as exc:
        # Solo una tabla inexistente apunta al esquema; una columna que no existe
        # (p. ej. UpdateTS en OITM) se reporta con el texto de HANA tal cual.
        if "invalid table name" in str(exc).lower():
            raise HanaError(
                f"Consulta '{etiqueta}': HANA no encuentra una tabla ({exc}). "
                f"Puede faltar la tabla en el esquema '{esquema}' o el esquema ser "
                "incorrecto: revisa HANA_SGX_SCHEMA / HANA_SDC_SCHEMA en robot/.env."
            ) from exc
        raise HanaError(f"Error ejecutando la consulta '{etiqueta}': {exc}") from exc
    finally:
        try:
            cursor.close()
        except Exception:
            pass


def contar(
    conn: Any, sql: str, etiqueta: str, params: Sequence[Any] | None = None
) -> int:
    """Ejecuta un SELECT COUNT(*) y devuelve el entero."""
    _, filas = ejecutar(conn, sql, etiqueta, params=params)
    if len(filas) != 1 or len(filas[0]) != 1:
        raise HanaError(
            f"La consulta de conteo '{etiqueta}' debía devolver una fila con una "
            f"columna y devolvió {len(filas)} filas."
        )
    return int(filas[0][0])


def listar_esquemas(conn: Any) -> list[str]:
    """Ayuda de diagnóstico: esquemas visibles que parecen de SAP B1."""
    cur = conn.cursor()
    try:
        cur.execute('SELECT SCHEMA_NAME FROM "SYS"."SCHEMAS" ORDER BY SCHEMA_NAME')
        nombres = [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
    # Se descartan los esquemas internos de HANA (_SYS_*, SYS, HANA_*).
    return [
        n for n in nombres
        if not n.startswith("_SYS") and n not in {"SYS", "SYSTEM", "PUBLIC"}
        and not n.startswith("HANA_")
    ]
