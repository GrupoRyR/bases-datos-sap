from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

import config
from config import ConfigError, cargar_config


def test_valores_por_defecto(tmp_path: Path) -> None:
    cfg = cargar_config()

    assert cfg.csv_dir == Path(r"C:\Users\Claude\Documents\CEREBRO\SAP\BASES_DE_DATOS")
    assert cfg.franjas == ["00:00", "05:00", "06:00", "12:00", "12:30"]
    assert cfg.margen_franja_min == 15
    assert cfg.historial_documentos is False
    assert cfg.hana.port == 30015
    assert cfg.hana.timeout == 600
    assert cfg.hana.empresas["SGX"].esquema == "SEGUREX"
    assert cfg.hana.empresas["SDC"].esquema == "HBT_SDERIVADOS"
    assert cfg.vpn.timeout == 90
    assert cfg.vpn.desconectar_al_final is True
    assert cfg.api.url == ""
    assert cfg.alertas.habilitada is False
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "state").is_dir()


def test_rutas_del_robot() -> None:
    etl = Path(config.__file__).resolve().parent
    assert config.BASE_DIR == etl
    assert config.ROBOT_DIR == etl.parent
    assert config.EMPRESAS == ("SGX", "SDC")


def test_ahora_usa_la_hora_de_bogota() -> None:
    hora = config.ahora()
    assert hora.utcoffset() == timedelta(hours=-5)


def test_cada_empresa_tiene_su_usuario_y_esquema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HANA_SGX_USER", "usuario-sgx")
    monkeypatch.setenv("HANA_SGX_PASSWORD", "clave-sgx")
    monkeypatch.setenv("HANA_SDC_USER", "usuario-sdc")
    monkeypatch.setenv("HANA_SDC_PASSWORD", "clave-sdc")
    monkeypatch.setenv("HANA_SDC_SCHEMA", "OTRO_ESQUEMA")

    cfg = cargar_config()

    sgx = cfg.hana.empresas["SGX"]
    sdc = cfg.hana.empresas["SDC"]
    assert (sgx.codigo, sgx.usuario, sgx.password, sgx.esquema) == (
        "SGX", "usuario-sgx", "clave-sgx", "SEGUREX",
    )
    assert (sdc.codigo, sdc.usuario, sdc.password, sdc.esquema) == (
        "SDC", "usuario-sdc", "clave-sdc", "OTRO_ESQUEMA",
    )


def test_carga_el_archivo_env_indicado(tmp_path: Path) -> None:
    env = tmp_path / "robot.env"
    env.write_text("HANA_HOST=10.0.0.9\nBASES_SAP_ROBOT_KEY_ID=r2026b\n", encoding="utf-8")

    cfg = cargar_config(env)

    assert cfg.hana.host == "10.0.0.9"
    assert cfg.api.key_id == "r2026b"


def test_url_de_la_api_sin_barra_final(entorno_completo: Path) -> None:
    cfg = cargar_config()
    assert cfg.api.url == "https://bases.prueba.test"


def test_configuracion_completa_es_valida(entorno_completo: Path) -> None:
    cargar_config().validar()


def test_validar_lista_todo_lo_que_falta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOPHOS_CLI", "/no/existe/sccli.exe")

    with pytest.raises(ConfigError) as error:
        cargar_config().validar()

    mensaje = str(error.value)
    for esperado in (
        "SOPHOS_CONNECTION",
        "SOPHOS_USER",
        "SOPHOS_PASSWORD",
        "SOPHOS_CLI",
        "HANA_HOST",
        "HANA_SGX_USER",
        "HANA_SGX_PASSWORD",
        "HANA_SDC_USER",
        "HANA_SDC_PASSWORD",
        "BASES_SAP_API_URL",
        "BASES_SAP_ROBOT_KEY_ID",
        "BASES_SAP_ROBOT_SECRET",
    ):
        assert esperado in mensaje


def test_validar_solo_revisa_lo_pedido(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HANA_HOST", "hana.prueba.local")
    monkeypatch.setenv("HANA_SGX_USER", "usuario-sgx")
    monkeypatch.setenv("HANA_SGX_PASSWORD", "clave-sgx")

    cargar_config().validar(requiere_vpn=False, requiere_api=False, empresas=("SGX",))


def test_validar_sin_empresas_no_pide_hana(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASES_SAP_API_URL", "https://bases.prueba.test")
    monkeypatch.setenv("BASES_SAP_ROBOT_KEY_ID", "r2026a")
    monkeypatch.setenv("BASES_SAP_ROBOT_SECRET", "secreto")

    cargar_config().validar(requiere_vpn=False, empresas=())


def test_validar_rechaza_empresa_desconocida(entorno_completo: Path) -> None:
    with pytest.raises(ConfigError, match="XYZ"):
        cargar_config().validar(empresas=("XYZ",))


def test_la_api_debe_ser_https(entorno_completo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASES_SAP_API_URL", "http://bases.prueba.test")

    with pytest.raises(ConfigError, match="https://"):
        cargar_config().validar()


def test_franjas_se_normalizan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASES_SAP_FRANJAS_BLOQUEADAS", " 6:00, 12:30 ,,23:45")

    assert cargar_config().franjas == ["06:00", "12:30", "23:45"]


def test_franja_invalida_falla_al_validar(
    entorno_completo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASES_SAP_FRANJAS_BLOQUEADAS", "06:00,25:00,mediodia")

    with pytest.raises(ConfigError) as error:
        cargar_config().validar()

    mensaje = str(error.value)
    assert "BASES_SAP_FRANJAS_BLOQUEADAS" in mensaje
    assert "25:00" in mensaje
    assert "mediodia" in mensaje


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("true", True), ("1", True), ("sí", True), ("Y", True),
     ("false", False), ("no", False), ("0", False), ("", False)],
)
def test_valores_booleanos(monkeypatch: pytest.MonkeyPatch, valor: str, esperado: bool) -> None:
    monkeypatch.setenv("BASES_SAP_ARCHIVO_HISTORIAL_DOCUMENTOS", valor)

    assert cargar_config().historial_documentos is esperado


def test_desconectar_vpn_al_final_se_puede_apagar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOPHOS_DISCONNECT_AL_FINAL", "false")

    assert cargar_config().vpn.desconectar_al_final is False


def test_numero_invalido_falla_al_validar(
    entorno_completo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HANA_PORT", "3OO15")

    with pytest.raises(ConfigError, match="HANA_PORT"):
        cargar_config().validar()


def test_alertas_habilitadas_con_host_y_destinatarios(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALERTA_SMTP_HOST", "smtp.prueba.test")
    monkeypatch.setenv("ALERTA_DESTINATARIOS", "ti@prueba.test, otro@prueba.test,")

    alertas = cargar_config().alertas

    assert alertas.habilitada is True
    assert alertas.destinatarios == ["ti@prueba.test", "otro@prueba.test"]


def test_leer_query(tmp_path: Path) -> None:
    carpeta = tmp_path / "queries" / "maestros"
    carpeta.mkdir(parents=True)
    (carpeta / "clientes.sql").write_text("SELECT 1 FROM DUMMY", encoding="utf-8")

    assert config.leer_query("maestros/clientes.sql") == "SELECT 1 FROM DUMMY"
    with pytest.raises(ConfigError, match="no_existe.sql"):
        config.leer_query("no_existe.sql")
