"""Comparación con SAP (T7b): run_robot.py --comparar, with fakes (contract §13.2 and §13.3).

The SAP side aggregates the rows exactly as the robot would send them (same queries, same
conversion in esquema.serializar); the fake API computes its /totales from what it received
in earlier runs, as the server would from MySQL, unless a test sets `servidor.totales`.
"""
from __future__ import annotations

import dataclasses
import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

import comparar
import config
import esquema
from api import ApiError, ApiRechazo
from conftest import AHORA
from fake_hana import fila, revisar_fases
from test_historico import _no_dormir, _Reloj
from test_run_robot import _estado, _main

AYER = (AHORA.date() - timedelta(days=1)).isoformat()  # 2026-10-25: VENTAS goes from 2025-01-01 to yesterday
MAESTROS = esquema.PARTES_POR_CONJUNTO["MAESTROS"]
# Active rows per part of fake_hana.datos_empresa: clients 1 and 3 active, supplier 1 active,
# two addresses per partner (no activo column: all count), the rest two rows active.
MAESTROS_ACTIVOS = {
    "clientes": 2, "proveedores": 1, "direcciones": 10, "contactos": 5, "articulos": 2,
    "grupos_articulos": 2, "marcas": 2, "precios": 2, "vendedores": 2, "grupos_clientes": 2,
    "condiciones_pago": 2, "municipios": 2,
}


def _venta(i: int, dia: date, total, cantidad, kilos, envio) -> dict:
    return fila("ventas", i, fecha_contabilizacion=dia, total=total, cantidad=cantidad, kilos=kilos,
                codigo_envio=envio)


def _ventas_de_prueba(e, empresa: str) -> None:
    e.hana.datos[empresa]["ventas"] = [
        _venta(1, date(2024, 12, 31), Decimal("999"), Decimal("1"), None, "X"),  # before 2025: out
        _venta(2, date(2026, 9, 10), Decimal("100.004"), Decimal("1.0000004"), Decimal("2.5"), "CEDI1"),
        # A credit note: negative total and quantity; no weight and an empty shipping code.
        _venta(3, date(2026, 9, 11), Decimal("-40.5"), Decimal("-1"), None, ""),
        _venta(4, date(2026, 9, 30), Decimal("0.006"), Decimal("2"), Decimal("1"), "   "),
        _venta(5, date(2026, 10, 2), Decimal("10"), Decimal("3.1234565"), None, "X"),
        _venta(6, date(2026, 10, 26), Decimal("5"), Decimal("1"), None, "X"),  # today: out (until yesterday)
    ]


def _leer(e, empresas=("SGX", "SDC"), cfg=None):
    return comparar.leer_sap(cfg or e.cfg, list(empresas), AHORA.date(), robot_vpn=e.vpn,
                             conectar=e.hana.conectar, ahora=e.ahora)


def _sap(comparaciones, conjunto: str, empresa: str) -> dict:
    [c] = [c for c in comparaciones if (c.conjunto, c.empresa) == (conjunto, empresa)]
    assert c.error is None, c.error
    return {clave: (g.filas, g.sumas, g.nulos) for clave, g in c.sap.items()}


def _comparaciones(e) -> list[dict]:
    return [p.datos for p in e.servidor.peticiones_a("comparaciones") if p.status == 201]


# --- SAP side: the same definition as what the robot sends ---------------------------------


def test_ventas_por_mes_con_la_conversion_del_envio(escenario):
    e = escenario
    for empresa in ("SGX", "SDC"):
        _ventas_de_prueba(e, empresa)
    comparaciones, fallos = _leer(e)
    assert fallos == []
    revisar_fases(e.linea)
    # Per line, total goes to 2 decimals and quantity to 6 (esquema._monto, _cantidad) before
    # adding: 100.004 -> 100.00 and 0.006 -> 0.01; empty or blank codes are null.
    assert _sap(comparaciones, "VENTAS", "SDC") == {
        "2026-09": (3, {"total": "59.51", "cantidad": "2.000000"}, {"kilos": 1, "codigo_envio": 2}),
        "2026-10": (1, {"total": "10.00", "cantidad": "3.123457"}, {"kilos": 1, "codigo_envio": 0}),
    }
    # Segurex sends kilos as null (the query brings a NULL): every line counts as null.
    assert _sap(comparaciones, "VENTAS", "SGX") == {
        "2026-09": (3, {"total": "59.51", "cantidad": "2.000000"}, {"kilos": 3, "codigo_envio": 2}),
        "2026-10": (1, {"total": "10.00", "cantidad": "3.123457"}, {"kilos": 1, "codigo_envio": 0}),
    }
    ventas = [c for c in comparaciones if c.conjunto == "VENTAS"]
    assert {(c.desde, c.hasta) for c in ventas} == {("2025-01-01", AYER)}
    # One month per tramo, from January 2025 to the month of yesterday (the last one up to it),
    # with the same range filter as the historico; never the HANA window.
    pasos = [x for x in e.hana.de("SDC", parte="ventas") if x.tipo == "todo"]
    assert len(pasos) == 22
    assert "BETWEEN TO_DATE('2025-01-01', 'YYYY-MM-DD') AND TO_DATE('2025-01-31', 'YYYY-MM-DD')" in pasos[0].sql
    assert "BETWEEN TO_DATE('2026-10-01', 'YYYY-MM-DD') AND TO_DATE('2026-10-25', 'YYYY-MM-DD')" in pasos[-1].sql
    assert not e.hana.de("SDC", "ventana")


