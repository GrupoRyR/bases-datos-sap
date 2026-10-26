from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

import bloqueo
import config
from bloqueo import Bloqueo, en_franja
from config import BOGOTA

FRANJAS = ["00:00", "05:00", "06:00", "12:00", "12:30"]
AHORA = datetime(2026, 10, 26, 2, 0, 5, tzinfo=config.BOGOTA)


def _h(hora: int, minuto: int, segundo: int = 0) -> datetime:
    return datetime(2026, 10, 26, hora, minuto, segundo, tzinfo=config.BOGOTA)


# --- Franjas bloqueadas (contrato §7.2, regla 5) ---------------------------------------


@pytest.mark.parametrize("momento, esperado", [
    (_h(11, 45), "12:00"),       # 15 minutos justos: bloqueado
    (_h(11, 44, 59), None),
    (_h(12, 10), "12:00"),
    (_h(12, 45), "12:30"),
    (_h(12, 45, 1), None),
    (_h(5, 15), "05:00"),
    (_h(5, 30), None),           # a 30 minutos de las 05:00 y de las 06:00
    (_h(5, 45), "06:00"),
    (_h(23, 45), "00:00"),       # cruza la medianoche
    (_h(23, 44, 59), None),
    (_h(23, 50), "00:00"),
    (_h(0, 15), "00:00"),
    (_h(0, 15, 1), None),
    (_h(2, 0), None),
    (_h(3, 0), None),
])
def test_en_franja(momento, esperado):
    assert en_franja(momento, FRANJAS) == esperado


def test_en_franja_usa_la_hora_de_bogota():
    assert en_franja(datetime(2026, 10, 26, 17, 5, tzinfo=timezone.utc), FRANJAS) == "12:00"
    assert en_franja(datetime(2026, 10, 26, 12, 5), FRANJAS) == "12:00"  # sin zona: Bogotá


def test_en_franja_con_otro_margen_y_sin_franjas():
    assert en_franja(_h(12, 5), ["12:00"], margen_min=3) is None
    assert en_franja(_h(12, 3), ["12:00"], margen_min=3) == "12:00"
    assert en_franja(_h(12, 0), []) is None


def test_franjas_por_defecto_dejan_libres_las_horas_programadas():
    cfg = config.cargar_config()
    assert (cfg.franjas, cfg.margen_franja_min) == (FRANJAS, 15)
    assert en_franja(_h(6, 10), cfg.franjas, cfg.margen_franja_min) == "06:00"
    for hora in (2, 3):  # nocturna 02:00 y domingo 03:00
        assert en_franja(_h(hora, 0), cfg.franjas, cfg.margen_franja_min) is None


# --- Candado ----------------------------------------------------------------------------


def _reloj():
    return AHORA


def _escribir(ruta, pid=4242, tomado_en=AHORA):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"pid": pid, "tomado_en": tomado_en.isoformat()}), encoding="utf-8")


def test_ruta_por_defecto_en_state():
    assert Bloqueo().ruta == config.STATE_DIR / "robot.lock"


def test_candado_exclusivo(tmp_path):
    ruta = tmp_path / "state" / "robot.lock"
    primero = Bloqueo(ruta, reloj=_reloj)
    segundo = Bloqueo(ruta, reloj=_reloj)
    assert primero.tomar()
    assert json.loads(ruta.read_text(encoding="utf-8")) == {
        "pid": os.getpid(), "tomado_en": AHORA.isoformat(),
    }
    assert not segundo.tomar()
    primero.soltar()
    assert not ruta.exists()
    assert segundo.tomar()
    segundo.soltar()


def test_como_contexto(tmp_path):
    ruta = tmp_path / "robot.lock"
    with Bloqueo(ruta, reloj=_reloj) as tomado:
        assert tomado and ruta.exists()
        with Bloqueo(ruta, reloj=_reloj) as otro:
            assert not otro
        assert ruta.exists()  # el que no lo tomó no lo suelta
    assert not ruta.exists()


def test_candado_vencido_se_toma(tmp_path, caplog):
    ruta = tmp_path / "robot.lock"
    _escribir(ruta, pid=1234, tomado_en=AHORA - timedelta(hours=3, seconds=1))
    with caplog.at_level(logging.WARNING, logger="bases_sap"):
        assert Bloqueo(ruta, reloj=_reloj).tomar()
    assert json.loads(ruta.read_text(encoding="utf-8"))["pid"] == os.getpid()
    assert "vencido" in caplog.text


def test_candado_vigente_no_se_toma(tmp_path):
    ruta = tmp_path / "robot.lock"
    _escribir(ruta, tomado_en=AHORA - timedelta(hours=2, minutes=59))
    assert not Bloqueo(ruta, reloj=_reloj).tomar()
    assert json.loads(ruta.read_text(encoding="utf-8"))["pid"] == 4242


def test_candado_ilegible_usa_la_hora_del_archivo(tmp_path):
    ruta = tmp_path / "robot.lock"
    ruta.write_text("", encoding="utf-8")  # otro proceso lo acaba de crear y aún no escribe
    assert not Bloqueo(ruta).tomar()
    viejo = time.time() - 4 * 3600
    os.utime(ruta, (viejo, viejo))
    assert Bloqueo(ruta).tomar()


def test_espera_a_que_lo_suelten(tmp_path):
    ruta = tmp_path / "robot.lock"
    _escribir(ruta)
    esperas: list[float] = []

    def dormir(segundos):
        esperas.append(segundos)
        if len(esperas) == 2:
            ruta.unlink()

    assert Bloqueo(ruta, reloj=_reloj).tomar(esperar=timedelta(minutes=20), dormir=dormir)
    assert esperas == [10, 10]


def test_deja_de_esperar(tmp_path):
    ruta = tmp_path / "robot.lock"
    _escribir(ruta)
    esperas: list[float] = []
    candado = Bloqueo(ruta, reloj=_reloj)
    assert not candado.tomar(esperar=timedelta(seconds=35), dormir=esperas.append)
    assert esperas == [10, 10, 10, 5]
    assert not candado.tomar(dormir=esperas.append)  # sin esperar no duerme
    assert len(esperas) == 4


def test_soltar_no_borra_el_candado_de_otro(tmp_path):
    ruta = tmp_path / "robot.lock"
    candado = Bloqueo(ruta, reloj=_reloj)
    assert candado.tomar()
    _escribir(ruta, pid=999)  # otro proceso lo dio por vencido y lo tomó
    candado.soltar()
    assert json.loads(ruta.read_text(encoding="utf-8"))["pid"] == 999


def test_soltar_sin_tomar_no_hace_nada(tmp_path):
    ruta = tmp_path / "robot.lock"
    _escribir(ruta)
    Bloqueo(ruta, reloj=_reloj).soltar()
    assert ruta.exists()


def test_fin_de_franja_salta_franjas_seguidas() -> None:
    franjas = ["00:00", "05:00", "06:00", "12:00", "12:30"]
    momento = datetime(2026, 10, 26, 11, 50, 30, tzinfo=BOGOTA)

    assert bloqueo.fin_de_franja(momento, franjas, 15) == datetime(2026, 10, 26, 12, 46, tzinfo=BOGOTA)


def test_fin_de_franja_fuera_de_franja_es_el_mismo_momento() -> None:
    momento = datetime(2026, 10, 26, 2, 0, 5, tzinfo=BOGOTA)

    assert bloqueo.fin_de_franja(momento, ["00:00", "05:00"], 15) == momento
