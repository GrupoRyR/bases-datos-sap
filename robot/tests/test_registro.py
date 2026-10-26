from __future__ import annotations

import logging
import sys
from pathlib import Path

import registro


def _registro(mensaje: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("bases_sap.prueba", logging.INFO, __file__, 1, mensaje, args, None)


def test_un_secreto_registrado_no_sale_en_el_log() -> None:
    registro.registrar_secreto("secreto-robot-de-prueba")
    record = _registro("Firmando con %s", "secreto-robot-de-prueba")

    registro._RedactarSecretos().filter(record)

    assert record.getMessage() == "Firmando con ***"


def test_secretos_muy_cortos_no_se_registran() -> None:
    registro.registrar_secreto("abc")
    registro.registrar_secreto(None)

    assert registro._SECRETOS == []


def test_la_opcion_p_de_la_linea_de_comandos_se_oculta() -> None:
    record = _registro("Ejecutando: sccli enable -n vpn -u yo -p clave123 --password otra")

    registro._RedactarSecretos().filter(record)

    mensaje = record.getMessage()
    assert "clave123" not in mensaje
    assert "otra" not in mensaje
    assert "-p ***" in mensaje


def test_configurar_escribe_robot_log_sin_secretos(tmp_path: Path) -> None:
    logger = registro.configurar()
    try:
        registro.registrar_secreto("clave-hana-prueba")
        registro.obtener("prueba").info("Conectando con clave-hana-prueba")
        for handler in logger.handlers:
            handler.flush()

        assert logger.name == "bases_sap"
        contenido = (tmp_path / "logs" / "robot.log").read_text(encoding="utf-8")
        assert "Conectando con ***" in contenido
        assert "clave-hana-prueba" not in contenido
    finally:
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)


def test_la_traza_de_una_excepcion_tampoco_lleva_secretos() -> None:
    registro.registrar_secreto("secreto-en-la-traza")
    try:
        raise RuntimeError("falló con secreto-en-la-traza")
    except RuntimeError:
        record = logging.LogRecord(
            "bases_sap.prueba", logging.ERROR, __file__, 1, "fallo", (), sys.exc_info()
        )

    registro._RedactarSecretos().filter(record)
    texto = logging.Formatter().format(record)

    assert "secreto-en-la-traza" not in texto
    assert "RuntimeError" in texto
