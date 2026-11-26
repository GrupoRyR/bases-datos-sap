"""Complemento de VENTAS (orden 016): run_robot.py --complemento-ventas, con fakes.

La corrida `complemento` (contrato §10.5) llena `kilos` y `codigo_envio` de las líneas ya
cargadas. La consulta real (queries/ventas/ventas.sql) trae las dos columnas: los kilos son
la expresión de «Tot KG» de «AnálisisVentas-1» en Derivados y un NULL en Segurex; el código
de envío (ShipToCode) es de verdad en las dos empresas. Las pruebas de falla cerrada usan una
copia de robot/queries en tmp SIN la columna de kilos (`sin_kilos`).
"""
from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

import bloqueo
import complemento
import config
import esquema
import historico
from api import ApiCliente, ApiRechazo
from fake_api import COLUMNAS_COMPLEMENTO
from fake_hana import QUERIES, VpnFalsa, fila, revisar_fases
from test_historico import TRAMOS_JUNIO, _no_dormir, _Reloj
from test_run_robot import _estado, _main
from trabajos import Trabajo

COLUMNAS = ["tipo_objeto", "doc_entry", "linea", "fecha_contabilizacion", "kilos", "codigo_envio"]
EXPRESION_KILOS = 'CAST(X."Quantity" * T4."NumInSale" * X."Signo" AS DECIMAL(19, 6)) AS "Kilos", -- @kilos'
KILOS_NULOS = 'CAST(NULL AS DECIMAL(19, 6)) AS "Kilos", -- @kilos'
PROYECCION = ('SELECT X."Tipo objeto", X."DocEntry", X."Línea", X."Fecha contabilización", X."Kilos", '
              'X."Código envío" FROM (')
# La columna de kilos de ventas.sql con su nota (la consulta de antes de la orden 016).
_ADICION_KILOS = re.compile(r'(?:    --[^\n]*\n)*    CAST\([^\n]*\) AS "Kilos", -- @kilos\n')


@pytest.fixture
def sin_kilos(entorno, tmp_path, monkeypatch):
    """El entorno con una copia de robot/queries cuya consulta de ventas NO trae kilos."""
    copia = tmp_path / "queries_sin_kilos"
    shutil.copytree(QUERIES, copia)
    ventas = copia / "ventas" / "ventas.sql"
    texto, cambios = _ADICION_KILOS.subn("", ventas.read_text(encoding="utf-8"))
    assert cambios == 1 and 'AS "Kilos"' not in texto
    ventas.write_bytes(texto.encode("utf-8"))
    monkeypatch.setattr(config, "QUERIES_DIR", copia)
    return entorno


def _ventas(e, empresa: str, *dias: date, kilos_por_fila: Decimal | None = Decimal("12.5")) -> None:
    # El código de envío de cada fila es el de prueba: "codigo_envio-<i>".
    e.hana.datos[empresa]["ventas"] = [
        fila("ventas", i, fecha_contabilizacion=dia, Kilos=kilos_por_fila) for i, dia in enumerate(dias, start=1)
    ]


def _datos_de_junio(e) -> None:
    # Derivados: nada en agosto (tramo vacío), una fila el 24/09 (ya es la ventana) y otra en
    # mayo. Segurex: una venta en cada mes.
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
    sin_kilos, correos, candado_ajeno, monkeypatch, caplog
):
    e = sin_kilos
    _datos_de_junio(e)
    candado_ajeno()  # ni siquiera espera a que otro proceso suelte el candado
    _sin_candado_ni_espera(monkeypatch)
    reloj = _Reloj(datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA), e.vpn)  # dentro de una franja
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--complemento-ventas", "--desde", "2026-06", ahora=reloj.ahora, dormir=_no_dormir) == 2
    assert e.vpn.conexiones == 0 and e.hana.ejecutadas == [] and e.servidor.peticiones == []
    estado = _estado()
    assert (estado["estado"], estado["modo"], estado["etapa"]) == ("ERROR", "complemento ventas", "CONFIGURACION")
    assert "kilos" in estado["error"] and "Tot KG" in estado["error"]
    assert any("no trae la columna de kilos" in m for m in caplog.messages)


