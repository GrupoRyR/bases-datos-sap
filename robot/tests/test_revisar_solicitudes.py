from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import pytest

import config
import revisar_solicitudes
from conftest import AHORA
from fake_hana import revisar_fases

CANDADO = "robot.lock"


def _revisar(e, ahora=None, **kwargs) -> int:
    kwargs.setdefault("fabrica_api", lambda cfg_api: e.nuevo_cliente(cfg_api))
    kwargs.setdefault("fabrica_vpn", lambda cfg_vpn: e.vpn)
    kwargs.setdefault("conectar", e.hana.conectar)
    kwargs.setdefault("ahora", ahora or e.ahora)
    return revisar_solicitudes.main([], **kwargs)


def _prohibida(*args, **kwargs):
    raise AssertionError("no debía llamarse")


def _candado_suelto() -> bool:
    return not (config.STATE_DIR / CANDADO).exists()


def _estado() -> dict:
    return json.loads((config.STATE_DIR / "ultima_ejecucion.json").read_text(encoding="utf-8"))


def test_en_una_franja_no_pregunta_a_la_api(entorno, correos):
    e = entorno
    e.servidor.encolar_solicitud({"id": 1, "empresa": "SGX", "conjunto": "CARTERA",
                                  "parte": None, "desde": {}})
    a_las_12 = lambda: datetime(2026, 10, 26, 12, 5, tzinfo=config.BOGOTA)  # noqa: E731
    assert _revisar(e, ahora=a_las_12, fabrica_api=_prohibida, fabrica_vpn=_prohibida) == 0
    assert e.servidor.peticiones == []
    assert e.linea == []
    assert _candado_suelto()
    assert correos == []


def test_con_el_candado_ocupado_no_pregunta_a_la_api(entorno, correos, candado_ajeno):
    e = entorno
    ruta = candado_ajeno()
    assert _revisar(e, fabrica_api=_prohibida, fabrica_vpn=_prohibida) == 0
    assert e.servidor.peticiones == []
    assert json.loads(ruta.read_text(encoding="utf-8"))["pid"] == 4242  # sigue siendo del otro


def test_sin_solicitudes_no_sube_la_vpn_ni_escribe_en_el_log(entorno, correos, caplog):
    e = entorno
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _revisar(e, fabrica_vpn=_prohibida) == 0
    assert [p.nombre for p in e.servidor.peticiones] == ["tomar"]
    assert e.servidor.peticiones[0].datos == {"max": 20}
    assert e.hana.ejecutadas == []
    assert not [ev for ev in e.linea if ev[0] in ("vpn", "hana")]
    assert [r for r in caplog.records if r.levelno >= logging.INFO] == []
    assert _candado_suelto()
    assert not (config.STATE_DIR / "ultima_ejecucion.json").exists()


def test_corre_las_solicitudes_y_suelta_el_candado(entorno, correos):
    e = entorno
    e.servidor.encolar_solicitud({"id": 118, "empresa": "SGX", "conjunto": "MAESTROS", "parte": "clientes",
                                  "desde": {"clientes": "2026-10-12T00:00:00-05:00"}})
    e.servidor.encolar_solicitud({"id": 119, "empresa": "SDC", "conjunto": "CARTERA",
                                  "parte": None, "desde": {}})
    assert _revisar(e) == 0
    corridas = [(c.conjunto, c.empresa, c.tipo, c.estado, c.solicitudes) for c in e.servidor.corridas.values()]
    assert corridas == [
        ("MAESTROS", "SGX", "solicitud", "cerrada", [118]),
        ("CARTERA", "SDC", "solicitud", "cerrada", [119]),
    ]
    assert e.servidor.estado_solicitudes == {118: "terminada", 119: "terminada"}
    assert e.vpn.conexiones == 1
    revisar_fases(e.linea)
    assert e.linea.index(("api", "tomar")) < e.linea.index(("vpn", "conectar"))
    assert _candado_suelto()
    assert correos == []
    assert (_estado()["estado"], _estado()["modo"]) == ("OK", "solicitudes")