def test_ventas_sin_lineas_no_tiene_grupos(escenario):
    e = escenario
    e.hana.datos["SGX"]["ventas"] = []
    comparaciones, fallos = _leer(e, ["SGX"])
    assert fallos == [] and _sap(comparaciones, "VENTAS", "SGX") == {}


def test_cartera_un_grupo_actual_con_filas_y_saldo(escenario):
    e = escenario
    e.hana.datos["SGX"]["cartera"] = [
        fila("cartera", 1, saldo=Decimal("1000.005")),  # -> 1000.01
        fila("cartera", 2, saldo=Decimal("-250.5")),
        fila("cartera", 3, saldo=Decimal("0.004")),     # -> 0.00
    ]
    comparaciones, _ = _leer(e, ["SGX"])
    assert _sap(comparaciones, "CARTERA", "SGX") == {"actual": (3, {"saldo": "749.51"}, {})}


def test_maestros_un_grupo_por_parte_con_las_filas_activas(escenario):
    e = escenario
    comparaciones, fallos = _leer(e, ["SGX"])
    assert fallos == []
    sap = _sap(comparaciones, "MAESTROS", "SGX")
    assert list(sap) == list(MAESTROS)
    assert {clave: filas for clave, (filas, _, _) in sap.items()} == MAESTROS_ACTIVOS
    assert all(sumas == {} and nulos == {} for _, sumas, nulos in sap.values())
    # Precios keeps only the public list (2 of the 3 rows), as the full run sends it.
    assert sap["precios"][0] == 2


def test_maestros_sin_lista_de_precios_da_precios_en_cero(escenario):
    # The full run of a company without a public price list does not send precios (contract
    # §4.1): its part is 0 rows, and the query is never run.
    e = escenario
    empresas = dict(e.cfg.hana.empresas)
    empresas["SDC"] = dataclasses.replace(empresas["SDC"], lista_precios=None)
    cfg = dataclasses.replace(e.cfg, hana=dataclasses.replace(e.cfg.hana, empresas=empresas))
    comparaciones, _ = _leer(e, ["SDC"], cfg=cfg)
    assert _sap(comparaciones, "MAESTROS", "SDC")["precios"] == (0, {}, {})
    assert not e.hana.de("SDC", parte="precios")


def test_conjuntos_que_no_son_de_la_empresa_no_se_comparan(escenario, monkeypatch):
    e = escenario
    monkeypatch.setattr(esquema, "EMPRESAS_POR_CONJUNTO", {**esquema.EMPRESAS_POR_CONJUNTO, "CARTERA": ("SGX",)})
    comparaciones, _ = _leer(e)
    assert [(c.conjunto, c.empresa) for c in comparaciones] == [
        ("MAESTROS", "SGX"), ("CARTERA", "SGX"), ("VENTAS", "SGX"), ("MAESTROS", "SDC"), ("VENTAS", "SDC")]
    assert not e.hana.de("SDC", parte="cartera")


def test_una_parte_que_falla_en_sap_falla_solo_su_conjunto(escenario):
    e = escenario
    e.hana.partes_que_fallan.add(("SGX", "cartera"))
    comparaciones, fallos = _leer(e)
    errores = [(c.conjunto, c.empresa) for c in comparaciones if c.error]
    assert errores == [("CARTERA", "SGX")]
    assert [etapa for etapa, _ in fallos] == ["HANA"]
    assert "falla simulada" not in json.dumps(fallos)


# --- Comparing with /totales -----------------------------------------------------------------


def test_diferencias_filas_sumas_nulos_y_grupos_de_un_solo_lado():
    G = comparar.Grupo
    sap = {"2026-09": G(3, {"total": "59.51", "cantidad": "2.000000"}, {"kilos": 1, "codigo_envio": 2}),
           "2026-11": G(15, {"total": "1.00", "cantidad": "1.000000"}, {"kilos": 0, "codigo_envio": 0})}
    mysql = {"2026-08": G(7, {}, {}),
             "2026-09": G(2, {"total": "59.50", "cantidad": "2.000000"}, {"kilos": 0, "codigo_envio": 2})}
    assert comparar.diferencias(sap, mysql, ordenar=True) == [
        {"clave": "2026-08", "campo": "filas", "sap": None, "mysql": "7"},
        {"clave": "2026-09", "campo": "filas", "sap": "3", "mysql": "2"},
        {"clave": "2026-09", "campo": "sumas.total", "sap": "59.51", "mysql": "59.50"},
        {"clave": "2026-09", "campo": "nulos.kilos", "sap": "1", "mysql": "0"},
        {"clave": "2026-11", "campo": "filas", "sap": "15", "mysql": None},
    ]
    assert comparar.diferencias(sap, {k: dataclasses.replace(v) for k, v in sap.items()}) == []