def test_sin_la_columna_de_kilos_tampoco_corre_con_forzar_ni_sin_vpn(sin_kilos, correos, monkeypatch):
    e = sin_kilos
    _sin_candado_ni_espera(monkeypatch)
    assert _main(e, "--complemento-ventas", "--desde", "2026-06", "--forzar", "--sin-vpn", dormir=_no_dormir) == 2
    assert e.hana.ejecutadas == [] and e.servidor.peticiones == []


def test_con_la_consulta_sin_kilos_un_tramo_tampoco_se_extrae(sin_kilos):
    # Si la consulta cambiara entre la revisión y la extracción, cada tramo la vuelve a exigir:
    # sin la expresión marcada `-- @kilos` la consulta de la empresa ni se arma.
    e = sin_kilos
    _datos_de_junio(e)
    tramos, fallos = complemento.ejecutar(
        e.cfg, ["SDC"], date(2026, 6, 1), date(2026, 6, 1), api=e.cliente, robot_vpn=e.vpn,
        conectar=e.hana.conectar, ahora=e.ahora,
    )
    assert [t.estado for t in tramos] == ["falló"]
    assert '"Kilos"' in (tramos[0].motivo or "") and "@kilos" in (tramos[0].motivo or "")
    assert [etapa for etapa, _ in fallos] == ["CONFIGURACION"]
    assert [x.tipo for x in e.hana.de("SDC")] == ["ventana"]  # la consulta del complemento no corrió
    assert e.servidor.peticiones == []


# --- La corrida complemento (contrato §10.5) -----------------------------------------------


def test_trabajo_de_un_tramo_es_una_corrida_complemento_de_ventas_con_su_rango():
    assert complemento.trabajo_complemento_ventas("SGX", date(2025, 1, 1), date(2025, 1, 31)) == Trabajo(
        empresa="SGX", conjunto="VENTAS", tipo="complemento", partes={"ventas": "todo"},
        ventana_fija="2025-01-01", ventana_hasta="2025-01-31",
    )
    assert complemento.TIPO == "complemento"
    assert complemento.PARTE_COMPLEMENTO.nombres == COLUMNAS
    assert set(COLUMNAS) == COLUMNAS_COMPLEMENTO
    assert complemento.PRIMER_MES == date(2025, 1, 1)
    assert complemento.PARTE_COMPLEMENTO.llave == esquema.PARTES["ventas"].llave


def _abrir(api: ApiCliente, ventana_desde: str = "2026-06-01", ventana_hasta: str = "2026-06-30",
           tipo: str = "complemento") -> int:
    return api.iniciar_corrida(
        conjunto="VENTAS", empresa="SGX", tipo=tipo, partes={"ventas": "todo"}, solicitudes=[],
        fecha_corte=None, extraida_en="2026-10-26T02:00:05-05:00",
        ventana_desde=ventana_desde, ventana_hasta=ventana_hasta,
    )["run_id"]


def test_ya_no_hay_corrida_kilos(escenario):
    with pytest.raises(ApiRechazo) as exc:
        _abrir(escenario.cliente, tipo="kilos")
    assert exc.value.status == 422 and "tipo" in exc.value.errors


@pytest.mark.parametrize("columnas", [
    esquema.PARTES["ventas"].nombres,                                     # el encabezado completo de §10
    ["tipo_objeto", "doc_entry", "linea", "fecha_contabilizacion", "kilos"],  # el de la corrida kilos
    ["tipo_objeto", "doc_entry", "linea", "fecha_contabilizacion", "codigo_envio"],
    [*COLUMNAS, "cantidad"],
])
def test_un_lote_complemento_lleva_exactamente_las_seis_columnas(escenario, columnas):
    api: ApiCliente = escenario.cliente
    run_id = _abrir(api)
    with pytest.raises(ApiRechazo) as exc:
        api.enviar_lote(run_id, batch=1, parte="ventas", columns=columnas, rows=[[None] * len(columnas)])
    assert exc.value.status == 422 and "columns" in exc.value.errors


