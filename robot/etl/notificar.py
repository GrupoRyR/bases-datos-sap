"""Aviso por correo cuando el robot falla. Opcional: sin Graph ni SMTP, no hace nada.

Canales, por prioridad (AlertaConfig.channel):
1. Microsoft Graph (sendMail con el flujo client credentials), si sus cuatro
   variables y los destinatarios están completos.
2. SMTP, si su host y los destinatarios están completos.
3. Ninguno: las alertas quedan desactivadas y el fallo solo va al log.

Un envío fallido solo se registra: nunca hace fallar la ejecución del robot.
En el log van estados y códigos de error, nunca el secreto, el token ni el
cuerpo de las respuestas.
"""
from __future__ import annotations

import json
import re
import smtplib
import socket
import ssl
import time
import urllib.parse
from datetime import datetime
from email.message import EmailMessage
from typing import Callable

import api
from config import AlertaConfig
from registro import obtener, redactar, registrar_secreto

log = obtener("alerta")

TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
SEND_URL = "https://graph.microsoft.com/v1.0/users/{remitente}/sendMail"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
TIMEOUT_S = 30
REINTENTOS = 1  # one retry after the first attempt
ESPERA_REINTENTO_S = 2

_RE_CODIGO = re.compile(r"[A-Za-z0-9_.\-]{1,64}")
_RE_AADSTS = re.compile(r"AADSTS\d{3,7}")


class GraphError(RuntimeError):
    """Microsoft Graph o Entra no dejó enviar. El mensaje es seguro para el log."""


def avisar_fallo(
    cfg: AlertaConfig, etapa: str, error: str, detalle: str = "", **kwargs: object
) -> None:
    avisar_fallos(cfg, [(etapa, error)], detalle, **kwargs)  # type: ignore[arg-type]


def avisar_fallos(
    cfg: AlertaConfig,
    fallos: list[tuple[str, str]],
    detalle: str = "",
    *,
    transporte: api.Transporte | None = None,
    dormir: Callable[[float], None] | None = None,
) -> None:
    """Envía UN correo con todos los fallos de la ejecución: (etapa, error)."""
    if not fallos:
        return
    asunto = fallos[0][0] if len(fallos) == 1 else f"{len(fallos)} fallos"
    lista = "\n".join(f"  - {etapa}: {error}" for etapa, error in fallos)
    cuerpo = (
        "El robot de Bases de datos SAP no pudo completar su ejecución.\n\n"
        f"Equipo:  {socket.gethostname()}\n\n"
        f"Fallos:\n{lista}\n\n"
        f"{detalle}\n\n"
        "La app sigue con los últimos datos buenos.\n"
        "Revisa robot/logs/robot.log para el detalle completo."
    )
    _enviar(cfg, f"[Bases SAP] Falló el robot - {asunto}", cuerpo, transporte, dormir)


def probar_alerta(
    cfg: AlertaConfig,
    *,
    transporte: api.Transporte | None = None,
    dormir: Callable[[float], None] | None = None,
) -> bool:
    """Manda un correo de prueba por el canal configurado. True si salió, False si no."""
    cuerpo = (
        "Este es un correo de prueba del robot de Bases de datos SAP.\n\n"
        f"Equipo:  {socket.gethostname()}\n"
        f"Hora:    {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
        "Si lo recibes, las alertas por correo funcionan."
    )
    return _enviar(cfg, "[Bases SAP] Prueba de alertas", cuerpo, transporte, dormir)


def _enviar(
    cfg: AlertaConfig,
    asunto: str,
    cuerpo: str,
    transporte: api.Transporte | None,
    dormir: Callable[[float], None] | None,
) -> bool:
    """Envía por el canal que toca. Nunca lanza: True si salió, False si no."""
    registrar_secreto(cfg.smtp_password)
    registrar_secreto(cfg.graph_client_secret)

    canal = cfg.channel
    faltan = cfg.graph_missing
    if faltan and canal != "graph":
        log.warning(
            "Microsoft Graph está a medias: falta %s. %s",
            ", ".join(faltan),
            "Se usa SMTP." if canal == "smtp" else "No hay alertas por correo hasta completarlo.",
        )
    if not canal:
        log.info("Alertas por correo desactivadas; el fallo queda solo en el log.")
        return False

    try:
        if canal == "graph":
            _enviar_por_graph(
                cfg, asunto, cuerpo,
                transporte or api.transporte_urllib, dormir or time.sleep,
            )
        else:
            _enviar_por_smtp(cfg, asunto, cuerpo)
    except GraphError as exc:
        log.error("No se pudo enviar la alerta por Microsoft Graph: %s", exc)
        return False
    except Exception:
        # Nunca dejar que el fallo del aviso oculte el fallo real.
        log.exception("No se pudo enviar la alerta por correo.")
        return False
    log.info("Alerta enviada por %s a: %s", "Microsoft Graph" if canal == "graph" else "SMTP",
             ", ".join(cfg.destinatarios))
    return True


