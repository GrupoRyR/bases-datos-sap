from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import config
import notificar
import run_robot
from fake_hana import VpnFalsa, revisar_fases
from trabajos import trabajos_de_solicitudes

HOY = date(2026, 10, 26)


@pytest.fixture
def correos(monkeypatch) -> list:
    enviados: list = []
    monkeypatch.setattr(notificar, "avisar_fallos", lambda cfg, fallos, detalle="": enviados.append(list(fallos)))
    return enviados


@pytest.fixture
def entorno(escenario, entorno_completo, monkeypatch):
    monkeypatch.setenv("BASES_SAP_CSV_DIR", str(escenario.csv_dir))
    return escenario


def _main(e, *argumentos, vpn=None, **kwargs):
    kwargs.setdefault("fabrica_api", lambda cfg_api: e.nuevo_cliente(cfg_api))
    kwargs.setdefault("fabrica_vpn", lambda cfg_vpn: vpn or e.vpn)
    kwargs.setdefault("conectar", e.hana.conectar)
    kwargs.setdefault("ahora", e.ahora)
    return run_robot.main(list(argumentos), **kwargs)


def _estado() -> dict:
    return json.loads((config.STATE_DIR / "ultima_ejecucion.json").read_text(encoding="utf-8"))


def _corridas(e):
    return [(c.conjunto, c.empresa, c.tipo, c.estado) for c in e.servidor.corridas.values()]


def test_completa_de_las_dos_empresas(entorno, correos):
    e = entorno
    assert _main(e, "--completa") == 0
    assert _corridas(e) == [
        ("MAESTROS", "SGX", "completa", "cerrada"), ("CARTERA", "SGX", "completa", "cerrada"),
        ("MAESTROS", "SDC", "completa", "cerrada"), ("CARTERA", "SDC", "completa", "cerrada"),
    ]
    revisar_fases(e.linea)
    # Las solicitudes se piden antes de subir la VPN.
    assert e.linea.index(("api", "tomar")) < e.linea.index(("vpn", "conectar"))
    assert e.vpn.conexiones == 1
    assert correos == []
    estado = _estado()
    assert estado["estado"] == "OK"
    assert estado["modo"] == "completa"
    assert estado["fallos"] == []
    assert (e.csv_dir / "CARTERA" / "SDC" / "historico" / "2026-10-25.csv").is_file()
    assert "CSGX001" not in json.dumps(estado)


def test_una_sola_empresa(entorno, correos):
    assert _main(entorno, "--completa", "--empresa", "SDC") == 0
    assert _corridas(entorno) == [
        ("MAESTROS", "SDC", "completa", "cerrada"), ("CARTERA", "SDC", "completa", "cerrada"),
    ]


def test_completa_incluye_las_solicitudes_tomadas(entorno, correos):
    e = entorno
    e.servidor.encolar_solicitud({"id": 118, "empresa": "SGX", "conjunto": "MAESTROS",
                                  "parte": "clientes", "desde": {"clientes": None}})
    e.servidor.encolar_solicitud({"id": 119, "empresa": "SDC", "conjunto": "CARTERA",
                                  "parte": None, "desde": {}})
    assert _main(e, "--completa") == 0
    corridas = list(e.servidor.corridas.values())
    assert [c.solicitudes for c in corridas] == [[118], [], [], [119]]
    assert e.servidor.estado_solicitudes == {118: "terminada", 119: "terminada"}


def test_solicitudes_de_otra_empresa_corren_como_solicitud(entorno, correos):
    e = entorno
    e.servidor.encolar_solicitud({"id": 7, "empresa": "SDC", "conjunto": "MAESTROS",
                                  "parte": "vendedores", "desde": {}})
    assert _main(e, "--completa", "--empresa", "SGX") == 0
    assert _corridas(e)[-1] == ("MAESTROS", "SDC", "solicitud", "cerrada")
    assert e.servidor.estado_solicitudes[7] == "terminada"


def test_toma_solicitudes_por_paginas(entorno, correos):
    e = entorno
    for i in range(1, 26):
        e.servidor.encolar_solicitud({"id": i, "empresa": "SGX", "conjunto": "CARTERA",
                                      "parte": None, "desde": {}})
    assert _main(e, "--completa") == 0
    assert len(e.servidor.peticiones_a("tomar")) == 2
    assert e.servidor.corridas[2].solicitudes == list(range(1, 26))


def test_si_tomar_falla_la_nocturna_sigue(entorno, correos):
    e = entorno
    e.servidor.programar_fallas("tomar", status=500, veces=4)
    assert _main(e, "--completa") == 0
    assert [c[3] for c in _corridas(e)] == ["cerrada"] * 4


def test_falla_la_vpn(entorno, correos):
    e = entorno
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    assert _main(e, "--completa", vpn=vpn) == 1
    assert e.hana.ejecutadas == []
    assert [c[3] for c in _corridas(e)] == ["fallida"] * 4
    assert all("VPN" in c.error for c in e.servidor.corridas.values())
    assert len(correos) == 1
    assert [etapa for etapa, _ in correos[0]] == ["VPN"] * 4
    assert _estado()["estado"] == "ERROR"
    revisar_fases(e.linea)