def test_un_lote_complemento_acepta_las_seis_en_cualquier_orden_con_nulls(escenario):
    api: ApiCliente = escenario.cliente
    run_id = _abrir(api)
    columnas = ["codigo_envio", "kilos", "linea", "fecha_contabilizacion", "doc_entry", "tipo_objeto"]
    api.enviar_lote(run_id, batch=1, parte="ventas", columns=columnas,
                    rows=[[None, None, 0, "2026-06-10", 7, 13]])
    respuesta = api.cerrar_corrida(run_id, batches=1, filas={"ventas": 1}, conteo_sap={"ventas": 1})
    assert respuesta["estado"] == "cerrada"
    [guardada] = escenario.servidor.corridas[run_id].filas("ventas")
    assert (guardada["kilos"], guardada["codigo_envio"]) == (None, None)


def test_una_corrida_complemento_no_empieza_antes_de_2025(escenario):
    with pytest.raises(ApiRechazo) as exc:
        _abrir(escenario.cliente, "2024-12-01", "2024-12-31")
    assert exc.value.status == 422 and "ventana_desde" in exc.value.errors


def test_si_el_conteo_de_sap_no_cuadra_el_cierre_falla_y_la_corrida_queda_fallida(escenario):
    api: ApiCliente = escenario.cliente
    run_id = _abrir(api)
    api.enviar_lote(run_id, batch=1, parte="ventas", columns=COLUMNAS,
                    rows=[[13, 7, 0, "2026-06-10", "1.5", "CEDI"]])
    with pytest.raises(ApiRechazo) as exc:
        api.cerrar_corrida(run_id, batches=1, filas={"ventas": 1}, conteo_sap={"ventas": 2})
    assert exc.value.status == 422 and "conteo_sap.ventas" in exc.value.errors
    assert escenario.servidor.corridas[run_id].estado == "fallida"


# --- run_robot.py --complemento-ventas con las columnas de ventas.sql -----------------------
# AHORA es el 26/10/2026 a las 02:00: HANA da la ventana desde el 24/09, así que con
# --desde 2026-06 los tramos son junio, julio, agosto y septiembre hasta el 23 (el último,
# parcial).


