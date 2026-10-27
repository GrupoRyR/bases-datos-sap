from __future__ import annotations

from datetime import date

import pytest

import esquema
from trabajos import Trabajo, TrabajoInvalido, trabajos_completos, trabajos_de_solicitudes

HOY = date(2026, 10, 26)


def _sol(id_: int, empresa: str = "SGX", conjunto: str = "MAESTROS", parte=None, desde=None) -> dict:
    return {
        "id": id_, "empresa": empresa, "conjunto": conjunto, "parte": parte,
        "desde": desde if desde is not None else {}, "solicitada_en": "2026-10-26T10:40:12-05:00",
    }


def test_solicitud_de_clientes():
    [t] = trabajos_de_solicitudes(
        [_sol(118, parte="clientes", desde={"clientes": "2026-10-23T09:58:00-05:00"})], HOY
    )
    assert t == Trabajo(
        empresa="SGX", conjunto="MAESTROS", tipo="solicitud",
        partes={"clientes": "cambios", "direcciones": "cambios", "contactos": "cambios"},
        desde={"clientes": "2026-10-23T09:58:00-05:00"},
        solicitudes=[118], fecha_corte=None,
    )
    assert list(t.partes) == ["clientes", "direcciones", "contactos"]


def test_solicitud_de_cartera_lleva_fecha_de_hoy():
    [t] = trabajos_de_solicitudes([_sol(5, empresa="SDC", conjunto="CARTERA")], HOY)
    assert t.partes == {"cartera": "todo"}
    assert t.fecha_corte == "2026-10-26"
    assert t.desde == {}
    assert t.tipo == "solicitud"


def test_solicitud_de_todo_maestros_usa_el_modo_de_cada_parte():
    [t] = trabajos_de_solicitudes([_sol(7, parte=None, desde={
        "clientes": None, "proveedores": "2026-10-01T00:00:00-05:00", "articulos": None,
    })], HOY)
    assert list(t.partes) == list(esquema.PARTES_POR_CONJUNTO["MAESTROS"])
    assert t.partes["clientes"] == "cambios"
    assert t.partes["direcciones"] == "cambios"
    assert t.partes["contactos"] == "cambios"
    assert t.partes["articulos"] == "cambios"
    assert t.partes["precios"] == "todo"
    assert t.partes["municipios"] == "todo"
    assert t.desde == {
        "clientes": None, "proveedores": "2026-10-01T00:00:00-05:00", "articulos": None,
    }


def test_agrupa_por_empresa_y_conjunto_con_la_union_de_partes():
    trabajos = trabajos_de_solicitudes([
        _sol(1, parte="clientes", desde={"clientes": "2026-10-23T09:58:00-05:00"}),
        _sol(2, parte="articulos", desde={"articulos": "2026-10-20T08:00:00-05:00"}),
        _sol(3, empresa="SDC", parte="precios"),
        _sol(4, parte="proveedores", desde={"proveedores": "2026-10-22T08:00:00-05:00"}),
        _sol(5, conjunto="CARTERA"),
    ], HOY)
    assert [(t.empresa, t.conjunto, t.solicitudes) for t in trabajos] == [
        ("SGX", "MAESTROS", [1, 2, 4]),
        ("SDC", "MAESTROS", [3]),
        ("SGX", "CARTERA", [5]),
    ]
    sgx = trabajos[0]
    # Socios primero, luego direcciones y contactos, luego el resto.
    assert list(sgx.partes) == [
        "clientes", "proveedores", "direcciones", "contactos",
        "articulos", "grupos_articulos", "marcas",
    ]
    assert sgx.partes["marcas"] == "todo"
    assert sgx.desde == {
        "clientes": "2026-10-23T09:58:00-05:00",
        "proveedores": "2026-10-22T08:00:00-05:00",
        "articulos": "2026-10-20T08:00:00-05:00",
    }


def test_gana_el_desde_mas_viejo_comparando_la_zona():
    [t] = trabajos_de_solicitudes([
        _sol(1, parte="clientes", desde={"clientes": "2026-10-23T09:58:00-05:00"}),
        # 14:00 UTC son las 09:00 de Bogotá: es más viejo aunque el texto sea mayor.
        _sol(2, parte="clientes", desde={"clientes": "2026-10-23T14:00:00+00:00"}),
    ], HOY)
    assert t.desde == {"clientes": "2026-10-23T14:00:00+00:00"}
    assert t.solicitudes == [1, 2]


def test_un_desde_nulo_o_ausente_trae_todo():
    [t] = trabajos_de_solicitudes([
        _sol(1, parte="clientes", desde={"clientes": "2026-10-23T09:58:00-05:00"}),
        _sol(2, parte="clientes", desde={"clientes": None}),
    ], HOY)
    assert t.desde == {"clientes": None}
    [t] = trabajos_de_solicitudes([
        _sol(1, parte="clientes", desde={"clientes": "2026-10-23T09:58:00-05:00"}),
        _sol(2, parte="clientes", desde={}),
    ], HOY)
    assert t.desde == {"clientes": None}


def test_el_desde_solo_cuenta_solicitudes_que_traen_esa_parte():
    [t] = trabajos_de_solicitudes([
        _sol(1, parte="clientes", desde={"clientes": "2026-10-23T09:58:00-05:00"}),
        _sol(2, parte="vendedores"),
    ], HOY)
    assert t.desde == {"clientes": "2026-10-23T09:58:00-05:00"}


