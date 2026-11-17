"""Email alert when the robot fails. Optional: with neither Graph nor SMTP it does nothing.

Channels, by priority (AlertaConfig.channel):
1. Microsoft Graph (sendMail with the client-credentials flow), when its four
   variables and the recipients are complete.
2. SMTP, when its host and the recipients are complete.
3. Neither: alerts are off and the failure only goes to the log.

A failed send is only logged: it never fails the robot run. The log carries
statuses and error codes, never the secret, the token or a response body.
"""
from __future__ import annotations

import json
import re
import smtplib
import socket
import ssl
import time
import urllib.parse
from email.message import EmailMessage
from typing import Callable

import api
from config import AlertaConfig, ahora
from registro import obtener, redactar, registrar_secreto

log = obtener("alerta")

TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
SEND_URL = "https://graph.microsoft.com/v1.0/users/{remitente}/sendMail"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
TIMEOUT_S = 30
RETRIES = 1  # one retry after the first attempt
RETRY_WAIT_S = 2

_RE_CODIGO = re.compile(r"[A-Za-z0-9_.\-]{1,64}")
_RE_AADSTS = re.compile(r"AADSTS\d{3,7}")


class GraphError(RuntimeError):
    """Entra ID or Graph refused the send. The message is safe to log."""


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
    """Send ONE email with all the failures of the run: (stage, error)."""
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
    _send(cfg, f"[Bases SAP] Falló el robot - {asunto}", cuerpo, transporte, dormir)


def probar_alerta(
    cfg: AlertaConfig,
    *,
    transporte: api.Transporte | None = None,
    dormir: Callable[[float], None] | None = None,
) -> bool:
    """Send a test email through the configured channel. True if sent, False if not."""
    cuerpo = (
        "Este es un correo de prueba del robot de Bases de datos SAP.\n\n"
        f"Equipo:  {socket.gethostname()}\n"
        f"Hora:    {ahora():%Y-%m-%d %H:%M:%S} (Bogotá)\n\n"
        "Si lo recibes, las alertas por correo funcionan."
    )
    return _send(cfg, "[Bases SAP] Prueba de alertas", cuerpo, transporte, dormir)


def _send(
    cfg: AlertaConfig,
    asunto: str,
    cuerpo: str,
    transporte: api.Transporte | None,
    dormir: Callable[[float], None] | None,
) -> bool:
    """Send through the channel in use. Never raises: True if sent, False if not."""
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
            _send_via_graph(
                cfg, asunto, cuerpo,
                transporte or api.transporte_urllib, dormir or time.sleep,
            )
        else:
            _send_via_smtp(cfg, asunto, cuerpo)
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


def _send_via_graph(
    cfg: AlertaConfig,
    asunto: str,
    cuerpo: str,
    transporte: api.Transporte,
    dormir: Callable[[float], None],
) -> None:
    token = _request_token(cfg, transporte, dormir)
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
        raise GraphError(f"sendMail respondió {respuesta.status}{_error_code(respuesta)}")


def _request_token(
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
        raise GraphError(f"el token respondió {respuesta.status}{_error_code(respuesta)}")
    try:
        token = json.loads(respuesta.cuerpo.decode("utf-8")).get("access_token")
    except (UnicodeDecodeError, ValueError, AttributeError):
        token = None
    if not isinstance(token, str) or not token:
        raise GraphError("el token respondió 200 sin access_token")
    return token


def _post(
    what: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
    transport: api.Transporte,
    sleep: Callable[[float], None],
) -> api.Respuesta:
    """POST with a 30 s timeout and one retry when there was no response, or it was a 429 or 5xx.

    Any other 4xx is a final answer (credentials, permissions): not retried. A sendMail retry
    after a lost response can deliver the same alert twice; that is harmless.
    """
    for attempt in range(RETRIES + 1):
        last = attempt == RETRIES
        try:
            response = transport(url, headers, body, TIMEOUT_S)
        except api.ErrorRed as exc:
            if last:
                raise GraphError(f"{what}: {redactar(str(exc))}") from exc
            log.warning("%s: sin respuesta (%s); reintento una vez.", what, redactar(str(exc)))
        else:
            retryable = response.status == 429 or response.status >= 500
            if last or not retryable:
                return response
            log.warning("%s: respondió %s; reintento una vez.", what, response.status)
        sleep(RETRY_WAIT_S)
    raise AssertionError("unreachable")  # pragma: no cover


def _error_code(respuesta: api.Respuesta) -> str:
    """Only the short error code, as " (invalid_client, AADSTS7000215)", or "" if there is none.

    Never the body: it can repeat the secret or the token. Anything that is not a plain code is dropped.
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


def _send_via_smtp(cfg: AlertaConfig, asunto: str, cuerpo: str) -> None:
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
