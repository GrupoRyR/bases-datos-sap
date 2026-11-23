"""Vigilante del robot: registro de la última completa y modo --vigilar."""
from __future__ import annotations

import json
import os
import urllib.error
from datetime import date, datetime, timedelta

import pytest

import config
import run_robot
import vigilante
from fake_hana import VpnFalsa
from vpn import VpnError

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


# --- VPN pegada (T3) ---------------------------------------------------------------------

SIN_SALIDA = "HTTPS de bases.prueba.test: timed out"


class RedTrasLaVpn(Red):
    """Sin salida a internet mientras la VPN (falsa) siga arriba: túnel completo pegado."""

    def __init__(self, vpn: VpnFalsa) -> None:
        super().__init__()
        self.vpn = vpn

    def __call__(self, url: str) -> str | None:
        self.probadas.append(url)
        return SIN_SALIDA if self.vpn.arriba else None


class VpnQueNoBaja(VpnFalsa):
    def forzar_desconexion(self) -> None:
        self.linea.append(("vpn", "forzada"))
        raise VpnError("El comando sccli no respondió en 60s.")


class VpnSinEstado(VpnFalsa):
    def esta_conectado(self) -> bool:
        raise VpnError("No se encontró el CLI de Sophos.")


@pytest.fixture
def reiniciar_vpn(monkeypatch):
    monkeypatch.setenv("VIGILANTE_REINICIAR_VPN", "true")


def test_con_la_vpn_pegada_la_baja_y_sigue_con_la_completa(entorno, correos, reiniciar_vpn):
    e = entorno
    e.vpn.arriba = True  # quedó conectada (desconexión sucia)
    red = RedTrasLaVpn(e.vpn)
    esperas: list[float] = []
    assert _vigilar(e, red, dormir=esperas.append) == 0
    assert e.linea[0] == ("vpn", "forzada")
    assert esperas[:3] == [60, 60, vigilante.ESPERA_VPN_S]
    assert len(red.probadas) == 4  # 3 sin salida, y la que sí, después de bajarla
    assert e.vpn.conexiones == 1  # luego corrió la completa de reparación
    assert vigilante.completa_buena_de_hoy(HOY)
    assert correos == []


def test_si_la_red_no_vuelve_tras_bajar_la_vpn_avisa(entorno, correos, reiniciar_vpn):
    e = entorno
    e.vpn.arriba = True
    red = Red(SIN_SALIDA)  # la falla no era la VPN
    assert _vigilar(e, red) == 1
    assert e.linea == [("vpn", "forzada")]
    assert len(red.probadas) == 6
    assert e.vpn.conexiones == 0
    assert [etapa for etapa, _ in correos[0]] == ["RED"]
    assert "se bajó la VPN y la red no volvió" in correos[0][0][1]


def test_sin_la_variable_no_toca_la_vpn(entorno, correos):
    e = entorno
    e.vpn.arriba = True

    def no_llamar(*args):
        raise AssertionError("no debía usar la VPN")

    assert _vigilar(e, RedTrasLaVpn(e.vpn), fabrica_vpn=no_llamar) == 1
    assert e.linea == []
    assert correos == [[("RED", f"Sin salida a internet: {SIN_SALIDA}")]]


def test_con_sin_vpn_no_toca_la_vpn(entorno, correos, reiniciar_vpn):
    e = entorno
    e.vpn.arriba = True

    def no_llamar(*args):
        raise AssertionError("no debía usar la VPN")

    red = RedTrasLaVpn(e.vpn)
    assert _main(e, "--vigilar", "--sin-vpn", probar=red, fabrica_vpn=no_llamar, dormir=lambda s: None) == 1
    assert [etapa for etapa, _ in correos[0]] == ["RED"]


def test_si_la_vpn_no_esta_conectada_no_la_baja(entorno, correos, reiniciar_vpn):
    e = entorno
    red = Red(SIN_SALIDA)
    assert _vigilar(e, red) == 1
    assert e.linea == []
    assert len(red.probadas) == 3
    assert correos == [[("RED", f"Sin salida a internet: {SIN_SALIDA}")]]


