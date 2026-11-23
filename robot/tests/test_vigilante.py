"""Vigilante del robot: registro de la última completa y modo --vigilar."""
from __future__ import annotations

import json
import urllib.error
from datetime import date, datetime

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


def _estado() -> dict:
    return json.loads((config.STATE_DIR / "ultima_ejecucion.json").read_text(encoding="utf-8"))


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


# --- Prueba de la red (T2) ------------------------------------------------------------


class Abrir:
    """Reemplaza el HEAD por HTTPS: anota la URL y lanza `error` si lo hay."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.llamadas: list[tuple[str, float]] = []

    def __call__(self, url: str, timeout: float) -> None:
        self.llamadas.append((url, timeout))
        if self.error is not None:
            raise self.error


def _resuelve(host, puerto):
    return [("ok",)]


def test_probar_url_responde():
    abrir = Abrir()
    assert vigilante.probar_url("https://bases.prueba.test/api", resolver=_resuelve, abrir=abrir) is None
    assert abrir.llamadas == [("https://bases.prueba.test/", vigilante.TIMEOUT_RED_S)]


def test_probar_url_sin_dns():
    def sin_dns(host, puerto):
        raise OSError("getaddrinfo failed")

    abrir = Abrir()
    motivo = vigilante.probar_url("https://bases.prueba.test", resolver=sin_dns, abrir=abrir)
    assert motivo == "DNS de bases.prueba.test: getaddrinfo failed"
    assert abrir.llamadas == []


@pytest.mark.parametrize("error, esperado", [
    (urllib.error.URLError("timed out"), "HTTPS de bases.prueba.test: timed out"),
    (ConnectionResetError("reset"), "HTTPS de bases.prueba.test: reset"),
])
def test_probar_url_sin_https(error, esperado):
    motivo = vigilante.probar_url("https://bases.prueba.test", resolver=_resuelve, abrir=Abrir(error))
    assert motivo == esperado


def test_probar_url_cualquier_respuesta_http_cuenta_como_salida():
    error = urllib.error.HTTPError("https://bases.prueba.test/", 404, "Not Found", None, None)
    assert vigilante.probar_url("https://bases.prueba.test", resolver=_resuelve, abrir=Abrir(error)) is None


def test_probar_url_sin_servidor():
    assert vigilante.probar_url("no-es-url", resolver=_resuelve, abrir=Abrir()) is not None


def test_probar_red_reintenta_cada_minuto_y_sale_cuando_responde():
    respuestas = iter([["DNS de a: falla", None], [None, None]])
    actual: list = []

    def probar(url):
        if not actual:
            actual.extend(next(respuestas))
        return actual.pop(0)

    esperas: list[float] = []
    assert vigilante.probar_red(["https://a", "https://b"], probar=probar, dormir=esperas.append) == []
    assert esperas == [60]


def test_probar_red_devuelve_los_motivos_tras_tres_intentos():
    intentos: list[str] = []

    def probar(url):
        intentos.append(url)
        return f"HTTPS de {url[8:]}: timed out"

    esperas: list[float] = []
    assert vigilante.probar_red(["https://a"], probar=probar, dormir=esperas.append) == ["HTTPS de a: timed out"]
    assert intentos == ["https://a"] * 3
    assert esperas == [60, 60]


# --- run_robot.py --vigilar (T2) -----------------------------------------------------


class Red:
    """probar_url falso: anota cada URL y devuelve `motivo` (None: hay salida)."""

    def __init__(self, motivo: str | None = None) -> None:
        self.motivo = motivo
        self.probadas: list[str] = []

    def __call__(self, url: str) -> str | None:
        self.probadas.append(url)
        return self.motivo


def _completa_de(fecha: date = HOY, estado: str = "OK") -> None:
    vigilante.guardar_completa(fecha=fecha, estado=estado, empresas=["SGX", "SDC"], etapas=[])


def _vigilar(e, red: Red | None = None, **kwargs):
    kwargs.setdefault("dormir", lambda s: None)
    return _main(e, "--vigilar", probar=red or Red(), **kwargs)


def test_con_red_y_la_completa_de_hoy_no_hace_nada(entorno, correos):
    e = entorno
    _completa_de()
    red = Red()

    def no_llamar(*args):
        raise AssertionError("no debía usar la VPN")

    assert _vigilar(e, red, fabrica_vpn=no_llamar) == 0
    assert red.probadas == ["https://bases.prueba.test"]
    assert e.servidor.peticiones == []
    assert e.linea == []
    assert correos == []
    assert (_estado()["estado"], _estado()["modo"]) == ("OK", "vigilar")


def test_sin_red_avisa_y_no_corre_la_completa(entorno, correos):
    e = entorno
    esperas: list[float] = []
    red = Red("DNS de bases.prueba.test: getaddrinfo failed")
    assert _vigilar(e, red, dormir=esperas.append) == 1
    assert esperas == [60, 60]
    assert len(red.probadas) == 3
    assert e.vpn.conexiones == 0
    assert e.servidor.peticiones == []
    assert correos == [[("RED", "Sin salida a internet: DNS de bases.prueba.test: getaddrinfo failed")]]
    assert [etapa for etapa, _ in _estado()["fallos"]] == ["RED"]
    assert not (config.STATE_DIR / vigilante.ARCHIVO_COMPLETA).exists()


@pytest.mark.parametrize("previa", [None, (date(2026, 10, 25), "OK"), (HOY, "ERROR")],
                         ids=["sin-registro", "de-ayer", "con-error-hoy"])
def test_sin_la_completa_buena_de_hoy_la_corre_una_vez(entorno, correos, previa):
    e = entorno
    if previa is not None:
        _completa_de(*previa)
    assert _vigilar(e) == 0
    assert e.vpn.conexiones == 1
    assert sorted((c.conjunto, c.empresa) for c in e.servidor.corridas.values()) == sorted(
        (conjunto, empresa) for empresa in ("SGX", "SDC")
        for conjunto in ("MAESTROS", "CARTERA", "VENTAS", "PEDIDOS", "PRODUCCION")
        if empresa == "SGX" or conjunto != "PRODUCCION"
    )
    assert all(c.estado == "cerrada" for c in e.servidor.corridas.values())
    assert vigilante.completa_buena_de_hoy(HOY)
    assert correos == []
    assert (_estado()["estado"], _estado()["modo"]) == ("OK", "vigilar")


def test_dos_vigilantes_seguidos_corren_una_sola_completa(entorno, correos):
    e = entorno
    assert _vigilar(e) == 0
    assert _vigilar(e) == 0
    assert e.vpn.conexiones == 1
    assert len(e.servidor.corridas) == 9


def test_dentro_de_una_franja_espera_a_que_pase_y_luego_trabaja(entorno, correos):
    e = entorno
    a_las_1150 = lambda: datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA)  # noqa: E731
    esperas: list[float] = []
    red = Red()

    def dormir(segundos):
        assert red.probadas == [] and e.vpn.conexiones == 0  # se espera antes de todo
        esperas.append(segundos)

    assert _vigilar(e, red, ahora=a_las_1150, dormir=dormir) == 0
    assert esperas == [56 * 60]
    assert e.vpn.conexiones == 1
    assert correos == []


def test_con_el_candado_ocupado_espera_20_minutos_y_avisa(entorno, correos, candado_ajeno):
    e = entorno
    ruta = candado_ajeno()
    esperas: list[float] = []
    red = Red()
    assert _vigilar(e, red, dormir=esperas.append) == 1
    assert sum(esperas) == 20 * 60
    assert red.probadas == []
    assert e.vpn.conexiones == 0
    assert [etapa for etapa, _ in correos[0]] == ["CANDADO"]
    assert ruta.exists()
    assert (_estado()["estado"], _estado()["etapa"], _estado()["modo"]) == ("ERROR", "CANDADO", "vigilar")


def test_si_la_completa_de_reparacion_falla_avisa_una_sola_vez(entorno, correos):
    e = entorno
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    assert _vigilar(e, vpn=vpn) == 1
    assert vpn.conexiones == 1
    assert correos == [[(
        "COMPLETA", "La completa de reparación terminó con fallos (VPN); el detalle está en el log.",
    )]]
    assert (_registro()["estado"], _registro()["etapas"]) == ("ERROR", ["VPN"])
    assert (_estado()["modo"], [etapa for etapa, _ in _estado()["fallos"]]) == ("vigilar", ["COMPLETA"])


def test_ctrl_c_en_la_completa_de_reparacion_sale_con_130(entorno, correos):
    def corta(cfg_api):
        raise KeyboardInterrupt

    assert _vigilar(entorno, fabrica_api=corta) == 130
    assert correos == []


def test_prueba_tambien_el_panel_si_esta_configurado(entorno, correos, monkeypatch):
    monkeypatch.setenv("VIGILANTE_PANEL_URL", "https://panel.prueba.test/")
    _completa_de()
    red = Red()
    assert _vigilar(entorno, red) == 0
    assert red.probadas == ["https://bases.prueba.test", "https://panel.prueba.test"]


def test_panel_sin_https_es_error_de_configuracion(entorno, correos, monkeypatch):
    monkeypatch.setenv("VIGILANTE_PANEL_URL", "http://panel.prueba.test")
    red = Red()
    assert _vigilar(entorno, red) == 2
    assert red.probadas == []
    assert (_estado()["estado"], _estado()["etapa"]) == ("ERROR", "CONFIGURACION")
    assert "VIGILANTE_PANEL_URL" in _estado()["error"]


def test_vigilar_no_va_con_empresa(entorno):
    with pytest.raises(SystemExit) as exc:
        _main(entorno, "--vigilar", "--empresa", "SGX", probar=Red())
    assert exc.value.code == 2
