from __future__ import annotations

import logging
import sys
import types
from dataclasses import replace
from typing import Any

import pytest

import hana
from config import EmpresaHana, HanaConfig
from hana import HanaError


class CursorFalso:
    def __init__(self, columnas: list[str], filas: list[tuple]) -> None:
        self.description = [(c,) for c in columnas] if columnas else None
        self._filas = list(filas)
        self.ejecutado: list[tuple[str, Any]] = []
        self.cerrado = False

    def execute(self, sql: str, params: Any = None) -> None:
        self.ejecutado.append((sql, params))

    def fetchmany(self, n: int) -> list[tuple]:
        lote, self._filas = self._filas[:n], self._filas[n:]
        return lote

    def close(self) -> None:
        self.cerrado = True


class ConexionFalsa:
    def __init__(self, cursor: CursorFalso | None = None) -> None:
        self._cursor = cursor
        self.cerrada = False

    def cursor(self) -> CursorFalso:
        assert self._cursor is not None
        return self._cursor

    def close(self) -> None:
        self.cerrada = True


class DbapiFalso:
    def __init__(self, errores: list[Exception] | None = None) -> None:
        self.errores = list(errores or [])
        self.llamadas: list[dict[str, Any]] = []
        self.conexion = ConexionFalsa()

    def connect(self, **kwargs: Any) -> ConexionFalsa:
        self.llamadas.append(kwargs)
        if self.errores:
            raise self.errores.pop(0)
        return self.conexion


@pytest.fixture
def dbapi(monkeypatch: pytest.MonkeyPatch, reloj) -> DbapiFalso:
    falso = DbapiFalso()
    modulo = types.ModuleType("hdbcli")
    modulo.dbapi = falso  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "hdbcli", modulo)
    monkeypatch.setattr(hana, "_esperar_puerto", lambda host, port: True)
    monkeypatch.setattr(hana.time, "sleep", reloj.sleep)
    return falso


def _cfg() -> HanaConfig:
    return HanaConfig(
        host="hana.prueba.local",
        port=30015,
        timeout=600,
        empresas={
            "SGX": EmpresaHana("SGX", "usuario-sgx", "clave-sgx-prueba", "SEGUREX"),
            "SDC": EmpresaHana("SDC", "usuario-sdc", "clave-sdc-prueba", "HBT_SDERIVADOS"),
        },
    )


def test_conecta_con_el_usuario_y_esquema_de_la_empresa(dbapi: DbapiFalso) -> None:
    cfg = _cfg()

    with hana.conectar(cfg, cfg.empresas["SDC"]) as conn:
        assert conn is dbapi.conexion

    llamada = dbapi.llamadas[0]
    assert llamada["address"] == "hana.prueba.local"
    assert llamada["port"] == 30015
    assert llamada["user"] == "usuario-sdc"
    assert llamada["password"] == "clave-sdc-prueba"
    assert llamada["currentSchema"] == "HBT_SDERIVADOS"
    assert dbapi.conexion.cerrada is True


def test_reintenta_un_error_de_red(dbapi: DbapiFalso) -> None:
    dbapi.errores = [RuntimeError("connection reset")]
    cfg = _cfg()

    with hana.conectar(cfg, cfg.empresas["SGX"]):
        pass

    assert len(dbapi.llamadas) == 2


def test_clave_rechazada_no_se_reintenta(dbapi: DbapiFalso) -> None:
    dbapi.errores = [RuntimeError("authentication failed"), RuntimeError("no")]
    cfg = _cfg()

    with pytest.raises(HanaError, match="HANA_SGX_PASSWORD"):
        with hana.conectar(cfg, cfg.empresas["SGX"]):
            pass

    assert len(dbapi.llamadas) == 1


def test_sin_ruta_al_puerto_falla(dbapi: DbapiFalso, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hana, "_esperar_puerto", lambda host, port: False)
    cfg = _cfg()

    with pytest.raises(HanaError, match="No hay ruta"):
        with hana.conectar(cfg, cfg.empresas["SGX"]):
            pass

    assert dbapi.llamadas == []


