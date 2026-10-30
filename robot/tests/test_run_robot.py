from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

import pytest

import config
import run_robot
from fake_hana import VpnFalsa, revisar_fases
from trabajos import trabajos_de_solicitudes

HOY = date(2026, 10, 26)


def _main(e, *argumentos, vpn=None, **kwargs):
    kwargs.setdefault("fabrica_api", lambda cfg_api: e.nuevo_cliente(cfg_api))
    kwargs.setdefault("fabrica_vpn", lambda cfg_vpn: vpn or e.vpn)
    kwargs.setdefault("conectar", e.hana.conectar)
    kwargs.setdefault("ahora", e.ahora)
    return run_robot.main(list(argumentos), **kwargs)


def _estado() -> dict:
    return json.loads((config.STATE_DIR / "ultima_ejecucion.json").read_text(encoding="utf-8"))


def _corridas(e):
    return [(c.conjunto, c.empresa, c.tipo, c.estado) for c in e.servidor.corridas.values()]


SEIS_CERRADAS = [
    (conjunto, empresa, "completa", "cerrada")
    for empresa in ("SGX", "SDC") for conjunto in ("MAESTROS", "CARTERA", "VENTAS")
]


def test_completa_de_las_dos_empresas(entorno, correos):
    e = entorno
    assert _main(e, "--completa") == 0
    assert _corridas(e) == SEIS_CERRADAS
    revisar_fases(e.linea)
    # Las solicitudes se toman con la VPN ya abajo y antes de abrir las corridas
    # (vencen 30 minutos después de tomarlas, contrato §7.3).
    assert e.linea.index(("vpn", "abajo")) < e.linea.index(("api", "tomar"))
    assert e.linea.index(("api", "tomar")) < e.linea.index(("api", "iniciar"))
    assert e.vpn.conexiones == 1
    assert correos == []
    estado = _estado()
    assert estado["estado"] == "OK"
    assert estado["modo"] == "completa"
    assert estado["fallos"] == []
    assert (e.csv_dir / "CARTERA" / "SDC" / "historico" / "2026-10-25.csv").is_file()
    assert "CSGX001" not in json.dumps(estado)
    assert estado["trabajos"] == [f"{c} {emp}" for c, emp, _, _ in SEIS_CERRADAS]


def test_completa_trae_ventas_de_las_dos_empresas_con_su_conteo_y_ventana(entorno, correos):
    e = entorno
    assert _main(e, "--completa") == 0
    ventas = [c for c in e.servidor.corridas.values() if c.conjunto == "VENTAS"]
    assert [(c.empresa, c.tipo, c.estado) for c in ventas] == [
        ("SGX", "completa", "cerrada"), ("SDC", "completa", "cerrada"),
    ]
    for corrida in ventas:
        assert corrida.partes == {"ventas": "todo"}
        assert corrida.conteo_sap == {"ventas": 2} == corrida.total_filas()
        assert (corrida.ventana_desde, corrida.fecha_corte) == ("2026-09-24", None)
    for empresa in ("SGX", "SDC"):
        assert (e.csv_dir / "VENTAS" / empresa / "2026-10-26_0200.csv").is_file()
        # La ventana se pide en la misma conexión de la extracción, antes y después.
        pasos = [x for x in e.hana.de(empresa) if x.parte in ("ventana", "ventas")]
        assert [x.tipo for x in pasos] == ["ventana", "todo", "contar", "ventana"]
        assert len({x.conexion for x in pasos}) == 1


def test_completa_sin_lista_de_precios_en_derivados_no_falla_y_no_pide_precios(entorno, correos, monkeypatch):
    e = entorno
    monkeypatch.delenv("HANA_SDC_LISTA_PRECIOS")  # Derivados todavía no tiene lista pública
    assert _main(e, "--completa") == 0
    assert _corridas(e) == SEIS_CERRADAS
    sgx, _, _, sdc, _, _ = e.servidor.corridas.values()
    assert "precios" in sgx.partes and "precios" not in sdc.partes
    assert not e.hana.de("SDC", parte="precios")
    assert correos == []
    assert _estado()["fallos"] == []


