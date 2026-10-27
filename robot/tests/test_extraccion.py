from __future__ import annotations

import logging
from dataclasses import replace
from datetime import date, datetime

import pytest

import esquema
import extraccion
from fake_hana import VpnFalsa, datos_empresa, fila, revisar_fases
from trabajos import Trabajo, trabajos_completos, trabajos_de_solicitudes

HOY = date(2026, 10, 26)


def _extraer(e, trabajos, **kwargs):
    kwargs.setdefault("robot_vpn", e.vpn)
    kwargs.setdefault("conectar", e.hana.conectar)
    kwargs.setdefault("ahora", e.ahora)
    return extraccion.extraer(e.cfg, trabajos, **kwargs)


def _solicitud_clientes(desde):
    return trabajos_de_solicitudes([{
        "id": 118, "empresa": "SGX", "conjunto": "MAESTROS", "parte": "clientes",
        "desde": {"clientes": desde},
    }], HOY)


def _columna(resultado, parte, nombre):
    posicion = resultado.columnas[parte].index(nombre)
    return [f[posicion] for f in resultado.filas[parte]]


def test_completa_de_las_dos_empresas(escenario):
    e = escenario
    resultados = _extraer(e, trabajos_completos(["SGX", "SDC"], HOY, []))

    assert [r.error for r in resultados] == [None] * 4
    assert e.vpn.conexiones == 1  # una sola sesión de VPN
    assert [ev for ev in e.linea if ev[:2] == ("hana", "conectar")] == [
        ("hana", "conectar", "SGX"), ("hana", "conectar", "SDC"),
    ]
    revisar_fases(e.linea)

    sgx_maestros, sgx_cartera = resultados[0], resultados[1]
    for parte in esquema.PARTES_POR_CONJUNTO["MAESTROS"]:
        # Precios: solo la lista 1 (2 de las 3 filas de prueba).
        esperadas = 2 if parte == "precios" else len(e.hana.datos["SGX"][parte])
        assert sgx_maestros.columnas[parte] == esquema.PARTES[parte].nombres
        assert len(sgx_maestros.filas[parte]) == esperadas
        assert sgx_maestros.conteo_sap[parte] == esperadas
    assert sgx_cartera.conteo_sap == {"cartera": 3}
    assert sgx_cartera.columnas["cartera"][0] == "codigo_sn"
    # Solo consultas sin filtro y conteos, y cada conteo justo después de su parte.
    tipos = [(x.tipo, x.parte) for x in e.hana.de("SGX")]
    assert {t for t, _ in tipos} == {"todo", "contar"}
    assert tipos[:4] == [("todo", "clientes"), ("contar", "clientes"),
                         ("todo", "proveedores"), ("contar", "proveedores")]
    assert sgx_maestros.extraida_en == "2026-10-26T02:00:05-05:00"


def test_valores_quedan_serializados(escenario):
    [r] = _extraer(escenario, trabajos_completos(["SGX"], HOY, [])[:1])
    cliente = dict(zip(r.columnas["clientes"], r.filas["clientes"][0]))
    assert cliente["codigo"] == "CSGX001"
    assert cliente["activo"] is True
    assert cliente["limite_credito"] == "1500000.51"
    assert cliente["actualizado_en_sap"] == "2026-10-11T09:00:00-05:00"
    assert cliente["creado_en_sap"] == "2026-10-01"


def test_solicitud_de_clientes_con_desde_trae_solo_los_cambiados(escenario):
    e = escenario
    [r] = _extraer(e, _solicitud_clientes("2026-10-12T00:00:00-05:00"))

    assert r.error is None
    assert r.conteo_sap is None
    assert _columna(r, "clientes", "codigo") == ["CSGX002", "CSGX003"]
    [cambios] = e.hana.de("SGX", "cambios", "clientes")
    assert cambios.params == (datetime(2026, 10, 12, 0, 0),)
    # Todas las direcciones y contactos de esos clientes, y de ningún otro socio.
    assert _columna(r, "direcciones", "codigo_socio") == ["CSGX002", "CSGX002", "CSGX003", "CSGX003"]
    assert _columna(r, "direcciones", "tipo") == ["B", "S", "B", "S"]
    assert _columna(r, "contactos", "codigo_socio") == ["CSGX002", "CSGX003"]
    for parte in ("direcciones", "contactos"):
        [x] = e.hana.de("SGX", "socios", parte)
        assert x.params == ("CSGX002", "CSGX003")
    assert not e.hana.de("SGX", "contar")
    assert not e.hana.de("SGX", "todo")


