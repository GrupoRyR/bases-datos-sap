from __future__ import annotations

from email.message import EmailMessage

import pytest

import notificar
from config import AlertaConfig


class SmtpFalso:
    instancias: list["SmtpFalso"] = []
    fallar = False

    def __init__(self, host: str, port: int, timeout: int = 0) -> None:
        self.host = host
        self.port = port
        self.enviados: list[EmailMessage] = []
        self.login_con: tuple[str, str] | None = None
        SmtpFalso.instancias.append(self)

    def __enter__(self) -> "SmtpFalso":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def starttls(self) -> None:
        pass

    def login(self, usuario: str, clave: str) -> None:
        self.login_con = (usuario, clave)

    def send_message(self, msg: EmailMessage) -> None:
        if SmtpFalso.fallar:
            raise OSError("SMTP caído")
        self.enviados.append(msg)


@pytest.fixture(autouse=True)
def smtp(monkeypatch: pytest.MonkeyPatch) -> type[SmtpFalso]:
    SmtpFalso.instancias = []
    SmtpFalso.fallar = False
    monkeypatch.setattr(notificar.smtplib, "SMTP", SmtpFalso)
    return SmtpFalso


def _cfg(habilitada: bool = True) -> AlertaConfig:
    return AlertaConfig(
        smtp_host="smtp.prueba.test" if habilitada else "",
        smtp_port=587,
        smtp_user="robot@prueba.test",
        smtp_password="clave-smtp-prueba",
        destinatarios=["ti@prueba.test"],
    )


def test_sin_configuracion_no_envia_nada(smtp: type[SmtpFalso]) -> None:
    notificar.avisar_fallo(_cfg(habilitada=False), "VPN", "sin túnel")

    assert smtp.instancias == []


def test_un_solo_correo_con_todos_los_fallos(smtp: type[SmtpFalso]) -> None:
    notificar.avisar_fallos(
        _cfg(),
        [("MAESTROS SGX", "HANA no responde"), ("CARTERA SDC", "API respondió 500")],
        detalle="Corrida nocturna",
    )

    assert len(smtp.instancias) == 1
    (msg,) = smtp.instancias[0].enviados
    cuerpo = msg.get_content()
    assert msg["Subject"].startswith("[Bases SAP] Falló el robot")
    assert msg["To"] == "ti@prueba.test"
    assert "MAESTROS SGX: HANA no responde" in cuerpo
    assert "CARTERA SDC: API respondió 500" in cuerpo
    assert "Corrida nocturna" in cuerpo
    assert "robot/logs/robot.log" in cuerpo
    assert smtp.instancias[0].login_con == ("robot@prueba.test", "clave-smtp-prueba")


def test_avisar_fallo_usa_la_etapa_en_el_asunto(smtp: type[SmtpFalso]) -> None:
    notificar.avisar_fallo(_cfg(), "VPN", "sin túnel")

    (msg,) = smtp.instancias[0].enviados
    assert msg["Subject"] == "[Bases SAP] Falló el robot - VPN"
    assert "VPN: sin túnel" in msg.get_content()


def test_lista_vacia_no_envia(smtp: type[SmtpFalso]) -> None:
    notificar.avisar_fallos(_cfg(), [])

    assert smtp.instancias == []


def test_un_error_de_smtp_no_se_propaga(smtp: type[SmtpFalso]) -> None:
    smtp.fallar = True

    notificar.avisar_fallo(_cfg(), "VPN", "sin túnel")

    assert smtp.instancias[0].enviados == []