def test_completa_falla_al_instante_la_solicitud_de_solo_precios_de_derivados(entorno, correos, monkeypatch):
    e = entorno
    monkeypatch.delenv("HANA_SDC_LISTA_PRECIOS")
    e.servidor.encolar_solicitud({"id": 50, "empresa": "SDC", "conjunto": "MAESTROS",
                                  "parte": "precios", "desde": {}})
    e.servidor.encolar_solicitud({"id": 51, "empresa": "SDC", "conjunto": "MAESTROS",
                                  "parte": None, "desde": {}})
    assert _main(e, "--completa") == 1
    assert [(c.conjunto, c.empresa, c.tipo, c.estado, c.solicitudes) for c in e.servidor.corridas.values()] == [
        ("MAESTROS", "SGX", "completa", "cerrada", []),
        ("CARTERA", "SGX", "completa", "cerrada", []),
        ("VENTAS", "SGX", "completa", "cerrada", []),
        ("MAESTROS", "SDC", "completa", "cerrada", [51]),
        ("CARTERA", "SDC", "completa", "cerrada", []),
        ("VENTAS", "SDC", "completa", "cerrada", []),
        ("MAESTROS", "SDC", "solicitud", "fallida", [50]),
    ]
    assert e.servidor.estado_solicitudes == {50: "fallida", 51: "terminada"}
    assert [etapa for etapa, _ in correos[0]] == ["CONFIGURACION"]
    assert "HANA_SDC_LISTA_PRECIOS" in correos[0][0][1]
    assert _estado()["trabajos"].count("MAESTROS SDC") == 2  # la completa y la solicitud fallida
    assert not e.hana.de("SDC", parte="precios")


def test_una_sola_empresa(entorno, correos):
    assert _main(entorno, "--completa", "--empresa", "SDC") == 0
    assert _corridas(entorno) == SEIS_CERRADAS[3:]


def test_completa_incluye_las_solicitudes_tomadas(entorno, correos):
    e = entorno
    e.servidor.encolar_solicitud({"id": 118, "empresa": "SGX", "conjunto": "MAESTROS",
                                  "parte": "clientes", "desde": {"clientes": None}})
    e.servidor.encolar_solicitud({"id": 119, "empresa": "SDC", "conjunto": "CARTERA",
                                  "parte": None, "desde": {}})
    e.servidor.encolar_solicitud({"id": 120, "empresa": "SDC", "conjunto": "VENTAS",
                                  "parte": None, "desde": {}})
    assert _main(e, "--completa") == 0
    corridas = list(e.servidor.corridas.values())
    assert [c.solicitudes for c in corridas] == [[118], [], [], [], [119], [120]]
    assert e.servidor.estado_solicitudes == {118: "terminada", 119: "terminada", 120: "terminada"}


def test_solicitudes_de_otra_empresa_quedan_tomadas(entorno, correos):
    e = entorno
    e.servidor.encolar_solicitud({"id": 7, "empresa": "SDC", "conjunto": "MAESTROS",
                                  "parte": "vendedores", "desde": {}})
    assert _main(e, "--completa", "--empresa", "SGX") == 0
    assert _corridas(e) == SEIS_CERRADAS[:3]
    assert e.hana.de("SDC") == []
    # No se extrae: queda tomada y la API la vence.
    assert e.servidor.estado_solicitudes[7] == "tomada"


def test_solicitudes_tomadas_fallan_con_la_corrida_si_falla_la_vpn(entorno, correos):
    e = entorno
    e.servidor.encolar_solicitud({"id": 21, "empresa": "SGX", "conjunto": "CARTERA",
                                  "parte": None, "desde": {}})
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    assert _main(e, "--completa", vpn=vpn) == 1
    assert e.linea.index(("vpn", "abajo")) < e.linea.index(("api", "tomar"))
    assert e.servidor.corridas[2].solicitudes == [21]
    assert e.servidor.estado_solicitudes[21] == "fallida"


