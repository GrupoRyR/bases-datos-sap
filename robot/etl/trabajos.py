"""Trabajos del robot: qué corrida armar para cada empresa y conjunto.

Un Trabajo es una corrida por hacer (contrato §4.1). Sale de las solicitudes
tomadas (§7.3) o de la corrida completa nocturna. Las partes van en el orden
de envío: socios primero, luego direcciones y contactos (dependen de los
socios extraídos), luego el resto; es el orden de esquema.PARTES.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Collection, Iterable

import esquema
from config import BOGOTA, EMPRESAS


class TrabajoInvalido(ValueError):
    """Una solicitud con empresa, conjunto, parte o desde que el contrato no admite."""


@dataclass
class Trabajo:
    empresa: str
    conjunto: str
    tipo: str  # completa | solicitud
    partes: dict[str, str]  # parte -> todo | cambios, en orden de envío
    desde: dict[str, str | None] = field(default_factory=dict)
    solicitudes: list[int] = field(default_factory=list)
    fecha_corte: str | None = None

    @property
    def nombre(self) -> str:
        return f"{self.conjunto} {self.empresa}"


_ORDEN = list(esquema.PARTES)


def _ordenar(partes: Iterable[str]) -> list[str]:
    return sorted(set(partes), key=_ORDEN.index)


def _momento(valor: str, id_solicitud: Any, parte: str) -> datetime:
    try:
        momento = datetime.fromisoformat(str(valor).strip())
    except ValueError:
        raise TrabajoInvalido(
            f"Solicitud {id_solicitud}: el desde de {parte} no es una hora ISO 8601."
        ) from None
    # Una hora sin zona se toma como de Bogotá (igual que consultas.desde_a_parametro).
    return momento if momento.tzinfo else momento.replace(tzinfo=BOGOTA)


def _partes_de(solicitud: dict[str, Any]) -> tuple[str, ...]:
    id_ = solicitud.get("id")
    empresa = solicitud.get("empresa")
    conjunto = solicitud.get("conjunto")
    parte = solicitud.get("parte")
    if empresa not in EMPRESAS:
        raise TrabajoInvalido(f"Solicitud {id_}: empresa desconocida {empresa!r}.")
    partes = esquema.PARTES_POR_SOLICITUD.get((conjunto, parte))
    if partes is None:
        raise TrabajoInvalido(
            f"Solicitud {id_}: conjunto {conjunto!r} con parte {parte!r} no existe en el contrato (§7.1)."
        )
    return partes


def _modos(partes: list[str]) -> dict[str, str]:
    """Modo de cada parte en una corrida de solicitud (contrato §5.1)."""
    socios_en_cambios = any(
        esquema.PARTES[p].modo_solicitud == "cambios" for p in partes if p in esquema.SOCIOS
    )
    modos: dict[str, str] = {}
    for nombre in partes:
        modo = esquema.PARTES[nombre].modo_solicitud
        if modo == "socio":  # direcciones y contactos siguen a su socio
            modo = "cambios" if socios_en_cambios else "todo"
        modos[nombre] = modo
    return modos


def _desde(grupo: list[tuple[dict[str, Any], tuple[str, ...]]], parte: str) -> str | None:
    """El desde más viejo de las solicitudes del grupo que traen la parte; None si alguna no tiene."""
    mas_viejo: tuple[datetime, str] | None = None
    for solicitud, partes in grupo:
        if parte not in partes:
            continue
        valor = (solicitud.get("desde") or {}).get(parte)
        if valor is None:
            return None
        momento = _momento(valor, solicitud.get("id"), parte)
        if mas_viejo is None or momento < mas_viejo[0]:
            mas_viejo = (momento, valor)
    return mas_viejo[1] if mas_viejo else None


def solo_precios(solicitud: dict[str, Any]) -> bool:
    """La solicitud pide únicamente la parte precios (no todo MAESTROS)."""
    return solicitud.get("conjunto") == "MAESTROS" and solicitud.get("parte") == esquema.PRECIOS


def sin_precios_en_la_corrida(empresa: str, conjunto: str, sin_precios: Collection[str]) -> bool:
    """Si la corrida de MAESTROS de esa empresa no lleva la parte precios (contrato §4.1)."""
    return conjunto == "MAESTROS" and empresa in sin_precios


def separar_solo_precios(
    solicitudes: list[dict[str, Any]], sin_precios: Collection[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(resto, solo_precios_sin_lista): las de solo precios de una empresa sin lista van aparte.

    Esas no caben en la corrida de su empresa, que va sin precios: llevan su propio
    trabajo, que falla con el aviso de qué variable falta sin arrastrar a las demás.
    """
    resto: list[dict[str, Any]] = []
    aparte: list[dict[str, Any]] = []
    for solicitud in solicitudes:
        sin_lista = solo_precios(solicitud) and solicitud.get("empresa") in sin_precios
        (aparte if sin_lista else resto).append(solicitud)
    return resto, aparte


