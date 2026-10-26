"""Aviso por correo cuando el robot falla. Opcional: si no hay SMTP, no hace nada."""
from __future__ import annotations

import smtplib
import socket
from email.message import EmailMessage

from config import AlertaConfig
from registro import obtener, registrar_secreto

log = obtener("alerta")


def avisar_fallo(cfg: AlertaConfig, etapa: str, error: str, detalle: str = "") -> None:
    avisar_fallos(cfg, [(etapa, error)], detalle)


def avisar_fallos(
    cfg: AlertaConfig, fallos: list[tuple[str, str]], detalle: str = ""
) -> None:
    """Envía UN correo con todos los fallos de la ejecución: (etapa, error)."""
    if not fallos:
        return
    if not cfg.habilitada:
        log.info("Alertas por correo desactivadas; el fallo queda solo en el log.")
        return

    registrar_secreto(cfg.smtp_password)
    equipo = socket.gethostname()
    asunto = fallos[0][0] if len(fallos) == 1 else f"{len(fallos)} fallos"
    lista = "\n".join(f"  - {etapa}: {error}" for etapa, error in fallos)

    msg = EmailMessage()
    msg["Subject"] = f"[Bases SAP] Falló el robot - {asunto}"
    msg["From"] = cfg.smtp_user or "robot-bases-sap@localhost"
    msg["To"] = ", ".join(cfg.destinatarios)
    msg.set_content(
        "El robot de Bases de datos SAP no pudo completar su ejecución.\n\n"
        f"Equipo:  {equipo}\n\n"
        f"Fallos:\n{lista}\n\n"
        f"{detalle}\n\n"
        "La app sigue con los últimos datos buenos.\n"
        "Revisa robot/logs/robot.log para el detalle completo."
    )

    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            if cfg.smtp_user:
                smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(msg)
        log.info("Alerta enviada a: %s", ", ".join(cfg.destinatarios))
    except Exception:
        # Nunca dejar que el fallo del aviso oculte el fallo real.
        log.exception("No se pudo enviar la alerta por correo.")