def test_solicitud_invalida_se_reporta_y_la_nocturna_sigue(entorno, correos):
    e = entorno
    e.servidor.encolar_solicitud({"id": 30, "empresa": "SGX", "conjunto": "INVENTARIO",
                                  "parte": None, "desde": {}})
    e.servidor.encolar_solicitud({"id": 31, "empresa": "SGX", "conjunto": "CARTERA",
                                  "parte": None, "desde": {}})
    assert _main(e, "--completa") == 1
    assert [c[3] for c in _corridas(e)] == ["cerrada"] * 6
    assert e.servidor.corridas[2].solicitudes == [31]
    assert [etapa for etapa, _ in correos[0]] == ["SOLICITUDES"]
    assert "30" in correos[0][0][1]


def test_toma_solicitudes_por_paginas(entorno, correos):
    e = entorno
    for i in range(1, 26):
        e.servidor.encolar_solicitud({"id": i, "empresa": "SGX", "conjunto": "CARTERA",
                                      "parte": None, "desde": {}})
    assert _main(e, "--completa") == 0
    assert len(e.servidor.peticiones_a("tomar")) == 2
    assert e.servidor.corridas[2].solicitudes == list(range(1, 26))


def test_si_tomar_falla_la_nocturna_sigue(entorno, correos):
    e = entorno
    e.servidor.programar_fallas("tomar", status=500, veces=4)
    assert _main(e, "--completa") == 0
    assert [c[3] for c in _corridas(e)] == ["cerrada"] * 6


def test_falla_la_vpn(entorno, correos):
    e = entorno
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    assert _main(e, "--completa", vpn=vpn) == 1
    assert e.hana.ejecutadas == []
    # VENTAS no se abre: sin HANA no hay ventana_desde (contrato §10.1). Igual va al correo.
    assert [c[:2] for c in _corridas(e)] == [
        ("MAESTROS", "SGX"), ("CARTERA", "SGX"), ("MAESTROS", "SDC"), ("CARTERA", "SDC"),
    ]
    assert [c[3] for c in _corridas(e)] == ["fallida"] * 4
    assert all("VPN" in c.error for c in e.servidor.corridas.values())
    assert len(correos) == 1
    assert [etapa for etapa, _ in correos[0]] == ["VPN"] * 6
    assert _estado()["estado"] == "ERROR"
    revisar_fases(e.linea)


def test_falla_hana_de_una_empresa_y_la_otra_cierra(entorno, correos):
    e = entorno
    e.hana.empresas_que_fallan.add("SDC")
    assert _main(e, "--completa") == 1
    assert [c[3] for c in _corridas(e)] == ["cerrada"] * 3 + ["fallida"] * 2
    assert [etapa for etapa, _ in correos[0]] == ["HANA"] * 3
    assert [msg.split(":")[0] for _, msg in correos[0]] == ["MAESTROS SDC", "CARTERA SDC", "VENTAS SDC"]


def test_parte_vacia_falla_la_corrida_y_no_envia_nada(entorno, correos):
    e = entorno
    e.hana.datos["SGX"]["marcas"] = []
    assert _main(e, "--completa") == 1
    maestros_sgx = e.servidor.corridas[1]
    assert (maestros_sgx.estado, maestros_sgx.lotes) == ("fallida", {})
    assert "marcas" in maestros_sgx.error
    assert [c[3] for c in _corridas(e)][1:] == ["cerrada"] * 5


def test_error_de_configuracion_sale_con_2(tmp_path, correos, monkeypatch):
    monkeypatch.setenv("HANA_HOST", "hana.prueba.local")
    assert run_robot.main(["--completa"]) == 2
    estado = _estado()
    assert (estado["estado"], estado["etapa"]) == ("ERROR", "CONFIGURACION")
    assert correos == []  # sin SMTP configurado no se intenta


