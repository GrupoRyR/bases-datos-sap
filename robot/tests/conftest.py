"""Aislamiento de las pruebas: nunca se lee el robot/.env real ni se escribe en robot/logs."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

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


AHORA = datetime(2026, 10, 26, 2, 0, 5, tzinfo=config.BOGOTA)


@pytest.fixture
def candado_ajeno():
    """Deja robot/state/robot.lock tomado por otro proceso (vigente a la hora AHORA)."""
    def poner(tomado_en: datetime = AHORA, pid: int = 4242) -> Path:
        ruta = config.STATE_DIR / "robot.lock"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps({"pid": pid, "tomado_en": tomado_en.isoformat()}), encoding="utf-8")
        return ruta

    return poner


@pytest.fixture
def correos(monkeypatch) -> list:
    """Cada llamada a notificar.avisar_fallos queda como la lista de sus fallos."""
    import notificar

    enviados: list = []
    monkeypatch.setattr(
        notificar, "avisar_fallos", lambda cfg, fallos, detalle="": enviados.append(list(fallos))
    )
    return enviados


@pytest.fixture
def escenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """VPN, HANA y API falsas que comparten una línea de tiempo, y la carpeta en tmp.

    Las consultas son las reales de robot/queries. Cada CSV escrito o ampliado
    queda en la línea como ("csv", ruta) para revisar las dos fases con revisar_fases().
    """
    import carpeta
    import esquema
    from api import ApiCliente
    from fake_api import ApiFalsa
    from fake_hana import QUERIES, HanaFalsa, VpnFalsa, config_de_prueba, datos_archivo, datos_empresa

    monkeypatch.setattr(config, "QUERIES_DIR", QUERIES)
    linea: list = []
    vpn = VpnFalsa(linea)
    hana = HanaFalsa(
        {e: datos_empresa(e) for e in config.EMPRESAS}, linea=linea, vpn=vpn,
        archivo={e: datos_archivo(e) for e in config.EMPRESAS},
    )
    servidor = ApiFalsa(
        linea=linea, columnas_por_parte={n: p.nombres for n, p in esquema.PARTES.items()}
    )
    cfg = config_de_prueba(tmp_path / "csv")

    def nuevo_cliente(cfg_api=cfg.api) -> ApiCliente:
        return ApiCliente(cfg_api, transporte=servidor, reloj=servidor.reloj, dormir=lambda s: None)

    escribir = carpeta.escribir_csv
    anexar = carpeta.anexar_csv

    def espia(ruta, columnas, filas):
        linea.append(("csv", Path(ruta)))
        return escribir(ruta, columnas, filas)

    def espia_anexar(ruta, columnas, filas):
        linea.append(("csv", Path(ruta)))
        return anexar(ruta, columnas, filas)

    monkeypatch.setattr(carpeta, "escribir_csv", espia)
    monkeypatch.setattr(carpeta, "anexar_csv", espia_anexar)
    return SimpleNamespace(
        linea=linea,
        vpn=vpn,
        hana=hana,
        servidor=servidor,
        cliente=nuevo_cliente(),
        nuevo_cliente=nuevo_cliente,
        cfg=cfg,
        carpeta=carpeta.Carpeta(cfg.csv_dir),
        csv_dir=cfg.csv_dir,
        ahora=lambda: AHORA,
    )


@pytest.fixture
def entorno(escenario, entorno_completo, monkeypatch) -> SimpleNamespace:
    """El escenario con un .env completo (en variables) que apunta la carpeta al tmp."""
    monkeypatch.setenv("BASES_SAP_CSV_DIR", str(escenario.csv_dir))
    return escenario