def test_desde_nulo_trae_todos_los_clientes(escenario):
    e = escenario
    [r] = _extraer(e, _solicitud_clientes(None))
    assert _columna(r, "clientes", "codigo") == ["CSGX001", "CSGX002", "CSGX003"]
    assert [x.tipo for x in e.hana.de("SGX", parte="clientes")] == ["todo"]
    [x] = e.hana.de("SGX", "socios", "direcciones")
    assert x.params == ("CSGX001", "CSGX002", "CSGX003")
    assert len(r.filas["direcciones"]) == 6


def test_cambios_sin_filas_no_consulta_hijas_y_no_falla(escenario):
    e = escenario
    [r] = _extraer(e, _solicitud_clientes("2026-12-01T00:00:00-05:00"))
    assert r.error is None
    assert r.filas == {"clientes": [], "direcciones": [], "contactos": []}
    assert r.columnas["direcciones"] == esquema.PARTES["direcciones"].nombres
    assert [x.parte for x in e.hana.de("SGX")] == ["clientes"]


def test_hijas_en_trozos_de_500(escenario):
    e = escenario
    e.hana.datos["SGX"] = datos_empresa("SGX", clientes=1200, proveedores=0)
    [r] = _extraer(e, _solicitud_clientes(None))
    assert r.error is None
    trozos = [len(x.params) for x in e.hana.de("SGX", "socios", "direcciones")]
    assert trozos == [500, 500, 200]
    assert len(r.filas["direcciones"]) == 2400
    assert len(r.filas["contactos"]) == 1200


def test_completa_trae_las_hijas_sin_filtro_y_filtra_en_python(escenario):
    e = escenario
    # Una dirección de un socio que no está en clientes ni proveedores.
    e.hana.datos["SGX"]["direcciones"].append(
        fila("direcciones", 99, codigo_socio="LSGX999", tipo="B", nombre="Lead")
    )
    [r] = _extraer(e, trabajos_completos(["SGX"], HOY, [])[:1])
    assert r.error is None
    assert "LSGX999" not in _columna(r, "direcciones", "codigo_socio")
    assert not e.hana.de("SGX", "socios")


def test_falla_la_vpn(escenario):
    e = escenario
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    resultados = _extraer(e, trabajos_completos(["SGX", "SDC"], HOY, []), robot_vpn=vpn)
    assert [r.etapa for r in resultados] == ["VPN"] * 4
    assert all("VPN" in r.error for r in resultados)
    assert e.hana.ejecutadas == []
    assert e.linea[-1] == ("vpn", "abajo")


def test_falla_la_conexion_de_una_empresa(escenario):
    e = escenario
    e.hana.empresas_que_fallan.add("SGX")
    resultados = _extraer(e, trabajos_completos(["SGX", "SDC"], HOY, []))
    assert [(r.trabajo.nombre, r.etapa) for r in resultados] == [
        ("MAESTROS SGX", "HANA"), ("CARTERA SGX", "HANA"),
        ("MAESTROS SDC", None), ("CARTERA SDC", None),
    ]
    assert "SGX" in resultados[0].error
    revisar_fases(e.linea)


def test_falla_una_consulta_solo_falla_su_trabajo(escenario):
    e = escenario
    e.hana.partes_que_fallan.add(("SGX", "marcas"))
    resultados = _extraer(e, trabajos_completos(["SGX"], HOY, []))
    assert resultados[0].etapa == "HANA"
    assert "marcas" in resultados[0].error
    assert resultados[0].filas == {}
    assert resultados[1].error is None


def test_parte_todo_vacia_falla_el_trabajo(escenario):
    e = escenario
    e.hana.datos["SDC"]["vendedores"] = []
    [r] = _extraer(e, [trabajos_completos(["SDC"], HOY, [])[0]])
    assert r.etapa == "VALIDACION"
    assert "vendedores" in r.error and "0 filas" in r.error


def test_proveedor_sin_nombre_no_frena_la_corrida(escenario, caplog):
    e = escenario
    e.hana.datos["SDC"]["proveedores"][0]["nombre"] = None
    with caplog.at_level(logging.WARNING, logger="bases_sap.esquema"):
        [r] = _extraer(e, [trabajos_completos(["SDC"], HOY, [])[0]])

    assert r.error is None
    codigos, nombres = _columna(r, "proveedores", "codigo"), _columna(r, "proveedores", "nombre")
    assert nombres[0] == codigos[0] == "PSDC001"
    assert nombres[1] == "Socio P2"
    avisos = [x.getMessage() for x in caplog.records if x.levelno == logging.WARNING]
    assert len(avisos) == 1 and "PSDC001 llegó sin nombre" in avisos[0]
    assert r.conteo_sap["proveedores"] == 2