def test_todo_cuadra_despues_de_una_completa(entorno, correos, caplog):
    e = entorno
    assert _main(e, "--completa") == 0
    antes = len(e.servidor.peticiones)
    e.linea.clear()
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--comparar", dormir=_no_dormir) == 0
    revisar_fases(e.linea)
    nombres = [p.nombre for p in e.servidor.peticiones[antes:]]
    # Read-only: no run is started (/corridas) and nothing else is sent.
    assert set(nombres) == {"totales", "comparaciones"}
    assert nombres.count("totales") == 6 and nombres.count("comparaciones") == 6
    assert e.vpn.conexiones == 2  # the completa and the comparison
    enviadas = _comparaciones(e)
    assert [(c["conjunto"], c["empresa"], c["cuadra"], c["diferencias"]) for c in enviadas] == [
        (conjunto, empresa, True, []) for empresa in ("SGX", "SDC") for conjunto in ("MAESTROS", "CARTERA", "VENTAS")]
    for c in enviadas:
        datetime.fromisoformat(c["comparada_en"])
        if c["conjunto"] == "VENTAS":
            assert (c["desde"], c["hasta"]) == ("2025-01-01", AYER)
        else:
            assert "desde" not in c and "hasta" not in c
    totales = [p.datos for p in e.servidor.peticiones_a("totales")]
    assert {"conjunto": "VENTAS", "empresa": "SGX", "desde": "2025-01-01", "hasta": AYER} in totales
    assert {"conjunto": "MAESTROS", "empresa": "SGX"} in totales
    assert "Comparación VENTAS SDC: cuadra." in caplog.messages
    assert correos == []
    estado = _estado()
    assert (estado["estado"], estado["modo"]) == ("OK", "comparar")
    assert [c["resultado"] for c in estado["comparaciones"]] == ["cuadra"] * 6
    assert not (config.STATE_DIR / "robot.lock").exists()


def test_sumas_iguales_despues_del_redondeo_por_linea_cuadran(entorno, correos):
    # 0.004 + 0.004 would be 0.01, but each line goes as 0.00 (as the app stored it): cuadra.
    e = entorno
    for empresa in ("SGX", "SDC"):
        e.hana.datos[empresa]["ventas"] = [
            _venta(1, date(2026, 10, 2), Decimal("0.004"), Decimal("1"), None, "X"),
            _venta(2, date(2026, 10, 3), Decimal("0.004"), Decimal("1"), None, "X"),
        ]
    assert _main(e, "--completa") == 0
    assert _main(e, "--comparar", dormir=_no_dormir) == 0
    [ventas] = [c for c in _comparaciones(e) if (c["conjunto"], c["empresa"]) == ("VENTAS", "SGX")]
    assert ventas["cuadra"] is True


def test_si_no_cuadra_lista_las_diferencias_sale_con_1_y_avisa(entorno, correos, caplog):
    e = entorno
    assert _main(e, "--completa") == 0
    # The data of the fake: two lines on 2026-10-01 (1000.50 and 2000.50, quantities 1.5 and 2.5).
    e.servidor.totales[("VENTAS", "SGX")] = [
        {"clave": "2026-08", "filas": 4, "sumas": {"total": "1.00", "cantidad": "1.000000"},
         "nulos": {"kilos": 4, "codigo_envio": 0}},
        {"clave": "2026-10", "filas": 3, "sumas": {"total": "3001.01", "cantidad": "4.000000"},
         "nulos": {"kilos": 2, "codigo_envio": 0}},
    ]
    e.servidor.totales[("MAESTROS", "SDC")] = [
        {"clave": p, "filas": MAESTROS_ACTIVOS[p] + (1 if p == "clientes" else 0), "sumas": {}, "nulos": {}}
        for p in MAESTROS
    ]
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--comparar", dormir=_no_dormir) == 1
    enviadas = {(c["conjunto"], c["empresa"]): c for c in _comparaciones(e)}
    assert len(enviadas) == 6
    ventas = enviadas[("VENTAS", "SGX")]
    assert ventas["cuadra"] is False
    assert ventas["diferencias"] == [
        {"clave": "2026-08", "campo": "filas", "sap": None, "mysql": "4"},
        {"clave": "2026-10", "campo": "filas", "sap": "2", "mysql": "3"},
        {"clave": "2026-10", "campo": "sumas.total", "sap": "3001.00", "mysql": "3001.01"},
    ]
    assert enviadas[("MAESTROS", "SDC")]["diferencias"] == [
        {"clave": "clientes", "campo": "filas", "sap": "2", "mysql": "3"}]
    assert all(c["cuadra"] for k, c in enviadas.items() if k not in {("VENTAS", "SGX"), ("MAESTROS", "SDC")})
    assert "Comparación VENTAS SGX: no cuadra en 2 grupos: 2026-08 (filas), 2026-10 (filas, sumas.total)." \
        in caplog.messages
    [aviso] = correos
    assert [etapa for etapa, _ in aviso] == ["COMPARAR", "COMPARAR"]
    assert "3001.00" not in json.dumps(aviso)  # claves and campos, never the aggregates
    estado = _estado()
    assert estado["estado"] == "ERROR"
    resultado = {(c["conjunto"], c["empresa"]): c for c in estado["comparaciones"]}
    assert resultado[("VENTAS", "SGX")] == {"conjunto": "VENTAS", "empresa": "SGX", "resultado": "no_cuadra",
                                           "grupos_con_diferencias": 2}
    assert "3001" not in json.dumps(estado)


