from __future__ import annotations

import csv
from pathlib import Path

import diagnostico
import esquema
import extraccion
from fake_hana import fila, revisar_fases


def _correr(e, empresas=("SGX", "SDC")) -> tuple[diagnostico.Diagnostico, list]:
    d = diagnostico.Diagnostico(e.cfg, e.ahora())
    fallos = extraccion.sesion(e.cfg, list(empresas), d, robot_vpn=e.vpn, conectar=e.hana.conectar)
    return d, fallos + d.escribir()


def _resumen(e) -> list[dict[str, str]]:
    ruta = e.csv_dir / "_DIAGNOSTICO" / "resumen" / "2026-10-26_0200.csv"
    with open(ruta, encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo, delimiter=";"))


def _fila(resumen, empresa, parte):
    [f] = [f for f in resumen if f["empresa"] == empresa and f["parte"] == parte]
    return f


def test_resumen_con_filas_conteos_y_activos(escenario):
    e = escenario
    _, fallos = _correr(e)
    assert fallos == []
    resumen = _resumen(e)
    assert list(resumen[0]) == diagnostico.COLUMNAS_RESUMEN
    partes = [*esquema.PARTES, "listas_precios"]
    assert [(f["empresa"], f["parte"]) for f in resumen] == [
        (emp, p) for emp in ("SGX", "SDC") for p in partes
    ]
    clientes = _fila(resumen, "SGX", "clientes")
    assert clientes == {"empresa": "SGX", "conjunto": "MAESTROS", "parte": "clientes", "filas": "3",
                        "conteo_sap": "3", "activos": "2", "inactivos": "1", "error": ""}
    cartera = _fila(resumen, "SDC", "cartera")
    assert (cartera["conjunto"], cartera["filas"], cartera["conteo_sap"], cartera["activos"]) == (
        "CARTERA", "3", "3", "")
    listas = _fila(resumen, "SGX", "listas_precios")
    assert (listas["filas"], listas["conteo_sap"], listas["error"]) == ("1", "", "")
    revisar_fases(e.linea)


def test_archivos_de_datos_por_parte(escenario):
    e = escenario
    _correr(e, ("SGX",))
    base = e.csv_dir / "_DIAGNOSTICO" / "SGX"
    clientes = (base / "clientes" / "2026-10-26_0200.csv").read_text(encoding="utf-8-sig").splitlines()
    assert clientes[0].split(";") == esquema.PARTES["clientes"].nombres
    assert len(clientes) == 4
    assert (base / "cartera" / "2026-10-26_0200.csv").is_file()
    listas = (base / "listas_precios" / "2026-10-26_0200.csv").read_text(encoding="utf-8-sig").splitlines()
    assert listas == ["ListNum;ListName;BASE_NUM;Factor;ValidFor", "1;PÚBLICA;1;1;Y"]


def test_parte_que_falla_queda_en_el_resumen_y_las_demas_siguen(escenario):
    e = escenario
    e.hana.partes_que_fallan.add(("SGX", "marcas"))
    e.hana.texto_de_falla = "invalid value 'MARCA-SECRETA'"
    _, fallos = _correr(e, ("SGX",))
    assert fallos == [("DIAGNOSTICO", "SGX marcas: Error ejecutando la consulta "
                                      "'SGX marcas (diagnóstico)'; revisa robot/logs/robot.log.")]
    resumen = _resumen(e)
    marcas = _fila(resumen, "SGX", "marcas")
    assert (marcas["filas"], marcas["conteo_sap"]) == ("", "")
    assert marcas["error"].startswith("Error ejecutando la consulta 'SGX marcas (diagnóstico)'")
    assert "MARCA-SECRETA" not in Path(e.csv_dir / "_DIAGNOSTICO" / "resumen" / "2026-10-26_0200.csv").read_text(
        encoding="utf-8-sig")
    assert not (e.csv_dir / "_DIAGNOSTICO" / "SGX" / "marcas").exists()
    assert _fila(resumen, "SGX", "vendedores")["error"] == ""


def test_parte_vacia_no_es_error(escenario):
    e = escenario
    e.hana.datos["SGX"]["marcas"] = []
    _, fallos = _correr(e, ("SGX",))
    assert fallos == []
    marcas = _fila(_resumen(e), "SGX", "marcas")
    assert (marcas["filas"], marcas["conteo_sap"], marcas["error"]) == ("0", "0", "")


def test_validacion_que_falla_guarda_las_filas_crudas(escenario):
    e = escenario
    e.hana.datos["SGX"]["vendedores"] = [fila("vendedores", 1), fila("vendedores", 1)]
    _, fallos = _correr(e, ("SGX",))
    assert [etapa for etapa, _ in fallos] == ["DIAGNOSTICO"]
    vendedores = _fila(_resumen(e), "SGX", "vendedores")
    assert vendedores["error"].startswith("Parte vendedores: 1 llaves repetidas")
    assert (vendedores["filas"], vendedores["conteo_sap"]) == ("2", "2")
    datos = (e.csv_dir / "_DIAGNOSTICO" / "SGX" / "vendedores" / "2026-10-26_0200.csv")
    assert len(datos.read_text(encoding="utf-8-sig").splitlines()) == 3


def test_retencion_de_90_dias(escenario):
    e = escenario
    vieja = e.csv_dir / "_DIAGNOSTICO" / "SGX" / "clientes" / "2026-07-01_0900.csv"
    vieja.parent.mkdir(parents=True, exist_ok=True)
    vieja.write_text("x", encoding="utf-8")
    _correr(e, ("SGX",))
    assert not vieja.exists()