def test_si_no_se_sabe_el_estado_de_la_vpn_no_la_baja(entorno, correos, reiniciar_vpn):
    e = entorno
    vpn = VpnSinEstado(e.linea)
    assert _vigilar(e, Red(SIN_SALIDA), vpn=vpn) == 1
    assert e.linea == []
    assert [etapa for etapa, _ in correos[0]] == ["RED"]


def test_dentro_de_una_franja_no_baja_la_vpn(entorno, correos, reiniciar_vpn):
    e = entorno
    e.vpn.arriba = True
    a_las_0555 = lambda: datetime(2026, 10, 26, 5, 55, tzinfo=config.BOGOTA)  # noqa: E731
    assert _vigilar(e, RedTrasLaVpn(e.vpn), ahora=a_las_0555) == 1
    assert e.linea == []
    assert e.vpn.arriba is True
    assert [etapa for etapa, _ in correos[0]] == ["RED"]
    assert "franja" in correos[0][0][1]


def test_si_no_puede_bajar_la_vpn_avisa(entorno, correos, reiniciar_vpn):
    e = entorno
    vpn = VpnQueNoBaja(e.linea)
    vpn.arriba = True
    assert _vigilar(e, RedTrasLaVpn(vpn), vpn=vpn) == 1
    assert e.linea == [("vpn", "forzada")]
    assert vpn.conexiones == 0
    assert [etapa for etapa, _ in correos[0]] == ["RED"]
    assert "no se pudo bajar la VPN" in correos[0][0][1]


# --- Cadena de los otros robots (T4) -----------------------------------------------------

IA = "SAP HANA - todo"
PUBLICADOR = "Publicador panel"
AYER = datetime(2026, 10, 25, 23, 0, tzinfo=config.BOGOTA).timestamp()
ESTA_MANANA = datetime(2026, 10, 26, 1, 0, tzinfo=config.BOGOTA).timestamp()


class TareasFalsas:
    """Reemplaza TareasWindows: anota cada tarea en la línea y corre su efecto.

    Revisa que nunca haya dos a la vez, que el candado del robot siga tomado y
    que la VPN del robot esté abajo mientras corre cada una.
    """

    def __init__(self, linea: list, vpn: VpnFalsa, *, efectos=None, fallos=None) -> None:
        self.linea = linea
        self.vpn = vpn
        self.efectos = efectos or {}
        self.fallos = fallos or {}
        self.corriendo = False
        self.lanzadas: list[str] = []

    def correr(self, nombre, limite):
        assert not self.corriendo, "dos tareas a la vez"
        assert (config.STATE_DIR / "robot.lock").exists(), "sin el candado del robot"
        assert not self.vpn.arriba, "con la VPN del robot arriba"
        self.corriendo = True
        try:
            self.lanzadas.append(nombre)
            self.linea.append(("tarea", nombre, limite))
            if nombre in self.efectos:
                self.efectos[nombre]()
            return self.fallos.get(nombre)
        finally:
            self.corriendo = False


def _tocar(ruta, momento: float) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if not ruta.exists():
        ruta.write_text("x", encoding="utf-8")
    os.utime(ruta, (momento, momento))


@pytest.fixture
def cadena(entorno, monkeypatch, tmp_path):
    """Los dos robots de la cadena configurados, con sus archivos de ayer."""
    carpeta = tmp_path / "ia"
    publicador = tmp_path / "publicador" / "estado.json"
    monkeypatch.setenv("VIGILANTE_IA_CARPETA", str(carpeta))
    monkeypatch.setenv("VIGILANTE_IA_TAREA", IA)
    monkeypatch.setenv("VIGILANTE_PUBLICADOR_ARCHIVO", str(publicador))
    monkeypatch.setenv("VIGILANTE_PUBLICADOR_TAREA", PUBLICADOR)
    for nombre in ("ia_clientes.csv", "ia_ventas.csv"):
        _tocar(carpeta / nombre, AYER)
    _tocar(publicador, AYER)
    return carpeta, publicador


def test_fecha_ia_es_la_del_archivo_ia_mas_nuevo(tmp_path):
    _tocar(tmp_path / "ia_a.csv", AYER)
    _tocar(tmp_path / "ia_b.csv", ESTA_MANANA)
    _tocar(tmp_path / "otro.csv", ESTA_MANANA + 86400)  # no es ia_*
    assert vigilante.fecha_ia(tmp_path) == HOY