def test_falla_hana_de_una_empresa_y_la_otra_cierra(entorno, correos):
    e = entorno
    e.hana.empresas_que_fallan.add("SDC")
    assert _main(e, "--completa") == 1
    assert [c[3] for c in _corridas(e)] == ["cerrada", "cerrada", "fallida", "fallida"]
    assert [etapa for etapa, _ in correos[0]] == ["HANA", "HANA"]
    assert all(msg.split(":")[0] in ("MAESTROS SDC", "CARTERA SDC") for _, msg in correos[0])


def test_parte_vacia_falla_la_corrida_y_no_envia_nada(entorno, correos):
    e = entorno
    e.hana.datos["SGX"]["marcas"] = []
    assert _main(e, "--completa") == 1
    maestros_sgx = e.servidor.corridas[1]
    assert (maestros_sgx.estado, maestros_sgx.lotes) == ("fallida", {})
    assert "marcas" in maestros_sgx.error
    assert [c[3] for c in _corridas(e)][1:] == ["cerrada"] * 3


def test_error_de_configuracion_sale_con_2(tmp_path, correos, monkeypatch):
    monkeypatch.setenv("HANA_HOST", "hana.prueba.local")
    assert run_robot.main(["--completa"]) == 2
    estado = _estado()
    assert (estado["estado"], estado["etapa"]) == ("ERROR", "CONFIGURACION")
    assert correos == []  # sin SMTP configurado no se intenta


def test_error_de_configuracion_avisa_si_hay_alertas(tmp_path, correos, monkeypatch):
    monkeypatch.setenv("ALERTA_SMTP_HOST", "smtp.prueba.local")
    monkeypatch.setenv("ALERTA_DESTINATARIOS", "ti@prueba.local")
    assert run_robot.main(["--completa"]) == 2
    assert [etapa for etapa, _ in correos[0]] == ["CONFIGURACION"]


def test_error_inesperado_avisa_y_sale_con_1(entorno, correos):
    def explota(cfg_api):
        raise RuntimeError("algo raro")

    assert _main(entorno, "--completa", fabrica_api=explota) == 1
    assert [etapa for etapa, _ in correos[0]] == ["INESPERADO"]
    assert _estado()["estado"] == "ERROR"


def test_ctrl_c_sale_con_130(entorno, correos):
    def corta(cfg_api):
        raise KeyboardInterrupt

    assert _main(entorno, "--completa", fabrica_api=corta) == 130


def test_hace_falta_un_modo(entorno):
    with pytest.raises(SystemExit) as exc:
        run_robot.main([])
    assert exc.value.code == 2


def test_retencion_borra_corridas_viejas(entorno, correos):
    e = entorno
    vieja = e.csv_dir / "MAESTROS" / "SGX" / "clientes" / "2026-07-01_0200.csv"
    foto = e.csv_dir / "CARTERA" / "SGX" / "historico" / "2025-07-01.csv"
    for ruta in (vieja, foto):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("x", encoding="utf-8")
    assert _main(e, "--completa") == 0
    assert not vieja.exists()
    assert foto.exists()


def test_ejecutar_trabajos_de_una_solicitud_de_clientes(escenario):
    e = escenario
    e.servidor.encolar_solicitud({"id": 118, "empresa": "SGX", "conjunto": "MAESTROS", "parte": "clientes",
                                  "desde": {"clientes": "2026-10-12T00:00:00-05:00"}})
    trabajos = trabajos_de_solicitudes(e.cliente.tomar_solicitudes(20), HOY)
    fallos = run_robot.ejecutar_trabajos(
        e.cfg, trabajos, api=e.cliente, robot_vpn=e.vpn, conectar=e.hana.conectar, ahora=e.ahora,
    )
    assert fallos == []
    revisar_fases(e.linea)
    [corrida] = e.servidor.corridas.values()
    assert corrida.partes == {"clientes": "cambios", "direcciones": "cambios", "contactos": "cambios"}
    assert [f["codigo"] for f in corrida.filas("clientes")] == ["CSGX002", "CSGX003"]
    assert sorted({f["codigo_socio"] for f in corrida.filas("direcciones")}) == ["CSGX002", "CSGX003"]
    assert len(corrida.filas("direcciones")) == 4
    assert [f["codigo_socio"] for f in corrida.filas("contactos")] == ["CSGX002", "CSGX003"]
    assert e.servidor.estado_solicitudes[118] == "terminada"
    assert (Path(e.csv_dir) / "MAESTROS" / "SGX" / "clientes" / "2026-10-26_0200.csv").is_file()


def test_sin_vpn_no_crea_la_vpn(entorno, correos):
    e = entorno
    e.hana.vpn = None

    def no_llamar(cfg_vpn):
        raise AssertionError("no debía crear la VPN")

    assert _main(e, "--completa", "--sin-vpn", fabrica_vpn=no_llamar) == 0
    assert not [ev for ev in e.linea if ev[0] == "vpn"]
    assert [c[3] for c in _corridas(e)] == ["cerrada"] * 4