def _textos(caplog: pytest.LogCaptureFixture, nivel: int = logging.INFO) -> str:
    return "\n".join(r.getMessage() for r in caplog.records if r.levelno >= nivel)


def test_por_defecto_cifra_y_valida_el_certificado(dbapi: DbapiFalso, caplog) -> None:
    cfg = _cfg()

    with caplog.at_level(logging.INFO, logger="bases_sap.hana"):
        with hana.conectar(cfg, cfg.empresas["SGX"]):
            pass

    llamada = dbapi.llamadas[0]
    assert llamada["encrypt"] is True
    assert llamada["sslValidateCertificate"] is True
    assert "sslTrustStore" not in llamada
    assert "Conexión a HANA cifrada (TLS)" in _textos(caplog)
    assert _textos(caplog, logging.WARNING) == ""


def test_hana_encrypt_false_conecta_sin_cifrar_y_avisa(dbapi: DbapiFalso, caplog) -> None:
    cfg = replace(_cfg(), encrypt=False)

    with caplog.at_level(logging.INFO, logger="bases_sap.hana"):
        with hana.conectar(cfg, cfg.empresas["SGX"]):
            pass

    llamada = dbapi.llamadas[0]
    assert llamada["encrypt"] is False
    assert llamada["sslValidateCertificate"] is False
    avisos = _textos(caplog, logging.WARNING)
    assert "sin cifrar" in avisos and "HANA_ENCRYPT=false" in avisos


def test_sin_validar_el_certificado_cifra_y_avisa(dbapi: DbapiFalso, caplog) -> None:
    cfg = replace(_cfg(), validar_certificado=False)

    with caplog.at_level(logging.INFO, logger="bases_sap.hana"):
        with hana.conectar(cfg, cfg.empresas["SGX"]):
            pass

    llamada = dbapi.llamadas[0]
    assert llamada["encrypt"] is True
    assert llamada["sslValidateCertificate"] is False
    assert "HANA_SSL_VALIDATE=false" in _textos(caplog, logging.WARNING)


def test_el_modo_tls_se_anuncia_una_vez_por_ejecucion(dbapi: DbapiFalso, caplog) -> None:
    cfg = replace(_cfg(), validar_certificado=False)

    with caplog.at_level(logging.INFO, logger="bases_sap.hana"):
        for codigo in ("SGX", "SDC"):
            with hana.conectar(cfg, cfg.empresas[codigo]):
                pass

    assert len(dbapi.llamadas) == 2
    assert all(llamada["sslValidateCertificate"] is False for llamada in dbapi.llamadas)
    assert _textos(caplog).count("Conexión a HANA cifrada (TLS)") == 1
    assert _textos(caplog, logging.WARNING).count("HANA_SSL_VALIDATE=false") == 1


ERROR_TLS = "(-10709, 'Connection failed (RTE:[300015] SSL certificate validation failed: host name mismatch')"


def test_un_error_de_tls_explica_como_corregirlo(dbapi: DbapiFalso) -> None:
    dbapi.errores = [RuntimeError(ERROR_TLS)] * 3
    cfg = _cfg()

    with pytest.raises(HanaError) as error:
        with hana.conectar(cfg, cfg.empresas["SGX"]):
            pass

    mensaje = str(error.value)
    assert "robot/.env" in mensaje
    assert "HANA_SSL_VALIDATE=false" in mensaje
    assert "HANA_ENCRYPT=false" in mensaje
    assert "--diagnostico" in mensaje
    assert "TRUSTSTORE" not in mensaje


def test_un_error_que_no_es_de_tls_no_sugiere_apagar_el_cifrado(dbapi: DbapiFalso) -> None:
    dbapi.errores = [RuntimeError("Connection refused")] * 3
    cfg = _cfg()

    with pytest.raises(HanaError) as error:
        with hana.conectar(cfg, cfg.empresas["SGX"]):
            pass

    assert len(dbapi.llamadas) == 3
    assert "HANA_ENCRYPT" not in str(error.value)