def test_complemento_llena_cada_tramo_de_las_dos_empresas_en_orden(entorno, correos, caplog, monkeypatch):
    e = entorno
    _datos_de_junio(e)
    renovaciones: list[bool] = []
    original = bloqueo.Bloqueo.renovar
    monkeypatch.setattr(bloqueo.Bloqueo, "renovar",
                        lambda self: renovaciones.append(True) or original(self))
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--complemento-ventas", "--desde", "2026-06", dormir=_no_dormir) == 0
    revisar_fases(e.linea)
    assert e.vpn.conexiones == 1
    # Sin --empresa, las dos, empresa por empresa y del mes más viejo al más nuevo; agosto de
    # Derivados no tiene ventas.
    assert _corridas(e) == [
        *[("SGX", "complemento", desde, hasta, "cerrada") for desde, hasta in TRAMOS_JUNIO],
        ("SDC", "complemento", "2026-06-01", "2026-06-30", "cerrada"),
        ("SDC", "complemento", "2026-07-01", "2026-07-31", "cerrada"),
        ("SDC", "complemento", "2026-09-01", "2026-09-23", "cerrada"),
    ]
    for corrida in e.servidor.corridas.values():
        assert (corrida.conjunto, corrida.partes, corrida.solicitudes) == ("VENTAS", {"ventas": "todo"}, [])
        assert corrida.conteo_sap == corrida.total_filas()
        # Cada lote lleva solo la llave, la fecha, los kilos y el código de envío, en ese orden.
        assert {tuple(lote.columns) for lote in corrida.lotes.values()} == {tuple(COLUMNAS)}
        for f in corrida.filas("ventas"):
            assert corrida.ventana_desde <= f["fecha_contabilizacion"] <= corrida.ventana_hasta
            # Segurex manda los kilos en null (la consulta trae un NULL); Derivados, los de SAP.
            assert f["kilos"] == (None if corrida.empresa == "SGX" else "12.500000")
            assert f["codigo_envio"] == f"codigo_envio-{f['linea']}"
    assert [c.conteo_sap for c in e.servidor.corridas.values()][4:] == [
        {"ventas": 2}, {"ventas": 1}, {"ventas": 1}]
    assert e.servidor.corridas[5].filas("ventas") == [
        {"tipo_objeto": 2, "doc_entry": 2, "linea": 2, "fecha_contabilizacion": "2026-06-01",
         "kilos": "12.500000", "codigo_envio": "codigo_envio-2"},
        {"tipo_objeto": 3, "doc_entry": 3, "linea": 3, "fecha_contabilizacion": "2026-06-30",
         "kilos": "12.500000", "codigo_envio": "codigo_envio-3"},
    ]
    inicio = e.servidor.peticiones_a("iniciar")[0].datos
    assert {k: v for k, v in inicio.items() if k != "extraida_en"} == {
        "conjunto": "VENTAS", "empresa": "SGX", "tipo": "complemento", "partes": {"ventas": "todo"},
        "solicitudes": [], "fecha_corte": None,
        "ventana_desde": "2026-06-01", "ventana_hasta": "2026-06-30",
    }
    # En HANA: la ventana una vez por empresa y, por tramo, la consulta del complemento con su
    # rango y su conteo, en la misma conexión.
    for empresa in ("SGX", "SDC"):
        pasos = e.hana.de(empresa)
        assert [p.tipo for p in pasos] == ["ventana"] + ["complemento", "contar"] * 4
        assert len({p.conexion for p in pasos}) == 1
        for (desde, hasta), (consulta, contar) in zip(TRAMOS_JUNIO, zip(pasos[1::2], pasos[2::2])):
            rango = f"BETWEEN TO_DATE('{desde}', 'YYYY-MM-DD') AND TO_DATE('{hasta}', 'YYYY-MM-DD')"
            assert consulta.sql.startswith(PROYECCION)
            assert rango in consulta.sql and consulta.sql in contar.sql
    # Derivados: el id del pedido de la app en NULL y los kilos de «Tot KG». Segurex: el id de
    # verdad y los kilos en NULL.
    sdc, sgx = e.hana.de("SDC", "complemento")[0].sql, e.hana.de("SGX", "complemento")[0].sql
    assert 'CAST(T0."U_SGX_IdPedidoApp"' not in sdc and EXPRESION_KILOS in sdc
    assert 'CAST(T0."U_SGX_IdPedidoApp"' in sgx and KILOS_NULOS in sgx
    # No escribe CSV.
    assert not any(evento[0] == "csv" for evento in e.linea)
    assert not (e.csv_dir / "VENTAS").exists()
    # Resumen por empresa.
    assert "Complemento de VENTAS SGX: 4 tramos; 4 llenos, 0 vacíos y 0 fallidos." in caplog.messages
    assert "Complemento de VENTAS SDC: 4 tramos; 3 llenos, 1 vacíos y 0 fallidos." in caplog.messages
    assert ("Complemento de VENTAS SDC: llenos: 2026-06-01 a 2026-06-30, 2026-07-01 a 2026-07-31, "
            "2026-09-01 a 2026-09-23.") in caplog.messages
    assert "Complemento de VENTAS SDC: vacíos (sin ventas en SAP): 2026-08-01 a 2026-08-31." in caplog.messages
    assert correos == []
    estado = _estado()
    assert (estado["estado"], estado["modo"], estado["fallos"]) == ("OK", "complemento ventas", [])
    assert [t["estado"] for t in estado["tramos"]] == ["lleno"] * 4 + ["lleno", "lleno", "vacío", "lleno"]
    assert "12.5" not in json.dumps(estado) and "codigo_envio-" not in json.dumps(estado)
    assert len(renovaciones) >= 8
    assert not (config.STATE_DIR / "robot.lock").exists()