def test_mas_de_500_diferencias_envia_las_primeras_500(entorno, correos):
    e = entorno
    c = comparar.Comparacion("MAESTROS", "SGX")
    c.sap = {f"parte{i}": comparar.Grupo(1, {}, {}) for i in range(600)}
    fallos = comparar.comparar_con_api(e.cliente, [c], e.ahora)
    [enviada] = _comparaciones(e)
    assert enviada["cuadra"] is False and len(enviada["diferencias"]) == 500
    assert len(c.diferencias) == 612  # the 600 only in SAP and the 12 parts only in MySQL
    assert [etapa for etapa, _ in fallos] == ["COMPARAR"]


def test_si_totales_falla_en_un_conjunto_no_se_envia_su_comparacion_y_sigue(entorno, correos, caplog):
    e = entorno
    assert _main(e, "--completa") == 0
    e.servidor.programar_fallas("totales", status=422, datos={"message": "x", "errors": {"conjunto": ["x"]}})
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--comparar", dormir=_no_dormir) == 1
    enviadas = [(c["conjunto"], c["empresa"]) for c in _comparaciones(e)]
    assert ("MAESTROS", "SGX") not in enviadas and len(enviadas) == 5
    assert all(c["cuadra"] for c in _comparaciones(e))
    [aviso] = correos
    assert aviso == [("API", "Comparación MAESTROS SGX: La API rechazó la petición (422) en conjunto.")]
    assert "Comparación MAESTROS SGX: error: La API rechazó la petición (422) en conjunto." in caplog.messages
    assert [c["resultado"] for c in _estado()["comparaciones"]][:2] == ["error", "cuadra"]


def test_si_comparaciones_falla_lo_registra_y_sale_con_1(entorno, correos):
    e = entorno
    assert _main(e, "--completa") == 0
    e.servidor.programar_fallas("comparaciones", veces=4, status=503)
    assert _main(e, "--comparar", "--empresa", "SGX", dormir=lambda s: None) == 1
    assert len(_comparaciones(e)) == 2
    [aviso] = correos
    assert aviso == [("API", "Comparación MAESTROS SGX: no se pudo guardar en la API: La API respondió 503 en "
                             "/api/robot/v1/comparaciones después de 4 intentos.")]


def test_si_falla_la_vpn_no_compara_nada(entorno, correos):
    from fake_hana import VpnFalsa

    e = entorno
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    assert _main(e, "--comparar", vpn=vpn, dormir=_no_dormir) == 1
    assert e.servidor.peticiones == [] and e.hana.ejecutadas == []
    assert [etapa for etapa, _ in correos[0]] == ["VPN"]
    assert {c["resultado"] for c in _estado()["comparaciones"]} == {"error"}


def test_empresa_y_sin_vpn(entorno, correos):
    e = entorno
    assert _main(e, "--completa", "--empresa", "SDC") == 0
    e.vpn.conexiones = 0

    def no_crear(cfg_vpn):
        raise AssertionError("con --sin-vpn no se crea la VPN")

    e.hana.vpn = None
    assert _main(e, "--comparar", "--empresa", "SDC", "--sin-vpn", fabrica_vpn=no_crear, dormir=_no_dormir) == 0
    assert {c["empresa"] for c in _comparaciones(e)} == {"SDC"}
    assert not e.hana.de("SGX")


# --- Slots, lock and estimate ----------------------------------------------------------------


def test_duracion_estimada_es_la_del_complemento_mas_maestros_y_cartera():
    # 22 months (January 2025 to October 2026, up to yesterday) of two companies: 2 minutes,
    # 10 s per month and company and 30 s per company for MAESTROS and for CARTERA: 680 s.
    assert comparar.duracion_estimada(2, date(2026, 10, 26)) == timedelta(seconds=120 + 440 + 120)
    assert comparar.duracion_estimada(1, date(2026, 10, 31)) == timedelta(seconds=120 + 220 + 60)
    # On the 1st, yesterday is the last day of the month before: October has no tramo.
    assert comparar.duracion_estimada(2, date(2026, 11, 1), ("VENTAS",)) == timedelta(seconds=120 + 440)
    assert comparar.duracion_estimada(2, date(2026, 10, 26), ("CARTERA",)) == timedelta(seconds=120 + 60)
    # Before any VENTAS month (yesterday before 2025-01-01): only the fixed part.
    assert comparar.duracion_estimada(2, date(2025, 1, 1), ("VENTAS",)) == timedelta(seconds=120)


