from __future__ import annotations

import gzip
import json
import logging

import pytest

import firma
import registro
from api import (
    ApiCliente,
    ApiError,
    ApiRechazo,
    CorridaAbierta,
    ErrorRed,
    FirmaRechazada,
    LotesFaltantes,
)
from config import ApiConfig
from fake_api import ApiFalsa

BASE = "https://bases.prueba.test"
KEY_ID = "r2026a"
SECRETO = "secreto-robot-de-prueba-0123456789abcdef"
EXTRAIDA = "2026-10-23T10:41:30-05:00"


@pytest.fixture
def servidor() -> ApiFalsa:
    return ApiFalsa(base_url=BASE, key_id=KEY_ID, secret=SECRETO)


def _cliente(servidor: ApiFalsa, falso, *, url: str = BASE, secreto: str = SECRETO, **kwargs) -> ApiCliente:
    kwargs.setdefault("reloj", servidor.reloj)
    return ApiCliente(
        ApiConfig(url=url, key_id=KEY_ID, secret=secreto),
        transporte=servidor,
        dormir=falso.sleep,
        **kwargs,
    )


@pytest.fixture
def cliente(servidor: ApiFalsa, reloj) -> ApiCliente:
    return _cliente(servidor, reloj)


def _iniciar_maestros(cliente: ApiCliente, **kwargs) -> dict:
    datos = {
        "conjunto": "MAESTROS",
        "empresa": "SGX",
        "tipo": "solicitud",
        "partes": {"vendedores": "todo"},
        "solicitudes": [],
        "fecha_corte": None,
        "extraida_en": EXTRAIDA,
    }
    datos.update(kwargs)
    return cliente.iniciar_corrida(**datos)


def _lote(cliente: ApiCliente, run_id: int, batch: int, filas: int = 2, parte: str = "vendedores") -> dict:
    return cliente.enviar_lote(
        run_id,
        batch=batch,
        parte=parte,
        columns=["codigo", "nombre", "activo"],
        rows=[[batch * 1000 + i, f"Vendedor ñ {i}", True] for i in range(filas)],
    )


# ------------------------------------------------------------- camino feliz
def test_tomar_solicitudes(cliente: ApiCliente, servidor: ApiFalsa) -> None:
    for sid in (118, 121):
        servidor.encolar_solicitud(
            {"id": sid, "empresa": "SGX", "conjunto": "MAESTROS", "parte": "vendedores", "desde": {}}
        )

    tomadas = cliente.tomar_solicitudes(max_solicitudes=1)

    assert [s["id"] for s in tomadas] == [118]
    assert servidor.peticiones_a("tomar")[0].datos == {"max": 1}
    assert cliente.tomar_solicitudes() == [{"id": 121, "empresa": "SGX", "conjunto": "MAESTROS", "parte": "vendedores", "desde": {}}]
    assert cliente.tomar_solicitudes() == []


def test_iniciar_corrida(cliente: ApiCliente, servidor: ApiFalsa) -> None:
    servidor.encolar_solicitud({"id": 118, "empresa": "SGX", "conjunto": "MAESTROS", "parte": "vendedores"})
    cliente.tomar_solicitudes()

    respuesta = _iniciar_maestros(cliente, solicitudes=[118])

    assert respuesta["run_id"] == 1
    assert respuesta["estado"] == "abierta"
    assert servidor.peticiones_a("iniciar")[0].datos == {
        "conjunto": "MAESTROS",
        "empresa": "SGX",
        "tipo": "solicitud",
        "partes": {"vendedores": "todo"},
        "solicitudes": [118],
        "fecha_corte": None,
        "extraida_en": EXTRAIDA,
    }


def test_enviar_lote_y_cerrar_sin_conteo_sap(cliente: ApiCliente, servidor: ApiFalsa) -> None:
    run_id = _iniciar_maestros(cliente)["run_id"]

    assert _lote(cliente, run_id, 1, filas=3) == {"batch": 1, "rows": 3}
    respuesta = cliente.cerrar_corrida(run_id, batches=1, filas={"vendedores": 3})

    assert respuesta["estado"] == "cerrada"
    assert "conteo_sap" not in servidor.peticiones_a("cerrar")[0].datos
    corrida = servidor.corridas[run_id]
    assert corrida.estado == "cerrada"
    assert corrida.filas("vendedores")[0] == {"codigo": 1000, "nombre": "Vendedor ñ 0", "activo": True}


