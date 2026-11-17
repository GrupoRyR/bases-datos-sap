"""run_robot.py --probar-alerta: a test email, with no SAP, VPN, API or lock involved."""
from __future__ import annotations

import json

import pytest

import api
import config
import notificar
import run_robot

TOKEN = "token-de-acceso-de-prueba"


class TransporteFalso:
    def __init__(self, status_envio: int = 202) -> None:
        self.status_envio = status_envio
        self.urls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str], cuerpo: bytes, timeout: float) -> api.Respuesta:
        self.urls.append(url)
        if "/oauth2/" in url:
            return api.Respuesta(200, {}, json.dumps({"access_token": TOKEN}).encode("utf-8"))
        return api.Respuesta(self.status_envio, {}, b"")


def _prohibido(*args: object, **kwargs: object) -> None:
    raise AssertionError("--probar-alerta no toca la VPN, SAP ni la API")


@pytest.fixture
def graph_en_el_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALERTA_GRAPH_TENANT_ID", "tenant-de-prueba")
    monkeypatch.setenv("ALERTA_GRAPH_CLIENT_ID", "cliente-de-prueba")
    monkeypatch.setenv("ALERTA_GRAPH_CLIENT_SECRET", "secreto-graph-de-prueba")
    monkeypatch.setenv("ALERTA_GRAPH_REMITENTE", "alertas@prueba.test")
    monkeypatch.setenv("ALERTA_DESTINATARIOS", "ti@prueba.test")
    monkeypatch.setattr(notificar.time, "sleep", lambda s: None)


def _main(*argumentos: str) -> int:
    return run_robot.main(
        list(argumentos), fabrica_api=_prohibido, fabrica_vpn=_prohibido, conectar=_prohibido,
    )


def test_sale_con_0_si_el_correo_salio(graph_en_el_env, monkeypatch: pytest.MonkeyPatch) -> None:
    transporte = TransporteFalso()
    monkeypatch.setattr(api, "transporte_urllib", transporte)

    assert _main("--probar-alerta") == 0

    assert len(transporte.urls) == 2  # token and sendMail
    assert transporte.urls[1].endswith("/users/alertas@prueba.test/sendMail")


def test_sale_con_1_si_graph_lo_rechaza(graph_en_el_env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "transporte_urllib", TransporteFalso(status_envio=403))

    assert _main("--probar-alerta") == 1


def test_sale_con_1_si_las_alertas_estan_desactivadas(monkeypatch: pytest.MonkeyPatch) -> None:
    transporte = TransporteFalso()
    monkeypatch.setattr(api, "transporte_urllib", transporte)

    assert _main("--probar-alerta") == 1
    assert transporte.urls == []


def test_sale_con_1_si_graph_esta_a_medias_y_no_hay_smtp(
    graph_en_el_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ALERTA_GRAPH_CLIENT_SECRET")
    transporte = TransporteFalso()
    monkeypatch.setattr(api, "transporte_urllib", transporte)

    assert _main("--probar-alerta") == 1
    assert transporte.urls == []


def test_no_pide_el_resto_de_la_configuracion(graph_en_el_env, monkeypatch: pytest.MonkeyPatch) -> None:
    # Only the ALERTA_* variables are set: no Sophos, HANA or API settings.
    monkeypatch.setattr(api, "transporte_urllib", TransporteFalso())

    assert _main("--probar-alerta") == 0


def test_no_toma_el_candado_ni_toca_el_estado(
    graph_en_el_env, monkeypatch: pytest.MonkeyPatch, candado_ajeno
) -> None:
    monkeypatch.setattr(api, "transporte_urllib", TransporteFalso())
    ruta = candado_ajeno()
    antes = ruta.read_text(encoding="utf-8")

    assert _main("--probar-alerta") == 0

    assert ruta.read_text(encoding="utf-8") == antes  # still the other process's lock
    assert not (config.STATE_DIR / "ultima_ejecucion.json").exists()


def test_no_se_combina_con_los_otros_modos(graph_en_el_env) -> None:
    with pytest.raises(SystemExit) as salida:
        _main("--probar-alerta", "--completa")

    assert salida.value.code == 2