def test_complemento_de_segurex_solo_y_con_hasta(entorno, correos):
    # Segurex sí corre: su código de envío es de verdad; sus kilos van en null.
    e = entorno
    _datos_de_junio(e)
    argumentos = ("--complemento-ventas", "--desde", "2026-06", "--hasta", "2026-07", "--empresa", "SGX")
    assert _main(e, *argumentos, dormir=_no_dormir) == 0
    assert _corridas(e) == [
        ("SGX", "complemento", "2026-06-01", "2026-06-30", "cerrada"),
        ("SGX", "complemento", "2026-07-01", "2026-07-31", "cerrada"),
    ]
    assert not e.hana.de("SDC")
    filas = [f for c in e.servidor.corridas.values() for f in c.filas("ventas")]
    assert [(f["kilos"], f["codigo_envio"]) for f in filas] == [(None, "codigo_envio-1"), (None, "codigo_envio-2")]


def test_un_tramo_que_falla_no_frena_los_demas(entorno, correos, caplog):
    e = entorno
    _datos_de_junio(e)
    e.servidor.programar_fallas("lote", status=422, datos={"message": "x", "errors": {"rows.0.kilos": ["x"]}})
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--complemento-ventas", "--desde", "2026-06", dormir=_no_dormir) == 1
    corridas = _corridas(e)
    assert corridas[0] == ("SGX", "complemento", "2026-06-01", "2026-06-30", "fallida")
    assert [c[4] for c in corridas[1:]] == ["cerrada"] * 6
    [aviso] = correos
    assert aviso == [("API", "VENTAS SGX 2026-06-01 a 2026-06-30: La API rechazó la petición (422) en rows.0.kilos.")]
    assert ("Complemento de VENTAS SGX: fallidos: 2026-06-01 a 2026-06-30 (La API rechazó la petición (422) "
            "en rows.0.kilos.).") in caplog.messages
    assert "Complemento de VENTAS SGX: 4 tramos; 3 llenos, 0 vacíos y 1 fallidos." in caplog.messages
    estado = _estado()
    assert estado["estado"] == "ERROR" and estado["tramos"][0]["estado"] == "falló"


def test_un_409_al_iniciar_es_un_tramo_fallido_y_sigue_con_los_demas(entorno, correos):
    e = entorno
    _datos_de_junio(e)
    e.servidor.programar_fallas("iniciar", status=409, datos={"message": "Ya tiene kilos."})
    assert _main(e, "--complemento-ventas", "--desde", "2026-06", "--empresa", "SDC", dormir=_no_dormir) == 1
    assert [c[2] for c in _corridas(e)] == ["2026-07-01", "2026-09-01"]
    tramos = _estado()["tramos"]
    assert [t["estado"] for t in tramos] == ["falló", "lleno", "vacío", "lleno"]
    assert tramos[0]["motivo"] == "La API rechazó la petición (409)."
    assert "ya cargado" not in json.dumps(tramos)


def test_si_falla_la_red_al_iniciar_un_tramo_sigue_con_el_siguiente(entorno, correos):
    e = entorno
    _datos_de_junio(e)
    e.servidor.programar_fallas("iniciar", veces=4, red=True)
    assert _main(e, "--complemento-ventas", "--desde", "2026-06", "--empresa", "SDC", dormir=lambda s: None) == 1
    assert [c[2] for c in _corridas(e)] == ["2026-07-01", "2026-09-01"]
    assert [t["estado"] for t in _estado()["tramos"]] == ["falló", "lleno", "vacío", "lleno"]


