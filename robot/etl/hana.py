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


class HanaError(RuntimeError):
    """No se pudo conectar a HANA o ejecutar la consulta."""


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
    for intento in range(1, intentos + 1):
        try:
            log.info("Conectando a HANA %s:%s (%s, esquema %s), intento %d/%d...",
                     cfg.host, cfg.port, codigo, empresa.esquema, intento, intentos)
            extra = {"currentSchema": empresa.esquema} if empresa.esquema else {}
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
        raise HanaError(
            f"No se pudo conectar a HANA ({codigo}) tras {intentos} intentos: {ultimo}"
        ) from ultimo

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
        texto = str(exc).lower()
        if "invalid table name" in texto or "not found" in texto:
            raise HanaError(
                f"Consulta '{etiqueta}': HANA no encuentra una tabla. "
                f"Lo más probable es que el esquema ('{esquema}') sea incorrecto. "
                "Revisa HANA_SGX_SCHEMA / HANA_SDC_SCHEMA en robot/.env."
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