def test_cerrar_completa_con_conteo_sap(cliente: ApiCliente, servidor: ApiFalsa) -> None:
    run_id = cliente.iniciar_corrida(
        conjunto="CARTERA",
        empresa="SDC",
        tipo="completa",
        partes={"cartera": "todo"},
        solicitudes=[],
        fecha_corte="2026-10-22",
        extraida_en=EXTRAIDA,
    )["run_id"]
    cliente.enviar_lote(run_id, batch=1, parte="cartera", columns=["codigo_sn", "saldo"], rows=[["C1", "10.50"]])

    respuesta = cliente.cerrar_corrida(run_id, batches=1, filas={"cartera": 1}, conteo_sap={"cartera": 1})

    assert respuesta["conteo"]["cartera"]["cuadra"] is True
    assert servidor.peticiones_a("cerrar")[0].datos["conteo_sap"] == {"cartera": 1}


def test_iniciar_ventas_manda_la_ventana_y_los_demas_no_la_mandan(cliente: ApiCliente, servidor: ApiFalsa) -> None:
    run_id = cliente.iniciar_corrida(
        conjunto="VENTAS", empresa="SGX", tipo="solicitud", partes={"ventas": "todo"},
        solicitudes=[], fecha_corte=None, extraida_en=EXTRAIDA, ventana_desde="2026-09-24",
    )["run_id"]
    assert servidor.peticiones_a("iniciar")[0].datos["ventana_desde"] == "2026-09-24"
    assert servidor.corridas[run_id].ventana_desde == "2026-09-24"
    _iniciar_maestros(cliente)
    assert "ventana_desde" not in servidor.peticiones_a("iniciar")[1].datos


def test_fallar_corrida_recorta_el_error_a_mil_caracteres(cliente: ApiCliente, servidor: ApiFalsa) -> None:
    run_id = _iniciar_maestros(cliente)["run_id"]

    respuesta = cliente.fallar_corrida(run_id, "x" * 1500)

    assert respuesta == {"run_id": run_id, "estado": "fallida"}
    assert len(servidor.peticiones_a("fallar")[0].datos["error"]) == 1000
    assert servidor.corridas[run_id].estado == "fallida"


# ---------------------------------------------------------- cuerpo y firma
def test_gzip_por_defecto_y_cuerpo_determinista(cliente: ApiCliente, servidor: ApiFalsa) -> None:
    run_id = _iniciar_maestros(cliente)["run_id"]

    _lote(cliente, run_id, 1)
    reenvio = _lote(cliente, run_id, 1)

    primero, segundo = servidor.peticiones_a("lote")
    assert primero.headers["content-encoding"] == "gzip"
    assert primero.headers["content-type"] == "application/json"
    assert primero.cuerpo[:2] == b"\x1f\x8b"
    assert gzip.decompress(primero.cuerpo).decode("utf-8") == json.dumps(
        primero.datos, ensure_ascii=False, separators=(",", ":")
    )
    assert primero.cuerpo == segundo.cuerpo
    assert primero.headers["x-robot-nonce"] != segundo.headers["x-robot-nonce"]
    assert reenvio == {"batch": 1, "rows": 2, "duplicate": True}


def test_sin_compresion(servidor: ApiFalsa, reloj) -> None:
    cliente = _cliente(servidor, reloj, comprimir=False)

    cliente.tomar_solicitudes()

    peticion = servidor.peticiones[0]
    assert "content-encoding" not in peticion.headers
    assert peticion.cuerpo == b'{"max":20}'


def test_la_ruta_firmada_excluye_el_subdirectorio_de_la_base(reloj) -> None:
    servidor = ApiFalsa(base_url="https://srv.prueba.test/bases", key_id=KEY_ID, secret=SECRETO)
    cliente = _cliente(servidor, reloj, url="https://srv.prueba.test/bases")

    assert cliente.tomar_solicitudes() == []

    peticion = servidor.peticiones[0]
    assert peticion.url == "https://srv.prueba.test/bases/api/robot/v1/solicitudes/tomar"
    assert peticion.status == 200
    h = peticion.headers
    assert h["x-robot-signature"] == firma.firmar(
        SECRETO, int(h["x-robot-timestamp"]), h["x-robot-nonce"], "/api/robot/v1/solicitudes/tomar", peticion.cuerpo
    )


def test_el_secreto_queda_registrado_para_los_logs(cliente: ApiCliente) -> None:
    assert SECRETO in registro._SECRETOS