def test_fecha_ia_sin_archivos(tmp_path):
    assert vigilante.fecha_ia(tmp_path / "no-existe") is None
    assert vigilante.fecha_ia(tmp_path) is None


def test_fecha_archivo(tmp_path):
    _tocar(tmp_path / "estado.json", AYER)
    assert vigilante.fecha_archivo(tmp_path / "estado.json") == date(2026, 10, 25)
    assert vigilante.fecha_archivo(tmp_path / "no-existe.json") is None


def test_sin_cadena_configurada_no_lanza_nada(entorno, correos):
    e = entorno
    _completa_de()
    tareas = TareasFalsas(e.linea, e.vpn)
    assert _vigilar(e, tareas=tareas) == 0
    assert tareas.lanzadas == []


def test_con_ia_vieja_lanza_ia_y_luego_el_publicador_despues_de_bases_sap(entorno, correos, cadena):
    e = entorno
    carpeta, publicador = cadena
    tareas = TareasFalsas(e.linea, e.vpn, efectos={
        IA: lambda: _tocar(carpeta / "ia_clientes.csv", ESTA_MANANA),
        PUBLICADOR: lambda: _tocar(publicador, ESTA_MANANA),
    })
    assert _vigilar(e, tareas=tareas) == 0  # sin completa de hoy: primero la repara
    assert tareas.lanzadas == [IA, PUBLICADOR]
    eventos = [evento[:2] for evento in e.linea if evento[0] in ("vpn", "tarea")]
    assert eventos[0] == ("vpn", "conectar")
    assert eventos[-3:] == [("vpn", "abajo"), ("tarea", IA), ("tarea", PUBLICADOR)]
    assert all(evento[2] == timedelta(minutes=60) for evento in e.linea if evento[0] == "tarea")
    assert vigilante.completa_buena_de_hoy(HOY)
    assert correos == []


def test_si_relanza_ia_tambien_relanza_el_publicador_aunque_este_al_dia(entorno, correos, cadena):
    e = entorno
    carpeta, publicador = cadena
    _tocar(publicador, ESTA_MANANA)  # publicó con los ia_* de ayer
    _completa_de()
    tareas = TareasFalsas(e.linea, e.vpn, efectos={IA: lambda: _tocar(carpeta / "ia_a.csv", ESTA_MANANA)})
    assert _vigilar(e, tareas=tareas) == 0
    assert tareas.lanzadas == [IA, PUBLICADOR]


def test_con_ia_al_dia_y_el_publicador_viejo_solo_lanza_el_publicador(entorno, correos, cadena):
    e = entorno
    carpeta, publicador = cadena
    _tocar(carpeta / "ia_ventas.csv", ESTA_MANANA)
    _completa_de()
    tareas = TareasFalsas(e.linea, e.vpn, efectos={PUBLICADOR: lambda: _tocar(publicador, ESTA_MANANA)})
    assert _vigilar(e, tareas=tareas) == 0
    assert tareas.lanzadas == [PUBLICADOR]


def test_con_todo_al_dia_no_lanza_nada(entorno, correos, cadena):
    e = entorno
    carpeta, publicador = cadena
    _tocar(carpeta / "ia_ventas.csv", ESTA_MANANA)
    _tocar(publicador, ESTA_MANANA)
    _completa_de()
    tareas = TareasFalsas(e.linea, e.vpn)
    assert _vigilar(e, tareas=tareas) == 0
    assert tareas.lanzadas == []


def test_solo_el_publicador_configurado(entorno, correos, cadena, monkeypatch):
    e = entorno
    _, publicador = cadena
    monkeypatch.delenv("VIGILANTE_IA_CARPETA")
    monkeypatch.delenv("VIGILANTE_IA_TAREA")
    _completa_de()
    tareas = TareasFalsas(e.linea, e.vpn, efectos={PUBLICADOR: lambda: _tocar(publicador, ESTA_MANANA)})
    assert _vigilar(e, tareas=tareas) == 0
    assert tareas.lanzadas == [PUBLICADOR]