def trabajos_de_solicitudes(
    solicitudes: list[dict[str, Any]], hoy: date, sin_precios: Collection[str] = ()
) -> list[Trabajo]:
    """Agrupa las solicitudes tomadas por empresa y conjunto: una corrida por grupo (§7.3).

    Una empresa sin lista de precios pública (`sin_precios`) no pide precios en una
    solicitud de todo MAESTROS. Una de solo precios va en su propio trabajo.
    """
    resto, aparte = separar_solo_precios(solicitudes, sin_precios)
    return _agrupar(resto, hoy, sin_precios) + _agrupar(aparte, hoy, ())


def _agrupar(
    solicitudes: list[dict[str, Any]], hoy: date, sin_precios: Collection[str]
) -> list[Trabajo]:
    grupos: dict[tuple[str, str], list[tuple[dict[str, Any], tuple[str, ...]]]] = {}
    for solicitud in solicitudes:
        partes = _partes_de(solicitud)
        clave = (solicitud["empresa"], solicitud["conjunto"])
        grupos.setdefault(clave, []).append((solicitud, partes))

    trabajos: list[Trabajo] = []
    for (empresa, conjunto), grupo in grupos.items():
        partes = _ordenar(p for _, ps in grupo for p in ps)
        if sin_precios_en_la_corrida(empresa, conjunto, sin_precios):
            partes = [p for p in partes if p != esquema.PRECIOS]
        modos = _modos(partes)
        desde = {
            p: _desde(grupo, p)
            for p in partes
            if modos[p] == "cambios" and esquema.PARTES[p].incremental
        }
        trabajos.append(Trabajo(
            empresa=empresa,
            conjunto=conjunto,
            tipo="solicitud",
            partes=modos,
            desde=desde,
            solicitudes=[s["id"] for s, _ in grupo],
            fecha_corte=hoy.isoformat() if conjunto == "CARTERA" else None,
        ))
    return trabajos


def trabajos_completos(
    empresas: Iterable[str],
    hoy: date,
    solicitudes_tomadas: list[dict[str, Any]],
    sin_precios: Collection[str] = (),
) -> list[Trabajo]:
    """Corrida nocturna: por empresa, MAESTROS y luego CARTERA, todo en modo `todo`.

    Las solicitudes tomadas de la misma empresa y conjunto van en la corrida
    completa (§7.3); las de otras empresas quedan como trabajos de solicitud.
    Una empresa sin lista de precios pública (`sin_precios`) manda su MAESTROS sin la
    parte precios (§4.1); una solicitud de solo precios de esa empresa no cabe en esa
    corrida y queda como trabajo de solicitud aparte.
    """
    empresas = list(dict.fromkeys(empresas))
    resto, aparte = separar_solo_precios(solicitudes_tomadas, sin_precios)
    por_grupo = {(t.empresa, t.conjunto): t for t in _agrupar(resto, hoy, sin_precios)}
    ayer = (hoy - timedelta(days=1)).isoformat()

    trabajos: list[Trabajo] = []
    for empresa in empresas:
        for conjunto in ("MAESTROS", "CARTERA"):
            de_solicitud = por_grupo.pop((empresa, conjunto), None)
            trabajos.append(Trabajo(
                empresa=empresa,
                conjunto=conjunto,
                tipo="completa",
                partes={
                    p: "todo" for p in esquema.PARTES_POR_CONJUNTO[conjunto]
                    if not (p == esquema.PRECIOS and sin_precios_en_la_corrida(empresa, conjunto, sin_precios))
                },
                solicitudes=list(de_solicitud.solicitudes) if de_solicitud else [],
                fecha_corte=ayer if conjunto == "CARTERA" else None,
            ))
    trabajos.extend(por_grupo.values())
    trabajos.extend(_agrupar(aparte, hoy, ()))
    return trabajos
