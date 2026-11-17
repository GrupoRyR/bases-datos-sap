"""Failure alerts through Microsoft Graph (client credentials). No network: the transport is a fake."""
from __future__ import annotations

import json
import logging
import urllib.parse

import pytest

import api
import notificar
from config import AlertaConfig

SECRETO = "secreto-graph-de-prueba"
TOKEN = "token-de-acceso-de-prueba"
TOKEN_URL = "https://login.microsoftonline.com/tenant-de-prueba/oauth2/v2.0/token"
SEND_URL = "https://graph.microsoft.com/v1.0/users/alertas@prueba.test/sendMail"


def _json(datos: object, status: int = 200) -> api.Respuesta:
    return api.Respuesta(status, {}, json.dumps(datos).encode("utf-8"))


class GraphFalso:
    """Fake transport: records every request and answers token and sendMail from queues."""

    def __init__(self) -> None:
        self.peticiones: list[tuple[str, dict[str, str], bytes, float]] = []
        self.token: list[object] = [_json({"access_token": TOKEN, "expires_in": 3599})]
        self.envio: list[object] = [api.Respuesta(202, {}, b"")]

    def __call__(self, url: str, headers: dict[str, str], cuerpo: bytes, timeout: float) -> api.Respuesta:
        self.peticiones.append((url, headers, cuerpo, timeout))
        cola = self.token if "/oauth2/" in url else self.envio
        siguiente = cola.pop(0) if len(cola) > 1 else cola[0]
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente  # type: ignore[return-value]

    def a(self, url: str) -> list[tuple[str, dict[str, str], bytes, float]]:
        return [p for p in self.peticiones if p[0] == url]


@pytest.fixture
def graph() -> GraphFalso:
    return GraphFalso()


@pytest.fixture
def dormidas() -> list[float]:
    return []


def _cfg(**cambios: object) -> AlertaConfig:
    valores: dict[str, object] = dict(
        smtp_host="", smtp_port=587, smtp_user="", smtp_password="",
        destinatarios=["ti@prueba.test", "otro@prueba.test"],
        graph_tenant_id="tenant-de-prueba", graph_client_id="cliente-de-prueba",
        graph_client_secret=SECRETO, graph_remitente="alertas@prueba.test",
    )
    valores.update(cambios)
    return AlertaConfig(**valores)  # type: ignore[arg-type]


def _avisar(cfg: AlertaConfig, graph: GraphFalso, dormidas: list[float], fallos=None) -> None:
    notificar.avisar_fallos(
        cfg, fallos or [("VPN", "sin túnel")], "Corrida nocturna",
        transporte=graph, dormir=dormidas.append,
    )


def test_pide_el_token_con_client_credentials(graph: GraphFalso, dormidas: list[float]) -> None:
    _avisar(_cfg(), graph, dormidas)

    (url, headers, cuerpo, timeout) = graph.a(TOKEN_URL)[0]
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert dict(urllib.parse.parse_qsl(cuerpo.decode("utf-8"))) == {
        "grant_type": "client_credentials",
        "client_id": "cliente-de-prueba",
        "client_secret": SECRETO,
        "scope": "https://graph.microsoft.com/.default",
    }
    assert timeout == 30


def test_envia_el_correo_con_sendmail_y_el_token(graph: GraphFalso, dormidas: list[float]) -> None:
    _avisar(_cfg(), graph, dormidas, [("MAESTROS SGX", "HANA no responde"), ("CARTERA SDC", "API 500")])

    assert [p[0] for p in graph.peticiones] == [TOKEN_URL, SEND_URL]
    (url, headers, cuerpo, timeout) = graph.a(SEND_URL)[0]
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert headers["Content-Type"] == "application/json"
    assert timeout == 30
    datos = json.loads(cuerpo)
    mensaje = datos["message"]
    assert mensaje["subject"] == "[Bases SAP] Falló el robot - 2 fallos"
    assert mensaje["body"]["contentType"] == "Text"
    assert "MAESTROS SGX: HANA no responde" in mensaje["body"]["content"]
    assert "CARTERA SDC: API 500" in mensaje["body"]["content"]
    assert "Corrida nocturna" in mensaje["body"]["content"]
    assert mensaje["toRecipients"] == [
        {"emailAddress": {"address": "ti@prueba.test"}},
        {"emailAddress": {"address": "otro@prueba.test"}},
    ]
    assert datos["saveToSentItems"] is False
    assert dormidas == []