def test_un_kilo_o_un_codigo_de_envio_vacio_en_sap_se_envia_como_null(entorno, correos):
    # SAP no tiene peso o dirección de envío para esa línea: la API guarda null (contrato
    # §10.5). Las columnas de la consulta sí tienen que existir; lo que puede venir vacío es el
    # valor de una fila.
    e = entorno
    _ventas(e, "SDC", date(2026, 9, 10), kilos_por_fila=None)
    e.hana.datos["SDC"]["ventas"].append(fila("ventas", 2, fecha_contabilizacion=date(2026, 9, 11),
                                              Kilos=Decimal("-3.25"), codigo_envio=None))
    assert _main(e, "--complemento-ventas", "--desde", "2026-09", "--empresa", "SDC", dormir=_no_dormir) == 0
    [corrida] = e.servidor.corridas.values()
    assert corrida.estado == "cerrada"
    assert [(f["kilos"], f["codigo_envio"]) for f in corrida.filas("ventas")] == [
        (None, "codigo_envio-1"), ("-3.250000", None)]
    assert [t["estado"] for t in _estado()["tramos"]] == ["lleno"]
    assert correos == []


def test_repetir_un_mes_no_hace_dano(entorno, correos):
    # A diferencia del histórico, no hay 409 por un rango ya cargado: se vuelven a escribir.
    e = entorno
    _datos_de_junio(e)
    assert _main(e, "--complemento-ventas", "--desde", "2026-09", dormir=_no_dormir) == 0
    assert _main(e, "--complemento-ventas", "--desde", "2026-09", dormir=_no_dormir) == 0
    assert [c[4] for c in _corridas(e)] == ["cerrada"] * 4
    assert [t["estado"] for t in _estado()["tramos"]] == ["lleno", "lleno"]


def test_si_las_lineas_no_cuadran_con_mysql_falla_el_tramo_con_los_conteos(entorno, correos, caplog):
    e = entorno
    _datos_de_junio(e)
    e.servidor.descuadres_complemento[("SDC", "2026-06-01")] = (2, 1)
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--complemento-ventas", "--desde", "2026-06", "--empresa", "SDC", dormir=_no_dormir) == 1
    assert [c[4] for c in _corridas(e)] == ["fallida", "cerrada", "cerrada"]
    motivo = "La API rechazó la petición (422) en filas.ventas (sobran 2 y faltan 1 líneas)."
    tramos = _estado()["tramos"]
    assert [t["estado"] for t in tramos] == ["falló", "lleno", "vacío", "lleno"]
    assert tramos[0]["motivo"] == motivo
    assert f"Complemento de VENTAS SDC: fallidos: 2026-06-01 a 2026-06-30 ({motivo})." in caplog.messages
    assert "Complemento de VENTAS SDC: 4 tramos; 2 llenos, 1 vacíos y 1 fallidos." in caplog.messages
    assert correos == [[("API", f"VENTAS SDC 2026-06-01 a 2026-06-30: {motivo}")]]


def test_si_falla_la_vpn_no_envia_nada(entorno, correos):
    e = entorno
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    assert _main(e, "--complemento-ventas", "--desde", "2026-06", vpn=vpn, dormir=_no_dormir) == 1
    assert e.servidor.peticiones == [] and e.hana.ejecutadas == []
    assert [etapa for etapa, _ in correos[0]] == ["VPN"]
    revisar_fases(e.linea)


# --- Estimación, franjas y candado ---------------------------------------------------------


