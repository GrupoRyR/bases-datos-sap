from __future__ import annotations

import re

import firma

# Vector de prueba del contrato (docs/contrato-robot.md §3).
SECRETO = "robot-secreto-de-prueba"
TIMESTAMP = 1792152000
NONCE = "9f86d081884c7d659a2feaa0c55ad015"
RUTA = "/api/robot/v1/corridas"
CUERPO = b'{"conjunto":"CARTERA"}'
SHA_CUERPO = "c04ff2072e7cfb7c308adf681b5c060ec271b48124895c3310a9a49e912091b9"
FIRMA = "sha256=29d3895ed1dec41dc0c471b2a3e0b148e975b479698a86a13833814b661e0dd2"

RE_NONCE = re.compile(r"^[0-9a-f]{32}$")


def test_sha256_del_cuerpo_del_vector() -> None:
    assert firma.sha256_hex(CUERPO) == SHA_CUERPO


def test_cadena_canonica_sin_salto_final() -> None:
    cadena = firma.cadena_canonica(TIMESTAMP, NONCE, RUTA, CUERPO)

    assert cadena == f"{TIMESTAMP}\n{NONCE}\nPOST\n{RUTA}\n{SHA_CUERPO}"
    assert not cadena.endswith("\n")


def test_firma_del_vector_del_contrato() -> None:
    assert firma.firmar(SECRETO, TIMESTAMP, NONCE, RUTA, CUERPO) == FIRMA


def test_encabezados_con_hora_y_nonce_dados() -> None:
    encabezados = firma.encabezados(
        "r2026a", SECRETO, RUTA, CUERPO, timestamp=TIMESTAMP, nonce=NONCE
    )

    assert encabezados == {
        "X-Robot-Key": "r2026a",
        "X-Robot-Timestamp": str(TIMESTAMP),
        "X-Robot-Nonce": NONCE,
        "X-Robot-Signature": FIRMA,
    }


def test_encabezados_generan_hora_y_nonce_nuevos() -> None:
    uno = firma.encabezados("r2026a", SECRETO, RUTA, CUERPO)
    otro = firma.encabezados("r2026a", SECRETO, RUTA, CUERPO)

    assert RE_NONCE.match(uno["X-Robot-Nonce"])
    assert uno["X-Robot-Nonce"] != otro["X-Robot-Nonce"]
    assert uno["X-Robot-Timestamp"].isdigit()
    assert uno["X-Robot-Signature"] == firma.firmar(
        SECRETO, int(uno["X-Robot-Timestamp"]), uno["X-Robot-Nonce"], RUTA, CUERPO
    )


def test_nonce_son_32_hexadecimales_en_minuscula() -> None:
    nonces = {firma.nuevo_nonce() for _ in range(50)}

    assert len(nonces) == 50
    assert all(RE_NONCE.match(n) for n in nonces)