def test_dentro_de_una_franja_espera_a_que_pase(entorno, correos):
    e = entorno
    reloj = _Reloj(datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA), e.vpn)
    assert _main(e, "--comparar", ahora=reloj.ahora, dormir=reloj.dormir) == 1  # nothing loaded: no cuadra
    assert reloj.esperas == [56 * 60]  # until 12:46, past the 12:00 and 12:30 slots
    assert len(_comparaciones(e)) == 6


def test_forzar_no_espera_la_franja(entorno, correos):
    e = entorno
    reloj = _Reloj(datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA), e.vpn)
    _main(e, "--comparar", "--forzar", ahora=reloj.ahora, dormir=reloj.dormir)
    assert reloj.esperas == []
    assert len(_comparaciones(e)) == 6


def test_con_el_candado_tomado_espera(entorno, correos, candado_ajeno):
    e = entorno
    ruta = candado_ajeno()
    esperas: list[float] = []

    def dormir(segundos):
        esperas.append(segundos)
        if len(esperas) == 2:
            ruta.unlink()

    _main(e, "--comparar", dormir=dormir)
    assert esperas == [10, 10]
    assert len(_comparaciones(e)) == 6


def test_sin_candado_en_20_minutos_avisa_y_no_corre(entorno, correos, candado_ajeno):
    e = entorno
    candado_ajeno()
    esperas: list[float] = []
    assert _main(e, "--comparar", dormir=esperas.append) == 1
    assert sum(esperas) == 20 * 60
    assert e.vpn.conexiones == 0 and e.servidor.peticiones == []
    assert [etapa for etapa, _ in correos[0]] == ["CANDADO"]


@pytest.mark.parametrize("extra", [["--desde", "2026-06"], ["--hasta", "2026-06"], ["--completa"],
                                   ["--conjunto", "PEDIDOS"]])
def test_argumentos_invalidos_no_corren(entorno, capsys, extra):
    with pytest.raises(SystemExit) as exc:
        _main(entorno, "--comparar", *extra)
    assert exc.value.code == 2
    assert entorno.servidor.peticiones == [] and entorno.hana.ejecutadas == []


# --- --tras-despliegue runs the comparison at the end ----------------------------------------


def test_tras_despliegue_sin_pendientes_compara_solo_ventas(entorno, correos):
    from test_autoactualizar import GitFalso

    e = entorno
    assert _main(e, "--completa") == 0
    antes, consultas = len(e.servidor.peticiones), len(e.hana.ejecutadas)
    e.linea.clear()
    assert _main(e, "--tras-despliegue", git=GitFalso(), dormir=_no_dormir) == 0
    revisar_fases(e.linea)
    nombres = {p.nombre for p in e.servidor.peticiones[antes:]}
    assert nombres == {"totales", "comparaciones"}
    assert [(c["conjunto"], c["empresa"], c["hasta"], c["cuadra"]) for c in _comparaciones(e)] == [
        ("VENTAS", "SGX", AYER, True), ("VENTAS", "SDC", AYER, True)]
    assert {p.datos["conjunto"] for p in e.servidor.peticiones_a("totales")} == {"VENTAS"}
    assert {x.parte for x in e.hana.ejecutadas[consultas:]} == {"ventas"}
    estado = _estado()
    assert (estado["estado"], estado["modo"], estado["complementos"]) == ("OK", "tras despliegue", [])
    assert len(estado["comparaciones"]) == 2


def test_tras_despliegue_estima_solo_ventas(entorno, correos, monkeypatch):
    from test_autoactualizar import GitFalso

    import run_robot

    estimados: list = []
    original = run_robot._esperar_hueco
    monkeypatch.setattr(run_robot, "_esperar_hueco",
                        lambda cfg, modo, estimado, *a, **k: estimados.append(estimado) or original(cfg, modo, estimado, *a, **k))
    assert _main(entorno, "--tras-despliegue", git=GitFalso(), dormir=_no_dormir) == 1  # nothing loaded
    assert estimados and set(estimados) == {comparar.duracion_estimada(2, AHORA.date(), ("VENTAS",))}


def test_tras_despliegue_compara_despues_de_un_complemento_que_falla(entorno, correos):
    from test_autoactualizar import _DOS, C, GitFalso, _escribir_complementos
    from test_complemento import _datos_de_junio

    e = entorno
    _datos_de_junio(e)
    _escribir_complementos(_DOS)
    e.servidor.programar_fallas("iniciar", status=409, datos={"message": "Ya tiene kilos."})
    assert _main(e, "--tras-despliegue", git=GitFalso(head=C), dormir=_no_dormir) == 1
    nombres = [p.nombre for p in e.servidor.peticiones]
    # The comparison goes last, after both complements, in its own VPN session.
    assert nombres.index("totales") > max(i for i, n in enumerate(nombres) if n in ("iniciar", "cerrar"))
    assert {c["conjunto"] for c in _comparaciones(e)} == {"VENTAS"} and len(_comparaciones(e)) == 2
    assert e.vpn.conexiones == 3
    revisar_fases(e.linea)


