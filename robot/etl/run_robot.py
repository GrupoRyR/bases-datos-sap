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
    python run_robot.py --completa                 # nocturna: MAESTROS y CARTERA de SGX y SDC,
                                                   # más los registros del archivo (AUDITORIA, ORTT)
    python run_robot.py --completa --empresa SGX   # solo una empresa (se puede repetir)
    python run_robot.py --completa --sin-vpn       # asume la VPN ya conectada a mano
    python run_robot.py --archivo fotos            # domingo 03:00: fotos del archivo y catálogo
    python run_robot.py --archivo registros        # solo los registros del archivo
    python run_robot.py --catalogo                 # solo el catálogo
    python run_robot.py --diagnostico              # cifras de MAESTROS y CARTERA, sin enviar

Salida: 0 todo bien, 1 algún fallo (se avisa por correo, salvo en el
diagnóstico, que lo corre el usuario), 2 configuración incompleta, 130
cancelado con Ctrl+C.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable

import archivo
import catalogo
import config
import diagnostico
import envio
import extraccion
import hana
import notificar
import registro
from api import ApiCliente
from carpeta import Carpeta
from config import EMPRESAS, Config, ConfigError, cargar_config
from trabajos import Trabajo, TrabajoInvalido, trabajos_completos, trabajos_de_solicitudes
from vpn import RobotVPN

SOLICITUDES_POR_PAGINA = 20
MAX_PAGINAS = 5

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
    pero nunca frenan MAESTROS ni CARTERA.
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
    trabajos: Iterable[Trabajo], tomadas: list[dict[str, Any]], hoy: date
) -> list[tuple[str, str]]:
    """Pega cada solicitud tomada a la corrida completa de su empresa y conjunto (§7.3).

    Ya no se extrae nada: una solicitud de una empresa que no está en esta
    corrida queda tomada y la API la vence. Una inválida va a los fallos.
    """
    por_grupo = {(t.empresa, t.conjunto): t for t in trabajos}
    fallos: list[tuple[str, str]] = []
    for solicitud in tomadas:
        try:
            trabajos_de_solicitudes([solicitud], hoy)  # valida empresa, conjunto, parte y desde
        except TrabajoInvalido as exc:
            log.error("Solicitud inválida: %s", exc)
            fallos.append(("SOLICITUDES", str(exc)))
            continue
        trabajo = por_grupo.get((solicitud["empresa"], solicitud["conjunto"]))
        if trabajo is None:
            log.warning(
                "Solicitud %s (%s %s): esa empresa no está en esta corrida; queda tomada "
                "y la API la vence.", solicitud.get("id"), solicitud["conjunto"], solicitud["empresa"],
            )
            continue
        trabajo.solicitudes.append(solicitud["id"])
    return fallos


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
    trabajos = trabajos_completos(empresas, hoy, [])
    log.info("Trabajos: %s.", ", ".join(t.nombre for t in trabajos))
    fallos_solicitudes: list[tuple[str, str]] = []

    def tomar(resultados: list[extraccion.Resultado]) -> None:
        # Los resultados comparten los objetos Trabajo: las solicitudes llegan a la corrida.
        fallos_solicitudes.extend(_asignar_solicitudes(trabajos, _tomar_solicitudes(api), hoy))

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
    return fallos


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Robot de Bases de datos SAP")
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--completa", action="store_true",
                      help="Corrida nocturna: MAESTROS y CARTERA completos, con la foto de cartera "
                           "y los registros del archivo.")
    modo.add_argument("--archivo", choices=("fotos", "registros"),
                      help="Tablas que solo van a la carpeta: fotos (domingo, con el catálogo) "
                           "o registros.")
    modo.add_argument("--catalogo", action="store_true",
                      help="Catálogo de tablas y columnas de cada empresa (carpeta _CATALOGO).")
    modo.add_argument("--diagnostico", action="store_true",
                      help="Extrae MAESTROS y CARTERA con sus conteos a _DIAGNOSTICO; no envía nada.")
    parser.add_argument("--empresa", action="append", choices=EMPRESAS,
                        help="Empresa a procesar (se puede repetir). Por defecto, todas.")
    parser.add_argument("--sin-vpn", action="store_true",
                        help="No gestionar la VPN (asume que ya está activa).")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    fabrica_api: Callable[..., ApiCliente] = ApiCliente,
    fabrica_vpn: Callable[..., Any] = RobotVPN,
    conectar: Callable[..., Any] = hana.conectar,
    ahora: Callable[[], datetime] = config.ahora,
) -> int:
    args = _parser().parse_args(argv)
    empresas = list(dict.fromkeys(args.empresa or EMPRESAS))
    if args.completa:
        modo = "completa"
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
        # Solo la completa habla con la API; el archivo, el catálogo y el diagnóstico no.
        cfg.validar(requiere_vpn=not args.sin_vpn, requiere_api=completa, empresas=empresas)
    except ConfigError as exc:
        log.error("Configuración incompleta:\n%s", exc)
        guardar_estado(estado="ERROR", modo=modo, etapa="CONFIGURACION", error=str(exc))
        if cfg is not None and cfg.alertas.habilitada:
            notificar.avisar_fallos(cfg.alertas, [("CONFIGURACION", str(exc))])
        return 2

    avisar = modo != "diagnostico"  # el diagnóstico lo corre el usuario y ve el resumen
    trabajos: list[Trabajo] = []
    try:
        if completa:
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
