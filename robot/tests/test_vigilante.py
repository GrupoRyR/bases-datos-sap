"""Vigilante del robot: registro de la última completa (T1)."""
from __future__ import annotations

import json
from datetime import date

import pytest

import config
import run_robot
import vigilante
from fake_hana import VpnFalsa

HOY = date(2026, 10, 26)  # el día de AHORA (conftest)


def _main(e, *argumentos, vpn=None, **kwargs):
    kwargs.setdefault("fabrica_api", lambda cfg_api: e.nuevo_cliente(cfg_api))
    kwargs.setdefault("fabrica_vpn", lambda cfg_vpn: vpn or e.vpn)
    kwargs.setdefault("conectar", e.hana.conectar)
    kwargs.setdefault("ahora", e.ahora)
    return run_robot.main(list(argumentos), **kwargs)


def _registro() -> dict:
    return json.loads((config.STATE_DIR / vigilante.ARCHIVO_COMPLETA).read_text(encoding="utf-8"))


# --- Registro de la última completa (T1) --------------------------------------------


def test_guardar_completa_escribe_fecha_estado_empresas_y_etapas():
    vigilante.guardar_completa(fecha=HOY, estado="ERROR", empresas=["SGX", "SDC"], etapas=["HANA", "ARCHIVO"])
    registro = _registro()
    assert {k: registro[k] for k in ("fecha", "estado", "empresas", "etapas")} == {
        "fecha": "2026-10-26", "estado": "ERROR", "empresas": ["SGX", "SDC"], "etapas": ["HANA", "ARCHIVO"],
    }
    assert registro["terminada_en"].endswith("+00:00")


def test_guardar_completa_no_repite_etapas():
    vigilante.guardar_completa(fecha=HOY, estado="ERROR", empresas=["SGX"], etapas=["VPN", "VPN", "HANA", "VPN"])
    assert _registro()["etapas"] == ["VPN", "HANA"]


def test_guardar_completa_no_revienta_si_no_puede_escribir(monkeypatch, tmp_path, caplog):
    bloqueada = tmp_path / "archivo-no-carpeta"
    bloqueada.write_text("x", encoding="utf-8")
    monkeypatch.setattr(config, "STATE_DIR", bloqueada)  # mkdir falla: es un archivo
    vigilante.guardar_completa(fecha=HOY, estado="OK", empresas=["SGX", "SDC"], etapas=[])
    assert "No se pudo guardar el registro de la completa" in caplog.text


def test_completa_buena_de_hoy_con_un_registro_bueno():
    vigilante.guardar_completa(fecha=HOY, estado="OK", empresas=["SGX", "SDC"], etapas=[])
    assert vigilante.completa_buena_de_hoy(HOY) is True


@pytest.mark.parametrize("fecha, estado, empresas", [
    (date(2026, 10, 25), "OK", ["SGX", "SDC"]),   # de ayer
    (HOY, "ERROR", ["SGX", "SDC"]),               # con fallos
    (HOY, "OK", ["SGX"]),                         # de una sola empresa
])
def test_completa_buena_de_hoy_no_cuenta(fecha, estado, empresas):
    vigilante.guardar_completa(fecha=fecha, estado=estado, empresas=empresas, etapas=[])
    assert vigilante.completa_buena_de_hoy(HOY) is False


def test_completa_buena_de_hoy_sin_registro():
    assert vigilante.completa_buena_de_hoy(HOY) is False


@pytest.mark.parametrize("contenido", ["{no es json", "[]", '{"estado": "OK"}', '{"fecha": 5, "estado": "OK", "empresas": 3}'])
def test_completa_buena_de_hoy_con_registro_danado(contenido):
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    (config.STATE_DIR / vigilante.ARCHIVO_COMPLETA).write_text(contenido, encoding="utf-8")
    assert vigilante.completa_buena_de_hoy(HOY) is False


def test_vigilante_no_importa_run_robot():
    fuente = (config.BASE_DIR / "vigilante.py").read_text(encoding="utf-8")
    assert "import run_robot" not in fuente and "from run_robot" not in fuente


def test_la_completa_buena_queda_registrada(entorno, correos):
    assert _main(entorno, "--completa") == 0
    registro = _registro()
    assert (registro["fecha"], registro["estado"], registro["empresas"], registro["etapas"]) == (
        "2026-10-26", "OK", ["SGX", "SDC"], [],
    )
    assert vigilante.completa_buena_de_hoy(HOY)


def test_la_completa_con_fallos_queda_registrada_con_sus_etapas(entorno, correos):
    e = entorno
    e.hana.empresas_que_fallan.add("SDC")
    e.hana.partes_que_fallan.add(("SGX", "archivo/AUDITORIA/USR5"))
    assert _main(e, "--completa") == 1
    registro = _registro()
    assert (registro["estado"], registro["etapas"]) == ("ERROR", ["HANA", "ARCHIVO"])
    assert "SDC" not in json.dumps(registro["etapas"])  # solo nombres de etapa, nunca mensajes
    assert not vigilante.completa_buena_de_hoy(HOY)


def test_la_completa_sin_vpn_queda_registrada_con_error(entorno, correos):
    e = entorno
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    assert _main(e, "--completa", vpn=vpn) == 1
    assert (_registro()["estado"], _registro()["etapas"]) == ("ERROR", ["VPN"])


def test_la_completa_de_una_empresa_no_es_buena_de_hoy(entorno, correos):
    assert _main(entorno, "--completa", "--empresa", "SGX") == 0
    assert (_registro()["estado"], _registro()["empresas"]) == ("OK", ["SGX"])
    assert not vigilante.completa_buena_de_hoy(HOY)


def test_error_inesperado_en_la_completa_queda_registrado(entorno, correos):
    def explota(cfg_api):
        raise RuntimeError("algo raro")

    assert _main(entorno, "--completa", fabrica_api=explota) == 1
    assert (_registro()["estado"], _registro()["etapas"]) == ("ERROR", ["INESPERADO"])


def test_ctrl_c_no_registra_la_completa(entorno, correos):
    def corta(cfg_api):
        raise KeyboardInterrupt

    assert _main(entorno, "--completa", fabrica_api=corta) == 130
    assert not (config.STATE_DIR / vigilante.ARCHIVO_COMPLETA).exists()


@pytest.mark.parametrize("argumentos", [
    ("--archivo", "registros"),
    ("--carga-produccion", "--desde", "2026-08-01"),
])
def test_otros_modos_no_registran_la_completa(entorno, correos, argumentos):
    _main(entorno, *argumentos)
    assert not (config.STATE_DIR / vigilante.ARCHIVO_COMPLETA).exists()