@pytest.mark.parametrize("solicitud", [
    _sol(1, conjunto="ARCHIVO"),
    _sol(1, parte="usuarios"),
    _sol(1, conjunto="CARTERA", parte="cartera"),
    _sol(1, empresa="XYZ"),
    _sol(1, parte="clientes", desde={"clientes": "ayer"}),
])
def test_solicitud_desconocida_da_un_error_claro(solicitud):
    with pytest.raises(TrabajoInvalido, match="Solicitud 1"):
        trabajos_de_solicitudes([solicitud], HOY)


def test_completa_de_las_dos_empresas():
    trabajos = trabajos_completos(["SGX", "SDC"], HOY, [])
    assert [(t.empresa, t.conjunto, t.tipo) for t in trabajos] == [
        ("SGX", "MAESTROS", "completa"), ("SGX", "CARTERA", "completa"),
        ("SDC", "MAESTROS", "completa"), ("SDC", "CARTERA", "completa"),
    ]
    maestros = trabajos[0]
    assert list(maestros.partes) == list(esquema.PARTES_POR_CONJUNTO["MAESTROS"])
    assert set(maestros.partes.values()) == {"todo"}
    assert maestros.fecha_corte is None
    assert maestros.solicitudes == []
    assert trabajos[1].partes == {"cartera": "todo"}
    assert trabajos[1].fecha_corte == "2026-10-25"


SIN_PRECIOS = frozenset({"SDC"})


def test_completa_de_la_empresa_sin_lista_de_precios_no_lleva_precios():
    sgx_m, _, sdc_m, sdc_c = trabajos_completos(["SGX", "SDC"], HOY, [], SIN_PRECIOS)
    assert "precios" in sgx_m.partes
    assert "precios" not in sdc_m.partes
    assert list(sdc_m.partes) == [p for p in esquema.PARTES_POR_CONJUNTO["MAESTROS"] if p != "precios"]
    assert set(sdc_m.partes.values()) == {"todo"}
    assert sdc_c.partes == {"cartera": "todo"}


def test_solicitud_de_todo_maestros_de_la_empresa_sin_precios_no_los_pide():
    [sdc, sgx] = trabajos_de_solicitudes([_sol(1, empresa="SDC", parte=None), _sol(2, parte=None)], HOY, SIN_PRECIOS)
    assert "precios" not in sdc.partes and "clientes" in sdc.partes
    assert "precios" in sgx.partes


def test_solicitud_de_solo_precios_de_la_empresa_sin_ellos_los_conserva_para_fallar_con_mensaje():
    [t] = trabajos_de_solicitudes([_sol(1, empresa="SDC", parte="precios")], HOY, SIN_PRECIOS)
    assert t.partes == {"precios": "todo"}


def test_solicitud_de_solo_precios_no_arrastra_a_la_de_todo_maestros_de_su_empresa():
    maestros, precios = trabajos_de_solicitudes(
        [_sol(1, empresa="SDC", parte="precios"), _sol(2, empresa="SDC", parte=None)], HOY, SIN_PRECIOS
    )
    assert (maestros.solicitudes, "precios" in maestros.partes) == ([2], False)
    assert (precios.solicitudes, precios.partes) == ([1], {"precios": "todo"})


def test_solicitudes_de_solo_precios_de_la_misma_empresa_comparten_su_trabajo():
    [t] = trabajos_de_solicitudes(
        [_sol(1, empresa="SDC", parte="precios"), _sol(2, empresa="SDC", parte="precios")], HOY, SIN_PRECIOS
    )
    assert t.solicitudes == [1, 2]


def test_solicitud_de_solo_precios_de_empresa_con_lista_sigue_en_su_grupo():
    [t] = trabajos_de_solicitudes(
        [_sol(1, parte="precios"), _sol(2, parte=None)], HOY, SIN_PRECIOS
    )
    assert t.solicitudes == [1, 2] and "precios" in t.partes


def test_completa_adjunta_las_solicitudes_tomadas():
    trabajos = trabajos_completos(["SGX", "SDC"], HOY, [
        _sol(10, parte="clientes", desde={"clientes": None}),
        _sol(11, empresa="SDC", conjunto="CARTERA"),
        _sol(12, parte="precios"),
    ])
    assert [(t.empresa, t.conjunto, t.tipo, t.solicitudes) for t in trabajos] == [
        ("SGX", "MAESTROS", "completa", [10, 12]),
        ("SGX", "CARTERA", "completa", []),
        ("SDC", "MAESTROS", "completa", []),
        ("SDC", "CARTERA", "completa", [11]),
    ]
    assert set(trabajos[0].partes.values()) == {"todo"}


def test_completa_de_una_empresa_deja_las_solicitudes_de_la_otra_como_trabajos():
    trabajos = trabajos_completos(["SGX"], HOY, [
        _sol(20, empresa="SDC", parte="clientes", desde={"clientes": "2026-10-23T09:58:00-05:00"}),
        _sol(21, conjunto="CARTERA"),
    ])
    assert [(t.empresa, t.conjunto, t.tipo, t.solicitudes) for t in trabajos] == [
        ("SGX", "MAESTROS", "completa", []),
        ("SGX", "CARTERA", "completa", [21]),
        ("SDC", "MAESTROS", "solicitud", [20]),
    ]
    assert trabajos[2].partes["clientes"] == "cambios"