def test_error_de_configuracion_avisa_si_hay_alertas(tmp_path, correos, monkeypatch):
    monkeypatch.setenv("ALERTA_SMTP_HOST", "smtp.prueba.local")
    monkeypatch.setenv("ALERTA_DESTINATARIOS", "ti@prueba.local")
    assert run_robot.main(["--completa"]) == 2
    assert [etapa for etapa, _ in correos[0]] == ["CONFIGURACION"]


def test_error_inesperado_avisa_y_sale_con_1(entorno, correos):
    def explota(cfg_api):
        raise RuntimeError("algo raro")

    assert _main(entorno, "--completa", fabrica_api=explota) == 1
    assert [etapa for etapa, _ in correos[0]] == ["INESPERADO"]
    assert _estado()["estado"] == "ERROR"


def test_ctrl_c_sale_con_130(entorno, correos):
    def corta(cfg_api):
        raise KeyboardInterrupt

    assert _main(entorno, "--completa", fabrica_api=corta) == 130


def test_hace_falta_un_modo(entorno):
    with pytest.raises(SystemExit) as exc:
        run_robot.main([])
    assert exc.value.code == 2


def test_retencion_borra_corridas_viejas(entorno, correos):
    e = entorno
    vieja = e.csv_dir / "MAESTROS" / "SGX" / "clientes" / "2026-07-01_0200.csv"
    vieja_ventas = e.csv_dir / "VENTAS" / "SDC" / "2026-07-27_0200.csv"
    ventas_90_dias = e.csv_dir / "VENTAS" / "SDC" / "2026-07-28_0200.csv"
    foto = e.csv_dir / "CARTERA" / "SGX" / "historico" / "2025-07-01.csv"
    for ruta in (vieja, vieja_ventas, ventas_90_dias, foto):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text("x", encoding="utf-8")
    assert _main(e, "--completa") == 0
    assert not vieja.exists() and not vieja_ventas.exists()
    assert foto.exists() and ventas_90_dias.exists()


def test_ejecutar_trabajos_de_una_solicitud_de_clientes(escenario):
    e = escenario
    e.servidor.encolar_solicitud({"id": 118, "empresa": "SGX", "conjunto": "MAESTROS", "parte": "clientes",
                                  "desde": {"clientes": "2026-10-12T00:00:00-05:00"}})
    trabajos = trabajos_de_solicitudes(e.cliente.tomar_solicitudes(20), HOY)
    fallos = run_robot.ejecutar_trabajos(
        e.cfg, trabajos, api=e.cliente, robot_vpn=e.vpn, conectar=e.hana.conectar, ahora=e.ahora,
    )
    assert fallos == []
    revisar_fases(e.linea)
    [corrida] = e.servidor.corridas.values()
    assert corrida.partes == {"clientes": "cambios", "direcciones": "cambios", "contactos": "cambios"}
    assert [f["codigo"] for f in corrida.filas("clientes")] == ["CSGX002", "CSGX003"]
    assert sorted({f["codigo_socio"] for f in corrida.filas("direcciones")}) == ["CSGX002", "CSGX003"]
    assert len(corrida.filas("direcciones")) == 4
    assert [f["codigo_socio"] for f in corrida.filas("contactos")] == ["CSGX002", "CSGX003"]
    assert e.servidor.estado_solicitudes[118] == "terminada"
    assert (Path(e.csv_dir) / "MAESTROS" / "SGX" / "clientes" / "2026-10-26_0200.csv").is_file()


def test_sin_vpn_no_crea_la_vpn(entorno, correos):
    e = entorno
    e.hana.vpn = None

    def no_llamar(cfg_vpn):
        raise AssertionError("no debía crear la VPN")

    assert _main(e, "--completa", "--sin-vpn", fabrica_vpn=no_llamar) == 0
    assert not [ev for ev in e.linea if ev[0] == "vpn"]
    assert [c[3] for c in _corridas(e)] == ["cerrada"] * 6


