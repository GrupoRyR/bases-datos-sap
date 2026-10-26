"""Aislamiento de las pruebas: nunca se lee el robot/.env real ni se escribe en robot/logs."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import config
import registro

PREFIJOS = ("SOPHOS_", "HANA_", "BASES_SAP_", "ALERTA_")


def _limpiar_variables() -> None:
    for nombre in list(os.environ):
        if nombre.startswith(PREFIJOS):
            del os.environ[nombre]


@pytest.fixture(autouse=True)
def aislar_entorno(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Apunta el .env a un archivo inexistente y las carpetas a tmp_path.

    load_dotenv escribe en os.environ, así que las variables del robot se
    borran antes y después de cada prueba.
    """
    _limpiar_variables()
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "no-existe.env")
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(config, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "QUERIES_DIR", tmp_path / "queries")
    monkeypatch.setattr(registro, "_SECRETOS", [])
    yield
    _limpiar_variables()


class RelojFalso:
    """Reemplaza time.monotonic y time.sleep: dormir solo avanza el reloj."""

    def __init__(self) -> None:
        self.ahora = 1000.0
        self.esperas: list[float] = []

    def monotonic(self) -> float:
        return self.ahora

    def sleep(self, segundos: float) -> None:
        self.esperas.append(segundos)
        self.ahora += segundos


@pytest.fixture
def reloj() -> RelojFalso:
    return RelojFalso()


@pytest.fixture
def entorno_completo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Variables mínimas para que Config.validar() pase. Devuelve la ruta del CLI falso."""
    cli = tmp_path / "sccli.exe"
    cli.write_text("", encoding="utf-8")
    valores = {
        "SOPHOS_CLI": str(cli),
        "SOPHOS_CONNECTION": "vpn-de-prueba",
        "SOPHOS_USER": "usuario-vpn",
        "SOPHOS_PASSWORD": "clave-vpn-prueba",
        "HANA_HOST": "hana.prueba.local",
        "HANA_SGX_USER": "usuario-sgx",
        "HANA_SGX_PASSWORD": "clave-sgx-prueba",
        "HANA_SDC_USER": "usuario-sdc",
        "HANA_SDC_PASSWORD": "clave-sdc-prueba",
        "BASES_SAP_API_URL": "https://bases.prueba.test/",
        "BASES_SAP_ROBOT_KEY_ID": "r2026a",
        "BASES_SAP_ROBOT_SECRET": "secreto-robot-de-prueba",
    }
    for nombre, valor in valores.items():
        monkeypatch.setenv(nombre, valor)
    return cli