def test_duracion_estimada_del_complemento_es_por_segundos_y_mucho_menor_que_la_del_historico():
    assert complemento.duracion_estimada(22, 2) == timedelta(
        seconds=complemento.SEGUNDOS_FIJOS + 44 * complemento.SEGUNDOS_POR_TRAMO)
    assert complemento.duracion_estimada(0, 2) == timedelta(seconds=complemento.SEGUNDOS_FIJOS)
    # El histórico real del 2026-11-24 tuvo la VPN arriba 78 s para 44 tramos: la estimación
    # cubre eso con holgura y no se acerca a la del histórico.
    assert timedelta(seconds=78) * 5 < complemento.duracion_estimada(22, 2) < timedelta(minutes=15)
    assert complemento.duracion_estimada(22, 2) * 5 < historico.duracion_estimada(22, 2)


def test_a_las_4_30_cabe_antes_de_la_franja_de_las_5_y_no_espera(entorno, correos):
    # 21 meses de dos empresas: 2 minutos más 42 tramos de 10 s, 9 minutos; terminan antes de
    # las 04:45, cuando empieza la franja de las 05:00. El histórico esperaba hasta las 06:16.
    e = entorno
    reloj = _Reloj(datetime(2026, 10, 26, 4, 30, tzinfo=config.BOGOTA), e.vpn)
    assert _main(e, "--complemento-ventas", "--desde", "2025-01", ahora=reloj.ahora, dormir=reloj.dormir) == 0
    assert complemento.duracion_estimada(21, 2) == timedelta(minutes=9)
    assert reloj.esperas == []
    assert e.vpn.conexiones == 1


def test_si_no_alcanza_antes_de_la_siguiente_franja_espera_a_que_pase(entorno, correos, caplog):
    # A las 04:40 los 9 minutos terminan a las 04:49, dentro de la franja de las 05:00: espera
    # a que pase (05:16) y ahí sí caben antes de la de las 06:00 (05:45).
    e = entorno
    reloj = _Reloj(datetime(2026, 10, 26, 4, 40, tzinfo=config.BOGOTA), e.vpn)
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--complemento-ventas", "--desde", "2025-01", ahora=reloj.ahora,
                     dormir=reloj.dormir) == 0
    assert reloj.esperas == [36 * 60]
    assert e.vpn.conexiones == 1
    assert any("La fase con VPN del complemento tarda unos 9 minutos y no cabe antes de la franja" in m
               for m in caplog.messages)


def test_dentro_de_una_franja_espera_a_que_pase(entorno, correos):
    e = entorno
    _datos_de_junio(e)
    reloj = _Reloj(datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA), e.vpn)
    assert _main(e, "--complemento-ventas", "--desde", "2026-06", ahora=reloj.ahora, dormir=reloj.dormir) == 0
    assert reloj.esperas == [56 * 60]  # hasta las 12:46, pasadas las franjas de las 12:00 y 12:30
    assert len(e.servidor.corridas) == 7


def test_con_el_candado_tomado_espera_como_el_historico(entorno, correos, candado_ajeno):
    e = entorno
    _datos_de_junio(e)
    ruta = candado_ajeno()
    esperas: list[float] = []

    def dormir(segundos):
        esperas.append(segundos)
        if len(esperas) == 2:
            ruta.unlink()

    assert _main(e, "--complemento-ventas", "--desde", "2026-09", dormir=dormir) == 0
    assert esperas == [10, 10]
    assert len(e.servidor.corridas) == 2


def test_sin_candado_en_20_minutos_avisa_y_no_corre(entorno, correos, candado_ajeno):
    e = entorno
    candado_ajeno()
    esperas: list[float] = []
    assert _main(e, "--complemento-ventas", "--desde", "2026-09", dormir=esperas.append) == 1
    assert sum(esperas) == 20 * 60
    assert e.vpn.conexiones == 0 and e.servidor.peticiones == []
    assert [etapa for etapa, _ in correos[0]] == ["CANDADO"]


# --- La nocturna y el histórico mandan kilos y codigo_envio al final ------------------------


