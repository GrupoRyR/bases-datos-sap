from __future__ import annotations

from datetime import date
from pathlib import Path

import envio
import esquema
import extraccion
from extraccion import Resultado
from fake_hana import datos_empresa, revisar_fases
from trabajos import Trabajo, trabajos_completos, trabajos_de_solicitudes

HOY = date(2026, 10, 26)


def _resultados(e, trabajos):
    return extraccion.extraer(e.cfg, trabajos, robot_vpn=e.vpn, conectar=e.hana.conectar, ahora=e.ahora)


def _enviar(e, resultados):
    return envio.enviar(e.cliente, e.carpeta, resultados, momento=e.ahora(), ahora=e.ahora)


def _leer_csv(ruta: Path) -> list[list[str]]:
    return [linea.split(";") for linea in ruta.read_text(encoding="utf-8-sig").splitlines()]


def test_completa_cierra_las_cuatro_corridas(escenario):
    e = escenario
    resultados = _resultados(e, trabajos_completos(["SGX", "SDC"], HOY, []))
    assert _enviar(e, resultados) == []
    revisar_fases(e.linea)

    corridas = list(e.servidor.corridas.values())
    assert [(c.conjunto, c.empresa, c.tipo, c.estado) for c in corridas] == [
        ("MAESTROS", "SGX", "completa", "cerrada"), ("CARTERA", "SGX", "completa", "cerrada"),
        ("MAESTROS", "SDC", "completa", "cerrada"), ("CARTERA", "SDC", "completa", "cerrada"),
    ]
    maestros = corridas[0]
    assert list(maestros.partes) == list(esquema.PARTES_POR_CONJUNTO["MAESTROS"])
    assert set(maestros.partes.values()) == {"todo"}
    assert maestros.fecha_corte is None
    assert maestros.extraida_en == "2026-10-26T02:00:05-05:00"
    assert maestros.conteo_sap == {p: len(e.hana.datos["SGX"][p]) for p in maestros.partes}
    assert maestros.total_filas() == maestros.conteo_sap
    cartera = corridas[1]
    assert cartera.fecha_corte == "2026-10-25"
    assert cartera.conteo_sap == {"cartera": 3}
    # Lotes numerados desde 1 por corrida, una parte cada uno, en el orden de las partes.
    assert sorted(maestros.lotes) == list(range(1, len(maestros.partes) + 1))
    assert [maestros.lotes[n].parte for n in sorted(maestros.lotes)] == list(maestros.partes)
    assert sorted(cartera.lotes) == [1]


def test_completa_escribe_los_csv_y_la_foto_de_cartera(escenario):
    e = escenario
    _enviar(e, _resultados(e, trabajos_completos(["SGX"], HOY, [])))
    raiz = e.csv_dir
    clientes = raiz / "MAESTROS" / "SGX" / "clientes" / "2026-10-26_0200.csv"
    filas = _leer_csv(clientes)
    assert filas[0] == esquema.PARTES["clientes"].nombres
    assert len(filas) == 4
    primera = dict(zip(filas[0], filas[1]))
    assert primera["codigo"] == "CSGX001"
    assert primera["activo"] == "true"
    assert primera["limite_credito"] == "1500000.51"
    assert primera["actualizado_en_sap"] == "2026-10-11T09:00:00-05:00"
    for parte in esquema.PARTES_POR_CONJUNTO["MAESTROS"]:
        assert (raiz / "MAESTROS" / "SGX" / parte / "2026-10-26_0200.csv").is_file()
    corrida = raiz / "CARTERA" / "SGX" / "cartera" / "2026-10-26_0200.csv"
    historico = raiz / "CARTERA" / "SGX" / "historico" / "2026-10-25.csv"
    assert _leer_csv(corrida)[0][0] == "codigo_sn"
    assert historico.read_bytes() == corrida.read_bytes()


def test_solicitud_no_escribe_foto_ni_conteo(escenario):
    e = escenario
    e.servidor.encolar_solicitud({"id": 5, "empresa": "SDC", "conjunto": "CARTERA", "parte": None, "desde": {}})
    tomadas = e.cliente.tomar_solicitudes(20)
    assert _enviar(e, _resultados(e, trabajos_de_solicitudes(tomadas, HOY))) == []
    [corrida] = e.servidor.corridas.values()
    assert (corrida.tipo, corrida.fecha_corte, corrida.conteo_sap) == ("solicitud", "2026-10-26", None)
    assert e.servidor.estado_solicitudes[5] == "terminada"
    assert not (e.csv_dir / "CARTERA" / "SDC" / "historico").exists()
    assert "conteo_sap" not in e.servidor.peticiones_a("cerrar")[0].datos