# --- api.py and fake_api: the shapes of §13.2 and §13.3 ----------------------------------------


def test_totales_devuelve_los_grupos(escenario):
    api, servidor = escenario.cliente, escenario.servidor
    servidor.totales[("CARTERA", "SGX")] = [{"clave": "actual", "filas": 0, "sumas": {"saldo": "0.00"}, "nulos": {}}]
    assert api.totales("CARTERA", "SGX") == [{"clave": "actual", "filas": 0, "sumas": {"saldo": "0.00"}, "nulos": {}}]
    assert servidor.peticiones_a("totales")[0].datos == {"conjunto": "CARTERA", "empresa": "SGX"}


@pytest.mark.parametrize("grupos", [
    None, [{"clave": "a"}], [{"clave": "a", "filas": "1"}], [{"clave": "a", "filas": True}],
    [{"clave": "a", "filas": 1, "sumas": {"total": 1.5}}], [{"clave": "a", "filas": 1, "nulos": {"kilos": "1"}}],
    [{"clave": "a", "filas": 1}, {"clave": "a", "filas": 2}],
])
def test_totales_con_una_forma_rara_es_un_error(escenario, grupos):
    escenario.servidor.totales[("CARTERA", "SGX")] = grupos
    with pytest.raises(ApiError):
        escenario.cliente.totales("CARTERA", "SGX")


@pytest.mark.parametrize("cuerpo, campo", [
    ({"conjunto": "PEDIDOS", "empresa": "SGX"}, "conjunto"),
    ({"conjunto": "VENTAS", "empresa": "XXX"}, "empresa"),
    ({"conjunto": "CARTERA", "empresa": "SGX", "desde": "2025-01-01"}, "desde"),
    ({"conjunto": "VENTAS", "empresa": "SGX", "desde": "2026-02-30"}, "desde"),
    ({"conjunto": "VENTAS", "empresa": "SGX", "desde": "2026-02-02", "hasta": "2026-02-01"}, "hasta"),
])
def test_totales_422_del_contrato(escenario, cuerpo, campo):
    with pytest.raises(ApiRechazo) as exc:
        escenario.cliente._post("/totales", cuerpo)
    assert exc.value.status == 422 and campo in exc.value.errors


def _cuerpo_comparacion(**cambios):
    cuerpo = {"conjunto": "VENTAS", "empresa": "SGX", "comparada_en": "2026-10-26T02:00:05-05:00",
              "desde": "2025-01-01", "hasta": AYER, "cuadra": False,
              "diferencias": [{"clave": "2026-10", "campo": "filas", "sap": "2", "mysql": None}]}
    cuerpo.update(cambios)
    return cuerpo


def test_guardar_comparacion_responde_el_id(escenario):
    api = escenario.cliente
    assert api.guardar_comparacion(**{k: v for k, v in _cuerpo_comparacion().items()}) == 1
    assert api.guardar_comparacion(conjunto="CARTERA", empresa="SGX", comparada_en="2026-10-26T02:00:05-05:00",
                                   cuadra=True, diferencias=[]) == 2
    assert "desde" not in escenario.servidor.peticiones_a("comparaciones")[1].datos


@pytest.mark.parametrize("cambios, campo", [
    ({"cuadra": "false"}, "cuadra"),
    ({"cuadra": True}, "diferencias"),
    ({"diferencias": []}, "diferencias"),
    ({"comparada_en": "2026-10-26T02:00:05"}, "comparada_en"),
    ({"diferencias": [{"clave": "2026-10", "campo": "filas", "sap": "2"}]}, "diferencias.0"),
    ({"diferencias": [{"clave": "2026-10", "campo": "filas", "sap": 2, "mysql": None}]}, "diferencias.0.sap"),
    ({"diferencias": [{"clave": "x" * 21, "campo": "filas", "sap": "2", "mysql": None}]}, "diferencias.0.clave"),
    ({"diferencias": [{"clave": "a", "campo": "filas", "sap": None, "mysql": None}] * 501}, "diferencias"),
    ({"conjunto": "MAESTROS"}, "desde"),
])
def test_comparaciones_422_del_contrato(escenario, cambios, campo):
    with pytest.raises(ApiRechazo) as exc:
        escenario.cliente._post("/comparaciones", _cuerpo_comparacion(**cambios))
    assert exc.value.status == 422 and campo in exc.value.errors
    assert escenario.servidor.comparaciones == []


# --- hasta = yesterday, with the Bogotá clock ------------------------------------------------