def test_error_de_hana_no_lleva_el_texto_del_driver(entorno, correos):
    e = entorno
    e.hana.partes_que_fallan.add(("SGX", "marcas"))
    e.hana.texto_de_falla = "invalid value 'CSGX001' for column CardCode"
    assert _main(e, "--completa") == 1
    maestros_sgx = e.servidor.corridas[1]
    assert maestros_sgx.estado == "fallida"
    assert "SGX marcas" in maestros_sgx.error
    assert "CSGX001" not in maestros_sgx.error
    assert "CSGX001" not in json.dumps(correos)
    assert "CSGX001" not in json.dumps(_estado())


@pytest.mark.parametrize("texto, esperado", [
    ("Error ejecutando la consulta 'SGX marcas': valor 'CSGX001' inválido",
     "Error ejecutando la consulta 'SGX marcas'; revisa robot/logs/robot.log."),
    ("Consulta 'SDC precios': HANA no encuentra una tabla (invalid table name: X 'CSGX001'). Puede faltar",
     "Consulta 'SDC precios': HANA no encuentra una tabla; revisa HANA_SGX_SCHEMA / "
     "HANA_SDC_SCHEMA y robot/logs/robot.log."),
    ("No se pudo conectar a HANA (SGX) tras 3 intentos: host 'CSGX001' rechazó",
     "No se pudo conectar a HANA (SGX) tras 3 intentos; revisa robot/logs/robot.log."),
    ("La consulta 'SGX clientes' no devolvió resultados.",
     "La consulta 'SGX clientes' no devolvió resultados."),
])
def test_mensaje_seguro_de_hana_corta_el_texto_del_driver(texto, esperado):
    import extraccion
    import hana

    assert extraccion.mensaje_seguro(hana.HanaError(texto)) == esperado


# --- Archivo, catálogo y diagnóstico (T5) ------------------------------------------

SIN_API = ("BASES_SAP_API_URL", "BASES_SAP_ROBOT_KEY_ID", "BASES_SAP_ROBOT_SECRET")


def _sin_api(e, monkeypatch):
    """Sin configuración de la API y con una fábrica que falla si se usa."""
    for nombre in SIN_API:
        monkeypatch.delenv(nombre, raising=False)

    def prohibida(cfg_api):
        raise AssertionError("el archivo, el catálogo y el diagnóstico nunca llaman a la API")

    return prohibida


def test_completa_suma_los_registros_del_archivo_en_la_misma_vpn(entorno, correos):
    e = entorno
    assert _main(e, "--completa") == 0
    assert e.vpn.conexiones == 1
    revisar_fases(e.linea)
    usr5 = e.csv_dir / "AUDITORIA" / "SGX" / "USR5"
    assert sorted(p.name for p in usr5.iterdir()) == ["2026-09.csv", "2026-10.csv"]
    assert (e.csv_dir / "CONTABILIDAD" / "SDC" / "ORTT" / "2026-10.csv").is_file()
    # Solo registros: las fotos y el catálogo son del domingo.
    assert not (e.csv_dir / "USUARIOS_Y_PERMISOS").exists()
    assert not (e.csv_dir / "_CATALOGO").exists()
    archivo_csv = [ev for ev in e.linea if ev[0] == "csv" and "AUDITORIA" in str(ev[1])]
    assert e.linea.index(("vpn", "abajo")) < e.linea.index(archivo_csv[0])