def test_la_url_codifica_el_remitente_y_el_tenant(graph: GraphFalso, dormidas: list[float]) -> None:
    cfg = _cfg(graph_tenant_id="a/b?c", graph_remitente="robot sap@prueba.test")

    notificar.avisar_fallos(cfg, [("VPN", "x")], transporte=graph, dormir=dormidas.append)

    assert graph.peticiones[0][0] == "https://login.microsoftonline.com/a%2Fb%3Fc/oauth2/v2.0/token"
    assert graph.peticiones[1][0] == "https://graph.microsoft.com/v1.0/users/robot%20sap@prueba.test/sendMail"


def test_graph_gana_a_smtp_cuando_esta_completo(
    graph: GraphFalso, dormidas: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    class SmtpProhibido:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("con Graph completo no se usa SMTP")

    monkeypatch.setattr(notificar.smtplib, "SMTP", SmtpProhibido)

    _avisar(_cfg(smtp_host="smtp.prueba.test", smtp_user="robot@prueba.test"), graph, dormidas)

    assert len(graph.a(SEND_URL)) == 1


def test_con_graph_a_medias_usa_smtp_y_nombra_lo_que_falta(
    graph: GraphFalso, dormidas: list[float], monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    enviados: list[object] = []

    class SmtpFalso:
        def __init__(self, host: str, port: int, timeout: int = 0) -> None: ...
        def __enter__(self) -> "SmtpFalso":
            return self
        def __exit__(self, *args: object) -> None: ...
        def starttls(self, context: object = None) -> None: ...
        def login(self, usuario: str, clave: str) -> None: ...
        def send_message(self, msg: object) -> None:
            enviados.append(msg)

    monkeypatch.setattr(notificar.smtplib, "SMTP", SmtpFalso)
    cfg = _cfg(smtp_host="smtp.prueba.test", graph_client_secret="")

    with caplog.at_level(logging.WARNING, logger="bases_sap"):
        _avisar(cfg, graph, dormidas)

    assert graph.peticiones == []
    assert len(enviados) == 1
    texto = caplog.text
    assert "ALERTA_GRAPH_CLIENT_SECRET" in texto
    assert "ALERTA_GRAPH_TENANT_ID" not in texto  # only the missing ones
    assert "SMTP" in texto


def test_graph_a_medias_sin_smtp_no_envia_y_nombra_lo_que_falta(
    graph: GraphFalso, dormidas: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    cfg = _cfg(graph_tenant_id="", graph_remitente="")

    with caplog.at_level(logging.INFO, logger="bases_sap"):
        _avisar(cfg, graph, dormidas)

    assert graph.peticiones == []
    assert "ALERTA_GRAPH_TENANT_ID" in caplog.text
    assert "ALERTA_GRAPH_REMITENTE" in caplog.text
    assert "desactivadas" in caplog.text


def test_sin_nada_configurado_no_avisa_de_graph(
    graph: GraphFalso, dormidas: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    cfg = _cfg(graph_tenant_id="", graph_client_id="", graph_client_secret="", graph_remitente="")

    with caplog.at_level(logging.INFO, logger="bases_sap"):
        _avisar(cfg, graph, dormidas)

    assert graph.peticiones == []
    assert "ALERTA_GRAPH" not in caplog.text


def test_un_error_de_red_se_reintenta_una_vez(graph: GraphFalso, dormidas: list[float]) -> None:
    graph.token = [api.ErrorRed("sin red"), _json({"access_token": TOKEN})]
    graph.envio = [api.ErrorRed("sin red"), api.Respuesta(202, {}, b"")]

    _avisar(_cfg(), graph, dormidas)

    assert len(graph.a(TOKEN_URL)) == 2
    assert len(graph.a(SEND_URL)) == 2
    assert len(dormidas) == 2


def test_un_503_se_reintenta_una_sola_vez_y_luego_se_rinde(
    graph: GraphFalso, dormidas: list[float]
) -> None:
    graph.envio = [api.Respuesta(503, {}, b"")]

    _avisar(_cfg(), graph, dormidas)  # does not raise

    assert len(graph.a(SEND_URL)) == 2


@pytest.mark.parametrize("status", [400, 401, 403])
def test_un_rechazo_definitivo_no_se_reintenta(
    graph: GraphFalso, dormidas: list[float], status: int
) -> None:
    graph.envio = [_json({"error": {"code": "ErrorAccessDenied"}}, status)]

    _avisar(_cfg(), graph, dormidas)

    assert len(graph.a(SEND_URL)) == 1
    assert dormidas == []


def test_si_el_token_falla_no_se_intenta_enviar(
    graph: GraphFalso, dormidas: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    graph.token = [_json({"error": "invalid_client", "error_description": "AADSTS7000215: bad"}, 401)]

    with caplog.at_level(logging.INFO, logger="bases_sap"):
        _avisar(_cfg(), graph, dormidas)

    assert graph.a(SEND_URL) == []
    assert "401" in caplog.text
    assert "invalid_client" in caplog.text
    assert "AADSTS7000215" in caplog.text


def test_una_respuesta_de_token_sin_access_token_cuenta_como_fallo(
    graph: GraphFalso, dormidas: list[float]
) -> None:
    graph.token = [_json({"token_type": "Bearer"})]

    assert notificar.probar_alerta(_cfg(), transporte=graph, dormir=dormidas.append) is False
    assert graph.a(SEND_URL) == []


def test_el_secreto_y_el_token_nunca_llegan_al_log(
    graph: GraphFalso, dormidas: list[float], caplog: pytest.LogCaptureFixture
) -> None:
    # Hostile fakes: every error body echoes the secret and the token.
    eco = {"error": {"code": "ErrorAccessDenied", "message": f"{SECRETO} {TOKEN}"},
           "error_description": f"{SECRETO} {TOKEN}", "access_token": TOKEN}
    caso_token = GraphFalso()
    caso_token.token = [_json(eco | {"error": "invalid_client"}, 401)]
    caso_envio = GraphFalso()
    caso_envio.envio = [_json(eco, 403)]
    caso_red = GraphFalso()
    caso_red.envio = [api.ErrorRed(f"fallo con {SECRETO} y {TOKEN}")]

    with caplog.at_level(logging.DEBUG):
        for caso in (graph, caso_token, caso_envio, caso_red):
            _avisar(_cfg(), caso, dormidas)
            notificar.probar_alerta(_cfg(), transporte=caso, dormir=dormidas.append)

    assert len(caplog.records) > 0
    assert SECRETO not in caplog.text
    assert TOKEN not in caplog.text


def test_el_secreto_y_el_token_quedan_registrados_para_la_redaccion(
    graph: GraphFalso, dormidas: list[float]
) -> None:
    import registro

    _avisar(_cfg(), graph, dormidas)

    assert SECRETO in registro._SECRETOS
    assert TOKEN in registro._SECRETOS


def test_un_error_inesperado_no_se_propaga(dormidas: list[float]) -> None:
    def explota(*args: object) -> api.Respuesta:
        raise RuntimeError("bug en el transporte")

    notificar.avisar_fallos(_cfg(), [("VPN", "x")], transporte=explota, dormir=dormidas.append)


def test_lista_vacia_no_pide_ni_el_token(graph: GraphFalso, dormidas: list[float]) -> None:
    notificar.avisar_fallos(_cfg(), [], transporte=graph, dormir=dormidas.append)

    assert graph.peticiones == []


def test_probar_alerta_devuelve_true_si_salio(graph: GraphFalso, dormidas: list[float]) -> None:
    assert notificar.probar_alerta(_cfg(), transporte=graph, dormir=dormidas.append) is True

    (_, _, cuerpo, _) = graph.a(SEND_URL)[0]
    mensaje = json.loads(cuerpo)["message"]
    assert mensaje["subject"] == "[Bases SAP] Prueba de alertas"


def test_probar_alerta_devuelve_false_si_no_salio(graph: GraphFalso, dormidas: list[float]) -> None:
    graph.envio = [_json({"error": {"code": "ErrorAccessDenied"}}, 403)]

    assert notificar.probar_alerta(_cfg(), transporte=graph, dormir=dormidas.append) is False


def test_probar_alerta_devuelve_false_si_las_alertas_estan_desactivadas(
    graph: GraphFalso, dormidas: list[float]
) -> None:
    cfg = _cfg(graph_client_id="", graph_client_secret="", graph_tenant_id="", graph_remitente="")

    assert notificar.probar_alerta(cfg, transporte=graph, dormir=dormidas.append) is False
    assert graph.peticiones == []


def test_probar_alerta_por_smtp_si_graph_no_esta_completo(
    graph: GraphFalso, dormidas: list[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    enviados: list[object] = []

    class SmtpFalso:
        def __init__(self, host: str, port: int, timeout: int = 0) -> None: ...
        def __enter__(self) -> "SmtpFalso":
            return self
        def __exit__(self, *args: object) -> None: ...
        def starttls(self, context: object = None) -> None: ...
        def login(self, usuario: str, clave: str) -> None: ...
        def send_message(self, msg: object) -> None:
            enviados.append(msg)

    monkeypatch.setattr(notificar.smtplib, "SMTP", SmtpFalso)
    cfg = _cfg(smtp_host="smtp.prueba.test", graph_tenant_id="")

    assert notificar.probar_alerta(cfg, transporte=graph, dormir=dormidas.append) is True
    assert len(enviados) == 1
    assert graph.peticiones == []
