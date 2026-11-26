"""Kilos de VENTAS (orden 016): run_robot.py --kilos-ventas, con fakes.

La consulta real (queries/ventas/ventas.sql) todavía no trae la columna de kilos: sin ella
el modo no corre. Las pruebas que sí lo corren usan una copia de robot/queries en tmp con
una columna de kilos DE PRUEBA (`con_kilos`); la expresión de verdad no existe aún.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

import bloqueo
import config
import consultas
import esquema
import historico
import kilos
from api import ApiCliente, ApiRechazo
from fake_api import COLUMNAS_KILOS
from fake_hana import QUERIES, VpnFalsa, fila, revisar_fases
from test_historico import TRAMOS_JUNIO, _no_dormir, _Reloj
from test_run_robot import _estado, _main
from trabajos import Trabajo

COMENTARIOS = '    X."Comments"                                               AS "Comentarios"\n'
LLAVE_FECHA_KILOS = ["tipo_objeto", "doc_entry", "linea", "fecha_contabilizacion", "kilos"]


@pytest.fixture
def con_kilos(entorno, tmp_path, monkeypatch):
    """El entorno con una copia de robot/queries cuya consulta de ventas trae kilos de prueba."""
    copia = tmp_path / "queries_con_kilos"
    shutil.copytree(QUERIES, copia)
    ventas = copia / "ventas" / "ventas.sql"
    texto = ventas.read_text(encoding="utf-8")
    assert texto.count(COMENTARIOS) == 1
    texto = texto.replace(COMENTARIOS, COMENTARIOS[:-1] + ',\n    X."Quantity" * 0 AS "Kilos"\n')
    ventas.write_bytes(texto.encode("utf-8"))
    monkeypatch.setattr(config, "QUERIES_DIR", copia)
    return entorno


def _ventas(e, empresa: str, *dias: date, kilos_por_fila: Decimal | None = Decimal("12.5")) -> None:
    e.hana.datos[empresa]["ventas"] = [
        fila("ventas", i, fecha_contabilizacion=dia, Kilos=kilos_por_fila) for i, dia in enumerate(dias, start=1)
    ]


def _datos_de_junio(e) -> None:
    # Derivados: nada en agosto (tramo vacío), una fila el 24/09 (ya es la ventana) y otra en
    # mayo. Segurex también tiene ventas, pero el modo de kilos no lo consulta (solo SDC).
    _ventas(e, "SDC", date(2026, 5, 31), date(2026, 6, 1), date(2026, 6, 30), date(2026, 7, 15),
            date(2026, 9, 23), date(2026, 9, 24))
    _ventas(e, "SGX", date(2026, 6, 10), date(2026, 7, 10), date(2026, 8, 10), date(2026, 9, 10))


def _corridas(e):
    return [(c.empresa, c.tipo, c.ventana_desde, c.ventana_hasta, c.estado) for c in e.servidor.corridas.values()]


def _sin_candado_ni_espera(monkeypatch) -> None:
    def no_tomar(self, *args, **kwargs):
        raise AssertionError("sin la columna de kilos no se toma el candado")

    monkeypatch.setattr(bloqueo.Bloqueo, "tomar", no_tomar)


# --- Sin la columna de kilos no corre (falla cerrado) ------------------------------------


def test_sin_la_columna_de_kilos_sale_con_2_antes_de_esperar_o_subir_la_vpn(
    entorno, correos, candado_ajeno, monkeypatch, caplog
):
    e = entorno
    _datos_de_junio(e)
    candado_ajeno()  # ni siquiera espera a que otro proceso suelte el candado
    _sin_candado_ni_espera(monkeypatch)
    reloj = _Reloj(datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA), e.vpn)  # dentro de una franja
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--kilos-ventas", "--desde", "2026-06", ahora=reloj.ahora, dormir=_no_dormir) == 2
    assert e.vpn.conexiones == 0 and e.hana.ejecutadas == [] and e.servidor.peticiones == []
    estado = _estado()
    assert (estado["estado"], estado["modo"], estado["etapa"]) == ("ERROR", "kilos ventas", "CONFIGURACION")
    assert "kilos" in estado["error"] and "Tot KG" in estado["error"]
    assert any("no trae la columna de kilos" in m for m in caplog.messages)


def test_sin_la_columna_de_kilos_tampoco_corre_con_forzar_ni_sin_vpn(entorno, correos, monkeypatch):
    e = entorno
    _sin_candado_ni_espera(monkeypatch)
    assert _main(e, "--kilos-ventas", "--desde", "2026-06", "--forzar", "--sin-vpn", dormir=_no_dormir) == 2
    assert e.hana.ejecutadas == [] and e.servidor.peticiones == []


def test_con_la_consulta_sin_kilos_un_tramo_tampoco_se_extrae(entorno):
    # Si la consulta cambiara entre la revisión y la extracción, cada tramo la vuelve a exigir.
    e = entorno
    _datos_de_junio(e)
    tramos, fallos = kilos.ejecutar(
        e.cfg, ["SDC"], date(2026, 6, 1), date(2026, 6, 1), api=e.cliente, robot_vpn=e.vpn,
        conectar=e.hana.conectar, ahora=e.ahora,
    )
    assert [t.estado for t in tramos] == ["falló"]
    assert "no trae la columna de kilos" in (tramos[0].motivo or "")
    assert [etapa for etapa, _ in fallos] == ["CONFIGURACION"]
    assert [x.tipo for x in e.hana.de("SDC")] == ["ventana"]  # la consulta de kilos no corrió
    assert e.servidor.peticiones == []


# --- Solo Derivados ------------------------------------------------------------------------


def test_los_kilos_son_solo_de_derivados():
    # La expresión de «Tot KG» es de «AnálisisVentas-1», de Derivados: en Segurex no está
    # confirmado que NumInSale sean kilos. Una sola lista manda en las dos cosas.
    assert kilos.EMPRESAS == consultas.EMPRESAS_CON_KILOS == ("SDC",)


def test_ejecutar_no_corre_en_una_empresa_sin_kilos(entorno):
    e = entorno
    with pytest.raises(ValueError, match="solo de SDC"):
        kilos.ejecutar(e.cfg, ["SDC", "SGX"], date(2026, 6, 1), None, api=e.cliente, robot_vpn=e.vpn,
                       conectar=e.hana.conectar, ahora=e.ahora)
    assert e.vpn.conexiones == 0 and e.hana.ejecutadas == [] and e.servidor.peticiones == []


# --- La corrida kilos (contrato §10.5) -----------------------------------------------------


def test_trabajo_de_un_tramo_es_una_corrida_kilos_de_ventas_con_su_rango():
    assert kilos.trabajo_kilos_ventas("SGX", date(2025, 1, 1), date(2025, 1, 31)) == Trabajo(
        empresa="SGX", conjunto="VENTAS", tipo="kilos", partes={"ventas": "todo"},
        ventana_fija="2025-01-01", ventana_hasta="2025-01-31",
    )
    assert kilos.PARTE_KILOS.nombres == LLAVE_FECHA_KILOS
    assert set(LLAVE_FECHA_KILOS) == COLUMNAS_KILOS
    assert kilos.PRIMER_MES == date(2025, 1, 1)
    assert kilos.PARTE_KILOS.llave == esquema.PARTES["ventas"].llave


def _abrir_kilos(api: ApiCliente, ventana_desde: str = "2026-06-01", ventana_hasta: str = "2026-06-30") -> int:
    return api.iniciar_corrida(
        conjunto="VENTAS", empresa="SGX", tipo="kilos", partes={"ventas": "todo"}, solicitudes=[],
        fecha_corte=None, extraida_en="2026-10-26T02:00:05-05:00",
        ventana_desde=ventana_desde, ventana_hasta=ventana_hasta,
    )["run_id"]


@pytest.mark.parametrize("columnas", [
    esquema.PARTES["ventas"].nombres,                                    # el encabezado completo de §10
    ["tipo_objeto", "doc_entry", "linea", "fecha_contabilizacion"],      # sin kilos
    ["tipo_objeto", "doc_entry", "linea", "fecha_contabilizacion", "kilos", "cantidad"],
])
def test_un_lote_kilos_lleva_exactamente_las_cinco_columnas(escenario, columnas):
    api: ApiCliente = escenario.cliente
    run_id = _abrir_kilos(api)
    with pytest.raises(ApiRechazo) as exc:
        api.enviar_lote(run_id, batch=1, parte="ventas", columns=columnas, rows=[[None] * len(columnas)])
    assert exc.value.status == 422 and "columns" in exc.value.errors


def test_un_lote_kilos_acepta_las_cinco_en_cualquier_orden_y_kilos_null(escenario):
    api: ApiCliente = escenario.cliente
    run_id = _abrir_kilos(api)
    columnas = ["kilos", "linea", "fecha_contabilizacion", "doc_entry", "tipo_objeto"]
    api.enviar_lote(run_id, batch=1, parte="ventas", columns=columnas, rows=[[None, 0, "2026-06-10", 7, 13]])
    respuesta = api.cerrar_corrida(run_id, batches=1, filas={"ventas": 1}, conteo_sap={"ventas": 1})
    assert respuesta["estado"] == "cerrada"
    assert escenario.servidor.corridas[run_id].filas("ventas")[0]["kilos"] is None


def test_una_corrida_kilos_no_empieza_antes_de_2025(escenario):
    with pytest.raises(ApiRechazo) as exc:
        _abrir_kilos(escenario.cliente, "2024-12-01", "2024-12-31")
    assert exc.value.status == 422 and "ventana_desde" in exc.value.errors


def test_si_el_conteo_de_sap_no_cuadra_el_cierre_falla_y_la_corrida_queda_fallida(escenario):
    api: ApiCliente = escenario.cliente
    run_id = _abrir_kilos(api)
    api.enviar_lote(run_id, batch=1, parte="ventas", columns=LLAVE_FECHA_KILOS, rows=[[13, 7, 0, "2026-06-10", "1.5"]])
    with pytest.raises(ApiRechazo) as exc:
        api.cerrar_corrida(run_id, batches=1, filas={"ventas": 1}, conteo_sap={"ventas": 2})
    assert exc.value.status == 422 and "conteo_sap.ventas" in exc.value.errors
    assert escenario.servidor.corridas[run_id].estado == "fallida"


# --- run_robot.py --kilos-ventas con la columna (de prueba) --------------------------------
# AHORA es el 26/10/2026 a las 02:00: HANA da la ventana desde el 24/09, así que con
# --desde 2026-06 los tramos son junio, julio, agosto y septiembre hasta el 23 (el último,
# parcial).


def test_kilos_llena_cada_tramo_en_orden(con_kilos, correos, caplog, monkeypatch):
    e = con_kilos
    _datos_de_junio(e)
    renovaciones: list[bool] = []
    original = bloqueo.Bloqueo.renovar
    monkeypatch.setattr(bloqueo.Bloqueo, "renovar",
                        lambda self: renovaciones.append(True) or original(self))
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--kilos-ventas", "--desde", "2026-06", dormir=_no_dormir) == 0
    revisar_fases(e.linea)
    assert e.vpn.conexiones == 1
    # Sin --empresa, solo Derivados, del mes más viejo al más nuevo; agosto no tiene ventas.
    # Segurex ni se consulta: ahí no está confirmado que haya kilos.
    assert _corridas(e) == [
        ("SDC", "kilos", "2026-06-01", "2026-06-30", "cerrada"),
        ("SDC", "kilos", "2026-07-01", "2026-07-31", "cerrada"),
        ("SDC", "kilos", "2026-09-01", "2026-09-23", "cerrada"),
    ]
    assert not e.hana.de("SGX")
    for corrida in e.servidor.corridas.values():
        assert (corrida.conjunto, corrida.partes, corrida.solicitudes) == ("VENTAS", {"ventas": "todo"}, [])
        assert corrida.conteo_sap == corrida.total_filas()
        # Cada lote lleva solo la llave, la fecha y los kilos, en ese orden.
        assert {tuple(lote.columns) for lote in corrida.lotes.values()} == {tuple(LLAVE_FECHA_KILOS)}
        for f in corrida.filas("ventas"):
            assert corrida.ventana_desde <= f["fecha_contabilizacion"] <= corrida.ventana_hasta
            assert f["kilos"] == "12.500000"
    assert [c.conteo_sap for c in e.servidor.corridas.values()][:3] == [
        {"ventas": 2}, {"ventas": 1}, {"ventas": 1}]
    assert e.servidor.corridas[1].filas("ventas") == [
        {"tipo_objeto": 2, "doc_entry": 2, "linea": 2, "fecha_contabilizacion": "2026-06-01", "kilos": "12.500000"},
        {"tipo_objeto": 3, "doc_entry": 3, "linea": 3, "fecha_contabilizacion": "2026-06-30", "kilos": "12.500000"},
    ]
    inicio = e.servidor.peticiones_a("iniciar")[0].datos
    assert {k: v for k, v in inicio.items() if k != "extraida_en"} == {
        "conjunto": "VENTAS", "empresa": "SDC", "tipo": "kilos", "partes": {"ventas": "todo"},
        "solicitudes": [], "fecha_corte": None,
        "ventana_desde": "2026-06-01", "ventana_hasta": "2026-06-30",
    }
    # En HANA: la ventana una vez y, por tramo, la consulta de kilos con su rango y su conteo,
    # en la misma conexión.
    pasos = e.hana.de("SDC")
    assert [p.tipo for p in pasos] == ["ventana"] + ["kilos", "contar"] * 4
    assert len({p.conexion for p in pasos}) == 1
    for (desde, hasta), (consulta, contar) in zip(TRAMOS_JUNIO, zip(pasos[1::2], pasos[2::2])):
        rango = f"BETWEEN TO_DATE('{desde}', 'YYYY-MM-DD') AND TO_DATE('{hasta}', 'YYYY-MM-DD')"
        assert consulta.sql.startswith('SELECT X."Tipo objeto", X."DocEntry", X."Línea", '
                                       'X."Fecha contabilización", X."Kilos" FROM (')
        assert rango in consulta.sql and consulta.sql in contar.sql
    # En Derivados el id del pedido de la app va en NULL, como en la nocturna.
    assert 'CAST(T0."U_SGX_IdPedidoApp"' not in e.hana.de("SDC", "kilos")[0].sql
    # No escribe CSV.
    assert not any(evento[0] == "csv" for evento in e.linea)
    assert not (e.csv_dir / "VENTAS").exists()
    # Resumen de la empresa.
    assert "Kilos de VENTAS SDC: 4 tramos; 3 llenos, 1 vacíos y 0 fallidos." in caplog.messages
    assert ("Kilos de VENTAS SDC: llenos: 2026-06-01 a 2026-06-30, 2026-07-01 a 2026-07-31, "
            "2026-09-01 a 2026-09-23.") in caplog.messages
    assert "Kilos de VENTAS SDC: vacíos (sin ventas en SAP): 2026-08-01 a 2026-08-31." in caplog.messages
    assert not any("Kilos de VENTAS SGX" in m for m in caplog.messages)
    assert correos == []
    estado = _estado()
    assert (estado["estado"], estado["modo"], estado["fallos"]) == ("OK", "kilos ventas", [])
    assert [t["estado"] for t in estado["tramos"]] == ["lleno", "lleno", "vacío", "lleno"]
    assert "12.5" not in json.dumps(estado) and "Socio" not in json.dumps(estado)
    assert len(renovaciones) >= 4
    assert not (config.STATE_DIR / "robot.lock").exists()


def test_kilos_de_una_empresa_y_con_hasta(con_kilos, correos):
    e = con_kilos
    _datos_de_junio(e)
    argumentos = ("--kilos-ventas", "--desde", "2026-06", "--hasta", "2026-07", "--empresa", "SDC")
    assert _main(e, *argumentos, dormir=_no_dormir) == 0
    assert _corridas(e) == [
        ("SDC", "kilos", "2026-06-01", "2026-06-30", "cerrada"),
        ("SDC", "kilos", "2026-07-01", "2026-07-31", "cerrada"),
    ]
    assert not e.hana.de("SGX")


def test_un_tramo_que_falla_no_frena_los_demas(con_kilos, correos, caplog):
    e = con_kilos
    _datos_de_junio(e)
    e.servidor.programar_fallas("lote", status=422, datos={"message": "x", "errors": {"rows.0.kilos": ["x"]}})
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--kilos-ventas", "--desde", "2026-06", dormir=_no_dormir) == 1
    corridas = _corridas(e)
    assert corridas[0] == ("SDC", "kilos", "2026-06-01", "2026-06-30", "fallida")
    assert [c[4] for c in corridas[1:]] == ["cerrada"] * 2
    [aviso] = correos
    assert aviso == [("API", "VENTAS SDC 2026-06-01 a 2026-06-30: La API rechazó la petición (422) en rows.0.kilos.")]
    assert ("Kilos de VENTAS SDC: fallidos: 2026-06-01 a 2026-06-30 (La API rechazó la petición (422) "
            "en rows.0.kilos.).") in caplog.messages
    assert "Kilos de VENTAS SDC: 4 tramos; 2 llenos, 1 vacíos y 1 fallidos." in caplog.messages
    estado = _estado()
    assert estado["estado"] == "ERROR" and estado["tramos"][0]["estado"] == "falló"


def test_un_409_al_iniciar_es_un_tramo_fallido_y_sigue_con_los_demas(con_kilos, correos):
    e = con_kilos
    _datos_de_junio(e)
    e.servidor.programar_fallas("iniciar", status=409, datos={"message": "Ya tiene kilos."})
    assert _main(e, "--kilos-ventas", "--desde", "2026-06", "--empresa", "SDC", dormir=_no_dormir) == 1
    assert [c[2] for c in _corridas(e)] == ["2026-07-01", "2026-09-01"]
    tramos = _estado()["tramos"]
    assert [t["estado"] for t in tramos] == ["falló", "lleno", "vacío", "lleno"]
    assert tramos[0]["motivo"] == "La API rechazó la petición (409)."
    assert "ya cargado" not in json.dumps(tramos)


def test_si_falla_la_red_al_iniciar_un_tramo_sigue_con_el_siguiente(con_kilos, correos):
    e = con_kilos
    _datos_de_junio(e)
    e.servidor.programar_fallas("iniciar", veces=4, red=True)
    assert _main(e, "--kilos-ventas", "--desde", "2026-06", "--empresa", "SDC", dormir=lambda s: None) == 1
    assert [c[2] for c in _corridas(e)] == ["2026-07-01", "2026-09-01"]
    assert [t["estado"] for t in _estado()["tramos"]] == ["falló", "lleno", "vacío", "lleno"]


def test_un_kilo_vacio_en_sap_se_envia_como_null(con_kilos, correos):
    # SAP no tiene peso para esa línea: la API guarda null (contrato §10.5). La columna de la
    # consulta sí tiene que existir; lo que puede venir vacío es el valor de una fila.
    e = con_kilos
    _ventas(e, "SDC", date(2026, 9, 10), kilos_por_fila=None)
    e.hana.datos["SDC"]["ventas"].append(fila("ventas", 2, fecha_contabilizacion=date(2026, 9, 11),
                                              Kilos=Decimal("-3.25")))
    assert _main(e, "--kilos-ventas", "--desde", "2026-09", "--empresa", "SDC", dormir=_no_dormir) == 0
    [corrida] = e.servidor.corridas.values()
    assert corrida.estado == "cerrada"
    assert [f["kilos"] for f in corrida.filas("ventas")] == [None, "-3.250000"]
    assert [t["estado"] for t in _estado()["tramos"]] == ["lleno"]
    assert correos == []


def test_repetir_un_mes_no_hace_dano(con_kilos, correos):
    # A diferencia del histórico, no hay 409 por un rango ya cargado: se vuelven a escribir.
    e = con_kilos
    _datos_de_junio(e)
    assert _main(e, "--kilos-ventas", "--desde", "2026-09", dormir=_no_dormir) == 0
    assert _main(e, "--kilos-ventas", "--desde", "2026-09", dormir=_no_dormir) == 0
    assert [c[4] for c in _corridas(e)] == ["cerrada"] * 2
    assert [t["estado"] for t in _estado()["tramos"]] == ["lleno"]


def test_si_las_lineas_no_cuadran_con_mysql_falla_el_tramo_con_los_conteos(con_kilos, correos, caplog):
    e = con_kilos
    _datos_de_junio(e)
    e.servidor.descuadres_kilos[("SDC", "2026-06-01")] = (2, 1)
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--kilos-ventas", "--desde", "2026-06", "--empresa", "SDC", dormir=_no_dormir) == 1
    assert [c[4] for c in _corridas(e)] == ["fallida", "cerrada", "cerrada"]
    motivo = "La API rechazó la petición (422) en filas.ventas (sobran 2 y faltan 1 líneas)."
    tramos = _estado()["tramos"]
    assert [t["estado"] for t in tramos] == ["falló", "lleno", "vacío", "lleno"]
    assert tramos[0]["motivo"] == motivo
    assert f"Kilos de VENTAS SDC: fallidos: 2026-06-01 a 2026-06-30 ({motivo})." in caplog.messages
    assert "Kilos de VENTAS SDC: 4 tramos; 2 llenos, 1 vacíos y 1 fallidos." in caplog.messages
    assert correos == [[("API", f"VENTAS SDC 2026-06-01 a 2026-06-30: {motivo}")]]


def test_si_falla_la_vpn_no_envia_nada(con_kilos, correos):
    e = con_kilos
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    assert _main(e, "--kilos-ventas", "--desde", "2026-06", vpn=vpn, dormir=_no_dormir) == 1
    assert e.servidor.peticiones == [] and e.hana.ejecutadas == []
    assert [etapa for etapa, _ in correos[0]] == ["VPN"]
    revisar_fases(e.linea)


# --- Estimación, franjas y candado ---------------------------------------------------------


def test_duracion_estimada_de_los_kilos_es_por_segundos_y_mucho_menor_que_la_del_historico():
    assert kilos.duracion_estimada(22, 2) == timedelta(
        seconds=kilos.SEGUNDOS_FIJOS + 44 * kilos.SEGUNDOS_POR_TRAMO)
    assert kilos.duracion_estimada(0, 2) == timedelta(seconds=kilos.SEGUNDOS_FIJOS)
    # El histórico real del 2026-11-24 tuvo la VPN arriba 78 s para 44 tramos: la estimación
    # cubre eso con holgura y no se acerca a la del histórico.
    assert timedelta(seconds=78) * 5 < kilos.duracion_estimada(22, 2) < timedelta(minutes=15)
    assert kilos.duracion_estimada(22, 2) * 5 < historico.duracion_estimada(22, 2)


def test_a_las_4_30_cabe_antes_de_la_franja_de_las_5_y_no_espera(con_kilos, correos):
    # 21 meses de Derivados: 2 minutos más 21 tramos de 10 s, 5 minutos y medio; terminan antes
    # de las 04:45, cuando empieza la franja de las 05:00. El histórico esperaba hasta las 06:16.
    e = con_kilos
    reloj = _Reloj(datetime(2026, 10, 26, 4, 30, tzinfo=config.BOGOTA), e.vpn)
    assert _main(e, "--kilos-ventas", "--desde", "2025-01", ahora=reloj.ahora, dormir=reloj.dormir) == 0
    assert kilos.duracion_estimada(21, 1) == timedelta(minutes=5, seconds=30)
    assert reloj.esperas == []
    assert e.vpn.conexiones == 1


def test_si_no_alcanza_antes_de_la_siguiente_franja_espera_a_que_pase(con_kilos, correos, caplog):
    # A las 04:40 los 5 minutos y medio terminan a las 04:45:30, dentro de la franja de las
    # 05:00: espera a que pase (05:16) y ahí sí caben antes de la de las 06:00 (05:45).
    e = con_kilos
    reloj = _Reloj(datetime(2026, 10, 26, 4, 40, tzinfo=config.BOGOTA), e.vpn)
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--kilos-ventas", "--desde", "2025-01", ahora=reloj.ahora,
                     dormir=reloj.dormir) == 0
    assert reloj.esperas == [36 * 60]
    assert e.vpn.conexiones == 1
    assert any("La fase con VPN de los kilos tarda unos 5 minutos y no cabe antes de la franja" in m
               for m in caplog.messages)


def test_dentro_de_una_franja_espera_a_que_pase(con_kilos, correos):
    e = con_kilos
    _datos_de_junio(e)
    reloj = _Reloj(datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA), e.vpn)
    assert _main(e, "--kilos-ventas", "--desde", "2026-06", ahora=reloj.ahora, dormir=reloj.dormir) == 0
    assert reloj.esperas == [56 * 60]  # hasta las 12:46, pasadas las franjas de las 12:00 y 12:30
    assert len(e.servidor.corridas) == 3


def test_con_el_candado_tomado_espera_como_el_historico(con_kilos, correos, candado_ajeno):
    e = con_kilos
    _datos_de_junio(e)
    ruta = candado_ajeno()
    esperas: list[float] = []

    def dormir(segundos):
        esperas.append(segundos)
        if len(esperas) == 2:
            ruta.unlink()

    assert _main(e, "--kilos-ventas", "--desde", "2026-09", dormir=dormir) == 0
    assert esperas == [10, 10]
    assert len(e.servidor.corridas) == 1


def test_sin_candado_en_20_minutos_avisa_y_no_corre(con_kilos, correos, candado_ajeno):
    e = con_kilos
    candado_ajeno()
    esperas: list[float] = []
    assert _main(e, "--kilos-ventas", "--desde", "2026-09", dormir=esperas.append) == 1
    assert sum(esperas) == 20 * 60
    assert e.vpn.conexiones == 0 and e.servidor.peticiones == []
    assert [etapa for etapa, _ in correos[0]] == ["CANDADO"]


# --- La nocturna y el histórico siguen igual ------------------------------------------------


def test_la_nocturna_y_el_historico_no_mandan_kilos(entorno, correos):
    e = entorno
    assert _main(e, "--completa") == 0  # los datos de prueba traen ventas de octubre
    for empresa in ("SGX", "SDC"):
        _ventas(e, empresa, date(2026, 9, 10))
    assert _main(e, "--historico-ventas", "--desde", "2026-09", dormir=_no_dormir) == 0
    ventas = [c for c in e.servidor.corridas.values() if c.conjunto == "VENTAS"]
    assert [c.tipo for c in ventas] == ["completa", "completa", "historico", "historico"]
    for corrida in ventas:
        assert {tuple(lote.columns) for lote in corrida.lotes.values()} == {
            tuple(esquema.PARTES["ventas"].nombres)}
        assert "kilos" not in esquema.PARTES["ventas"].nombres
    assert not any(x.tipo == "kilos" for x in e.hana.ejecutadas)


# --- Argumentos ------------------------------------------------------------------------------


@pytest.mark.parametrize("argumentos, texto", [
    (["--kilos-ventas"], "--kilos-ventas necesita --desde AAAA-MM"),
    (["--kilos-ventas", "--desde", "2025-01-01"], "AAAA-MM"),
    (["--kilos-ventas", "--desde", "2024-12"], "--kilos-ventas va desde 2025-01"),
    (["--kilos-ventas", "--desde", "2024-12", "--hasta", "2025-03"], "--kilos-ventas va desde 2025-01"),
    (["--kilos-ventas", "--desde", "2025-01", "--hasta", "2026-11"], "ventana nocturna"),
    (["--kilos-ventas", "--desde", "2025-03", "--hasta", "2025-02"], "--hasta"),
    (["--kilos-ventas", "--historico-ventas", "--desde", "2025-01"], "not allowed"),
    (["--completa", "--desde", "2025-01"], "--desde va solo con --carga-produccion, --historico-ventas o --kilos"),
    (["--kilos-ventas", "--desde", "2025-01", "--empresa", "SGX"], "--kilos-ventas es solo de SDC"),
    (["--kilos-ventas", "--desde", "2025-01", "--empresa", "SDC", "--empresa", "SGX"], "NumInSale"),
])
def test_argumentos_invalidos_no_corren(entorno, capsys, argumentos, texto):
    with pytest.raises(SystemExit) as exc:
        _main(entorno, *argumentos)
    assert exc.value.code == 2
    assert texto in capsys.readouterr().err
    assert entorno.servidor.corridas == {} and entorno.hana.ejecutadas == []
    assert not (config.STATE_DIR / "ultima_ejecucion.json").exists()