def test_la_nocturna_y_el_historico_mandan_kilos_y_codigo_envio_al_final(entorno, correos):
    # Contrato §10: kilos y codigo_envio son las dos últimas de las 37 columnas. Los kilos van
    # null en Segurex (la consulta trae un NULL) y en Derivados son lo que da SAP; el código de
    # envío sale de SAP en las dos empresas.
    e = entorno
    assert _main(e, "--completa") == 0  # los datos de prueba traen ventas de octubre
    for empresa in ("SGX", "SDC"):
        _ventas(e, empresa, date(2026, 9, 10), kilos_por_fila=Decimal("-2.5"))
    assert _main(e, "--historico-ventas", "--desde", "2026-09", dormir=_no_dormir) == 0
    ventas = [c for c in e.servidor.corridas.values() if c.conjunto == "VENTAS"]
    assert [(c.empresa, c.tipo) for c in ventas] == [
        ("SGX", "completa"), ("SDC", "completa"), ("SGX", "historico"), ("SDC", "historico")]
    nombres = esquema.PARTES["ventas"].nombres
    assert len(nombres) == 37 and nombres[-2:] == ["kilos", "codigo_envio"]
    for corrida in ventas:
        assert {tuple(lote.columns) for lote in corrida.lotes.values()} == {tuple(nombres)}
        envios = [f["codigo_envio"] for f in corrida.filas("ventas")]
        assert envios and all(v.startswith("codigo_envio-") for v in envios)
        valores = [f["kilos"] for f in corrida.filas("ventas")]
        if corrida.empresa == "SGX":
            assert valores and all(v is None for v in valores)
        elif corrida.tipo == "completa":
            assert valores == ["1.500000", "2.500000"]  # los kilos de las filas de prueba
        else:
            assert valores == ["-2.500000"]
    # La consulta de Segurex lleva el NULL; la de Derivados, la expresión.
    for empresa, esperado in (("SGX", KILOS_NULOS), ("SDC", EXPRESION_KILOS)):
        consultadas = [x for x in e.hana.de(empresa, parte="ventas") if x.tipo == "todo"]
        assert consultadas and all(esperado in x.sql for x in consultadas)
    assert not any(x.tipo == "complemento" for x in e.hana.ejecutadas)


# --- Argumentos ------------------------------------------------------------------------------


@pytest.mark.parametrize("argumentos, texto", [
    (["--complemento-ventas"], "--complemento-ventas necesita --desde AAAA-MM"),
    (["--complemento-ventas", "--desde", "2025-01-01"], "AAAA-MM"),
    (["--complemento-ventas", "--desde", "2024-12"], "--complemento-ventas va desde 2025-01"),
    (["--complemento-ventas", "--desde", "2024-12", "--hasta", "2025-03"], "--complemento-ventas va desde 2025-01"),
    (["--complemento-ventas", "--desde", "2025-01", "--hasta", "2026-11"], "ventana nocturna"),
    (["--complemento-ventas", "--desde", "2025-03", "--hasta", "2025-02"], "--hasta"),
    (["--complemento-ventas", "--historico-ventas", "--desde", "2025-01"], "not allowed"),
    (["--completa", "--desde", "2025-01"],
     "--desde va solo con --carga-produccion, --historico-ventas o --complemento-ventas"),
    # La bandera vieja ya no existe: la corrida `kilos` pasó a ser `complemento`.
    (["--kilos-ventas", "--desde", "2025-01"], "--complemento-ventas"),
])
def test_argumentos_invalidos_no_corren(entorno, capsys, argumentos, texto):
    with pytest.raises(SystemExit) as exc:
        _main(entorno, *argumentos)
    assert exc.value.code == 2
    assert texto in capsys.readouterr().err
    assert entorno.servidor.corridas == {} and entorno.hana.ejecutadas == []
    assert not (config.STATE_DIR / "ultima_ejecucion.json").exists()
