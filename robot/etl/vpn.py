"""Robot de la VPN Sophos Connect.

Controla el túnel mediante el CLI oficial `sccli.exe`, sin automatizar la
interfaz gráfica (más rápido y fiable, y funciona con la sesión bloqueada).

Comandos usados:
    sccli enable  -n <conexion> -u <usuario> -p <password>   -> conectar
    sccli disable -n <conexion>                              -> desconectar
    sccli get     -n <conexion> -t endpoints                 -> estado

El perfil es de túnel completo (0.0.0.0/0): mientras la VPN está arriba no hay
salida a internet, así que nunca se llama a la API con la VPN conectada.
"""
from __future__ import annotations

import re
import subprocess
import time

from config import VpnConfig
from registro import obtener, registrar_secreto

log = obtener("vpn")

# `sccli get -t endpoints` imprime  "Connected: 1 (connected)"  o  "Connected: 0"
_RE_CONECTADO = re.compile(r"Connected:\s*(\d)", re.IGNORECASE)


class VpnError(RuntimeError):
    """No se pudo establecer o verificar el túnel VPN."""


class RobotVPN:
    def __init__(self, cfg: VpnConfig) -> None:
        self.cfg = cfg
        registrar_secreto(cfg.password)
        self._la_conectamos_nosotros = False

    # ---------------------------------------------------------------- interno
    def _sccli(self, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
        """Ejecuta sccli sin shell (evita problemas con $ y espacios)."""
        cmd = [str(self.cfg.cli), *args]
        seguro = " ".join("***" if a == self.cfg.password else a for a in cmd)
        log.debug("Ejecutando: %s", seguro)
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError as exc:
            raise VpnError(
                f"No se encontró el CLI de Sophos en {self.cfg.cli}. "
                "Revisa SOPHOS_CLI en robot/.env."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise VpnError(
                f"El comando sccli no respondió en {timeout}s. "
                "El servicio 'Sophos Connect' puede estar detenido."
            ) from exc

    # ---------------------------------------------------------------- público
    def conexion_existe(self) -> bool:
        res = self._sccli("list")
        return self.cfg.conexion in (res.stdout or "")

    def esta_conectado(self) -> bool:
        res = self._sccli("get", "-n", self.cfg.conexion, "-t", "endpoints")
        m = _RE_CONECTADO.search(res.stdout or "")
        return bool(m and m.group(1) == "1")

    def conectar(self, intentos: int = 3) -> None:
        """Levanta el túnel. Idempotente: si ya está arriba, no hace nada."""
        if not self.cfg.conexion:
            raise VpnError("SOPHOS_CONNECTION está vacío en robot/.env.")

        if self.esta_conectado():
            log.info("La VPN ya estaba conectada (%s). Se reutiliza el túnel.",
                     self.cfg.conexion)
            return

        if not self.conexion_existe():
            raise VpnError(
                f"El perfil VPN '{self.cfg.conexion}' no está importado en "
                "Sophos Connect. Importa el archivo .pro/.tgb del firewall "
                "antes de ejecutar el robot."
            )

        ultimo_error = ""
        for intento in range(1, intentos + 1):
            log.info("Conectando a la VPN '%s' (intento %d/%d)...",
                     self.cfg.conexion, intento, intentos)
            res = self._sccli(
                "enable",
                "-n", self.cfg.conexion,
                "-u", self.cfg.usuario,
                "-p", self.cfg.password,
                timeout=self.cfg.timeout,
            )
            salida = f"{res.stdout or ''}\n{res.stderr or ''}".strip()

            if self._esperar_tunel():
                self._la_conectamos_nosotros = True
                log.info("VPN conectada correctamente.")
                return

            ultimo_error = salida or "sccli no reportó un motivo."
            log.warning("Intento %d fallido. Respuesta de sccli: %s",
                        intento, ultimo_error)

            if self._credenciales_rechazadas(salida):
                raise VpnError(
                    "La VPN rechazó el usuario o la contraseña. Corrige "
                    "SOPHOS_USER / SOPHOS_PASSWORD en robot/.env. "
                    "(No se reintenta para no bloquear la cuenta.)"
                )

            self._sccli("disable", "-n", self.cfg.conexion)
            if intento < intentos:
                espera = 5 * intento
                log.info("Reintentando en %ds...", espera)
                time.sleep(espera)

        raise VpnError(
            f"No se pudo conectar la VPN tras {intentos} intentos. "
            f"Último detalle: {ultimo_error}"
        )

    @staticmethod
    def _credenciales_rechazadas(salida: str) -> bool:
        s = salida.lower()
        return any(
            p in s
            for p in ("auth", "credential", "password", "denied", "rejected")
        )

    def _esperar_tunel(self) -> bool:
        """Sondea el estado hasta que el túnel levante o se agote el tiempo."""
        limite = time.monotonic() + self.cfg.timeout
        while time.monotonic() < limite:
            if self.esta_conectado():
                return True
            time.sleep(2)
        return False

    def desconectar(self) -> None:
        if not self.cfg.desconectar_al_final:
            log.info("Se deja la VPN conectada (SOPHOS_DISCONNECT_AL_FINAL=false).")
            return
        if not self._la_conectamos_nosotros:
            log.info("La VPN ya estaba activa antes del robot; no se desconecta.")
            return
        log.info("Desconectando la VPN...")
        self._sccli("disable", "-n", self.cfg.conexion)
        self._la_conectamos_nosotros = False

    # ------------------------------------------------- gestor de contexto
    def __enter__(self) -> "RobotVPN":
        self.conectar()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.desconectar()
        except Exception:
            log.exception("Falló al desconectar la VPN (se ignora).")