def test_completa_reporta_el_archivo_sin_frenar_maestros_ni_cartera(entorno, correos):
    e = entorno
    e.hana.partes_que_fallan.add(("SGX", "archivo/AUDITORIA/USR5"))
    assert _main(e, "--completa") == 1
    assert [c[3] for c in _corridas(e)] == ["cerrada"] * 6
    assert correos == [[("ARCHIVO", "SGX AUDITORIA/USR5: Error ejecutando la consulta "
                                    "'SGX AUDITORIA/USR5'; revisa robot/logs/robot.log.")]]
    assert (e.csv_dir / "AUDITORIA" / "SDC" / "USR5" / "2026-10.csv").is_file()


def test_archivo_fotos_con_el_catalogo_en_una_vpn_y_sin_api(entorno, correos, monkeypatch):
    e = entorno
    prohibida = _sin_api(e, monkeypatch)
    assert _main(e, "--archivo", "fotos", fabrica_api=prohibida) == 0
    assert e.vpn.conexiones == 1
    revisar_fases(e.linea)
    assert e.servidor.peticiones == []
    for empresa in ("SGX", "SDC"):
        assert (e.csv_dir / "USUARIOS_Y_PERMISOS" / empresa / "OUSR" / "2026-10-26.csv").is_file()
        assert (e.csv_dir / "CONFIGURACION" / empresa / "@HBT_CONFIG" / "2026-10-26.csv").is_file()
        assert (e.csv_dir / "_CATALOGO" / empresa / "columnas" / "2026-10-26.csv").is_file()
    assert not (e.csv_dir / "AUDITORIA").exists()
    estado = _estado()
    assert (estado["estado"], estado["modo"]) == ("OK", "archivo fotos")
    assert correos == []


@pytest.mark.parametrize("argumentos, esperado", [
    (("--archivo", "registros"), "AUDITORIA/SGX/USR5/2026-10.csv"),
    (("--catalogo",), "_CATALOGO/SDC/tablas/2026-10-26.csv"),
    (("--diagnostico",), "_DIAGNOSTICO/resumen/2026-10-26_0200.csv"),
])
def test_modos_de_carpeta_nunca_llaman_a_la_api(entorno, correos, monkeypatch, argumentos, esperado):
    e = entorno
    prohibida = _sin_api(e, monkeypatch)
    assert _main(e, *argumentos, fabrica_api=prohibida) == 0
    assert (e.csv_dir / esperado).is_file()
    assert e.servidor.peticiones == []
    assert not [ev for ev in e.linea if ev[0] == "api"]
    assert e.vpn.conexiones == 1
    revisar_fases(e.linea)


def test_modulos_de_carpeta_no_importan_la_api():
    import archivo
    import catalogo
    import diagnostico

    for modulo in (archivo, catalogo, diagnostico):
        fuente = Path(modulo.__file__).read_text(encoding="utf-8")
        assert "import api" not in fuente and "from api " not in fuente, modulo.__name__
        assert "ApiCliente" not in vars(modulo)


def test_diagnostico_con_errores_sale_con_1_sin_correo(entorno, correos, monkeypatch):
    e = entorno
    prohibida = _sin_api(e, monkeypatch)
    e.hana.partes_que_fallan.add(("SDC", "precios"))
    assert _main(e, "--diagnostico", fabrica_api=prohibida) == 1
    assert correos == []
    estado = _estado()
    assert estado["modo"] == "diagnostico"
    assert [etapa for etapa, _ in estado["fallos"]] == ["DIAGNOSTICO"]


def test_archivo_si_falla_la_vpn_avisa_y_no_escribe(entorno, correos, monkeypatch):
    e = entorno
    prohibida = _sin_api(e, monkeypatch)
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    assert _main(e, "--archivo", "fotos", vpn=vpn, fabrica_api=prohibida) == 1
    assert [etapa for etapa, _ in correos[0]] == ["VPN"]
    assert not any(Path(e.csv_dir).rglob("*.csv"))
    revisar_fases(e.linea)