def _enviar_por_graph(
    cfg: AlertaConfig,
    asunto: str,
    cuerpo: str,
    transporte: api.Transporte,
    dormir: Callable[[float], None],
) -> None:
    token = _pedir_token(cfg, transporte, dormir)
    registrar_secreto(token)  # in case it ever reaches a log line
    mensaje = {
        "message": {
            "subject": asunto,
            "body": {"contentType": "Text", "content": cuerpo},
            "toRecipients": [{"emailAddress": {"address": d}} for d in cfg.destinatarios],
        },
        "saveToSentItems": False,
    }
    url = SEND_URL.format(remitente=urllib.parse.quote(cfg.graph_remitente, safe="@"))
    respuesta = _post(
        "sendMail", url,
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json.dumps(mensaje).encode("utf-8"), transporte, dormir,
    )
    if not 200 <= respuesta.status < 300:
        raise GraphError(f"sendMail respondió {respuesta.status}{_codigo_error(respuesta)}")


def _pedir_token(
    cfg: AlertaConfig, transporte: api.Transporte, dormir: Callable[[float], None]
) -> str:
    formulario = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": cfg.graph_client_id,
        "client_secret": cfg.graph_client_secret,
        "scope": GRAPH_SCOPE,
    })
    respuesta = _post(
        "token", TOKEN_URL.format(tenant=urllib.parse.quote(cfg.graph_tenant_id, safe="")),
        {"Content-Type": "application/x-www-form-urlencoded"},
        formulario.encode("utf-8"), transporte, dormir,
    )
    if respuesta.status != 200:
        raise GraphError(f"el token respondió {respuesta.status}{_codigo_error(respuesta)}")
    try:
        token = json.loads(respuesta.cuerpo.decode("utf-8")).get("access_token")
    except (UnicodeDecodeError, ValueError, AttributeError):
        token = None
    if not isinstance(token, str) or not token:
        raise GraphError("el token respondió 200 sin access_token")
    return token


def _post(
    que: str,
    url: str,
    headers: dict[str, str],
    cuerpo: bytes,
    transporte: api.Transporte,
    dormir: Callable[[float], None],
) -> api.Respuesta:
    """POST con 30 s de plazo y un reintento si no hubo respuesta, o fue 429 o 5xx.

    Un 4xx distinto de 429 es una respuesta definitiva (credenciales, permisos): no se reintenta.
    """
    for intento in range(REINTENTOS + 1):
        ultimo = intento == REINTENTOS
        try:
            respuesta = transporte(url, headers, cuerpo, TIMEOUT_S)
        except api.ErrorRed as exc:
            if ultimo:
                raise GraphError(f"{que}: {redactar(str(exc))}") from exc
            log.warning("%s: sin respuesta (%s); reintento una vez.", que, redactar(str(exc)))
        else:
            if respuesta.status != 429 and respuesta.status < 500 or ultimo:
                return respuesta
            log.warning("%s: respondió %s; reintento una vez.", que, respuesta.status)
        dormir(ESPERA_REINTENTO_S)
    raise AssertionError("inalcanzable")  # pragma: no cover


def _codigo_error(respuesta: api.Respuesta) -> str:
    """" (código)" con solo el código corto del error (invalid_client, AADSTS7000215...).

    Nunca el cuerpo: puede repetir el secreto o el token. Lo que no parezca un código se omite.
    """
    try:
        datos = json.loads(respuesta.cuerpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ""
    if not isinstance(datos, dict):
        return ""
    error = datos.get("error")
    codigo = error.get("code") if isinstance(error, dict) else error
    partes: list[str] = []
    if isinstance(codigo, str) and _RE_CODIGO.fullmatch(codigo):
        partes.append(codigo)
    descripcion = datos.get("error_description")
    if isinstance(descripcion, str) and (m := _RE_AADSTS.search(descripcion)):
        partes.append(m.group(0))
    return f" ({', '.join(partes)})" if partes else ""


def _enviar_por_smtp(cfg: AlertaConfig, asunto: str, cuerpo: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = cfg.smtp_user or "robot-bases-sap@localhost"
    msg["To"] = ", ".join(cfg.destinatarios)
    msg.set_content(cuerpo)

    # El puerto 465 es TLS desde el inicio; los demás (587) suben a TLS con STARTTLS.
    # En los dos casos se verifica el certificado y el nombre del servidor: sin
    # contexto, smtplib cifra pero acepta cualquier certificado.
    contexto = ssl.create_default_context()
    ssl_directo = cfg.smtp_port == 465
    if ssl_directo:
        servidor = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=30, context=contexto)
    else:
        servidor = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30)
    with servidor as smtp:
        if not ssl_directo:
            smtp.starttls(context=contexto)
        if cfg.smtp_user:
            smtp.login(cfg.smtp_user, cfg.smtp_password)
        smtp.send_message(msg)
