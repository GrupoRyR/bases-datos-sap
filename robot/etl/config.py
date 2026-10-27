"""Carga y validación de la configuración del robot (archivo robot/.env)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ROBOT_DIR = BASE_DIR.parent
ENV_PATH = ROBOT_DIR / ".env"
QUERIES_DIR = ROBOT_DIR / "queries"
LOGS_DIR = ROBOT_DIR / "logs"
STATE_DIR = ROBOT_DIR / "state"

# Bogotá no tiene horario de verano, así que basta un desfase fijo UTC-05:00.
# zoneinfo("America/Bogota") necesitaría el paquete tzdata en Windows.
BOGOTA = timezone(timedelta(hours=-5), "America/Bogota")

EMPRESAS = ("SGX", "SDC")
ESQUEMAS_POR_DEFECTO = {"SGX": "SEGUREX", "SDC": "HBT_SDERIVADOS"}
# Número (OPLN.ListNum) de la lista de precios pública de cada empresa. Segurex:
# la 1, «LISTA PUBLICO». Derivados todavía no tiene una definida.
LISTAS_PRECIOS_POR_DEFECTO: dict[str, int | None] = {"SGX": 1, "SDC": None}
CSV_DIR_POR_DEFECTO = r"C:\Users\Claude\Documents\CEREBRO\SAP\BASES_DE_DATOS"
FRANJAS_POR_DEFECTO = "00:00,05:00,06:00,12:00,12:30"
SOPHOS_CLI_POR_DEFECTO = r"C:\Program Files (x86)\Sophos\Connect\sccli.exe"

_RE_FRANJA = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def ahora() -> datetime:
    """Hora actual de Bogotá, con zona horaria."""
    return datetime.now(BOGOTA)


class ConfigError(RuntimeError):
    """Falta configuración obligatoria o tiene un valor inválido."""


def _bool(valor: str | None, por_defecto: bool = False) -> bool:
    if valor is None or valor.strip() == "":
        return por_defecto
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes", "y"}


def _int(nombre: str, por_defecto: int, invalidos: list[str]) -> int:
    """Entero de la variable; si falta, el valor por defecto.

    Un valor que no es número también usa el valor por defecto, pero queda en
    `invalidos` para que validar() lo reporte en vez de ignorarlo en silencio.
    """
    valor = (os.getenv(nombre) or "").strip()
    if not valor:
        return por_defecto
    try:
        return int(valor)
    except ValueError:
        invalidos.append(f"{nombre}={valor}")
        return por_defecto


def _int_o_nada(nombre: str, por_defecto: int | None, invalidos: list[str]) -> int | None:
    """Como `_int`, pero el valor por defecto puede ser None (la variable es opcional)."""
    valor = (os.getenv(nombre) or "").strip()
    if not valor:
        return por_defecto
    try:
        return int(valor)
    except ValueError:
        invalidos.append(f"{nombre}={valor}")
        return por_defecto


def variable_lista_precios(empresa: str) -> str:
    """Nombre de la variable con el número de la lista de precios pública de la empresa."""
    return f"HANA_{empresa}_LISTA_PRECIOS"


def _texto(nombre: str, por_defecto: str = "") -> str:
    """Valor sin espacios; si la variable falta o está vacía, el valor por defecto."""
    return (os.getenv(nombre) or "").strip() or por_defecto


def _franjas(valor: str) -> list[str]:
    """Convierte "6:00, 12:30" en ["06:00", "12:30"].

    Las entradas inválidas se conservan tal cual para que validar() las reporte.
    """
    franjas: list[str] = []
    for parte in valor.split(","):
        parte = parte.strip()
        if not parte:
            continue
        m = _RE_FRANJA.match(parte)
        franjas.append(f"{int(m.group(1)):02d}:{m.group(2)}" if m else parte)
    return franjas


@dataclass(frozen=True)
class VpnConfig:
    cli: Path
    conexion: str
    usuario: str
    password: str
    timeout: int
    desconectar_al_final: bool


@dataclass(frozen=True)
class EmpresaHana:
    codigo: str
    usuario: str
    password: str
    esquema: str
    # Número de la lista de precios pública (OPLN.ListNum); None: la empresa no tiene.
    lista_precios: int | None = None

    @property
    def variable_lista_precios(self) -> str:
        return variable_lista_precios(self.codigo)

    @property
    def sin_precios(self) -> bool:
        """Sin lista pública no se piden precios: su MAESTROS va sin la parte precios (contrato §4.1)."""
        return self.lista_precios is None

    def error_sin_precios(self) -> ConfigError:
        """Lo que falla cuando, aun así, alguien pide los precios de esta empresa."""
        return ConfigError(
            f"{self.codigo} no tiene lista de precios pública definida: pon su número en "
            f"{self.variable_lista_precios} (robot/.env). El número sale de "
            f"_DIAGNOSTICO\\{self.codigo}\\listas_precios."
        )


@dataclass(frozen=True)
class HanaConfig:
    host: str
    port: int
    timeout: int
    empresas: dict[str, EmpresaHana] = field(default_factory=dict)

    def sin_precios(self) -> frozenset[str]:
        """Códigos de las empresas sin lista de precios pública."""
        return frozenset(c for c, e in self.empresas.items() if e.sin_precios)


@dataclass(frozen=True)
class ApiConfig:
    url: str  # base de la app, sin barra final (contrato §2)
    key_id: str
    secret: str


@dataclass(frozen=True)
class AlertaConfig:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    destinatarios: list[str] = field(default_factory=list)

    @property
    def habilitada(self) -> bool:
        return bool(self.smtp_host and self.destinatarios)


@dataclass(frozen=True)
class Config:
    vpn: VpnConfig
    hana: HanaConfig
    api: ApiConfig
    csv_dir: Path
    franjas: list[str]
    margen_franja_min: int
    historial_documentos: bool
    alertas: AlertaConfig
    numeros_invalidos: tuple[str, ...] = ()

    def validar(
        self,
        *,
        requiere_vpn: bool = True,
        requiere_api: bool = True,
        empresas: Iterable[str] = EMPRESAS,
    ) -> None:
        """Lanza ConfigError con un mensaje accionable si falta algo."""
        faltantes: list[str] = []
        empresas = tuple(empresas)

        if requiere_vpn:
            if not self.vpn.conexion:
                faltantes.append("SOPHOS_CONNECTION (perfil de la VPN Sophos, ej: 20.186.106.194)")
            if not self.vpn.usuario:
                faltantes.append("SOPHOS_USER (usuario de la VPN Sophos)")
            if not self.vpn.password:
                faltantes.append("SOPHOS_PASSWORD (contraseña de la VPN Sophos)")
            if not self.vpn.cli.exists():
                faltantes.append(f"SOPHOS_CLI apunta a un archivo inexistente: {self.vpn.cli}")

        if empresas and not self.hana.host:
            faltantes.append("HANA_HOST (IP o nombre del servidor SAP HANA)")
        for codigo in empresas:
            empresa = self.hana.empresas.get(codigo)
            if empresa is None:
                faltantes.append(
                    f"Empresa desconocida: {codigo} (las válidas son {', '.join(EMPRESAS)})"
                )
                continue
            if not empresa.usuario:
                faltantes.append(f"HANA_{codigo}_USER (usuario de HANA de {codigo})")
            if not empresa.password:
                faltantes.append(f"HANA_{codigo}_PASSWORD (contraseña de HANA de {codigo})")
            if not empresa.esquema:
                faltantes.append(f"HANA_{codigo}_SCHEMA (esquema de SAP B1 de {codigo})")

        if requiere_api:
            if not self.api.url:
                faltantes.append("BASES_SAP_API_URL (base de la app, ej: https://<subdominio>)")
            elif not self.api.url.lower().startswith("https://"):
                faltantes.append(
                    f"BASES_SAP_API_URL debe empezar por https:// (solo HTTPS): {self.api.url}"
                )
            if not self.api.key_id:
                faltantes.append("BASES_SAP_ROBOT_KEY_ID (id de la llave del robot)")
            if not self.api.secret:
                faltantes.append("BASES_SAP_ROBOT_SECRET (secreto de la llave del robot)")

        invalidas = [f for f in self.franjas if not _RE_FRANJA.match(f)]
        if invalidas:
            faltantes.append(
                "BASES_SAP_FRANJAS_BLOQUEADAS tiene horas inválidas (usa HH:MM separadas "
                f"por comas): {', '.join(invalidas)}"
            )

        if self.numeros_invalidos:
            faltantes.append(
                "Estas variables deben ser números enteros: "
                + ", ".join(self.numeros_invalidos)
            )

        if faltantes:
            detalle = "\n  - ".join(faltantes)
            raise ConfigError(
                f"Faltan datos obligatorios en {ENV_PATH}:\n  - {detalle}\n\n"
                "Edita ese archivo y vuelve a ejecutar."
            )


def cargar_config(env_path: Path | None = None) -> Config:
    ruta = env_path or ENV_PATH
    if ruta.exists():
        load_dotenv(ruta, override=True)
    for carpeta in (LOGS_DIR, STATE_DIR):
        carpeta.mkdir(parents=True, exist_ok=True)

    invalidos: list[str] = []
    destinatarios = [
        c.strip()
        for c in os.getenv("ALERTA_DESTINATARIOS", "").split(",")
        if c.strip()
    ]

    # Las contraseñas se registran en registro.registrar_secreto() donde se usan
    # (vpn, hana, notificar, api): registro importa config, no al revés.
    return Config(
        vpn=VpnConfig(
            cli=Path(_texto("SOPHOS_CLI", SOPHOS_CLI_POR_DEFECTO)),
            conexion=_texto("SOPHOS_CONNECTION"),
            usuario=_texto("SOPHOS_USER"),
            password=os.getenv("SOPHOS_PASSWORD", ""),
            timeout=_int("SOPHOS_TIMEOUT", 90, invalidos),
            desconectar_al_final=_bool(os.getenv("SOPHOS_DISCONNECT_AL_FINAL"), True),
        ),
        hana=HanaConfig(
            host=_texto("HANA_HOST"),
            port=_int("HANA_PORT", 30015, invalidos),
            timeout=_int("HANA_TIMEOUT", 600, invalidos),
            empresas={
                codigo: EmpresaHana(
                    codigo=codigo,
                    usuario=_texto(f"HANA_{codigo}_USER"),
                    password=os.getenv(f"HANA_{codigo}_PASSWORD", ""),
                    esquema=_texto(f"HANA_{codigo}_SCHEMA", ESQUEMAS_POR_DEFECTO[codigo]),
                    lista_precios=_int_o_nada(
                        variable_lista_precios(codigo), LISTAS_PRECIOS_POR_DEFECTO[codigo], invalidos
                    ),
                )
                for codigo in EMPRESAS
            },
        ),
        api=ApiConfig(
            url=_texto("BASES_SAP_API_URL").rstrip("/"),
            key_id=_texto("BASES_SAP_ROBOT_KEY_ID"),
            secret=os.getenv("BASES_SAP_ROBOT_SECRET", ""),
        ),
        csv_dir=Path(_texto("BASES_SAP_CSV_DIR", CSV_DIR_POR_DEFECTO)),
        franjas=_franjas(_texto("BASES_SAP_FRANJAS_BLOQUEADAS", FRANJAS_POR_DEFECTO)),
        margen_franja_min=15,
        historial_documentos=_bool(os.getenv("BASES_SAP_ARCHIVO_HISTORIAL_DOCUMENTOS"), False),
        alertas=AlertaConfig(
            smtp_host=_texto("ALERTA_SMTP_HOST"),
            smtp_port=_int("ALERTA_SMTP_PORT", 587, invalidos),
            smtp_user=_texto("ALERTA_SMTP_USER"),
            smtp_password=os.getenv("ALERTA_SMTP_PASSWORD", ""),
            destinatarios=destinatarios,
        ),
        numeros_invalidos=tuple(invalidos),
    )


def leer_query(nombre: str) -> str:
    """Lee una consulta relativa a robot/queries (ej: "maestros/clientes.sql")."""
    ruta = QUERIES_DIR / nombre
    if not ruta.exists():
        raise ConfigError(f"No existe la consulta {ruta}")
    return ruta.read_text(encoding="utf-8")