def test_archivo_falla_hana_de_una_empresa_y_la_otra_sigue(entorno, correos, monkeypatch):
    e = entorno
    prohibida = _sin_api(e, monkeypatch)
    e.hana.empresas_que_fallan.add("SGX")
    assert _main(e, "--archivo", "registros", fabrica_api=prohibida) == 1
    assert [(etapa, msg.split(":")[0]) for etapa, msg in correos[0]] == [("HANA", "SGX")]
    assert (e.csv_dir / "AUDITORIA" / "SDC" / "USR5" / "2026-10.csv").is_file()


def test_los_modos_se_excluyen(entorno):
    with pytest.raises(SystemExit):
        run_robot.main(["--completa", "--catalogo"])
    with pytest.raises(SystemExit):
        run_robot.main(["--archivo", "todo"])


# --- Candado y franjas bloqueadas (T6) ----------------------------------------------

CANDADO = "robot.lock"


def test_completa_espera_el_candado_y_corre(entorno, correos, candado_ajeno):
    e = entorno
    ruta = candado_ajeno()  # una revisión de solicitudes que está terminando
    esperas: list[float] = []

    def dormir(segundos):
        esperas.append(segundos)
        if len(esperas) == 2:
            ruta.unlink()

    assert _main(e, "--completa", dormir=dormir) == 0
    assert esperas == [10, 10]
    assert [c[3] for c in _corridas(e)] == ["cerrada"] * 6
    assert not (config.STATE_DIR / CANDADO).exists()


def test_completa_sin_candado_en_20_minutos_avisa(entorno, correos, candado_ajeno):
    e = entorno
    ruta = candado_ajeno()
    esperas: list[float] = []
    assert _main(e, "--completa", dormir=esperas.append) == 1
    assert sum(esperas) == 20 * 60
    assert e.vpn.conexiones == 0
    assert e.servidor.peticiones == []
    assert [etapa for etapa, _ in correos[0]] == ["CANDADO"]
    assert ruta.exists()
    assert (_estado()["estado"], _estado()["etapa"]) == ("ERROR", "CANDADO")


@pytest.mark.parametrize("argumentos", [("--completa",), ("--archivo", "fotos")])
def test_dentro_de_una_franja_espera_a_que_pase(entorno, correos, argumentos):
    # El PC prendió tarde (StartWhenAvailable): la tarea arranca a las 11:50, dentro
    # de las franjas de las 12:00 y las 12:30, y corre a las 12:46, cuando ya pasaron.
    e = entorno
    a_las_1150 = lambda: datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA)  # noqa: E731
    esperas: list[float] = []

    def dormir(segundos):
        assert e.vpn.conexiones == 0  # la espera es antes de subir la VPN
        esperas.append(segundos)

    assert _main(e, *argumentos, ahora=a_las_1150, dormir=dormir) == 0
    assert esperas == [56 * 60]
    assert e.vpn.conexiones == 1
    assert correos == []


def test_forzar_corre_dentro_de_la_franja_sin_esperar(entorno, correos):
    e = entorno
    a_las_1150 = lambda: datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA)  # noqa: E731

    def no_esperar(segundos):
        raise AssertionError("con --forzar no se espera la franja")

    assert _main(e, "--completa", "--forzar", ahora=a_las_1150, dormir=no_esperar) == 0
    assert e.vpn.conexiones == 1


@pytest.mark.parametrize("modo", ["--diagnostico", "--catalogo"])
def test_diagnostico_con_el_candado_ocupado_sale_sin_vpn(entorno, correos, monkeypatch, candado_ajeno, modo, caplog):
    e = entorno
    prohibida = _sin_api(e, monkeypatch)
    candado_ajeno()

    def no_llamar(*args):
        raise AssertionError("no debía usar la VPN ni esperar")

    with caplog.at_level(logging.WARNING, logger="bases_sap"):
        assert _main(e, modo, fabrica_api=prohibida, fabrica_vpn=no_llamar, dormir=no_llamar) == 1
    assert "unos minutos" in caplog.text
    assert e.linea == []
    assert correos == []