def test_falla_dentro_de_una_corrida_avisa_una_vez(entorno, correos):
    e = entorno
    e.servidor.encolar_solicitud({"id": 5, "empresa": "SGX", "conjunto": "CARTERA",
                                  "parte": None, "desde": {}})
    e.hana.empresas_que_fallan.add("SGX")
    assert _revisar(e) == 1
    assert e.servidor.estado_solicitudes[5] == "fallida"
    assert len(correos) == 1
    assert [etapa for etapa, _ in correos[0]] == ["HANA"]
    assert _candado_suelto()
    assert _estado()["estado"] == "ERROR"


def test_solicitud_invalida_se_reporta_y_las_demas_corren(entorno, correos):
    e = entorno
    e.servidor.encolar_solicitud({"id": 30, "empresa": "SGX", "conjunto": "INVENTARIO",
                                  "parte": None, "desde": {}})
    e.servidor.encolar_solicitud({"id": 31, "empresa": "SGX", "conjunto": "CARTERA",
                                  "parte": None, "desde": {}})
    assert _revisar(e) == 1
    assert [c.estado for c in e.servidor.corridas.values()] == ["cerrada"]
    assert e.servidor.estado_solicitudes[31] == "terminada"
    assert [etapa for etapa, _ in correos[0]] == ["SOLICITUDES"]
    assert "30" in correos[0][0][1]


def test_tomar_rechazado_avisa_una_vez_por_hora(entorno, correos):
    e = entorno
    e.servidor.programar_fallas("tomar", status=401, veces=3)
    assert _revisar(e, fabrica_vpn=_prohibida) == 1
    assert _revisar(e, fabrica_vpn=_prohibida) == 1  # el minuto siguiente: sin otro correo
    assert len(correos) == 1
    assert correos[0][0][0] == "SOLICITUDES"
    assert "401" in correos[0][0][1]
    assert _candado_suelto()
    una_hora_despues = lambda: AHORA + timedelta(hours=1, minutes=1)  # noqa: E731
    assert _revisar(e, ahora=una_hora_despues, fabrica_vpn=_prohibida) == 1
    assert len(correos) == 2


def test_error_de_configuracion_sale_con_2_y_avisa_una_vez_al_dia(correos, monkeypatch):
    monkeypatch.setenv("HANA_HOST", "hana.prueba.local")
    monkeypatch.setenv("ALERTA_SMTP_HOST", "smtp.prueba.local")
    monkeypatch.setenv("ALERTA_DESTINATARIOS", "ti@prueba.local")
    otras = {"fabrica_api": _prohibida, "fabrica_vpn": _prohibida, "conectar": _prohibida}
    assert revisar_solicitudes.main([], ahora=lambda: AHORA, **otras) == 2
    assert revisar_solicitudes.main([], ahora=lambda: AHORA + timedelta(hours=23), **otras) == 2
    assert [[etapa for etapa, _ in c] for c in correos] == [["CONFIGURACION"]]
    assert revisar_solicitudes.main([], ahora=lambda: AHORA + timedelta(hours=24), **otras) == 2
    assert len(correos) == 2


def test_error_inesperado_avisa_y_suelta_el_candado(entorno, correos):
    def explota(cfg_api):
        raise RuntimeError("algo raro")

    assert _revisar(entorno, fabrica_api=explota) == 1
    assert [etapa for etapa, _ in correos[0]] == ["INESPERADO"]
    assert "algo raro" not in correos[0][0][1]
    assert _candado_suelto()


@pytest.mark.parametrize("argumentos", [["--ayuda"], ["--completa"]])
def test_no_recibe_argumentos(argumentos):
    with pytest.raises(SystemExit):
        revisar_solicitudes.main(argumentos)