def test_mas_de_mil_filas_van_en_varios_lotes(escenario):
    e = escenario
    e.hana.datos["SGX"] = datos_empresa("SGX", clientes=2300, proveedores=1)
    trabajo = Trabajo("SGX", "MAESTROS", "solicitud", {
        "clientes": "cambios", "direcciones": "cambios", "contactos": "cambios",
    }, desde={"clientes": None})
    assert _enviar(e, _resultados(e, [trabajo])) == []
    [corrida] = e.servidor.corridas.values()
    tamanos = [(corrida.lotes[n].parte, len(corrida.lotes[n].rows)) for n in sorted(corrida.lotes)]
    assert tamanos == [
        ("clientes", 1000), ("clientes", 1000), ("clientes", 300),
        ("direcciones", 1000), ("direcciones", 1000), ("direcciones", 1000),
        ("direcciones", 1000), ("direcciones", 600),
        ("contactos", 1000), ("contactos", 1000), ("contactos", 300),
    ]
    assert corrida.estado == "cerrada"
    assert e.servidor.peticiones_a("cerrar")[0].datos["batches"] == 11


def test_cambios_sin_filas_cierra_con_cero(escenario):
    e = escenario
    trabajo = Trabajo("SGX", "MAESTROS", "solicitud", {
        "clientes": "cambios", "direcciones": "cambios", "contactos": "cambios",
    }, desde={"clientes": "2027-01-01T00:00:00-05:00"})
    assert _enviar(e, _resultados(e, [trabajo])) == []
    cierre = e.servidor.peticiones_a("cerrar")[0].datos
    assert cierre == {"batches": 0, "filas": {"clientes": 0, "direcciones": 0, "contactos": 0}}
    assert e.servidor.peticiones_a("lote") == []


def test_lotes_faltantes_se_reenvian_y_se_cierra(escenario):
    e = escenario
    e.servidor.programar_fallas("cerrar", status=409, datos={"message": "Faltan lotes.", "faltan": [2, 3]})
    [r] = _resultados(e, [trabajos_completos(["SGX"], HOY, [])[0]])
    assert _enviar(e, [r]) == []
    lotes = e.servidor.peticiones_a("lote")
    assert len(lotes) == 12 + 2
    reenviados = lotes[-2:]
    assert [p.datos["batch"] for p in reenviados] == [2, 3]
    assert [p.status for p in reenviados] == [200, 200]  # mismo cuerpo: duplicado
    assert reenviados[0].cuerpo == lotes[1].cuerpo
    assert len(e.servidor.peticiones_a("cerrar")) == 2
    assert e.servidor.corridas[1].estado == "cerrada"


def test_filas_que_no_cuadran_fallan_la_corrida(escenario):
    e = escenario
    e.servidor.programar_fallas("cerrar", status=409, datos={"message": "No cuadra.", "faltan": []})
    [r] = _resultados(e, [trabajos_completos(["SGX"], HOY, [])[1]])
    fallos = _enviar(e, [r])
    assert len(fallos) == 1
    etapa, mensaje = fallos[0]
    assert etapa == "API"
    assert mensaje.startswith("CARTERA SGX: ")
    corrida = e.servidor.corridas[1]
    assert corrida.estado == "fallida"
    assert "no cuadran" in corrida.error


def test_corrida_abierta_vieja_se_falla_y_se_empieza_de_nuevo(escenario):
    e = escenario
    vieja = e.cliente.iniciar_corrida(
        conjunto="MAESTROS", empresa="SGX", tipo="solicitud", partes={"vendedores": "todo"},
        solicitudes=[], fecha_corte=None, extraida_en="2026-10-26T01:00:00-05:00",
    )["run_id"]
    [r] = _resultados(e, [trabajos_completos(["SGX"], HOY, [])[0]])
    assert _enviar(e, [r]) == []
    assert e.servidor.corridas[vieja].estado == "fallida"
    assert e.servidor.corridas[vieja].error == "Corrida anterior sin terminar; la reemplaza una nueva."
    nueva = e.servidor.corridas[vieja + 1]
    assert (nueva.tipo, nueva.estado) == ("completa", "cerrada")


