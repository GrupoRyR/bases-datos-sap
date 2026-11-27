"""Robot de Bases de datos SAP: extrae de SAP HANA y envía a la API de la app.

Flujo (dos fases, a propósito):
    FASE 1 - con VPN:  conectar Sophos -> todas las consultas de SAP -> bajar la VPN
    FASE 2 - sin VPN:  tomar las solicitudes (/solicitudes/tomar) -> CSV en
                       BASES_SAP_CSV_DIR -> corridas en la API -> retención

Las solicitudes se toman después de extraer porque vencen 30 minutos después
de tomarlas (contrato §7.3) y la fase 1 puede tardar más.

Se separan porque el perfil VPN es de túnel completo (0.0.0.0/0): con la VPN
arriba no hay salida a internet. Se extrae todo, se baja el túnel y recién ahí
se escribe y se envía.

Las tablas que solo van a la carpeta (archivo, catálogo, diagnóstico, plan §5)
siguen las mismas dos fases y nunca llaman a la API.

Uso:
    python run_robot.py --completa                 # nocturna: MAESTROS, CARTERA, VENTAS y PEDIDOS de SGX y SDC,
                                                   # PRODUCCION solo de SGX,
                                                   # más los registros del archivo (AUDITORIA, ORTT);
                                                   # si salió bien, la comparación diaria con SAP
    python run_robot.py --completa --empresa SGX   # solo una empresa (se puede repetir)
    python run_robot.py --completa --sin-vpn       # asume la VPN ya conectada a mano
    python run_robot.py --archivo fotos            # domingo 03:00: fotos del archivo y catálogo
    python run_robot.py --archivo registros        # solo los registros del archivo
    python run_robot.py --catalogo                 # solo el catálogo
    python run_robot.py --diagnostico              # cifras de MAESTROS, CARTERA, VENTAS, PEDIDOS y
                                                   # PRODUCCION (solo SGX), sin enviar
    python run_robot.py --completa --forzar        # no espera la franja bloqueada
    python run_robot.py --carga-produccion --desde 2026-08-01
                                                   # una vez, a mano: PRODUCCION de SGX desde esa
                                                   # fecha en vez de la ventana de HANA (contrato §12)
    python run_robot.py --historico-ventas --desde 2025-01 [--hasta 2026-06]
                                                   # una vez, a mano: VENTAS mes por mes antes de la
                                                   # ventana nocturna (historico.py, contrato §10.4)
    python run_robot.py --complemento-ventas --desde 2025-01 [--hasta 2026-06]
                                                   # a mano: llena kilos y codigo_envio de VENTAS
                                                   # mes por mes, como el histórico (complemento.py,
                                                   # orden 016). No corre si ventas.sql no trae los
                                                   # kilos
    python run_robot.py --comparar [--empresa SGX] [--conjunto VENTAS]
                                                   # solo lee: totales de MAESTROS, CARTERA y VENTAS
                                                   # (VENTAS hasta ayer) en SAP contra los de la app
                                                   # (/totales), y el resultado a /comparaciones
                                                   # (comparar.py)
    python run_robot.py --tras-despliegue          # lo lanza la revisión de cada minuto después de
                                                   # actualizarse (autoactualizar.py): corre los
                                                   # complementos pendientes de robot/complementos.toml
                                                   # y al final la comparación de VENTAS

Un solo proceso del robot a la vez (bloqueo.Bloqueo, robot/state/robot.lock): la
completa y el archivo esperan hasta 20 minutos a que lo suelte otro (la
revisión de solicitudes que está terminando); el catálogo y el diagnóstico, que
los corre el usuario, no esperan. Si la completa o el archivo arrancan dentro de
una franja bloqueada de los otros robots (±15 minutos), esperan a que pase,
salvo con --forzar (--tras-despliegue nunca lo usa). El histórico, el complemento de ventas,
la comparación y --tras-despliegue, además, esperan a que su fase
con VPN quepa entera antes de la siguiente franja (bloqueo.inicio_hueco) y renuevan el
candado por cada tramo, porque pueden durar más que su vigencia.

Salida: 0 todo bien, 1 algún fallo (se avisa por correo, salvo en el
diagnóstico, que lo corre el usuario), 2 configuración incompleta, 130
cancelado con Ctrl+C.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable

import archivo
import autoactualizar
import bloqueo
import catalogo
import comparar
import complemento
import config
import diagnostico
import envio
import extraccion
import hana
import historico
import notificar
import registro
from api import ApiCliente
from carpeta import Carpeta
from config import EMPRESAS, Config, ConfigError, HanaConfig, cargar_config
from trabajos import (
    Trabajo,
    TrabajoInvalido,
    separar_solo_precios,
    trabajo_carga_produccion,
    trabajos_completos,
    trabajos_de_solicitudes,
)
from vpn import RobotVPN

SOLICITUDES_POR_PAGINA = 20
MAX_PAGINAS = 5
ESPERA_CANDADO = timedelta(minutes=20)  # la nocturna y el domingo esperan a la revisión que termina
TRAS_DESPLIEGUE = "tras despliegue"
# After a deploy or a complement only VENTAS is compared (the complements change it); the daily
# comparison after a good completa compares the three (_comparacion_diaria).
CONJUNTOS_TRAS_DESPLIEGUE = ("VENTAS",)
# Options a pending complement (robot/complementos.toml) may carry, per mode. Anything else,
# --forzar, --sin-vpn or another mode included, makes the entry invalid.
OPCIONES_COMPLEMENTO = {"complemento-ventas": ("--desde", "--hasta", "--empresa")}

log = registro.obtener("robot")


def guardar_estado(**datos: Any) -> None:
    """Estado local de la última ejecución. Nunca lleva datos de SAP."""
    try:
        config.STATE_DIR.mkdir(parents=True, exist_ok=True)
        datos["actualizado_en"] = datetime.now(timezone.utc).isoformat()
        (config.STATE_DIR / "ultima_ejecucion.json").write_text(
            json.dumps(datos, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except OSError:
        log.warning("No se pudo guardar el estado local.", exc_info=True)


def ejecutar_trabajos(
    cfg: Config,
    trabajos: list[Trabajo],
    *,
    api: ApiCliente | None = None,
    carpeta: Carpeta | None = None,
    robot_vpn: Any = None,
    conectar: Callable[..., Any] = hana.conectar,
    sin_vpn: bool = False,
    ahora: Callable[[], datetime] = config.ahora,
    antes_de_enviar: Callable[[list[extraccion.Resultado]], None] | None = None,
    registros: archivo.Archivo | None = None,
) -> list[tuple[str, str]]:
    """Fase 1 (extraer), fase 2 (CSV y API) y retención de la carpeta. Devuelve los fallos.

    `antes_de_enviar(resultados)` corre con la VPN ya abajo, antes del envío
    (la nocturna toma ahí las solicitudes). `registros` lee el archivo en la
    misma sesión de VPN y lo escribe en la fase 2; sus fallos van a la lista,
    pero nunca frenan MAESTROS, CARTERA, VENTAS ni PEDIDOS.
    """
    api = api or ApiCliente(cfg.api)
    carpeta = carpeta or Carpeta(cfg.csv_dir)
    momento = ahora()  # hora de la ejecución: nombre de los CSV

    resultados = extraccion.extraer(
        cfg, trabajos, robot_vpn=robot_vpn, conectar=conectar, sin_vpn=sin_vpn, ahora=ahora,
        extra=registros,
    )
    if antes_de_enviar is not None:
        antes_de_enviar(resultados)
    fallos = envio.enviar(api, carpeta, resultados, momento=momento, ahora=ahora)
    if registros is not None:
        fallos += registros.escribir()
    try:
        carpeta.purgar_corridas(momento.date())
    except OSError as exc:
        log.error("Falló la retención de la carpeta: %s", exc)
        fallos.append(("CARPETA", f"Falló la retención de la carpeta: {exc}"))
    try:
        carpeta.purgar_temporales()
    except OSError as exc:
        log.error("Falló la limpieza de temporales de la carpeta: %s", exc)
        fallos.append(("CARPETA", f"Falló la limpieza de temporales de la carpeta: {exc}"))
    return fallos


def _tomar_solicitudes(api: ApiCliente) -> list[dict[str, Any]]:
    """Solicitudes listas, con la VPN abajo. Si la API falla, la nocturna sigue sin ellas."""
    tomadas: list[dict[str, Any]] = []
    for _ in range(MAX_PAGINAS):
        try:
            pagina = api.tomar_solicitudes(SOLICITUDES_POR_PAGINA)
        except Exception as exc:
            log.error("No se pudieron tomar las solicitudes; se sigue sin ellas: %s", exc)
            break
        tomadas.extend(pagina)
        if len(pagina) < SOLICITUDES_POR_PAGINA:
            break
    if tomadas:
        log.info("Solicitudes tomadas: %s.", ", ".join(str(s.get("id")) for s in tomadas))
    return tomadas


def _asignar_solicitudes(
    trabajos: Iterable[Trabajo], tomadas: list[dict[str, Any]], hoy: date, hana: HanaConfig
) -> tuple[list[tuple[str, str]], list[extraccion.Resultado]]:
    """Pega cada solicitud tomada a la corrida completa de su empresa y conjunto (§7.3).

    Ya no se extrae nada: una solicitud de una empresa que no está en esta
    corrida queda tomada y la API la vence. Una inválida va a los fallos. Una de
    solo precios de una empresa sin lista no cabe en su corrida (va sin precios):
    sale como resultado ya fallido, para que se envíe fallida con el motivo.
    """
    por_grupo = {(t.empresa, t.conjunto): t for t in trabajos}
    fallos: list[tuple[str, str]] = []
    validas: list[dict[str, Any]] = []
    for solicitud in tomadas:
        try:
            trabajos_de_solicitudes([solicitud], hoy)  # valida empresa, conjunto, parte y desde
        except TrabajoInvalido as exc:
            log.error("Solicitud inválida: %s", exc)
            fallos.append(("SOLICITUDES", str(exc)))
            continue
        validas.append(solicitud)
    resto, aparte = separar_solo_precios(validas, hana.sin_precios())
    fallidos = [
        extraccion.resultado_fallido(t, hana.empresas[t.empresa].error_sin_precios())
        for t in trabajos_de_solicitudes(aparte, hoy)
    ]
    for solicitud in resto:
        trabajo = por_grupo.get((solicitud["empresa"], solicitud["conjunto"]))
        if trabajo is None:
            log.warning(
                "Solicitud %s (%s %s): esa empresa no está en esta corrida; queda tomada "
                "y la API la vence.", solicitud.get("id"), solicitud["conjunto"], solicitud["empresa"],
            )
            continue
        trabajo.solicitudes.append(solicitud["id"])
    return fallos, fallidos


def _completa(
    cfg: Config,
    empresas: list[str],
    *,
    sin_vpn: bool,
    fabrica_api: Callable[..., ApiCliente],
    fabrica_vpn: Callable[..., Any],
    conectar: Callable[..., Any],
    ahora: Callable[[], datetime],
) -> tuple[list[Trabajo], list[tuple[str, str]]]:
    api = fabrica_api(cfg.api)
    hoy = ahora().date()
    trabajos = trabajos_completos(empresas, hoy, [], cfg.hana.sin_precios())
    log.info("Trabajos: %s.", ", ".join(t.nombre for t in trabajos))
    fallos_solicitudes: list[tuple[str, str]] = []

    def tomar(resultados: list[extraccion.Resultado]) -> None:
        # Los resultados comparten los objetos Trabajo: las solicitudes llegan a la corrida.
        fallos, fallidos = _asignar_solicitudes(trabajos, _tomar_solicitudes(api), hoy, cfg.hana)
        fallos_solicitudes.extend(fallos)
        resultados.extend(fallidos)
        trabajos.extend(r.trabajo for r in fallidos)  # el estado de la ejecución los lista

    fallos = ejecutar_trabajos(
        cfg,
        trabajos,
        api=api,
        robot_vpn=None if sin_vpn else fabrica_vpn(cfg.vpn),
        conectar=conectar,
        sin_vpn=sin_vpn,
        ahora=ahora,
        antes_de_enviar=tomar,
        registros=archivo.Archivo(cfg, "registros", hoy),
    )
    return trabajos, fallos_solicitudes + fallos


def _solo_carpeta(
    cfg: Config,
    empresas: list[str],
    modo: str,
    *,
    sin_vpn: bool,
    fabrica_vpn: Callable[..., Any],
    conectar: Callable[..., Any],
    ahora: Callable[[], datetime],
) -> list[tuple[str, str]]:
    """Archivo, catálogo o diagnóstico: una sesión de VPN para leer y luego escribir.

    Nunca crea el cliente de la API.
    """
    momento = ahora()
    hoy = momento.date()
    pasos: list[Any] = []
    if modo == "archivo fotos":
        pasos = [archivo.Archivo(cfg, "fotos", hoy), catalogo.Catalogo(cfg, hoy)]
    elif modo == "archivo registros":
        pasos = [archivo.Archivo(cfg, "registros", hoy)]
    elif modo == "catalogo":
        pasos = [catalogo.Catalogo(cfg, hoy)]
    elif modo == "diagnostico":
        pasos = [diagnostico.Diagnostico(cfg, momento)]
    else:
        raise ValueError(f"Modo desconocido: {modo}")

    def leer(conn: Any, empresa: str) -> None:
        for paso in pasos:
            paso(conn, empresa)

    fallos = extraccion.sesion(
        cfg, empresas, leer,
        robot_vpn=None if sin_vpn else fabrica_vpn(cfg.vpn), conectar=conectar, sin_vpn=sin_vpn,
    )
    for paso in pasos:  # FASE 2: la VPN ya está abajo
        fallos += paso.escribir()
    if modo == "diagnostico":
        # Lo configurado, no lo probado: la prueba es que el resumen no traiga fallos de HANA.
        log.info("Modo TLS configurado para HANA: %s.", hana.describir_cifrado(cfg.hana))
    return fallos


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Robot de Bases de datos SAP")
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--completa", action="store_true",
                      help="Corrida nocturna: MAESTROS, CARTERA, VENTAS, PEDIDOS y PRODUCCION (solo SGX) completos, "
                           "con la foto de cartera "
                           "y los registros del archivo.")
    modo.add_argument("--archivo", choices=("fotos", "registros"),
                      help="Tablas que solo van a la carpeta: fotos (domingo, con el catálogo) "
                           "o registros.")
    modo.add_argument("--catalogo", action="store_true",
                      help="Catálogo de tablas y columnas de cada empresa (carpeta _CATALOGO).")
    modo.add_argument("--carga-produccion", action="store_true",
                      help="Carga inicial de PRODUCCION desde la fecha de --desde, en vez de la ventana de "
                           "HANA. Solo SGX: PRODUCCION no existe en SDC. Se corre una vez, a mano.")
    modo.add_argument("--historico-ventas", action="store_true",
                      help="Histórico de VENTAS: los meses de --desde a --hasta, uno por corrida, hasta el "
                           "día antes de la ventana nocturna. Se corre una vez, a mano.")
    modo.add_argument("--complemento-ventas", action="store_true",
                      help="Complemento de VENTAS: llena kilos y codigo_envio en los meses de --desde a "
                           "--hasta, uno por corrida, como el histórico. Se corre a mano. Los kilos solo "
                           "son de verdad en SDC (en SGX van vacíos). No corre si "
                           "queries/ventas/ventas.sql no trae la columna de kilos.")
    modo.add_argument("--tras-despliegue", action="store_true",
                      help="Lo lanza la revisión de cada minuto después de actualizarse al commit desplegado: "
                           "corre los complementos pendientes de robot/complementos.toml y al final la "
                           "comparación de VENTAS con SAP (--comparar --conjunto VENTAS). Respeta las franjas y espera el candado; no lleva "
                           "otras opciones.")
    modo.add_argument("--comparar", action="store_true",
                      help="Solo lee: calcula en SAP los totales de MAESTROS, CARTERA y VENTAS (VENTAS de "
                           "2025-01-01 a ayer), o los de --conjunto, y los compara con los de la app (/totales); "
                           "guarda cada resultado en /comparaciones. No escribe en SAP ni abre corridas. Respeta "
                           "las franjas y espera el candado.")
    modo.add_argument("--diagnostico", action="store_true",
                      help="Extrae MAESTROS, CARTERA, VENTAS, PEDIDOS y PRODUCCION (solo SGX) con sus conteos "
                           "a _DIAGNOSTICO; no envía nada.")
    parser.add_argument("--empresa", action="append", choices=EMPRESAS,
                        help="Empresa a procesar (se puede repetir). Por defecto, todas.")
    parser.add_argument("--conjunto", action="append", choices=comparar.CONJUNTOS,
                        help="Conjunto que compara --comparar (se puede repetir). Por defecto, los tres.")
    parser.add_argument("--sin-vpn", action="store_true",
                        help="No gestionar la VPN (asume que ya está activa).")
    parser.add_argument("--forzar", action="store_true",
                        help="Correr la completa, la carga de producción, el histórico o el complemento "
                             "de ventas, la comparación o el archivo aunque sea dentro de una franja bloqueada "
                             "de los otros robots.")
    parser.add_argument("--desde", metavar="AAAA-MM-DD | AAAA-MM",
                        help="Primer día de la carga de producción (AAAA-MM-DD, con --carga-produccion) "
                             "o primer mes del histórico o del complemento de ventas (AAAA-MM, con "
                             "--historico-ventas o --complemento-ventas).")
    parser.add_argument("--hasta", metavar="AAAA-MM",
                        help="Último mes del histórico o del complemento de ventas (solo con "
                             "--historico-ventas o --complemento-ventas). Por defecto, el mes en que empieza "
                             "la ventana nocturna, hasta el día antes.")
    return parser


def _plan_por_meses(
    args: argparse.Namespace, empresas: list[str], ahora: Callable[[], datetime]
) -> tuple[tuple[date, date | None], timedelta]:
    """(--desde, --hasta) del histórico o del complemento de ventas y cuánto estará arriba la
    VPN. Lanza historico.RangoInvalido si el rango no sirve."""
    desde_mes = historico.mes(args.desde)
    hasta_mes = historico.mes(args.hasta) if args.hasta is not None else None
    if args.complemento_ventas:
        complemento.revisar_desde(desde_mes)
    # Con la ventana estimada (reloj del PC): los tramos de verdad salen de la de HANA.
    plan = historico.tramos(desde_mes, hasta_mes, historico.inicio_ventana_estimado(ahora().date()))
    duracion = complemento.duracion_estimada if args.complemento_ventas else historico.duracion_estimada
    return (desde_mes, hasta_mes), duracion(len(plan), len(empresas))


class ComplementoInvalido(ValueError):
    """A pending complement whose arguments run_robot would not accept."""


@dataclass(frozen=True)
class PlanComplemento:
    empresas: list[str]
    desde: date
    hasta: date | None
    estimado: timedelta  # how long its VPN phase takes (complemento.duracion_estimada)


def plan_complemento(
    modo: str, argumentos: list[str], ahora: Callable[[], datetime] = config.ahora
) -> PlanComplemento:
    """Validates a pending complement as `run_robot.py --<modo> <argumentos...>` would, and
    returns its plan. Raises ComplementoInvalido."""
    permitidas = OPCIONES_COMPLEMENTO.get(modo)
    if permitidas is None:
        raise ComplementoInvalido(f"modo {modo!r} no permitido.")
    for token in argumentos:
        if token.startswith("-") and token.split("=", 1)[0] not in permitidas:
            raise ComplementoInvalido(f"{token} no va en un complemento pendiente (solo {', '.join(permitidas)}).")
    parser = _parser()

    def error(mensaje: str) -> None:
        raise ComplementoInvalido(mensaje)

    parser.error = error  # type: ignore[method-assign]
    args = parser.parse_args([f"--{modo}", *argumentos])
    if args.desde is None:
        raise ComplementoInvalido(f"--{modo} necesita --desde AAAA-MM.")
    empresas = list(dict.fromkeys(args.empresa or EMPRESAS))
    try:
        (desde, hasta), estimado = _plan_por_meses(args, empresas, ahora)
    except historico.RangoInvalido as exc:
        raise ComplementoInvalido(str(exc)) from exc
    return PlanComplemento(empresas, desde, hasta, estimado)


def complementos_pendientes(
    ahora: Callable[[], datetime], git: autoactualizar.Ejecutor | None = None
) -> tuple[list[tuple[autoactualizar.Complemento, PlanComplemento]], list[str]]:
    """The pending complements of robot/complementos.toml with their plans, in order, and the
    problems found (invalid entries or an unreadable state). Never raises for those."""
    entradas, problemas = autoactualizar.cargar_complementos(
        lambda modo, argumentos: plan_complemento(modo, argumentos, ahora)
    )
    try:
        estado = autoactualizar.leer_estado()
    except autoactualizar.EstadoIlegible as exc:
        return [], [*problemas, str(exc)]
    lista = autoactualizar.pendientes(entradas, estado, lambda: autoactualizar.commit_actual(git))
    return [(c, plan_complemento(c.modo, list(c.argumentos), ahora)) for c in lista], problemas


def _esperar_hueco(
    cfg: Config,
    modo: str,
    estimado: timedelta,
    forzar: bool,
    ahora: Callable[[], datetime],
    dormir: Callable[[float], None],
    carga: str = "del histórico",
) -> int | None:
    """Histórico, complemento de ventas o --tras-despliegue: espera a que su fase con VPN quepa entera antes de la
    siguiente franja de los otros robots. None si puede seguir; el código de salida si no hay
    hueco. `carga` nombra la carga en los mensajes ("del histórico", "del complemento")."""
    momento = ahora()
    minutos = int(estimado.total_seconds() // 60)
    try:
        inicio = bloqueo.inicio_hueco(momento, estimado, cfg.franjas, cfg.margen_franja_min)
    except ValueError as exc:
        mensaje = (f"{exc} La fase con VPN {carga} tarda unos {minutos} minutos: "
                   "córrelo por partes con --hasta.")
        if forzar:
            log.warning("%s Se corre igual por --forzar.", mensaje)
            return None
        log.error(mensaje)
        guardar_estado(estado="ERROR", modo=modo, etapa="FRANJA", error=mensaje)
        notificar.avisar_fallos(cfg.alertas, [("FRANJA", mensaje)])
        return 1
    if inicio <= momento:
        return None
    franja = bloqueo.en_franja(momento, cfg.franjas, cfg.margen_franja_min)
    if franja:
        mensaje = (f"Son las {momento:%H:%M}, dentro de la franja de las {franja} "
                   f"(±{cfg.margen_franja_min} minutos) en que los otros robots usan la VPN")
    else:
        siguiente = bloqueo.proxima_franja(momento, cfg.franjas, cfg.margen_franja_min)
        hora = bloqueo.en_franja(siguiente, cfg.franjas, cfg.margen_franja_min) if siguiente else "?"
        mensaje = (f"La fase con VPN {carga} tarda unos {minutos} minutos y no cabe antes de la "
                   f"franja de las {hora} (±{cfg.margen_franja_min} minutos) en que los otros robots "
                   "usan la VPN")
    if forzar:
        log.warning("%s: se corre igual por --forzar.", mensaje)
        return None
    log.warning("%s: espero hasta las %s para no cruzarme con ellos.", mensaje, f"{inicio:%H:%M}")
    dormir((inicio - momento).total_seconds())
    return None


def main(
    argv: list[str] | None = None,
    *,
    fabrica_api: Callable[..., ApiCliente] = ApiCliente,
    fabrica_vpn: Callable[..., Any] = RobotVPN,
    conectar: Callable[..., Any] = hana.conectar,
    ahora: Callable[[], datetime] = config.ahora,
    dormir: Callable[[float], None] = time.sleep,
    git: autoactualizar.Ejecutor | None = None,
) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    tras = args.tras_despliegue
    if tras and (args.empresa or args.desde is not None or args.hasta is not None or args.forzar):
        parser.error("--tras-despliegue no lleva --empresa, --desde, --hasta ni --forzar: cada complemento "
                     "pendiente trae sus argumentos y nunca se corre dentro de una franja.")
    if args.conjunto and not args.comparar:
        parser.error("--conjunto va solo con --comparar.")
    empresas = list(dict.fromkeys(args.empresa or EMPRESAS))
    # Los conjuntos de --comparar, en el orden de comparar.CONJUNTOS.
    conjuntos = [c for c in comparar.CONJUNTOS if not args.conjunto or c in args.conjunto]
    carga: Trabajo | None = None
    # (--desde, --hasta) del histórico o del complemento de ventas
    meses: tuple[date, date | None] | None = None
    estimado: timedelta | None = None  # cuánto estará arriba la VPN en el histórico o el complemento
    por_meses = args.historico_ventas or args.complemento_ventas
    opcion = "--complemento-ventas" if args.complemento_ventas else "--historico-ventas"
    if args.desde is not None and not (args.carga_produccion or por_meses):
        parser.error("--desde va solo con --carga-produccion, --historico-ventas o --complemento-ventas.")
    if args.hasta is not None and not por_meses:
        parser.error("--hasta va solo con --historico-ventas o --complemento-ventas.")
    if args.carga_produccion:
        if args.desde is None:
            parser.error("--carga-produccion necesita --desde AAAA-MM-DD.")
        try:
            carga = trabajo_carga_produccion(args.desde, ahora().date())
        except TrabajoInvalido as exc:
            parser.error(str(exc))
        if args.empresa and empresas != [carga.empresa]:
            parser.error(f"--carga-produccion es solo de {carga.empresa}.")
        empresas = [carga.empresa]
    if por_meses:
        if args.desde is None:
            parser.error(f"{opcion} necesita --desde AAAA-MM.")
        try:
            meses, estimado = _plan_por_meses(args, empresas, ahora)
        except historico.RangoInvalido as exc:
            parser.error(str(exc))
    if args.completa:
        modo = "completa"
    elif carga is not None:
        modo = "carga produccion"
    elif meses is not None:
        modo = "complemento ventas" if args.complemento_ventas else "historico ventas"
    elif tras:
        modo = TRAS_DESPLIEGUE
    elif args.comparar:
        modo = "comparar"
    elif args.archivo:
        modo = f"archivo {args.archivo}"
    else:
        modo = "catalogo" if args.catalogo else "diagnostico"
    completa = modo == "completa"

    registro.configurar()
    inicio = time.monotonic()
    log.info("=" * 68)
    log.info("Inicio del robot (%s) para %s%s.", modo, ", ".join(empresas),
             " [SIN VPN]" if args.sin_vpn else "")

    cfg: Config | None = None
    try:
        cfg = cargar_config()
        registro.registrar_secretos(cfg)
        # Solo la completa, la carga, el histórico, el complemento y la comparación hablan con la
        # API; el archivo, el catálogo y el diagnóstico no.
        cfg.validar(requiere_vpn=not args.sin_vpn,
                    requiere_api=completa or carga is not None or meses is not None or tras or args.comparar,
                    empresas=empresas)
        if args.complemento_ventas:
            # Sin la columna de kilos en ventas.sql no corre: antes de esperar la franja o el
            # candado y de subir la VPN (complemento.revisar_consulta).
            complemento.revisar_consulta()
    except ConfigError as exc:
        log.error("Configuración incompleta:\n%s", exc)
        guardar_estado(estado="ERROR", modo=modo, etapa="CONFIGURACION", error=str(exc))
        if cfg is not None and cfg.alertas.habilitada:
            notificar.avisar_fallos(cfg.alertas, [("CONFIGURACION", str(exc))])
        return 2

    # Los modos de las tareas programadas, y la carga, el histórico y el complemento, que son largos:
    # respetan las franjas de los otros robots y esperan el candado. Los dos manuales que
    # hablan con la API avisan por correo como la nocturna: el diagnóstico no.
    if tras:
        planes, problemas = complementos_pendientes(ahora, git)
        for problema in problemas:
            # The per-minute check alerts these (once an hour); here they only go to the log.
            log.error("%s", problema)
        if planes:
            log.info("Complementos pendientes: %s.", ", ".join(c.id for c, _ in planes))
        else:
            log.info("Sin complementos pendientes después del despliegue: queda la comparación con SAP.")
        # The comparison of VENTAS always runs at the end, also with nothing pending.
        estimado = (sum((plan.estimado for _, plan in planes), timedelta())
                    + comparar.duracion_estimada(len(EMPRESAS), comparar.hoy_bogota(ahora), CONJUNTOS_TRAS_DESPLIEGUE))
    elif args.comparar:
        estimado = comparar.duracion_estimada(len(empresas), comparar.hoy_bogota(ahora), conjuntos)

    programado = (completa or carga is not None or meses is not None or tras or args.comparar
                  or modo.startswith("archivo"))
    avisar = modo != "diagnostico"  # el diagnóstico lo corre el usuario y ve el resumen
    momento = ahora()
    franja = bloqueo.en_franja(momento, cfg.franjas, cfg.margen_franja_min)
    carga_meses = ("de los complementos y la comparación" if tras
                   else "de la comparación" if args.comparar
                   else "del complemento" if args.complemento_ventas else "del histórico")
    if estimado is not None:
        # El histórico y el complemento tienen la VPN arriba mucho tiempo: no basta con estar fuera
        # de la franja, toda la fase con VPN debe caber antes de la siguiente.
        codigo = _esperar_hueco(cfg, modo, estimado, args.forzar, ahora, dormir, carga_meses)
        if codigo is not None:
            return codigo
    elif programado and franja:
        mensaje = (f"Son las {momento:%H:%M}, dentro de la franja de las {franja} "
                   f"(±{cfg.margen_franja_min} minutos) en que los otros robots usan la VPN")
        if args.forzar:
            log.warning("%s: se corre igual por --forzar.", mensaje)
        else:
            # Pasa cuando el PC prendió tarde (StartWhenAvailable): se espera a que la
            # franja termine, antes de subir la VPN, en vez de perder la corrida.
            try:
                fin = bloqueo.fin_de_franja(momento, cfg.franjas, cfg.margen_franja_min)
            except ValueError as exc:
                log.error("%s", exc)
                guardar_estado(estado="ERROR", modo=modo, etapa="FRANJA", error=str(exc))
                notificar.avisar_fallos(cfg.alertas, [("FRANJA", str(exc))])
                return 1
            log.warning("%s: espero hasta las %s para no cruzarme con ellos.", mensaje, f"{fin:%H:%M}")
            dormir((fin - momento).total_seconds())

    candado = bloqueo.Bloqueo(reloj=ahora)
    try:
        if programado:
            if not candado.tomar(dormir=dormir):
                log.info("Otro proceso del robot tiene el candado (%s); espero hasta %s minutos.",
                         candado.quien(), int(ESPERA_CANDADO.total_seconds() // 60))
                if not candado.tomar(esperar=ESPERA_CANDADO, dormir=dormir):
                    mensaje = (f"Otro proceso del robot no soltó el candado {candado.ruta} en "
                               f"{int(ESPERA_CANDADO.total_seconds() // 60)} minutos ({candado.quien()}).")
                    log.error(mensaje)
                    guardar_estado(estado="ERROR", modo=modo, etapa="CANDADO", error=mensaje)
                    notificar.avisar_fallos(cfg.alertas, [("CANDADO", mensaje)])
                    return 1
            if estimado is not None:
                # La espera del candado pudo correr la hora: se revisa de nuevo, ya con él.
                codigo = _esperar_hueco(cfg, modo, estimado, args.forzar, ahora, dormir, carga_meses)
                if codigo is not None:
                    candado.soltar()
                    return codigo
        elif not candado.tomar():
            log.warning("El robot está ocupado con otra ejecución (%s). Intenta de nuevo en unos "
                        "minutos.", candado.quien())
            return 1
    except KeyboardInterrupt:
        log.warning("Ejecución cancelada por el usuario.")
        return 130

    try:
        return _ejecutar(
            cfg, args, modo, empresas, inicio, avisar=avisar, fabrica_api=fabrica_api,
            fabrica_vpn=fabrica_vpn, conectar=conectar, ahora=ahora, carga=carga, meses=meses,
            renovar=candado.renovar, git=git,
        )
    finally:
        candado.soltar()


def _complemento_ventas(
    cfg: Config, args: argparse.Namespace, plan: PlanComplemento, **kwargs: Any
) -> tuple[list[historico.Tramo], list[tuple[str, str]]]:
    """The same path as `run_robot.py --complemento-ventas` (see _ejecutar)."""
    fabrica_api, fabrica_vpn = kwargs.pop("fabrica_api"), kwargs.pop("fabrica_vpn")
    complemento.revisar_consulta()  # ConfigError if ventas.sql lost the kilos column
    return complemento.ejecutar(
        cfg, plan.empresas, plan.desde, plan.hasta, api=fabrica_api(cfg.api),
        robot_vpn=None if args.sin_vpn else fabrica_vpn(cfg.vpn), sin_vpn=args.sin_vpn, **kwargs,
    )


_CORRER_COMPLEMENTO = {"complemento-ventas": _complemento_ventas}


def _tras_despliegue(
    cfg: Config,
    args: argparse.Namespace,
    *,
    fabrica_api: Callable[..., ApiCliente],
    fabrica_vpn: Callable[..., Any],
    conectar: Callable[..., Any],
    ahora: Callable[[], datetime],
    renovar: Callable[[], Any],
    git: autoactualizar.Ejecutor | None,
) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """--tras-despliegue, with the lock held: each pending complement in order, through the
    path of its manual mode. A failing one is marked failed at this commit and the next one
    still runs. Returns the failures and what goes to the state."""
    # Again under the lock: another process may have run some while this one waited.
    planes, problemas = complementos_pendientes(ahora, git)
    for problema in problemas:
        log.error("%s", problema)
    commit = autoactualizar.commit_actual(git)
    fallos: list[tuple[str, str]] = []
    resumen: list[dict[str, Any]] = []
    if not planes:
        log.info("Sin complementos pendientes: otro proceso ya los corrió.")
    for c, plan in planes:
        log.info("Complemento %s: --%s %s.", c.id, c.modo, " ".join(c.argumentos))
        tramos: list[historico.Tramo] = []
        try:
            tramos, propios = _CORRER_COMPLEMENTO[c.modo](
                cfg, args, plan, fabrica_api=fabrica_api, fabrica_vpn=fabrica_vpn, conectar=conectar,
                ahora=ahora, renovar=renovar,
            )
        except ConfigError as exc:
            propios = [("CONFIGURACION", str(exc))]
        except Exception as exc:  # one complement never stops the next
            log.exception("Error inesperado en el complemento %s.", c.id)
            propios = [("INESPERADO", extraccion.mensaje_seguro(exc))]
        renovar()
        hecho = not propios
        try:
            autoactualizar.marcar(c.id, hecho=hecho, commit=commit, momento=ahora(),
                                  motivo="; ".join(m for _, m in propios))
        except OSError as exc:
            log.error("No se pudo guardar el estado del complemento %s: %s", c.id, exc)
            propios = [*propios,
                       ("ESTADO", f"No se pudo guardar el estado del complemento: {exc.__class__.__name__}.")]
        if hecho:
            log.info("Complemento %s: hecho (%d tramos).", c.id, len(tramos))
        else:
            log.error("Complemento %s: fallido (%d tramos, %d fallos); se reintenta después del "
                      "siguiente despliegue.", c.id, len(tramos), len(propios))
        fallos += [(etapa, f"Complemento {c.id}: {mensaje}") for etapa, mensaje in propios]
        resumen.append({"id": c.id, "modo": c.modo, "argumentos": list(c.argumentos),
                        "estado": "hecho" if hecho else "fallido",
                        "tramos": [t.para_estado() for t in tramos]})
    # Always the comparison of VENTAS at the end, once, also after a failed complement or with
    # nothing pending: it only reads SAP (its own VPN session) and the app.
    renovar()
    try:
        comparaciones, propios = _comparar(cfg, args, EMPRESAS, fabrica_api=fabrica_api, fabrica_vpn=fabrica_vpn,
                                           conectar=conectar, ahora=ahora, renovar=renovar,
                                           conjuntos=CONJUNTOS_TRAS_DESPLIEGUE)
    except Exception as exc:
        log.exception("Error inesperado en la comparación con SAP.")
        comparaciones, propios = [], [("INESPERADO", f"Comparación: {extraccion.mensaje_seguro(exc)}")]
    fallos += propios
    return fallos, {"complementos": resumen, "comparaciones": [c.para_estado() for c in comparaciones]}


def _comparar(
    cfg: Config,
    args: argparse.Namespace,
    empresas: list[str],
    *,
    fabrica_api: Callable[..., ApiCliente],
    fabrica_vpn: Callable[..., Any],
    **kwargs: Any,
) -> tuple[list[comparar.Comparacion], list[tuple[str, str]]]:
    """The same path as `run_robot.py --comparar` (see _ejecutar)."""
    return comparar.ejecutar(
        cfg, empresas, api=fabrica_api(cfg.api), robot_vpn=None if args.sin_vpn else fabrica_vpn(cfg.vpn),
        sin_vpn=args.sin_vpn, **kwargs,
    )


def _comparacion_diaria(
    cfg: Config,
    args: argparse.Namespace,
    empresas: list[str],
    *,
    fabrica_api: Callable[..., ApiCliente],
    fabrica_vpn: Callable[..., Any],
    conectar: Callable[..., Any],
    ahora: Callable[[], datetime],
    renovar: Callable[[], Any],
) -> None:
    """After a --completa that ended OK, with the lock still held: the full comparison of the
    three datasets, at most once per Bogotá day (comparar.comparada_el / anotar_dia).

    Only after a completa of every company (the nightly one): a partial one does not compare.
    It never changes the completa's exit code or state: a mismatch or a failure goes to the
    log, to robot/state/comparacion_diaria.json and to its own alert. If it could not compare
    everything (SAP, the VPN or the API failed), the day is not recorded, so a later good
    completa that day retries.
    """
    if set(empresas) != set(EMPRESAS):
        log.info("La comparación diaria va después de una completa de todas las empresas; esta no compara.")
        return
    hoy = comparar.hoy_bogota(ahora)
    if comparar.comparada_el(hoy):
        log.info("La comparación diaria con SAP ya se hizo hoy (%s); no se repite.", hoy)
        return
    log.info("Comparación diaria con SAP: %s.", ", ".join(comparar.CONJUNTOS))
    renovar()
    try:
        comparaciones, fallos = _comparar(cfg, args, list(EMPRESAS), fabrica_api=fabrica_api,
                                          fabrica_vpn=fabrica_vpn, conectar=conectar, ahora=ahora,
                                          renovar=renovar, conjuntos=comparar.CONJUNTOS)
    except Exception as exc:  # the load already went well: nothing here changes it
        log.exception("Error inesperado en la comparación diaria con SAP.")
        comparaciones, fallos = [], [("INESPERADO", f"Comparación diaria: {extraccion.mensaje_seguro(exc)}")]
    try:
        if comparar.anotar_dia(hoy, comparaciones, ahora()):
            log.info("Comparación diaria del %s anotada en %s.", hoy, comparar.ARCHIVO_DIARIO)
        else:
            log.warning("La comparación diaria no se pudo completar: no se anota el día; la reintenta la "
                        "siguiente completa buena de hoy.")
    except OSError as exc:
        log.error("No se pudo guardar %s: %s", comparar.ARCHIVO_DIARIO, exc)
        fallos.append(("ESTADO", f"No se pudo guardar el estado de la comparación diaria: {exc.__class__.__name__}."))
    if fallos:
        for etapa, mensaje in fallos:
            log.error("FALLO en la etapa %s: %s", etapa, mensaje)
        notificar.avisar_fallos(cfg.alertas, fallos)


def _ejecutar(
    cfg: Config,
    args: argparse.Namespace,
    modo: str,
    empresas: list[str],
    inicio: float,
    *,
    avisar: bool,
    fabrica_api: Callable[..., ApiCliente],
    fabrica_vpn: Callable[..., Any],
    conectar: Callable[..., Any],
    ahora: Callable[[], datetime],
    carga: Trabajo | None = None,
    meses: tuple[date, date | None] | None = None,
    renovar: Callable[[], Any] = lambda: None,
    git: autoactualizar.Ejecutor | None = None,
) -> int:
    """El modo pedido, con el candado ya tomado."""
    completa = modo == "completa" or carga is not None
    trabajos: list[Trabajo] = []
    extra: dict[str, Any] = {}
    try:
        if modo == TRAS_DESPLIEGUE:
            fallos, extra = _tras_despliegue(
                cfg, args, fabrica_api=fabrica_api, fabrica_vpn=fabrica_vpn, conectar=conectar,
                ahora=ahora, renovar=renovar, git=git,
            )
        elif modo == "comparar":
            comparaciones, fallos = _comparar(
                cfg, args, empresas, fabrica_api=fabrica_api, fabrica_vpn=fabrica_vpn, conectar=conectar,
                ahora=ahora, renovar=renovar,
                conjuntos=[c for c in comparar.CONJUNTOS if not args.conjunto or c in args.conjunto],
            )
            extra["comparaciones"] = [c.para_estado() for c in comparaciones]
        elif meses is not None and modo == "complemento ventas":
            tramos, fallos = complemento.ejecutar(
                cfg, empresas, *meses, api=fabrica_api(cfg.api),
                robot_vpn=None if args.sin_vpn else fabrica_vpn(cfg.vpn), conectar=conectar,
                sin_vpn=args.sin_vpn, ahora=ahora, renovar=renovar,
            )
            extra["tramos"] = [t.para_estado() for t in tramos]
        elif meses is not None:
            tramos, fallos = historico.ejecutar(
                cfg, empresas, *meses, api=fabrica_api(cfg.api), carpeta=Carpeta(cfg.csv_dir),
                robot_vpn=None if args.sin_vpn else fabrica_vpn(cfg.vpn), conectar=conectar,
                sin_vpn=args.sin_vpn, ahora=ahora, renovar=renovar,
            )
            extra["tramos"] = [t.para_estado() for t in tramos]
        elif carga is not None:
            trabajos = [carga]
            fallos = ejecutar_trabajos(
                cfg, trabajos, api=fabrica_api(cfg.api),
                robot_vpn=None if args.sin_vpn else fabrica_vpn(cfg.vpn), conectar=conectar,
                sin_vpn=args.sin_vpn, ahora=ahora,
            )
        elif completa:
            trabajos, fallos = _completa(
                cfg, empresas, sin_vpn=args.sin_vpn, fabrica_api=fabrica_api,
                fabrica_vpn=fabrica_vpn, conectar=conectar, ahora=ahora,
            )
        else:
            fallos = _solo_carpeta(
                cfg, empresas, modo, sin_vpn=args.sin_vpn, fabrica_vpn=fabrica_vpn,
                conectar=conectar, ahora=ahora,
            )
    except KeyboardInterrupt:
        log.warning("Ejecución cancelada por el usuario.")
        return 130
    except Exception as exc:  # red de seguridad: nada sale sin registrar
        log.exception("Error inesperado en el robot.")
        mensaje = extraccion.mensaje_seguro(exc)
        guardar_estado(estado="ERROR", modo=modo, etapa="INESPERADO", error=mensaje,
                       duracion_seg=round(time.monotonic() - inicio, 1))
        if avisar:
            notificar.avisar_fallos(cfg.alertas, [("INESPERADO", mensaje)])
        return 1

    duracion = round(time.monotonic() - inicio, 1)
    guardar_estado(
        estado="ERROR" if fallos else "OK",
        modo=modo,
        empresas=empresas,
        trabajos=[t.nombre for t in trabajos],
        fallos=[list(f) for f in fallos],
        duracion_seg=duracion,
        **extra,
    )
    if fallos:
        for etapa, mensaje in fallos:
            log.error("FALLO en la etapa %s: %s", etapa, mensaje)
        if completa:
            log.error("La app conserva los datos de la última corrida buena de lo que falló.")
        if avisar:
            notificar.avisar_fallos(cfg.alertas, fallos)
        return 1
    log.info("Robot terminado sin fallos en %.1fs.", duracion)
    if modo == "completa":
        # The load ended OK (the same condition as returning 0): the daily full comparison, in
        # its own VPN session. Its outcome never changes this exit code nor the state above.
        try:
            _comparacion_diaria(cfg, args, empresas, fabrica_api=fabrica_api, fabrica_vpn=fabrica_vpn,
                                conectar=conectar, ahora=ahora, renovar=renovar)
        except KeyboardInterrupt:
            log.warning("Comparación diaria cancelada por el usuario.")
            return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