@pytest.mark.parametrize("momento, ayer", [
    (datetime(2026, 10, 26, 0, 0, 30, tzinfo=config.BOGOTA), "2026-10-25"),  # just after midnight
    (datetime(2026, 10, 25, 23, 59, 59, tzinfo=config.BOGOTA), "2026-10-24"),  # just before
    # 04:30 UTC on the 26th is still 23:30 of the 25th in Bogotá.
    (datetime(2026, 10, 26, 4, 30, tzinfo=timezone.utc), "2026-10-24"),
])
def test_hasta_es_ayer_en_sap_totales_y_comparaciones(escenario, momento, ayer):
    e = escenario
    comparaciones, fallos = comparar.ejecutar(
        e.cfg, ["SDC"], conjuntos=("VENTAS",), api=e.cliente, robot_vpn=e.vpn, conectar=e.hana.conectar,
        ahora=lambda: momento,
    )
    [c] = comparaciones
    assert (c.conjunto, c.desde, c.hasta) == ("VENTAS", "2025-01-01", ayer)
    ultimo = [x for x in e.hana.de("SDC", parte="ventas") if x.tipo == "todo"][-1]
    assert f"AND TO_DATE('{ayer}', 'YYYY-MM-DD')" in ultimo.sql
    [totales] = e.servidor.peticiones_a("totales")
    assert totales.datos == {"conjunto": "VENTAS", "empresa": "SDC", "desde": "2025-01-01", "hasta": ayer}
    [enviada] = _comparaciones(e)
    assert (enviada["desde"], enviada["hasta"]) == ("2025-01-01", ayer)
    revisar_fases(e.linea)


def test_si_ayer_es_antes_de_2025_ventas_no_tiene_nada_que_comparar(escenario, caplog):
    e = escenario
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        comparaciones, fallos = comparar.leer_sap(e.cfg, ["SGX"], date(2025, 1, 1), robot_vpn=e.vpn,
                                                  conectar=e.hana.conectar, ahora=e.ahora)
    assert fallos == [] and [c.conjunto for c in comparaciones] == ["MAESTROS", "CARTERA"]
    assert not e.hana.de("SGX", parte="ventas")
    assert any("VENTAS SGX: nada que comparar" in m and "2024-12-31" in m for m in caplog.messages)


# --- --conjunto --------------------------------------------------------------------------------


def test_conjunto_filtra_los_conjuntos(entorno, correos):
    e = entorno
    assert _main(e, "--completa") == 0
    assert _main(e, "--comparar", "--conjunto", "VENTAS", "--conjunto", "CARTERA", dormir=_no_dormir) == 0
    assert [(c["conjunto"], c["empresa"]) for c in _comparaciones(e)] == [
        ("CARTERA", "SGX"), ("VENTAS", "SGX"), ("CARTERA", "SDC"), ("VENTAS", "SDC")]
    assert {p.datos["conjunto"] for p in e.servidor.peticiones_a("totales")} == {"CARTERA", "VENTAS"}


@pytest.mark.parametrize("modo", [["--completa"], ["--diagnostico"], ["--tras-despliegue"],
                                  ["--complemento-ventas", "--desde", "2026-06"]])
def test_conjunto_va_solo_con_comparar(entorno, capsys, modo):
    with pytest.raises(SystemExit) as exc:
        _main(entorno, *modo, "--conjunto", "VENTAS")
    assert exc.value.code == 2
    assert "--conjunto va solo con --comparar" in capsys.readouterr().err
    assert entorno.servidor.peticiones == [] and entorno.hana.ejecutadas == []


# --- The daily full comparison after a successful --completa ---------------------------------


def _diaria() -> dict:
    return json.loads((config.STATE_DIR / comparar.ARCHIVO_DIARIO).read_text(encoding="utf-8"))


def test_una_completa_buena_compara_todo_una_vez_y_anota_el_dia(entorno, correos, comparacion_diaria, caplog):
    e = entorno
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--completa") == 0
    revisar_fases(e.linea)
    assert e.vpn.conexiones == 2  # the completa and then the comparison, each with its VPN
    nombres = [p.nombre for p in e.servidor.peticiones]
    ultimo_cierre = max(i for i, n in enumerate(nombres) if n == "cerrar")
    assert min(i for i, n in enumerate(nombres) if n == "totales") > ultimo_cierre
    assert [(c["conjunto"], c["empresa"], c["cuadra"]) for c in _comparaciones(e)] == [
        (conjunto, empresa, True) for empresa in ("SGX", "SDC") for conjunto in ("MAESTROS", "CARTERA", "VENTAS")]
    diaria = _diaria()
    assert diaria["fecha"] == "2026-10-26"
    assert diaria["ultima"]["resultado"] == "cuadra" and len(diaria["ultima"]["comparaciones"]) == 6
    # The completa's own state keeps reporting the load.
    estado = _estado()
    assert (estado["estado"], estado["modo"]) == ("OK", "completa") and "comparaciones" not in estado
    assert correos == []
    assert not list(config.STATE_DIR.glob("*.tmp"))
    assert not (config.STATE_DIR / "robot.lock").exists()