def test_el_log_no_lleva_secreto_firma_ni_datos(
    cliente: ApiCliente, servidor: ApiFalsa, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="bases_sap")
    run_id = _iniciar_maestros(cliente)["run_id"]
    servidor.programar_fallas("lote", 1, status=503)

    _lote(cliente, run_id, 1)

    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "/api/robot/v1/corridas/1/lotes" in texto
    assert "503" in texto
    assert SECRETO not in texto
    assert "Vendedor" not in texto
    for peticion in servidor.peticiones:
        assert peticion.headers["x-robot-signature"] not in texto


# ---------------------------------------------------------------- reintentos
def test_reintenta_503_con_la_misma_carga_y_firma_nueva(cliente: ApiCliente, servidor: ApiFalsa, reloj) -> None:
    servidor.programar_fallas("tomar", 2, status=503)

    assert cliente.tomar_solicitudes() == []

    intentos = servidor.peticiones_a("tomar")
    assert len(intentos) == 3
    assert reloj.esperas == [2, 4]
    assert len({p.cuerpo for p in intentos}) == 1
    assert len({p.headers["x-robot-nonce"] for p in intentos}) == 3


def test_se_rinde_despues_de_cuatro_intentos(cliente: ApiCliente, servidor: ApiFalsa, reloj) -> None:
    servidor.programar_fallas("tomar", 4, status=502)

    with pytest.raises(ApiError) as error:
        cliente.tomar_solicitudes()

    assert error.value.status == 502
    assert len(servidor.peticiones_a("tomar")) == 4
    assert reloj.esperas == [2, 4, 8]


def test_reintenta_errores_de_red_y_luego_se_rinde(cliente: ApiCliente, servidor: ApiFalsa, reloj) -> None:
    servidor.programar_fallas("tomar", 1, red=True)
    assert cliente.tomar_solicitudes() == []
    assert reloj.esperas == [2]

    servidor.programar_fallas("tomar", 4, red=True)
    with pytest.raises(ErrorRed):
        cliente.tomar_solicitudes()
    assert len(servidor.peticiones_a("tomar")) == 2 + 4


@pytest.mark.parametrize(
    ("retry_after", "espera"),
    [({"Retry-After": "7"}, 7), ({}, 30), ({"Retry-After": "500"}, 120), ({"Retry-After": "basura"}, 30)],
)
def test_429_respeta_retry_after(cliente: ApiCliente, servidor: ApiFalsa, reloj, retry_after, espera) -> None:
    servidor.programar_fallas("tomar", 1, status=429, headers=retry_after)

    assert cliente.tomar_solicitudes() == []

    assert reloj.esperas == [espera]


def test_429_cuenta_contra_los_mismos_intentos(cliente: ApiCliente, servidor: ApiFalsa, reloj) -> None:
    servidor.programar_fallas("tomar", 2, status=503)
    servidor.programar_fallas("tomar", 2, status=429, headers={"Retry-After": "5"})

    with pytest.raises(ApiError) as error:
        cliente.tomar_solicitudes()

    assert error.value.status == 429
    assert reloj.esperas == [2, 4, 5]


def test_401_lanza_firma_rechazada_sin_reintentar(servidor: ApiFalsa, reloj) -> None:
    cliente = _cliente(servidor, reloj, secreto="otro-secreto-que-no-es-el-del-servidor")

    with pytest.raises(FirmaRechazada) as error:
        cliente.tomar_solicitudes()

    assert error.value.status == 401
    assert "BASES_SAP_ROBOT_SECRET" in str(error.value)
    assert "hora" in str(error.value)
    assert len(servidor.peticiones) == 1
    assert reloj.esperas == []


def test_reloj_desfasado_mas_de_cinco_minutos_da_401(servidor: ApiFalsa, reloj) -> None:
    cliente = _cliente(servidor, reloj, reloj=lambda: servidor.hora - 301)

    with pytest.raises(FirmaRechazada):
        cliente.tomar_solicitudes()

    assert _cliente(servidor, reloj, reloj=lambda: servidor.hora + 299).tomar_solicitudes() == []


def test_413_no_se_reintenta(cliente: ApiCliente, servidor: ApiFalsa, reloj) -> None:
    servidor.programar_fallas("tomar", 1, status=413)

    with pytest.raises(ApiError) as error:
        cliente.tomar_solicitudes()

    assert error.value.status == 413
    assert len(servidor.peticiones) == 1


def test_cuerpo_de_mas_de_10_mb_no_se_envia(servidor: ApiFalsa, reloj) -> None:
    cliente = _cliente(servidor, reloj, comprimir=False)

    with pytest.raises(ApiError, match="10 MB"):
        cliente.enviar_lote(1, batch=1, parte="vendedores", columns=["nombre"], rows=[["x" * 11_000_000]])

    assert servidor.peticiones == []