def test_iniciar_recuperado_cuenta_como_exito(escenario):
    e = escenario
    e.servidor.programar_fallas("iniciar", red=True, despues=True)
    [r] = _resultados(e, [trabajos_completos(["SGX"], HOY, [])[1]])
    assert _enviar(e, [r]) == []
    assert len(e.servidor.corridas) == 1
    assert e.servidor.corridas[1].estado == "cerrada"


def test_error_de_extraccion_abre_y_falla_la_corrida(escenario):
    e = escenario
    for sid, parte in ((118, "clientes"), (121, "proveedores")):
        e.servidor.encolar_solicitud({"id": sid, "empresa": "SGX", "conjunto": "MAESTROS",
                                      "parte": parte, "desde": {parte: None}})
    trabajo = trabajos_de_solicitudes(e.cliente.tomar_solicitudes(20), HOY)[0]
    resultado = Resultado(trabajo)
    resultado.fallar("VPN", "No se pudo conectar la VPN tras 3 intentos.")

    fallos = _enviar(e, [resultado])

    assert fallos == [("VPN", "MAESTROS SGX: No se pudo conectar la VPN tras 3 intentos.")]
    [corrida] = e.servidor.corridas.values()
    assert corrida.estado == "fallida"
    assert corrida.error == "No se pudo conectar la VPN tras 3 intentos."
    assert corrida.solicitudes == [118, 121]
    assert corrida.extraida_en == "2026-10-26T02:00:05-05:00"
    assert e.servidor.estado_solicitudes == {118: "fallida", 121: "fallida"}
    assert e.servidor.peticiones_a("lote") == []
    assert not e.csv_dir.exists()


def test_error_de_extraccion_en_completa_sin_solicitudes_tambien_se_reporta(escenario):
    e = escenario
    resultado = Resultado(trabajos_completos(["SDC"], HOY, [])[1])
    resultado.fallar("HANA", "No se pudo conectar a HANA (SDC).")
    assert _enviar(e, [resultado]) == [("HANA", "CARTERA SDC: No se pudo conectar a HANA (SDC).")]
    [corrida] = e.servidor.corridas.values()
    assert (corrida.tipo, corrida.estado, corrida.fecha_corte) == ("completa", "fallida", "2026-10-25")


def test_un_lote_rechazado_falla_esa_corrida_y_sigue_con_las_demas(escenario):
    e = escenario
    e.servidor.programar_fallas("lote", status=422, datos={
        "message": "El valor CSGX001 no sirve.", "errors": {"rows.0.codigo": ["El valor CSGX001 no sirve."]},
    })
    resultados = _resultados(e, trabajos_completos(["SGX"], HOY, []))
    fallos = _enviar(e, resultados)
    assert len(fallos) == 1
    etapa, mensaje = fallos[0]
    assert etapa == "API" and mensaje.startswith("MAESTROS SGX: ")
    assert "rows.0.codigo" in mensaje
    assert "CSGX001" not in mensaje
    assert e.servidor.corridas[1].estado == "fallida"
    assert "CSGX001" not in e.servidor.corridas[1].error
    assert e.servidor.corridas[2].estado == "cerrada"


def test_si_falla_la_carpeta_igual_se_envia(escenario, monkeypatch):
    e = escenario

    def sin_disco(*args, **kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr(e.carpeta, "guardar_corrida", sin_disco)
    [r] = _resultados(e, [trabajos_completos(["SGX"], HOY, [])[1]])
    fallos = _enviar(e, [r])
    assert fallos == [("CARPETA", "CARTERA SGX: No se pudo guardar el CSV: disco lleno")]
    assert e.servidor.corridas[1].estado == "cerrada"


def test_si_fallar_tambien_falla_no_revienta(escenario):
    e = escenario
    e.servidor.programar_fallas("lote", status=422)
    e.servidor.programar_fallas("fallar", status=500, veces=4)
    [r] = _resultados(e, [trabajos_completos(["SGX"], HOY, [])[1]])
    fallos = _enviar(e, [r])
    assert [f[0] for f in fallos] == ["API"]
    assert e.servidor.corridas[1].estado == "abierta"  # vencerá sola en la API