def test_llave_repetida_falla_sin_mostrar_el_valor(escenario):
    e = escenario
    e.hana.datos["SGX"]["marcas"] = [fila("marcas", 7), fila("marcas", 7)]
    [r] = _extraer(e, [trabajos_completos(["SGX"], HOY, [])[0]])
    assert r.etapa == "VALIDACION"
    assert "marcas" in r.error and "llaves repetidas" in r.error
    assert "7" not in r.error


def test_valor_invalido_falla_sin_mostrar_el_valor(escenario):
    e = escenario
    e.hana.datos["SGX"]["clientes"][1]["grupo_codigo"] = "SECRETO-SAP"
    [r] = _extraer(e, [trabajos_completos(["SGX"], HOY, [])[0]])
    assert r.etapa == "VALIDACION"
    assert "clientes" in r.error and "fila 2" in r.error and "grupo_codigo" in r.error
    assert "SECRETO-SAP" not in r.error


def test_precios_trae_solo_la_lista_configurada_de_la_empresa(escenario):
    e = escenario
    e.cfg.hana.empresas["SDC"] = replace(e.cfg.hana.empresas["SDC"], lista_precios=2)
    resultados = _extraer(e, [trabajos_completos(["SGX", "SDC"], HOY, [])[i] for i in (0, 2)])

    assert [r.error for r in resultados] == [None, None]
    sgx, sdc = resultados
    assert _columna(sgx, "precios", "lista_codigo") == [1, 1]
    assert _columna(sdc, "precios", "lista_codigo") == [2]
    assert (sgx.conteo_sap["precios"], sdc.conteo_sap["precios"]) == (2, 1)
    # Se filtra por número, no por el nombre de la lista.
    [consulta] = e.hana.de("SDC", "todo", "precios")
    assert 'X."lista_codigo" = 2' in consulta.sql
    assert "ListName\" =" not in consulta.sql


def test_empresa_sin_lista_de_precios_falla_su_trabajo_con_un_mensaje_claro(escenario):
    e = escenario
    e.cfg.hana.empresas["SDC"] = replace(e.cfg.hana.empresas["SDC"], lista_precios=None)
    resultados = _extraer(e, trabajos_completos(["SDC"], HOY, []))

    maestros, cartera = resultados
    assert maestros.etapa == "CONFIGURACION"
    assert "HANA_SDC_LISTA_PRECIOS" in maestros.error
    assert cartera.error is None  # la cartera de la empresa no depende de los precios
    assert not e.hana.de("SDC", parte="precios")


def test_columna_faltante_falla_el_trabajo(escenario):
    e = escenario
    e.hana.columnas_que_faltan[("SGX", "precios")] = {"lista_nombre"}
    [r] = _extraer(e, [trabajos_completos(["SGX"], HOY, [])[0]])
    assert r.etapa == "VALIDACION"
    assert "lista_nombre" in r.error


def test_sin_vpn_no_toca_la_vpn(escenario):
    e = escenario
    e.hana.vpn = None
    resultados = _extraer(e, trabajos_completos(["SGX"], HOY, []), sin_vpn=True)
    assert [r.error for r in resultados] == [None, None]
    assert e.vpn.conexiones == 0
    assert not [ev for ev in e.linea if ev[0] == "vpn"]


def test_sin_trabajos_no_sube_la_vpn(escenario):
    assert _extraer(escenario, []) == []
    assert escenario.vpn.conexiones == 0


def test_gancho_extra_por_empresa_no_afecta_los_trabajos(escenario):
    e = escenario
    llamadas = []

    def extra(conn, empresa):
        llamadas.append((conn.empresa, empresa))
        if empresa == "SGX":
            raise RuntimeError("el archivo falló")

    resultados = _extraer(e, trabajos_completos(["SGX", "SDC"], HOY, []), extra=extra)
    assert llamadas == [("SGX", "SGX"), ("SDC", "SDC")]
    assert [r.error for r in resultados] == [None] * 4


def test_trabajo_sin_socios_no_trae_hijas(escenario):
    e = escenario
    trabajo = Trabajo("SGX", "MAESTROS", "solicitud", {"direcciones": "cambios"})
    [r] = _extraer(e, [trabajo])
    assert r.error is None
    assert r.filas == {"direcciones": []}
    assert e.hana.ejecutadas == []


@pytest.mark.parametrize("parte", ["direcciones", "contactos"])
def test_hija_todo_vacia_en_completa_falla(escenario, parte):
    e = escenario
    e.hana.datos["SGX"][parte] = []
    [r] = _extraer(e, [trabajos_completos(["SGX"], HOY, [])[0]])
    assert r.etapa == "VALIDACION"
    assert parte in r.error
