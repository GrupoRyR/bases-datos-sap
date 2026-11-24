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


def test_candado_que_se_esta_borrando_se_reintenta(tmp_path, monkeypatch) -> None:
    ruta = tmp_path / "robot.lock"
    ruta.write_text("no es json", encoding="utf-8")
    candado = Bloqueo(ruta)
    original = type(ruta).stat

    def stat(self, *args, **kwargs):
        if self == ruta:
            ruta.unlink()  # el otro proceso termina de borrarlo
            raise PermissionError("borrado pendiente")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(ruta), "stat", stat)

    assert candado.tomar() is True


# --- Huecos entre franjas: una ejecución larga no puede alcanzar la siguiente ---------


def _d(dia: int, hora: int, minuto: int) -> datetime:
    return datetime(2026, 10, dia, hora, minuto, tzinfo=BOGOTA)


@pytest.mark.parametrize("momento, esperado", [
    (_h(2, 0, 5), _d(26, 4, 45)),   # la franja de las 05:00 empieza a las 04:45
    (_h(4, 45), _d(26, 4, 45)),     # ya dentro: es ese mismo minuto
    (_h(5, 16), _d(26, 5, 45)),
    (_h(12, 46), _d(26, 23, 45)),   # la de las 00:00 empieza el mismo día a las 23:45
])
def test_proxima_franja(momento, esperado):
    assert bloqueo.proxima_franja(momento, FRANJAS, 15) == esperado


def test_proxima_franja_sin_franjas():
    assert bloqueo.proxima_franja(_h(2, 0), [], 15) is None


@pytest.mark.parametrize("momento, minutos, esperado", [
    (_h(2, 0, 5), 21, _h(2, 0, 5)),         # cabe antes de las 04:45: arranca ya
    (_h(4, 30), 20, _d(26, 5, 16)),         # cabe en el hueco de 05:16 a 05:44
    (_h(4, 30), 89, _d(26, 6, 16)),         # no cabe ahí: después de la de las 06:00
    (_h(11, 50), 21, _d(26, 12, 46)),       # dentro de una franja: cuando termina
    (_h(23, 0), 60, _d(27, 0, 16)),         # cruza la medianoche
    (_h(4, 15), 29, _d(26, 4, 15)),         # termina a las 04:44: justo antes
    (_h(4, 15), 30, _d(26, 6, 16)),         # termina a las 04:45: ya es franja (y no cabe a las 05:16)
])
def test_inicio_hueco(momento, minutos, esperado):
    assert bloqueo.inicio_hueco(momento, timedelta(minutes=minutos), FRANJAS, 15) == esperado


def test_inicio_hueco_sin_franjas_es_ya():
    assert bloqueo.inicio_hueco(_h(12, 0), timedelta(hours=30), [], 15) == _h(12, 0)


def test_inicio_hueco_sin_un_hueco_tan_largo_falla():
    # El hueco más largo del día va de 12:46 a 23:44.
    assert bloqueo.inicio_hueco(_h(2, 0), timedelta(minutes=658), FRANJAS, 15) == _d(26, 12, 46)
    with pytest.raises(ValueError, match="hueco"):
        bloqueo.inicio_hueco(_h(2, 0), timedelta(minutes=659), FRANJAS, 15)


# --- Renovar el candado en una ejecución larga ------------------------------------------


def test_renovar_pone_la_hora_actual_y_no_se_vence(tmp_path):
    ruta = tmp_path / "robot.lock"
    horas = [AHORA]
    candado = Bloqueo(ruta, reloj=lambda: horas[0])
    assert candado.tomar()
    horas[0] = AHORA + timedelta(hours=2, minutes=30)
    assert candado.renovar() is True
    assert json.loads(ruta.read_text(encoding="utf-8")) == {
        "pid": os.getpid(), "tomado_en": horas[0].isoformat(),
    }
    # A las 4 horas de tomarlo, otro proceso lo ve renovado hace 1 h 30: no está vencido.
    otro = Bloqueo(ruta, reloj=lambda: AHORA + timedelta(hours=4))
    assert otro.tomar() is False
    candado.soltar()  # sigue siendo nuestro con la marca nueva
    assert not ruta.exists()


def test_renovar_un_candado_ajeno_no_lo_toca(tmp_path):
    ruta = tmp_path / "robot.lock"
    candado = Bloqueo(ruta, reloj=_reloj)
    assert candado.tomar()
    _escribir(ruta, pid=999)  # otro proceso lo dio por vencido y lo tomó
    antes = ruta.read_text(encoding="utf-8")
    assert candado.renovar() is False
    assert ruta.read_text(encoding="utf-8") == antes


def test_renovar_sin_tomar_no_hace_nada(tmp_path):
    ruta = tmp_path / "robot.lock"
    assert Bloqueo(ruta, reloj=_reloj).renovar() is False
    assert not ruta.exists()