# ---------------------------------------------------------- rechazos de la API
def test_corrida_abierta_trae_el_run_id(cliente: ApiCliente) -> None:
    run_id = _iniciar_maestros(cliente)["run_id"]

    with pytest.raises(CorridaAbierta) as error:
        _iniciar_maestros(cliente, partes={"marcas": "todo"})

    assert error.value.status == 409
    assert error.value.run_id == run_id


def test_iniciar_invalido_es_api_rechazo(cliente: ApiCliente) -> None:
    with pytest.raises(ApiRechazo) as error:
        _iniciar_maestros(cliente, partes={"cartera": "todo"})

    assert error.value.status == 422
    assert error.value.errors


def test_lotes_faltantes_traen_la_lista(cliente: ApiCliente, servidor: ApiFalsa) -> None:
    run_id = _iniciar_maestros(cliente)["run_id"]
    _lote(cliente, run_id, 1)
    _lote(cliente, run_id, 3)

    with pytest.raises(LotesFaltantes) as error:
        cliente.cerrar_corrida(run_id, batches=3, filas={"vendedores": 6})

    assert error.value.faltan == [2]
    assert servidor.corridas[run_id].estado == "abierta"

    _lote(cliente, run_id, 2)
    assert cliente.cerrar_corrida(run_id, batches=3, filas={"vendedores": 6})["estado"] == "cerrada"


def test_mismo_lote_con_otro_cuerpo_es_rechazo(cliente: ApiCliente) -> None:
    run_id = _iniciar_maestros(cliente)["run_id"]
    _lote(cliente, run_id, 1, filas=2)

    with pytest.raises(ApiRechazo) as error:
        _lote(cliente, run_id, 1, filas=3)

    assert error.value.status == 409


@pytest.mark.parametrize(
    ("parte", "columns", "rows"),
    [
        ("marcas", ["codigo"], [[1]]),
        ("vendedores", ["codigo", "nombre"], [[1]]),
        ("vendedores", ["codigo"], [[i] for i in range(1001)]),
    ],
)
def test_lote_invalido_es_422(cliente: ApiCliente, parte, columns, rows) -> None:
    run_id = _iniciar_maestros(cliente)["run_id"]

    with pytest.raises(ApiRechazo) as error:
        cliente.enviar_lote(run_id, batch=1, parte=parte, columns=columns, rows=rows)

    assert error.value.status == 422
    assert error.value.message


def test_cerrar_completa_sin_conteo_sap_es_422(cliente: ApiCliente) -> None:
    run_id = cliente.iniciar_corrida(
        conjunto="CARTERA", empresa="SGX", tipo="completa", partes={"cartera": "todo"},
        solicitudes=[], fecha_corte="2026-10-22", extraida_en=EXTRAIDA,
    )["run_id"]
    cliente.enviar_lote(run_id, batch=1, parte="cartera", columns=["codigo_sn"], rows=[["C1"]])

    with pytest.raises(ApiRechazo) as error:
        cliente.cerrar_corrida(run_id, batches=1, filas={"cartera": 1})

    assert error.value.status == 422
    assert "conteo_sap" in error.value.errors


def test_parte_todo_sin_filas_falla_la_corrida(cliente: ApiCliente, servidor: ApiFalsa) -> None:
    run_id = _iniciar_maestros(cliente)["run_id"]

    with pytest.raises(ApiRechazo) as error:
        cliente.cerrar_corrida(run_id, batches=0, filas={"vendedores": 0})

    assert error.value.status == 422
    assert servidor.corridas[run_id].estado == "fallida"


def test_la_api_falsa_rechaza_un_nonce_repetido(servidor: ApiFalsa) -> None:
    cuerpo = b'{"max":1}'
    ruta = "/api/robot/v1/solicitudes/tomar"
    encabezados = firma.encabezados(KEY_ID, SECRETO, ruta, cuerpo, timestamp=int(servidor.hora))

    assert servidor(BASE + ruta, encabezados, cuerpo, 5).status == 200
    repetida = servidor(BASE + ruta, encabezados, cuerpo, 5)

    assert repetida.status == 401
    assert json.loads(repetida.cuerpo) == {"message": "Firma inválida."}


# ------------------------------------------------------------ transporte real
class _RespuestaUrllib:
    status = 201
    headers = {"Content-Type": "application/json"}

    def __enter__(self) -> "_RespuestaUrllib":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"ok":true}'