def test_una_segunda_completa_buena_el_mismo_dia_no_compara(entorno, correos, comparacion_diaria, caplog):
    e = entorno
    assert _main(e, "--completa") == 0
    antes = len(_comparaciones(e))
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--completa") == 0
    assert len(_comparaciones(e)) == antes == 6
    assert any("ya se hizo hoy" in m for m in caplog.messages)
    # The next day it compares again.
    assert _main(e, "--completa", ahora=lambda: AHORA + timedelta(days=1)) == 0
    assert len(_comparaciones(e)) == 12 and _diaria()["fecha"] == "2026-10-27"


def test_una_completa_que_falla_no_compara(entorno, correos, comparacion_diaria):
    e = entorno
    e.servidor.programar_fallas("lote", status=422, datos={"message": "x", "errors": {"rows.0.codigo": ["x"]}})
    assert _main(e, "--completa") == 1
    assert e.servidor.peticiones_a("totales") == [] and e.vpn.conexiones == 1
    assert not (config.STATE_DIR / comparar.ARCHIVO_DIARIO).exists()


def test_una_completa_de_una_sola_empresa_no_compara(entorno, correos, comparacion_diaria):
    e = entorno
    assert _main(e, "--completa", "--empresa", "SGX") == 0
    assert e.servidor.peticiones_a("totales") == []
    assert not (config.STATE_DIR / comparar.ARCHIVO_DIARIO).exists()


def test_si_no_cuadra_la_completa_sigue_en_0_y_avisa(entorno, correos, comparacion_diaria):
    e = entorno
    e.servidor.totales[("CARTERA", "SDC")] = [{"clave": "actual", "filas": 9, "sumas": {"saldo": "1.00"}, "nulos": {}}]
    assert _main(e, "--completa") == 0
    assert _estado()["estado"] == "OK"
    [aviso] = correos
    assert aviso == [("COMPARAR", "Comparación CARTERA SDC: no cuadra en 1 grupos: actual (filas, sumas.saldo).")]
    diaria = _diaria()
    assert diaria["fecha"] == "2026-10-26" and diaria["ultima"]["resultado"] == "no_cuadra"


def test_si_la_comparacion_no_pudo_correr_no_anota_el_dia_y_otra_completa_reintenta(
    entorno, correos, comparacion_diaria
):
    e = entorno
    e.servidor.programar_fallas("totales", status=422, datos={"message": "x", "errors": {"conjunto": ["x"]}})
    assert _main(e, "--completa") == 0
    assert _estado()["estado"] == "OK"
    [aviso] = correos
    assert [etapa for etapa, _ in aviso] == ["API"]
    diaria = _diaria()
    assert "fecha" not in diaria and diaria["ultima"]["resultado"] == "error"
    assert len(_comparaciones(e)) == 5
    # A later good completa that same day retries, and now records the day.
    assert _main(e, "--completa") == 0
    assert len(_comparaciones(e)) == 11 and _diaria()["fecha"] == "2026-10-26"


def test_si_falla_la_vpn_de_la_comparacion_no_anota_el_dia(entorno, correos, comparacion_diaria):
    e = entorno
    conectar = e.vpn.conectar
    veces: list[int] = []

    def segunda_falla():
        veces.append(1)
        if len(veces) == 2:
            from vpn import VpnError

            e.linea.append(("vpn", "conectar"))
            raise VpnError("No se pudo conectar la VPN tras 3 intentos.")
        conectar()

    e.vpn.conectar = segunda_falla
    assert _main(e, "--completa") == 0
    revisar_fases(e.linea)
    [aviso] = correos
    assert [etapa for etapa, _ in aviso] == ["VPN"]
    assert e.servidor.peticiones_a("totales") == []
    assert "fecha" not in _diaria()


def test_un_error_inesperado_en_la_comparacion_no_cambia_la_completa(entorno, correos, comparacion_diaria,
                                                                      monkeypatch):
    e = entorno

    def explota(*args, **kwargs):
        raise RuntimeError("algo raro con un valor de SAP")

    monkeypatch.setattr(comparar, "ejecutar", explota)
    assert _main(e, "--completa") == 0
    [aviso] = correos
    assert [etapa for etapa, _ in aviso] == ["INESPERADO"] and "valor de SAP" not in aviso[0][1]
    assert _estado()["estado"] == "OK"
    assert not (config.STATE_DIR / comparar.ARCHIVO_DIARIO).exists() or "fecha" not in _diaria()


def test_un_archivo_diario_danado_se_toma_como_sin_comparar(entorno, correos, comparacion_diaria):
    e = entorno
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    (config.STATE_DIR / comparar.ARCHIVO_DIARIO).write_text("{no es json", encoding="utf-8")
    assert _main(e, "--completa") == 0
    assert len(_comparaciones(e)) == 6 and _diaria()["fecha"] == "2026-10-26"