def test_si_falla_ia_no_lanza_el_publicador_y_avisa(entorno, correos, cadena):
    e = entorno
    _completa_de()
    tareas = TareasFalsas(e.linea, e.vpn, fallos={IA: f"La tarea {IA} terminó con código 1"})
    assert _vigilar(e, tareas=tareas) == 1
    assert tareas.lanzadas == [IA]
    assert correos == [[("CADENA", f"La tarea {IA} terminó con código 1")]]
    assert [etapa for etapa, _ in _estado()["fallos"]] == ["CADENA"]


def test_si_ia_termina_sin_renovar_sus_archivos_avisa(entorno, correos, cadena):
    e = entorno
    _completa_de()
    tareas = TareasFalsas(e.linea, e.vpn)  # termina bien pero no toca los ia_*
    assert _vigilar(e, tareas=tareas) == 1
    assert tareas.lanzadas == [IA]
    assert [etapa for etapa, _ in correos[0]] == ["CADENA"]
    assert "no renovó" in correos[0][0][1]


def test_si_el_publicador_termina_sin_renovar_su_archivo_avisa(entorno, correos, cadena):
    e = entorno
    carpeta, _ = cadena
    _tocar(carpeta / "ia_ventas.csv", ESTA_MANANA)
    _completa_de()
    tareas = TareasFalsas(e.linea, e.vpn)
    assert _vigilar(e, tareas=tareas) == 1
    assert tareas.lanzadas == [PUBLICADOR]
    assert [etapa for etapa, _ in correos[0]] == ["CADENA"]
    assert "no renovó" in correos[0][0][1]


def test_si_la_completa_de_reparacion_falla_no_corre_la_cadena(entorno, correos, cadena):
    e = entorno
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    tareas = TareasFalsas(e.linea, vpn)
    assert _vigilar(e, vpn=vpn, tareas=tareas) == 1
    assert tareas.lanzadas == []
    assert [etapa for etapa, _ in correos[0]] == ["COMPLETA"]


def test_sin_red_no_corre_la_cadena(entorno, correos, cadena):
    e = entorno
    _completa_de()
    tareas = TareasFalsas(e.linea, e.vpn)
    assert _vigilar(e, Red(SIN_SALIDA), tareas=tareas) == 1
    assert tareas.lanzadas == []


def test_dentro_de_una_franja_espera_antes_de_lanzar_cada_tarea(entorno, correos, cadena):
    e = entorno
    carpeta, publicador = cadena
    _completa_de()
    a_las_1150 = lambda: datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA)  # noqa: E731
    tareas = TareasFalsas(e.linea, e.vpn, efectos={
        IA: lambda: _tocar(carpeta / "ia_a.csv", ESTA_MANANA),
        PUBLICADOR: lambda: _tocar(publicador, ESTA_MANANA),
    })

    def dormir(segundos):
        e.linea.append(("dormir", segundos))

    assert _vigilar(e, ahora=a_las_1150, dormir=dormir, tareas=tareas) == 0
    # la espera de run_robot al arrancar, y la de la cadena antes de cada tarea
    assert [evento[:2] for evento in e.linea] == [
        ("dormir", 56 * 60), ("dormir", 56 * 60), ("tarea", IA), ("dormir", 56 * 60), ("tarea", PUBLICADOR),
    ]


def test_un_robot_de_la_cadena_a_medias_es_error_de_configuracion(entorno, correos, monkeypatch):
    monkeypatch.setenv("VIGILANTE_IA_TAREA", IA)
    tareas = TareasFalsas(entorno.linea, entorno.vpn)
    assert _vigilar(entorno, tareas=tareas) == 2
    assert tareas.lanzadas == []
    assert "VIGILANTE_IA_CARPETA" in _estado()["error"]


def test_el_limite_de_las_tareas_sale_del_env(entorno, correos, cadena, monkeypatch):
    e = entorno
    carpeta, publicador = cadena
    monkeypatch.setenv("VIGILANTE_LIMITE_TAREA_MIN", "15")
    _completa_de()
    tareas = TareasFalsas(e.linea, e.vpn, efectos={
        IA: lambda: _tocar(carpeta / "ia_a.csv", ESTA_MANANA),
        PUBLICADOR: lambda: _tocar(publicador, ESTA_MANANA),
    })
    assert _vigilar(e, tareas=tareas) == 0
    assert {evento[2] for evento in e.linea if evento[0] == "tarea"} == {timedelta(minutes=15)}
