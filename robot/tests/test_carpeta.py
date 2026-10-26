from __future__ import annotations

import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import carpeta
from carpeta import Carpeta, escribir_csv
from config import BOGOTA


def _leer(ruta: Path) -> bytes:
    return ruta.read_bytes()


def test_escribir_csv_formato(tmp_path: Path):
    ruta = tmp_path / "a" / "b" / "datos.csv"
    escribir_csv(ruta, ["codigo", "activo", "nota", "monto"], [
        ["C1", True, None, "12.50"],
        ["C2", False, "con; punto y coma", "0.00"],
    ])
    crudo = _leer(ruta)
    assert crudo.startswith(b"\xef\xbb\xbf")  # BOM
    texto = crudo.decode("utf-8-sig")
    assert texto.splitlines() == [
        "codigo;activo;nota;monto",
        "C1;true;;12.50",
        'C2;false;"con; punto y coma";0.00',
    ]
    # Sin archivos temporales que sobren.
    assert [p.name for p in ruta.parent.iterdir()] == ["datos.csv"]


def test_escribir_csv_no_deja_medio_archivo(tmp_path: Path):
    ruta = tmp_path / "datos.csv"
    escribir_csv(ruta, ["a"], [["viejo"]])

    class Explota:
        def __iter__(self):
            yield ["nuevo"]
            raise RuntimeError("se cayó a la mitad")

    with pytest.raises(RuntimeError):
        escribir_csv(ruta, ["a"], Explota())
    assert ruta.read_text(encoding="utf-8-sig").splitlines() == ["a", "viejo"]
    assert [p.name for p in tmp_path.iterdir()] == ["datos.csv"]


def test_guardar_corrida_ruta_y_nombre_en_hora_de_bogota(tmp_path: Path):
    c = Carpeta(tmp_path)
    # 07:05 UTC son las 02:05 en Bogotá.
    momento = datetime(2026, 10, 26, 7, 5, tzinfo=timezone.utc)
    ruta = c.guardar_corrida("MAESTROS", "SGX", "clientes", ["codigo"], [["C1"]], momento)
    assert ruta == tmp_path / "MAESTROS" / "SGX" / "clientes" / "2026-10-26_0205.csv"
    assert ruta.read_text(encoding="utf-8-sig").splitlines() == ["codigo", "C1"]


def test_guardar_corrida_no_pisa_otra_del_mismo_minuto(tmp_path: Path):
    c = Carpeta(tmp_path)
    momento = datetime(2026, 10, 26, 10, 42, tzinfo=BOGOTA)
    rutas = [
        c.guardar_corrida("CARTERA", "SDC", "cartera", ["x"], [[i]], momento) for i in range(3)
    ]
    assert [r.name for r in rutas] == [
        "2026-10-26_1042.csv", "2026-10-26_1042-2.csv", "2026-10-26_1042-3.csv",
    ]


def test_guardar_historico_cartera_reemplaza_el_mismo_dia(tmp_path: Path):
    c = Carpeta(tmp_path)
    c.guardar_historico_cartera("SGX", "2026-10-25", ["saldo"], [["1.00"]])
    ruta = c.guardar_historico_cartera("SGX", "2026-10-25", ["saldo"], [["2.00"]])
    assert ruta == tmp_path / "CARTERA" / "SGX" / "historico" / "2026-10-25.csv"
    assert ruta.read_text(encoding="utf-8-sig").splitlines() == ["saldo", "2.00"]


def test_guardar_historico_rechaza_fecha_invalida(tmp_path: Path):
    with pytest.raises(ValueError):
        Carpeta(tmp_path).guardar_historico_cartera("SGX", "../x", ["a"], [])


def _tocar(ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("x", encoding="utf-8")
    return ruta


def test_purgar_corridas_borra_solo_corridas_viejas(tmp_path: Path):
    raiz = tmp_path
    vieja_m = _tocar(raiz / "MAESTROS" / "SGX" / "clientes" / "2026-07-27_0200.csv")
    vieja_m2 = _tocar(raiz / "MAESTROS" / "SDC" / "precios" / "2026-01-02_1042-2.csv")
    limite_m = _tocar(raiz / "MAESTROS" / "SGX" / "clientes" / "2026-07-28_0200.csv")
    vieja_c = _tocar(raiz / "CARTERA" / "SGX" / "cartera" / "2026-05-01_0200.csv")
    nueva_c = _tocar(raiz / "CARTERA" / "SGX" / "cartera" / "2026-10-25_0200.csv")
    historico = _tocar(raiz / "CARTERA" / "SGX" / "historico" / "2025-01-01.csv")
    otro = _tocar(raiz / "MAESTROS" / "SGX" / "clientes" / "notas.txt")
    archivo = _tocar(raiz / "AUDITORIA" / "SGX" / "USR5" / "2024-01-01.csv")

    borrados = Carpeta(raiz).purgar_corridas(date(2026, 10, 26))

    assert sorted(borrados) == sorted([vieja_m, vieja_m2, vieja_c])
    for ruta in (vieja_m, vieja_m2, vieja_c):
        assert not ruta.exists()
    for ruta in (limite_m, nueva_c, historico, otro, archivo):
        assert ruta.exists()


def test_purgar_corridas_sin_carpetas_no_falla(tmp_path: Path):
    assert Carpeta(tmp_path / "no-existe").purgar_corridas(date(2026, 10, 26)) == []


def test_purgar_por_fecha_generico(tmp_path: Path):
    _tocar(tmp_path / "2026-01-01.csv")
    _tocar(tmp_path / "2026-03-01.csv")
    _tocar(tmp_path / "2026-13-45.csv")  # fecha imposible: no se toca
    borrados = carpeta.purgar_por_fecha(
        tmp_path, re.compile(r"^(\d{4}-\d{2}-\d{2})\.csv$"), date(2026, 2, 1)
    )
    assert [p.name for p in borrados] == ["2026-01-01.csv"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["2026-03-01.csv", "2026-13-45.csv"]


def test_purgar_sigue_si_un_archivo_no_se_puede_borrar(tmp_path: Path, monkeypatch):
    a = _tocar(tmp_path / "MAESTROS" / "SGX" / "clientes" / "2026-01-01_0200.csv")
    b = _tocar(tmp_path / "MAESTROS" / "SGX" / "clientes" / "2026-01-02_0200.csv")
    original = Path.unlink

    def unlink(self, *args, **kwargs):
        if self.name == a.name:
            raise PermissionError("en uso")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    borrados = Carpeta(tmp_path).purgar_corridas(date(2026, 10, 26))
    assert borrados == [b]
    assert a.exists() and not b.exists()
    assert os.path.exists(a)