def test_sin_cifrado_un_error_de_tls_no_trae_la_ayuda(dbapi: DbapiFalso) -> None:
    dbapi.errores = [RuntimeError(ERROR_TLS)] * 3
    cfg = replace(_cfg(), encrypt=False)

    with pytest.raises(HanaError) as error:
        with hana.conectar(cfg, cfg.empresas["SGX"]):
            pass

    assert "HANA_SSL_VALIDATE" not in str(error.value)


def test_sin_validar_la_ayuda_no_sugiere_lo_que_ya_esta_apagado(dbapi: DbapiFalso) -> None:
    dbapi.errores = [RuntimeError(ERROR_TLS)] * 3
    cfg = replace(_cfg(), validar_certificado=False)

    with pytest.raises(HanaError) as error:
        with hana.conectar(cfg, cfg.empresas["SGX"]):
            pass

    mensaje = str(error.value)
    assert "HANA_SSL_VALIDATE" not in mensaje
    assert "HANA_ENCRYPT=false" in mensaje


def test_describir_cifrado_resume_el_modo() -> None:
    cfg = _cfg()

    assert hana.describir_cifrado(cfg) == "cifrado sí, validación de certificado sí"
    assert hana.describir_cifrado(replace(cfg, validar_certificado=False)) == (
        "cifrado sí, validación de certificado no"
    )
    assert hana.describir_cifrado(replace(cfg, encrypt=False)) == "cifrado no, validación de certificado no"


def test_ejecutar_devuelve_columnas_y_filas_y_pasa_parametros() -> None:
    cursor = CursorFalso(["codigo", "nombre"], [("C1", "Uno"), ("C2", "Dos")])

    columnas, filas = hana.ejecutar(
        ConexionFalsa(cursor), "SELECT ... WHERE X > ?", "clientes", "SEGUREX", params=["2026-10-01"]
    )

    assert columnas == ["codigo", "nombre"]
    assert filas == [("C1", "Uno"), ("C2", "Dos")]
    assert cursor.ejecutado == [("SELECT ... WHERE X > ?", ["2026-10-01"])]
    assert cursor.cerrado is True


def test_ejecutar_sin_parametros_no_los_envia() -> None:
    cursor = CursorFalso(["codigo"], [])

    columnas, filas = hana.ejecutar(ConexionFalsa(cursor), "SELECT 1", "vacia")

    assert columnas == ["codigo"]
    assert filas == []
    assert cursor.ejecutado == [("SELECT 1", None)]


def test_ejecutar_traduce_tabla_inexistente() -> None:
    class CursorQueFalla(CursorFalso):
        def execute(self, sql: str, params: Any = None) -> None:
            raise RuntimeError("invalid table name: OCRD")

    with pytest.raises(HanaError, match="SEGUREX"):
        hana.ejecutar(ConexionFalsa(CursorQueFalla([], [])), "SELECT 1", "x", "SEGUREX")


def test_contar_devuelve_un_entero() -> None:
    cursor = CursorFalso(["COUNT(*)"], [(1234,)])

    total = hana.contar(ConexionFalsa(cursor), "SELECT COUNT(*) FROM (?) X", "conteo", params=[1])

    assert total == 1234
    assert isinstance(total, int)
    assert cursor.ejecutado[0][1] == [1]


def test_contar_con_resultado_raro_falla() -> None:
    cursor = CursorFalso(["a", "b"], [(1, 2)])

    with pytest.raises(HanaError, match="conteo"):
        hana.contar(ConexionFalsa(cursor), "SELECT 1, 2 FROM DUMMY", "conteo")


def test_ejecutar_columna_inexistente_no_culpa_al_esquema() -> None:
    class CursorQueFalla(CursorFalso):
        def execute(self, sql: str, params: Any = None) -> None:
            raise RuntimeError("invalid column name: UPDATETS: not found")

    with pytest.raises(HanaError) as error:
        hana.ejecutar(ConexionFalsa(CursorQueFalla([], [])), "SELECT 1", "articulos", "SEGUREX")

    assert "invalid column name: UPDATETS: not found" in str(error.value)
    assert "esquema" not in str(error.value)
