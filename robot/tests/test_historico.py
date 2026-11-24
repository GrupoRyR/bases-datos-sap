"""Histórico de VENTAS (contrato §10.4): tramos, ventana estimada y run_robot.py --historico-ventas."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

import pytest

import bloqueo
import config
import esquema
import extraccion
import historico
from fake_hana import VpnFalsa, fila, revisar_fases
from historico import RangoInvalido, inicio_ventana_estimado, mes, tramos
from test_run_robot import _estado, _main
from trabajos import Trabajo, trabajo_historico_ventas

VENTANA = date(2026, 10, 25)  # la ventana nocturna del 24/11/2026


def _mes(anio: int, numero: int) -> date:
    return date(anio, numero, 1)


# --- La ventana estimada (contrato §10.1) ----------------------------------------------


@pytest.mark.parametrize("hoy, inicio", [
    (date(2026, 11, 24), date(2026, 10, 25)),
    (date(2026, 10, 16), date(2026, 9, 24)),
    (date(2026, 10, 1), date(2026, 9, 24)),
    (date(2026, 3, 1), date(2026, 2, 22)),
    (date(2025, 1, 31), date(2024, 12, 25)),
])
def test_inicio_ventana_estimado_es_la_formula_del_contrato(hoy: date, inicio: date):
    assert inicio_ventana_estimado(hoy) == inicio


# --- mes: AAAA-MM -------------------------------------------------------------------


def test_mes_da_el_primer_dia():
    assert mes("2025-01") == date(2025, 1, 1)
    assert mes("2026-12") == date(2026, 12, 1)


@pytest.mark.parametrize("texto", ["2025-1", "2025-13", "2025-00", "2025-01-01", "enero", "", " 2025-01"])
def test_mes_invalido(texto: str):
    with pytest.raises(RangoInvalido, match="AAAA-MM"):
        mes(texto)


# --- tramos -----------------------------------------------------------------------


def test_meses_completos_antes_de_la_ventana():
    assert tramos(_mes(2025, 1), _mes(2025, 3), VENTANA) == [
        (date(2025, 1, 1), date(2025, 1, 31)),
        (date(2025, 2, 1), date(2025, 2, 28)),
        (date(2025, 3, 1), date(2025, 3, 31)),
    ]


def test_sin_hasta_llega_al_dia_antes_de_la_ventana():
    # El 24/11 la ventana empieza el 25/10: octubre va del 1 al 24 y noviembre no tiene tramo.
    assert tramos(_mes(2026, 9), None, VENTANA) == [
        (date(2026, 9, 1), date(2026, 9, 30)),
        (date(2026, 10, 1), date(2026, 10, 24)),
    ]


def test_hasta_el_mes_de_la_ventana_tambien_corta_el_dia_antes():
    assert tramos(_mes(2026, 10), _mes(2026, 10), VENTANA) == [(date(2026, 10, 1), date(2026, 10, 24))]


def test_hasta_antes_del_mes_de_la_ventana_da_solo_meses_completos():
    assert tramos(_mes(2026, 7), _mes(2026, 9), VENTANA) == [
        (date(2026, 7, 1), date(2026, 7, 31)),
        (date(2026, 8, 1), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 30)),
    ]


def test_febrero_bisiesto():
    assert tramos(_mes(2024, 2), _mes(2024, 2), VENTANA) == [(date(2024, 2, 1), date(2024, 2, 29))]
    assert tramos(_mes(2025, 2), _mes(2025, 2), VENTANA) == [(date(2025, 2, 1), date(2025, 2, 28))]


def test_cambio_de_anio():
    assert tramos(_mes(2025, 11), _mes(2026, 2), VENTANA) == [
        (date(2025, 11, 1), date(2025, 11, 30)),
        (date(2025, 12, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
    ]


def test_desde_enero_de_2025_hasta_la_ventana():
    lista = tramos(_mes(2025, 1), None, VENTANA)
    assert len(lista) == 22  # enero de 2025 a octubre de 2026
    assert lista[0] == (date(2025, 1, 1), date(2025, 1, 31))
    assert lista[-1] == (date(2026, 10, 1), date(2026, 10, 24))
    # Seguidos, sin huecos ni días repetidos.
    for (_, fin), (inicio, _) in zip(lista, lista[1:]):
        assert (inicio - fin).days == 1


def test_meses_anteriores_a_2025_se_permiten():
    # El contrato no fija un primer mes: enero de 2025 es el inicio previsto, no un límite.
    assert tramos(_mes(2024, 12), _mes(2025, 1), VENTANA) == [
        (date(2024, 12, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 1, 31)),
    ]


def test_ventana_que_empieza_el_primero_deja_ese_mes_sin_tramo():
    # Con la fórmula de §10.1 no pasa (cae entre el 22 y el 25), pero se maneja.
    primero = date(2026, 10, 1)
    assert tramos(_mes(2026, 8), None, primero) == [
        (date(2026, 8, 1), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 30)),
    ]
    assert tramos(_mes(2026, 9), _mes(2026, 10), primero) == [(date(2026, 9, 1), date(2026, 9, 30))]
    with pytest.raises(RangoInvalido, match="ventana nocturna"):
        tramos(_mes(2026, 10), None, primero)


@pytest.mark.parametrize("desde, hasta, texto", [
    (_mes(2026, 3), _mes(2026, 2), "--hasta"),          # al revés
    (_mes(2026, 9), _mes(2026, 11), "--hasta"),         # después del mes de la ventana
    (_mes(2026, 11), None, "ventana nocturna"),         # todo dentro de la ventana
    (_mes(2026, 11), _mes(2026, 11), "--hasta"),
    (_mes(2027, 1), None, "ventana nocturna"),
])
def test_rangos_invalidos(desde: date, hasta: date | None, texto: str):
    with pytest.raises(RangoInvalido, match=texto):
        tramos(desde, hasta, VENTANA)


def test_los_meses_van_por_su_primer_dia():
    with pytest.raises(ValueError, match="primer día"):
        tramos(date(2025, 1, 15), None, VENTANA)
    with pytest.raises(ValueError, match="primer día"):
        tramos(_mes(2025, 1), date(2025, 3, 2), VENTANA)


def test_rango_invalido_es_un_value_error():
    assert issubclass(historico.RangoInvalido, ValueError)


# --- Estimación de la fase con VPN ----------------------------------------------------


def test_duracion_estimada_de_la_fase_con_vpn():
    assert historico.duracion_estimada(4, 2) == timedelta(
        minutes=historico.MINUTOS_FIJOS + 8 * historico.MINUTOS_POR_TRAMO
    )
    assert historico.duracion_estimada(0, 2) == timedelta(minutes=historico.MINUTOS_FIJOS)


# --- El trabajo de un tramo y la revisión del rango -----------------------------------


def test_trabajo_de_un_tramo_es_una_corrida_historico_de_ventas_con_su_rango():
    assert trabajo_historico_ventas("SDC", date(2025, 1, 1), date(2025, 1, 31)) == Trabajo(
        empresa="SDC", conjunto="VENTAS", tipo="historico", partes={"ventas": "todo"},
        ventana_fija="2025-01-01", ventana_hasta="2025-01-31",
    )


def test_una_fila_fuera_del_rango_falla_antes_de_enviar():
    parte = esquema.PARTES["ventas"]
    posicion = parte.nombres.index("fecha_contabilizacion")

    def filas(*dias: str) -> list[list]:
        vacia = [None] * len(parte.nombres)
        return [vacia[:posicion] + [d] + vacia[posicion + 1:] for d in dias]

    extraccion.revisar_ventana(parte, filas("2025-01-01", "2025-01-31"), "2025-01-01", "2025-01-31")
    with pytest.raises(extraccion.FalloTrabajo, match="posterior a ventana_hasta 2025-01-31"):
        extraccion.revisar_ventana(parte, filas("2025-01-31", "2025-02-01"), "2025-01-01", "2025-01-31")
    with pytest.raises(extraccion.FalloTrabajo, match="anterior a ventana_desde 2025-01-01"):
        extraccion.revisar_ventana(parte, filas("2024-12-31"), "2025-01-01", "2025-01-31")


# --- run_robot.py --historico-ventas ----------------------------------------------------
# AHORA es el 26/10/2026 a las 02:00: HANA (y la API) dan la ventana desde el 24/09, así
# que con --desde 2026-06 los tramos son junio, julio, agosto y septiembre hasta el 23.

TRAMOS_JUNIO = [
    ("2026-06-01", "2026-06-30"), ("2026-07-01", "2026-07-31"),
    ("2026-08-01", "2026-08-31"), ("2026-09-01", "2026-09-23"),
]


def _ventas(e, empresa: str, *dias: date) -> None:
    e.hana.datos[empresa]["ventas"] = [
        fila("ventas", i, fecha_contabilizacion=dia) for i, dia in enumerate(dias, start=1)
    ]


def _datos_de_junio(e) -> None:
    # Segurex: nada en agosto (tramo vacío), una fila el 24/09 (ya es la ventana) y otra en mayo.
    _ventas(e, "SGX", date(2026, 5, 31), date(2026, 6, 1), date(2026, 6, 30), date(2026, 7, 15),
            date(2026, 9, 23), date(2026, 9, 24))
    _ventas(e, "SDC", date(2026, 6, 10), date(2026, 7, 10), date(2026, 8, 10), date(2026, 9, 10))


def _historicas(e):
    return [
        (c.empresa, c.ventana_desde, c.ventana_hasta, c.estado)
        for c in e.servidor.corridas.values()
    ]


def _no_dormir(segundos):
    raise AssertionError(f"no debía esperar ({segundos} s)")


def test_historico_carga_cada_tramo_en_orden(entorno, correos, caplog, monkeypatch):
    e = entorno
    _datos_de_junio(e)
    renovaciones: list[bool] = []
    original = bloqueo.Bloqueo.renovar
    monkeypatch.setattr(bloqueo.Bloqueo, "renovar",
                        lambda self: renovaciones.append(True) or original(self))
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--historico-ventas", "--desde", "2026-06", dormir=_no_dormir) == 0
    revisar_fases(e.linea)
    assert e.vpn.conexiones == 1
    # Empresa por empresa y del mes más viejo al más nuevo; agosto de Segurex no tiene ventas.
    assert _historicas(e) == [
        ("SGX", "2026-06-01", "2026-06-30", "cerrada"),
        ("SGX", "2026-07-01", "2026-07-31", "cerrada"),
        ("SGX", "2026-09-01", "2026-09-23", "cerrada"),
        *[("SDC", desde, hasta, "cerrada") for desde, hasta in TRAMOS_JUNIO],
    ]
    for corrida in e.servidor.corridas.values():
        assert (corrida.conjunto, corrida.tipo, corrida.partes, corrida.solicitudes) == (
            "VENTAS", "historico", {"ventas": "todo"}, [])
        assert corrida.conteo_sap == corrida.total_filas()
        fechas = [f["fecha_contabilizacion"] for f in corrida.filas("ventas")]
        assert all(corrida.ventana_desde <= dia <= corrida.ventana_hasta for dia in fechas)
    assert [c.conteo_sap for c in e.servidor.corridas.values()][:3] == [
        {"ventas": 2}, {"ventas": 1}, {"ventas": 1}]
    # El inicio lleva el rango y el tipo historico, sin solicitudes ni fecha de corte.
    inicio = e.servidor.peticiones_a("iniciar")[0].datos
    assert {k: v for k, v in inicio.items() if k != "extraida_en"} == {
        "conjunto": "VENTAS", "empresa": "SGX", "tipo": "historico", "partes": {"ventas": "todo"},
        "solicitudes": [], "fecha_corte": None,
        "ventana_desde": "2026-06-01", "ventana_hasta": "2026-06-30",
    }
    # En HANA: la ventana una vez por empresa y, por tramo, la consulta con su rango y su
    # conteo, en la misma conexión.
    for empresa in ("SGX", "SDC"):
        pasos = e.hana.de(empresa)
        assert [p.tipo for p in pasos] == ["ventana"] + ["todo", "contar"] * 4
        assert len({p.conexion for p in pasos}) == 1
        for (desde, hasta), (todo, contar) in zip(TRAMOS_JUNIO, zip(pasos[1::2], pasos[2::2])):
            rango = f"BETWEEN TO_DATE('{desde}', 'YYYY-MM-DD') AND TO_DATE('{hasta}', 'YYYY-MM-DD')"
            assert rango in todo.sql and todo.sql in contar.sql
    # Un CSV por tramo con filas, en VENTAS\<EMPRESA>\historico.
    assert sorted(p.name for p in (e.csv_dir / "VENTAS" / "SGX" / "historico").iterdir()) == [
        "2026-06-01_2026-06-30.csv", "2026-07-01_2026-07-31.csv", "2026-09-01_2026-09-23.csv",
    ]
    assert len(list((e.csv_dir / "VENTAS" / "SDC" / "historico").iterdir())) == 4
    # Resumen por empresa: primer y último día cargados y los tramos vacíos.
    assert "Histórico de VENTAS SGX: cargado del 2026-06-01 al 2026-09-23." in caplog.messages
    assert "Histórico de VENTAS SGX: vacíos (sin ventas en SAP): 2026-08-01 a 2026-08-31." in caplog.messages
    assert "Histórico de VENTAS SDC: cargado del 2026-06-10 al 2026-09-10." in caplog.messages
    assert correos == []
    estado = _estado()
    assert (estado["estado"], estado["modo"], estado["fallos"]) == ("OK", "historico ventas", [])
    assert estado["tramos"][2] == {"empresa": "SGX", "desde": "2026-08-01", "hasta": "2026-08-31",
                                   "estado": "vacío", "motivo": None}
    assert "CSGX" not in json.dumps(estado) and "Socio" not in json.dumps(estado)
    # El candado se renueva por cada tramo extraído y enviado.
    assert len(renovaciones) >= 8
    assert not (config.STATE_DIR / "robot.lock").exists()


def test_historico_de_una_empresa_y_con_hasta(entorno, correos):
    e = entorno
    _datos_de_junio(e)
    argumentos = ("--historico-ventas", "--desde", "2026-06", "--hasta", "2026-07", "--empresa", "SDC")
    assert _main(e, *argumentos, dormir=_no_dormir) == 0
    assert _historicas(e) == [
        ("SDC", "2026-06-01", "2026-06-30", "cerrada"), ("SDC", "2026-07-01", "2026-07-31", "cerrada"),
    ]
    assert not e.hana.de("SGX")


def test_mes_ya_cargado_responde_409_y_sigue_con_los_demas(entorno, correos, caplog):
    e = entorno
    _datos_de_junio(e)
    e.servidor.ventas_cargadas["SGX"] = {"2026-07-02"}
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--historico-ventas", "--desde", "2026-06", "--empresa", "SGX",
                     dormir=_no_dormir) == 0
    assert _historicas(e) == [
        ("SGX", "2026-06-01", "2026-06-30", "cerrada"), ("SGX", "2026-09-01", "2026-09-23", "cerrada"),
    ]
    assert [p.status for p in e.servidor.peticiones_a("iniciar")] == [201, 409, 201]
    assert "Histórico de VENTAS SGX: ya cargados (la app ya tenía ventas): 2026-07-01 a 2026-07-31." in (
        caplog.messages)
    assert correos == []
    assert _estado()["tramos"][1]["estado"] == "ya cargado"


def test_repetir_el_historico_no_hace_dano(entorno, correos):
    e = entorno
    _datos_de_junio(e)
    assert _main(e, "--historico-ventas", "--desde", "2026-06", dormir=_no_dormir) == 0
    cerradas = len(e.servidor.corridas)
    assert _main(e, "--historico-ventas", "--desde", "2026-06", dormir=_no_dormir) == 0
    assert len(e.servidor.corridas) == cerradas  # todo responde 409: no se abre nada
    assert {t["estado"] for t in _estado()["tramos"]} == {"ya cargado", "vacío"}


def test_un_tramo_que_falla_no_frena_los_demas(entorno, correos, caplog):
    e = entorno
    _datos_de_junio(e)
    e.servidor.programar_fallas("lote", status=422, datos={"message": "x", "errors": {"rows.0.total": ["x"]}})
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--historico-ventas", "--desde", "2026-06", dormir=_no_dormir) == 1
    corridas = _historicas(e)
    assert corridas[0] == ("SGX", "2026-06-01", "2026-06-30", "fallida")
    assert [c[3] for c in corridas[1:]] == ["cerrada"] * 6
    [aviso] = correos
    assert [etapa for etapa, _ in aviso] == ["API"]
    assert aviso[0][1].startswith("VENTAS SGX 2026-06-01 a 2026-06-30: La API rechazó la petición (422)")
    assert any(m.startswith("Histórico de VENTAS SGX: fallidos: 2026-06-01 a 2026-06-30 (")
               for m in caplog.messages)
    assert "Histórico de VENTAS SGX: cargado del 2026-07-15 al 2026-09-23." in caplog.messages
    estado = _estado()
    assert estado["estado"] == "ERROR" and estado["tramos"][0]["estado"] == "falló"


def test_si_falla_la_red_al_iniciar_un_tramo_sigue_con_el_siguiente(entorno, correos):
    e = entorno
    _datos_de_junio(e)
    e.servidor.programar_fallas("iniciar", veces=4, red=True)
    assert _main(e, "--historico-ventas", "--desde", "2026-06", "--empresa", "SDC",
                 dormir=lambda s: None) == 1
    assert [c[1] for c in _historicas(e)] == ["2026-07-01", "2026-08-01", "2026-09-01"]
    assert [t["estado"] for t in _estado()["tramos"]] == ["falló", "cargado", "cargado", "cargado"]


def test_si_falla_la_vpn_no_envia_nada(entorno, correos):
    e = entorno
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    assert _main(e, "--historico-ventas", "--desde", "2026-06", vpn=vpn, dormir=_no_dormir) == 1
    assert e.servidor.peticiones == [] and e.hana.ejecutadas == []
    assert [etapa for etapa, _ in correos[0]] == ["VPN"]
    assert _estado()["estado"] == "ERROR"
    revisar_fases(e.linea)


def test_sin_vpn_no_crea_la_vpn(entorno, correos):
    e = entorno
    _datos_de_junio(e)
    e.hana.vpn = None

    def no_crear(cfg_vpn):
        raise AssertionError("con --sin-vpn no se crea la VPN")

    assert _main(e, "--historico-ventas", "--desde", "2026-09", "--sin-vpn", fabrica_vpn=no_crear,
                 dormir=_no_dormir) == 0
    assert len(e.servidor.corridas) == 2


# --- Candado y franjas --------------------------------------------------------------


class _Reloj:
    """La hora avanza con cada espera, para que la segunda revisión vea la hora nueva."""

    def __init__(self, momento: datetime, vpn) -> None:
        self.momento = momento
        self.vpn = vpn
        self.esperas: list[float] = []

    def ahora(self) -> datetime:
        return self.momento

    def dormir(self, segundos: float) -> None:
        assert self.vpn.conexiones == 0, "la espera es antes de subir la VPN"
        self.esperas.append(segundos)
        self.momento += timedelta(seconds=segundos)


def test_con_el_candado_tomado_espera(entorno, correos, candado_ajeno):
    e = entorno
    _datos_de_junio(e)
    ruta = candado_ajeno()
    esperas: list[float] = []

    def dormir(segundos):
        esperas.append(segundos)
        if len(esperas) == 2:
            ruta.unlink()

    assert _main(e, "--historico-ventas", "--desde", "2026-09", dormir=dormir) == 0
    assert esperas == [10, 10]
    assert len(e.servidor.corridas) == 2


def test_sin_candado_en_20_minutos_avisa_y_no_corre(entorno, correos, candado_ajeno):
    e = entorno
    candado_ajeno()
    esperas: list[float] = []
    assert _main(e, "--historico-ventas", "--desde", "2026-09", dormir=esperas.append) == 1
    assert sum(esperas) == 20 * 60
    assert e.vpn.conexiones == 0 and e.servidor.peticiones == []
    assert [etapa for etapa, _ in correos[0]] == ["CANDADO"]


def test_dentro_de_una_franja_espera_a_que_pase(entorno, correos):
    e = entorno
    _datos_de_junio(e)
    reloj = _Reloj(datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA), e.vpn)
    assert _main(e, "--historico-ventas", "--desde", "2026-06", ahora=reloj.ahora, dormir=reloj.dormir) == 0
    assert reloj.esperas == [56 * 60]
    assert len(e.servidor.corridas) == 7


def test_si_no_alcanza_antes_de_la_siguiente_franja_espera_a_que_pase(entorno, correos, caplog):
    # A las 04:30, 21 meses de dos empresas (unos 89 minutos con VPN) no caben antes de la
    # franja de las 05:00 (04:45) ni en el hueco de 05:16 a 05:44: arranca a las 06:16.
    e = entorno
    reloj = _Reloj(datetime(2026, 10, 26, 4, 30, tzinfo=config.BOGOTA), e.vpn)
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--historico-ventas", "--desde", "2025-01", ahora=reloj.ahora,
                     dormir=reloj.dormir) == 0
    assert historico.duracion_estimada(21, 2) == timedelta(minutes=89)
    assert reloj.esperas == [106 * 60]
    assert e.vpn.conexiones == 1
    assert any("no cabe antes de la franja" in m for m in caplog.messages)
    # Los datos de prueba solo traen ventas de octubre: todos los tramos quedan vacíos.
    assert e.servidor.corridas == {}
    assert len(_estado()["tramos"]) == 42


def test_forzar_no_espera_la_franja(entorno, correos):
    e = entorno
    _datos_de_junio(e)
    reloj = _Reloj(datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA), e.vpn)
    assert _main(e, "--historico-ventas", "--desde", "2026-09", "--forzar", ahora=reloj.ahora,
                 dormir=_no_dormir) == 0
    assert len(e.servidor.corridas) == 2


def test_sin_un_hueco_tan_largo_en_el_dia_falla_sin_subir_la_vpn(entorno, correos):
    e = entorno
    assert _main(e, "--historico-ventas", "--desde", "2010-01", dormir=_no_dormir) == 1
    assert e.vpn.conexiones == 0 and e.servidor.peticiones == []
    assert [etapa for etapa, _ in correos[0]] == ["FRANJA"]
    assert "--hasta" in correos[0][0][1]
    assert (_estado()["estado"], _estado()["etapa"]) == ("ERROR", "FRANJA")


# --- Argumentos ---------------------------------------------------------------------


@pytest.mark.parametrize("argumentos, texto", [
    (["--historico-ventas"], "--desde AAAA-MM"),
    (["--historico-ventas", "--desde", "2025-01-01"], "AAAA-MM"),
    (["--historico-ventas", "--desde", "2025-01", "--hasta", "2026-11"], "ventana nocturna"),
    (["--historico-ventas", "--desde", "2025-03", "--hasta", "2025-02"], "--hasta"),
    (["--historico-ventas", "--desde", "2026-10"], "ventana nocturna"),
    (["--completa", "--hasta", "2025-02"], "--hasta va solo con --historico-ventas"),
    (["--carga-produccion", "--desde", "2026-08"], "AAAA-MM-DD"),
    (["--historico-ventas", "--carga-produccion", "--desde", "2025-01"], "not allowed"),
])
def test_argumentos_invalidos_no_corren(entorno, capsys, argumentos, texto):
    with pytest.raises(SystemExit) as exc:
        _main(entorno, *argumentos)
    assert exc.value.code == 2
    assert texto in capsys.readouterr().err
    assert entorno.servidor.corridas == {} and entorno.hana.ejecutadas == []
    assert not (config.STATE_DIR / "ultima_ejecucion.json").exists()