def test_transporte_urllib_envia_post(monkeypatch: pytest.MonkeyPatch) -> None:
    import api

    vistas = []

    def urlopen(peticion, timeout):
        vistas.append((peticion, timeout))
        return _RespuestaUrllib()

    monkeypatch.setattr(api, "_abrir", urlopen)

    respuesta = api.transporte_urllib(BASE + "/x", {"X-Robot-Key": KEY_ID}, b"{}", 12)

    assert respuesta == api.Respuesta(201, {"content-type": "application/json"}, b'{"ok":true}')
    peticion, timeout = vistas[0]
    assert (peticion.get_method(), peticion.data, timeout) == ("POST", b"{}", 12)
    assert peticion.get_header("X-robot-key") == KEY_ID


def test_transporte_urllib_devuelve_los_errores_http(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import urllib.error
    from email.message import Message

    import api

    encabezados = Message()
    encabezados["Retry-After"] = "9"

    def urlopen(peticion, timeout):
        raise urllib.error.HTTPError(peticion.full_url, 429, "Too Many", encabezados, io.BytesIO(b"{}"))

    monkeypatch.setattr(api, "_abrir", urlopen)

    respuesta = api.transporte_urllib(BASE + "/x", {}, b"{}", 5)

    assert (respuesta.status, respuesta.headers, respuesta.cuerpo) == (429, {"retry-after": "9"}, b"{}")


@pytest.mark.parametrize("falla", [TimeoutError("timed out"), ConnectionResetError("reset")])
def test_transporte_urllib_sin_respuesta_es_error_red(monkeypatch: pytest.MonkeyPatch, falla) -> None:
    import urllib.error

    import api

    def urlopen(peticion, timeout):
        raise urllib.error.URLError(falla) if isinstance(falla, TimeoutError) else falla

    monkeypatch.setattr(api, "_abrir", urlopen)

    with pytest.raises(ErrorRed):
        api.transporte_urllib(BASE + "/x", {}, b"{}", 5)


# ------------------------------------------------- respuestas que se pierden
def test_iniciar_recupera_su_corrida_si_se_perdio_la_respuesta(
    cliente: ApiCliente, servidor: ApiFalsa
) -> None:
    servidor.programar_fallas("iniciar", status=502, despues=True)

    respuesta = _iniciar_maestros(cliente)

    assert respuesta["run_id"] == 1
    assert respuesta["recuperada"] is True
    assert len(servidor.corridas) == 1


def test_corrida_abierta_en_el_primer_intento_sigue_siendo_error(cliente: ApiCliente) -> None:
    _iniciar_maestros(cliente)

    with pytest.raises(CorridaAbierta):
        _iniciar_maestros(cliente)


def test_cerrar_recupera_el_cierre_si_se_perdio_la_respuesta(
    cliente: ApiCliente, servidor: ApiFalsa
) -> None:
    run_id = _iniciar_maestros(cliente)["run_id"]
    _lote(cliente, run_id, 1)
    servidor.programar_fallas("cerrar", red=True, despues=True)

    respuesta = cliente.cerrar_corrida(run_id, batches=1, filas={"vendedores": 2})

    assert respuesta["estado"] == "cerrada"
    assert respuesta["recuperada"] is True


def test_fallar_recupera_la_falla_si_se_perdio_la_respuesta(
    cliente: ApiCliente, servidor: ApiFalsa
) -> None:
    run_id = _iniciar_maestros(cliente)["run_id"]
    servidor.programar_fallas("fallar", status=504, despues=True)

    respuesta = cliente.fallar_corrida(run_id, "VPN no conectó")

    assert respuesta["estado"] == "fallida"


def test_el_422_lleva_el_detalle_de_las_filas(cliente: ApiCliente, servidor: ApiFalsa) -> None:
    run_id = _iniciar_maestros(cliente)["run_id"]
    servidor.programar_fallas(
        "lote",
        status=422,
        datos={"message": "Datos inválidos.", "errors": {"rows.12.codigo": ["Obligatorio."]}},
    )

    with pytest.raises(ApiRechazo) as error:
        _lote(cliente, run_id, 1)

    assert "rows.12.codigo: Obligatorio." in str(error.value)


def test_una_redireccion_no_se_sigue_y_explica_la_url(cliente: ApiCliente, servidor: ApiFalsa) -> None:
    servidor.programar_fallas("tomar", status=301, headers={"Location": "https://www.bases.prueba.test/"})

    with pytest.raises(ApiError, match="BASES_SAP_API_URL"):
        cliente.tomar_solicitudes()

    assert len(servidor.peticiones_a("tomar")) == 1
