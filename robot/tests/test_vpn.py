from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import vpn
from config import VpnConfig
from vpn import RobotVPN, VpnError


class SccliFalso:
    """Simula sccli.exe: list, get, enable y disable."""

    def __init__(self, conectado: bool = False, rechazar: bool = False) -> None:
        self.conectado = conectado
        self.rechazar = rechazar
        self.llamadas: list[list[str]] = []

    def __call__(self, cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        args = list(cmd[1:])
        self.llamadas.append(args)
        salida = ""
        if args[0] == "list":
            salida = "Connections:\n  vpn-de-prueba\n"
        elif args[0] == "get":
            salida = f"Connected: {1 if self.conectado else 0}"
        elif args[0] == "enable":
            if self.rechazar:
                salida = "Error: authentication failed"
            else:
                self.conectado = True
                salida = "Connection enabled"
        elif args[0] == "disable":
            self.conectado = False
        return subprocess.CompletedProcess(cmd, 0, salida, "")

    def comandos(self) -> list[str]:
        return [a[0] for a in self.llamadas]


def _cfg(desconectar: bool = True) -> VpnConfig:
    return VpnConfig(
        cli=Path("sccli.exe"),
        conexion="vpn-de-prueba",
        usuario="usuario-vpn",
        password="clave-vpn-prueba",
        timeout=10,
        desconectar_al_final=desconectar,
    )


@pytest.fixture
def sccli(monkeypatch: pytest.MonkeyPatch, reloj) -> SccliFalso:
    falso = SccliFalso()
    monkeypatch.setattr(vpn.subprocess, "run", falso)
    monkeypatch.setattr(vpn.time, "monotonic", reloj.monotonic)
    monkeypatch.setattr(vpn.time, "sleep", reloj.sleep)
    return falso


def test_conecta_y_desconecta_cuando_la_levantamos(sccli: SccliFalso) -> None:
    with RobotVPN(_cfg()):
        assert sccli.conectado is True

    assert sccli.conectado is False
    assert sccli.comandos().count("enable") == 1
    assert sccli.comandos()[-1] == "disable"


def test_reutiliza_el_tunel_y_no_lo_baja(sccli: SccliFalso) -> None:
    sccli.conectado = True

    with RobotVPN(_cfg()):
        pass

    assert "enable" not in sccli.comandos()
    assert "disable" not in sccli.comandos()
    assert sccli.conectado is True


def test_credenciales_rechazadas_no_se_reintentan(sccli: SccliFalso) -> None:
    sccli.rechazar = True

    with pytest.raises(VpnError, match="SOPHOS_USER"):
        RobotVPN(_cfg()).conectar()

    assert sccli.comandos().count("enable") == 1


def test_no_desconecta_si_se_pidio_dejarla_arriba(sccli: SccliFalso) -> None:
    with RobotVPN(_cfg(desconectar=False)):
        pass

    assert "disable" not in sccli.comandos()
    assert sccli.conectado is True


def test_la_clave_no_sale_en_el_log(sccli: SccliFalso, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG", logger="bases_sap")

    with RobotVPN(_cfg()):
        pass

    assert "clave-vpn-prueba" not in caplog.text
    assert "-p ***" in caplog.text
