from __future__ import annotations

import dataclasses
from datetime import date
from pathlib import Path

import pytest

import archivo
import extraccion
from fake_hana import QUERIES, VpnFalsa, revisar_fases

HOY = date(2026, 10, 26)
ENCABEZADO_USR5 = "UserCode;Date;Time;Action;ClientName"


def _correr(e, modo: str, empresas=("SGX",), cfg=None, vpn=None) -> tuple[archivo.Archivo, list]:
    a = archivo.Archivo(cfg or e.cfg, modo, HOY)
    fallos = extraccion.sesion(
        cfg or e.cfg, list(empresas), a, robot_vpn=vpn or e.vpn, conectar=e.hana.conectar
    )
    fallos += a.escribir()
    return a, fallos


def _lineas(ruta: Path) -> list[str]:
    return ruta.read_text(encoding="utf-8-sig").splitlines()


def _tabla(e, carpeta: str, tabla: str, empresa: str = "SGX") -> Path:
    return e.csv_dir / carpeta / empresa / tabla


def _escribir(ruta: Path, lineas: list[str]) -> None:
    """CSV como los del robot: BOM, `;` y fin de línea CRLF."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes("".join(f"{linea}\r\n" for linea in lineas).encode("utf-8-sig"))


# --- Registro de tablas -------------------------------------------------------

PLAN = {
    "AUDITORIA": "USR5 OSUL ACRD ACR1 AITM AUSR ADOC ADO1 AJDT AJD1 OWDD WDD1",
    "USUARIOS_Y_PERMISOS": "OUSR USR3 UGR1 OUPT UPT1",
    "CONTABILIDAD": "OACT OPRC OOCR OPRJ OFPR OCRN ORTT OSTC OWHT",
    "BANCOS": "ODSC DSC1 OPYM",
    "INVENTARIO": "OWHS OUOM OUGP OITT ITT1 OSPP SPP1",
    "ORGANIZACION": "OADM OBPL OUDP OHPS OTER OIND OHEM",
    "VENTAS_Y_CRM": "OCLG OOPR OPR1 OSHP OCRY OCST",
    "CONFIGURACION": "NNM1 CUFD UFD1 OUTB OUDO OUQR OQCN OALT",
}


def test_el_registro_cubre_las_tablas_del_plan():
    esperado = {(c, t) for c, tablas in PLAN.items() for t in tablas.split()}
    assert {(t.carpeta, t.tabla) for t in archivo.TABLAS} == esperado
    assert len(archivo.TABLAS) == len(esperado)


def test_cada_tabla_tiene_su_consulta():
    for t in archivo.TABLAS:
        assert (QUERIES / t.consulta).is_file(), t.consulta
        if t.tabla not in ("CUFD", "OUTB"):
            assert t.consulta == f"archivo/{t.carpeta}/{t.tabla}.sql"
    sueltos = {r.relative_to(QUERIES / "archivo").as_posix()
               for r in (QUERIES / "archivo").rglob("*.sql")}
    registrados = {t.consulta.removeprefix("archivo/") for t in archivo.TABLAS}
    assert sueltos - registrados == {"hbt_tablas.sql", "hbt_columnas.sql"}


def test_modos_y_columnas_de_fecha():
    registros = {t.tabla: t.columna_fecha for t in archivo.TABLAS if t.modo == "registro"}
    assert set(registros) == set(PLAN["AUDITORIA"].split()) | {"ORTT"}
    assert registros["USR5"] == "Date"
    assert registros["ORTT"] == "RateDate"
    assert registros["OWDD"] == "CreateDate"
    assert all(t.columna_fecha is None for t in archivo.TABLAS if t.modo == "foto")
    assert {t.tabla for t in archivo.TABLAS if t.grande} == {"ADOC", "ADO1", "AJDT", "AJD1"}


def test_tablas_grandes_omitidas_salvo_que_se_activen(caplog):
    caplog.set_level("INFO", logger="bases_sap")
    apagado = {t.tabla for t in archivo.seleccionar("registros", False)}
    assert not apagado & {"ADOC", "ADO1", "AJDT", "AJD1"}
    assert "omitida hasta que TI confirme su tamaño en el catálogo" in caplog.text
    assert "BASES_SAP_ARCHIVO_HISTORIAL_DOCUMENTOS" in caplog.text
    encendido = {t.tabla for t in archivo.seleccionar("registros", True)}
    assert encendido - apagado == {"ADOC", "ADO1", "AJDT", "AJD1"}
    with pytest.raises(ValueError):
        archivo.seleccionar("todo", False)


def test_tablas_grandes_se_leen_con_el_historial_activo(escenario):
    e = escenario
    cfg = dataclasses.replace(e.cfg, historial_documentos=True)
    _, fallos = _correr(e, "registros", cfg=cfg)
    assert fallos == []
    leidas = {x.parte for x in e.hana.de("SGX")}
    assert {"archivo/AUDITORIA/ADOC", "archivo/AUDITORIA/AJD1"} <= leidas


# --- Registros ------------------------------------------------------------------


def test_registro_primera_vez_trae_todo_hasta_ayer_por_mes(escenario):
    e = escenario
    _, fallos = _correr(e, "registros")
    assert fallos == []
    [usr5] = e.hana.de("SGX", parte="archivo/AUDITORIA/USR5")
    assert usr5.tipo == "registro"
    assert usr5.params == (HOY,)  # sin marca de agua: solo el tope (hoy, excluido)
    assert 'X."Date" < ?' in usr5.sql
    carpeta = _tabla(e, "AUDITORIA", "USR5")
    assert sorted(p.name for p in carpeta.iterdir()) == ["2026-09.csv", "2026-10.csv"]
    assert _lineas(carpeta / "2026-09.csv") == [ENCABEZADO_USR5, "uSGX1;2026-09-30;801;I;PC1"]
    assert _lineas(carpeta / "2026-10.csv") == [
        ENCABEZADO_USR5, "uSGX2;2026-10-24;802;I;PC2", "uSGX3;2026-10-25;803;I;PC3",
    ]  # nada de hoy (2026-10-26): solo días completos
    # ORTT (CONTABILIDAD) también es registro nocturno; el decimal va tal cual.
    assert _lineas(_tabla(e, "CONTABILIDAD", "ORTT") / "2026-10.csv") == [
        "RateDate;Currency;Rate", "2026-10-25;USD;4100.5000",
    ]
    # Un registro sin filas no crea archivo.
    assert not _tabla(e, "AUDITORIA", "ACRD").exists()
    revisar_fases(e.linea)


def test_registro_sigue_desde_el_ultimo_dia_del_mes_mas_nuevo_sin_duplicar(escenario):
    e = escenario
    carpeta = _tabla(e, "AUDITORIA", "USR5")
    _escribir(carpeta / "2026-09.csv", [ENCABEZADO_USR5, "uSGX1;2026-09-30;801;I;PC1"])
    _escribir(carpeta / "2026-10.csv", [ENCABEZADO_USR5, "uSGX2;2026-10-24;802;I;PC2"])
    septiembre = (carpeta / "2026-09.csv").read_bytes()

    _, fallos = _correr(e, "registros")
    assert fallos == []
    [usr5] = e.hana.de("SGX", parte="archivo/AUDITORIA/USR5")
    assert usr5.params == (date(2026, 10, 25), HOY)
    assert 'X."Date" >= ? AND X."Date" < ?' in usr5.sql
    assert (carpeta / "2026-09.csv").read_bytes() == septiembre
    assert _lineas(carpeta / "2026-10.csv") == [
        ENCABEZADO_USR5, "uSGX2;2026-10-24;802;I;PC2", "uSGX3;2026-10-25;803;I;PC3",
    ]

    # Otra vez el mismo día: ya está al día, no consulta ni suma nada.
    e.hana.ejecutadas.clear()
    antes = (carpeta / "2026-10.csv").read_bytes()
    _, fallos = _correr(e, "registros")
    assert fallos == []
    assert e.hana.de("SGX", parte="archivo/AUDITORIA/USR5") == []
    assert (carpeta / "2026-10.csv").read_bytes() == antes


def test_registro_reparte_las_filas_en_cada_mes(escenario):
    e = escenario
    _escribir(_tabla(e, "AUDITORIA", "USR5") / "2026-08.csv", [ENCABEZADO_USR5, "u0;2026-08-31;1;I;PC"])
    _, fallos = _correr(e, "registros")
    assert fallos == []
    carpeta = _tabla(e, "AUDITORIA", "USR5")
    assert [len(_lineas(carpeta / f"2026-{m}.csv")) - 1 for m in ("08", "09", "10")] == [1, 1, 2]


def test_registro_con_archivo_de_otras_columnas_falla_solo_esa_tabla(escenario):
    e = escenario
    _escribir(_tabla(e, "AUDITORIA", "USR5") / "2026-10.csv", ["UserCode;Date", "u;2026-10-01"])
    _, fallos = _correr(e, "registros")
    assert [etapa for etapa, _ in fallos] == ["ARCHIVO"]
    assert fallos[0][1].startswith("SGX AUDITORIA/USR5: ")
    assert (_tabla(e, "CONTABILIDAD", "ORTT") / "2026-10.csv").is_file()


def test_registro_sin_la_columna_de_fecha_falla(escenario, monkeypatch):
    e = escenario
    tablas = [dataclasses.replace(t, columna_fecha="NoExiste") if t.tabla == "USR5" else t
              for t in archivo.TABLAS]
    monkeypatch.setattr(archivo, "TABLAS", tuple(tablas))
    _, fallos = _correr(e, "registros")
    assert fallos == [("ARCHIVO", "SGX AUDITORIA/USR5: Error inesperado (ValueError); "
                                  "revisa robot/logs/robot.log.")]
    assert not _tabla(e, "AUDITORIA", "USR5").exists()


def test_una_tabla_que_falla_no_detiene_las_demas(escenario):
    e = escenario
    e.hana.partes_que_fallan.add(("SGX", "archivo/AUDITORIA/OSUL"))
    e.hana.texto_de_falla = "invalid column name: 'uSGX9'"
    _, fallos = _correr(e, "registros", empresas=("SGX", "SDC"))
    assert fallos == [("ARCHIVO", "SGX AUDITORIA/OSUL: Error ejecutando la consulta "
                                  "'SGX AUDITORIA/OSUL'; revisa robot/logs/robot.log.")]
    assert (_tabla(e, "AUDITORIA", "USR5") / "2026-10.csv").is_file()
    assert (_tabla(e, "AUDITORIA", "USR5", "SDC") / "2026-10.csv").is_file()
    revisar_fases(e.linea)


# --- Fotos ----------------------------------------------------------------------


def test_fotos_nombre_del_dia_y_contenido(escenario):
    e = escenario
    _, fallos = _correr(e, "fotos")
    assert fallos == []
    ousr = _tabla(e, "USUARIOS_Y_PERMISOS", "OUSR") / "2026-10-26.csv"
    assert _lineas(ousr) == [
        "USERID;USER_CODE;U_NAME;E_Mail;SUPERUSER;Locked;Department;Branch",
        "1;manager;Gerente;g@prueba.local;Y;N;-2;-2",
    ]
    # Una foto sin filas igual queda (estado del día), con su encabezado.
    assert _lineas(_tabla(e, "BANCOS", "ODSC") / "2026-10-26.csv") == [
        "AbsEntry;BankCode;BankName;CountryCod;SwiftNum",
    ]
    # CUFD y OUTB reutilizan las consultas del catálogo.
    assert (_tabla(e, "CONFIGURACION", "CUFD") / "2026-10-26.csv").is_file()
    assert (_tabla(e, "CONFIGURACION", "OUTB") / "2026-10-26.csv").is_file()
    # Las fotos no leen registros.
    assert not [x for x in e.hana.de("SGX") if x.tipo == "registro"]
    assert not _tabla(e, "AUDITORIA", "USR5").exists()
    revisar_fases(e.linea)


def test_fotos_purgan_las_de_mas_de_52_semanas(escenario):
    e = escenario
    vieja = _tabla(e, "BANCOS", "ODSC") / "2025-10-26.csv"
    reciente = _tabla(e, "BANCOS", "ODSC") / "2025-10-27.csv"
    registro_viejo = _tabla(e, "CONTABILIDAD", "ORTT") / "2020-01.csv"
    for ruta in (vieja, reciente):
        _escribir(ruta, ["AbsEntry;BankCode;BankName;CountryCod;SwiftNum"])
    _escribir(registro_viejo, ["RateDate;Currency;Rate", "2020-01-02;USD;3000"])
    _, fallos = _correr(e, "fotos")
    assert fallos == []
    assert not vieja.exists()
    assert reciente.exists()
    assert registro_viejo.exists()


def test_hbt_se_descubren_y_se_leen_sin_columnas_de_claves(escenario):
    e = escenario
    _, fallos = _correr(e, "fotos")
    assert fallos == []
    [config] = e.hana.de("SGX", parte="@HBT_CONFIG")
    assert config.sql == 'SELECT\n    T0."Code",\n    T0."Name",\n    T0."U_Valor"\nFROM "@HBT_CONFIG" T0'
    foto = _tabla(e, "CONFIGURACION", "@HBT_CONFIG") / "2026-10-26.csv"
    assert _lineas(foto) == ["Code;Name;U_Valor", "1;Ajuste;10"]
    assert "no-debe-salir" not in foto.read_text(encoding="utf-8-sig")
    assert _lineas(_tabla(e, "CONFIGURACION", "@HBT_MUNICIPIO") / "2026-10-26.csv") == [
        "Code;Name", "05001;Medellín",
    ]


def test_hbt_tabla_sin_columnas_legibles_falla_sola(escenario):
    e = escenario
    e.hana.archivo["SGX"]["archivo/hbt_tablas"].append({"TABLE_NAME": "@HBT_SOLOCLAVE"})
    e.hana.archivo["SGX"]["archivo/hbt_columnas"].append(
        {"TABLE_NAME": "@HBT_SOLOCLAVE", "COLUMN_NAME": "U_Pwd", "POSITION": 1})
    _, fallos = _correr(e, "fotos")
    assert [m.split(":")[0] for _, m in fallos] == ["SGX CONFIGURACION/@HBT_SOLOCLAVE"]
    assert (_tabla(e, "CONFIGURACION", "@HBT_CONFIG") / "2026-10-26.csv").is_file()


def test_hbt_si_falla_el_descubrimiento_siguen_las_demas(escenario):
    e = escenario
    e.hana.partes_que_fallan.add(("SGX", "archivo/hbt_columnas"))
    _, fallos = _correr(e, "fotos")
    assert [m.split(":")[0] for _, m in fallos] == ["SGX CONFIGURACION/@HBT_*"]
    assert (_tabla(e, "CONFIGURACION", "NNM1") / "2026-10-26.csv").is_file()


@pytest.mark.parametrize("nombre", ["U_PASSWORD", "U_Pwd_Web", "U_ClaveApi", "U_Contraseña", "Pass1"])
def test_es_clave(nombre):
    assert archivo.es_clave(nombre)


def test_sql_hbt_rechaza_nombres_raros():
    with pytest.raises(ValueError):
        archivo.sql_hbt('@HBT_X" T0; DROP', ["Code"])
    with pytest.raises(ValueError):
        archivo.sql_hbt("@HBT_X", [])


# --- Dos fases --------------------------------------------------------------------


def test_si_falla_la_vpn_no_se_lee_ni_se_escribe(escenario):
    e = escenario
    vpn = VpnFalsa(e.linea, fallar=True)
    e.hana.vpn = vpn
    _, fallos = _correr(e, "fotos", vpn=vpn)
    assert [etapa for etapa, _ in fallos] == ["VPN"]
    assert e.hana.ejecutadas == []
    assert not any(e.csv_dir.rglob("*.csv"))
    revisar_fases(e.linea)


def test_no_se_escribe_nada_con_la_vpn_arriba(escenario):
    e = escenario
    a = archivo.Archivo(e.cfg, "fotos", HOY)
    escritos: list = []

    def leer(conn, empresa):
        a(conn, empresa)
        escritos.extend(e.csv_dir.rglob("*.csv"))

    extraccion.sesion(e.cfg, ["SGX"], leer, robot_vpn=e.vpn, conectar=e.hana.conectar)
    assert escritos == []
    assert a.lecturas
    a.escribir()
    assert any(e.csv_dir.rglob("*.csv"))
    revisar_fases(e.linea)
