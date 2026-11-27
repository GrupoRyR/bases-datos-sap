"""Self-update of the robot and its pending complements (T6b of the automatic deploy).

The per-minute check (revisar_solicitudes.py), once it is outside the blocked slots and
holds the lock, asks the API which commit is deployed and calls actualizar():

    a. no commit, or the same as the local HEAD: nothing;
    b. the same commit failed less than an hour ago (robot/state/actualizacion.json): nothing,
       not even a git fetch, and no alert; another commit, or an hour later, is tried again;
    c. the copy must be on `main`;
    d. git fetch --quiet origin main;
    e. the commit must exist and be on origin/main;
    f. the local copy already ahead of it: nothing (not an error);
    g. HEAD must be an ancestor of it (fast-forward only);
    h. if robot/requirements.txt changes, it does not update at all: the coordinator updates
       the robot by hand (pip install -r requirements.txt and git pull --ff-only). Nothing
       installs packages by itself;
    i. git merge --ff-only <commit>: only git's own refusal stops it. If it refuses, the
       reason names the tracked files with local changes (git status --porcelain
       --untracked-files=no, paths only); if it succeeds anyway, they go in a warning.
       Untracked files never stop it and are never listed;
    j. HEAD must be the commit afterwards.

A failure of c, e, g, h, i or j is remembered for that commit (b). One of git itself (fetch,
rev-parse, merge-base) is not: it may be the network, so the next minute tries again. A good
update or a copy already up to date forgets the failure.

It never touches robot/.env, never uses --forzar and never runs pip, git pull or reset.
Only robot/requirements.txt matters: robot/requirements-dev.txt is for the tests and the
TI PC does not need it.

robot/complementos.toml lists the one-off complements to run after a deploy (today only
`complemento-ventas`); robot/state/complementos.json, outside git, records which ones are
done and which failed at which commit. A failed one is retried only after the next
deploy, never every minute.

Commands, git's answers and the state never carry SAP values.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import config
from registro import obtener

log = obtener("autoactualizar")

RAMA = "main"
REMOTO = "origin"
REQUISITOS = "robot/requirements.txt"  # relative to the repository root, as git sees it
TIMEOUT_GIT_S = 120
MAX_MOTIVO = 300
REINTENTO = timedelta(hours=1)  # a failed commit is tried again after this
MAX_RUTAS = 10  # tracked files with local changes named in a message

AL_DIA = "al_dia"
ACTUALIZADO = "actualizado"
FALLO = "fallo"
ESPERA = "espera"  # the same commit failed less than REINTENTO ago: not tried, not alerted

RUTA_COMPLEMENTOS = config.ROBOT_DIR / "complementos.toml"
MODOS_COMPLEMENTO = ("complemento-ventas",)
_CLAVES_COMPLEMENTO = {"id", "modo", "argumentos"}

_RE_SHA = re.compile(r"^[0-9a-f]{40}$")
_RE_CREDENCIAL_URL = re.compile(r"://[^/@\s]+@")


@dataclass(frozen=True)
class Salida:
    """What a command answered: exit code, stdout and stderr."""

    codigo: int
    salida: str = ""
    error: str = ""


Ejecutor = Callable[[list[str]], Salida]
Lanzador = Callable[[list[str], Path], None]


def correr(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
           timeout: int) -> Salida:
    """Runs a command without a shell or a window. Never raises: a missing program or a
    timeout is a Salida with an exit code other than 0."""
    try:
        res = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError:
        return Salida(127, "", f"No se encontró el programa {cmd[0]}.")
    except subprocess.TimeoutExpired:
        return Salida(124, "", f"{Path(cmd[0]).name} no respondió en {timeout} s.")
    except OSError as exc:
        return Salida(126, "", f"No se pudo correr {Path(cmd[0]).name}: {exc.__class__.__name__}.")
    return Salida(res.returncode, res.stdout or "", res.stderr or "")


def ejecutar_git(args: list[str]) -> Salida:
    """git -C <repository root>, never asking for credentials (GIT_TERMINAL_PROMPT=0)."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    return correr(["git", "-C", str(config.ROBOT_DIR.parent), *args], env=env, timeout=TIMEOUT_GIT_S)


def comando_tras_despliegue() -> list[str]:
    """The new process: the same python (pythonw.exe in the scheduled task) and the new code."""
    return [sys.executable, str(config.BASE_DIR / "run_robot.py"), "--tras-despliegue"]


def lanzar_proceso(cmd: list[str], cwd: Path) -> None:
    """Starts `cmd` detached: no console, no window, no inherited handles. It outlives the
    per-minute check. On Windows it first tries to leave the scheduled task's job, if the job
    allows it."""
    comunes: dict[str, Any] = dict(
        cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    if sys.platform != "win32":
        subprocess.Popen(cmd, start_new_session=True, **comunes)
        return
    banderas = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    fuera_del_job = getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    if fuera_del_job:
        try:
            subprocess.Popen(cmd, creationflags=banderas | fuera_del_job, **comunes)
            return
        except OSError:
            log.debug("El job de la tarea no deja salir al proceso nuevo; se lanza dentro de él.")
    subprocess.Popen(cmd, creationflags=banderas, **comunes)


# The defaults, looked up at call time: the tests replace them (conftest.py) so that no test
# runs the real git or a new process.
git_por_defecto: Ejecutor = ejecutar_git
lanzador_por_defecto: Lanzador = lanzar_proceso


# --- actualizar() -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Resultado:
    estado: str  # AL_DIA, ACTUALIZADO, FALLO or ESPERA
    antes: str | None = None
    despues: str | None = None
    motivo: str = ""
    recordado: bool = False  # FALLO remembered for this commit: not tried again for an hour
    cambios_locales: tuple[str, ...] = ()  # tracked files with local changes (paths only)


class _Fallo(Exception):
    """A step of the update that stops it; the message is the reason (Spanish, short).
    `recordar` is False for a failure of git itself, which may be the network."""

    def __init__(self, mensaje: str, *, recordar: bool = True) -> None:
        super().__init__(mensaje)
        self.recordar = recordar


def resumir(texto: str) -> str:
    """git's answer on one short line, without credentials in URLs."""
    linea = " | ".join(p.strip() for p in (texto or "").splitlines() if p.strip())
    linea = _RE_CREDENCIAL_URL.sub("://***@", linea)
    return linea if len(linea) <= MAX_MOTIVO else linea[: MAX_MOTIVO - 1] + "…"


def _sin_rutas(texto: str) -> str:
    """git's refusal without its indented list of files: the untracked ones are never named,
    and the tracked ones come from git status."""
    return "\n".join(linea for linea in (texto or "").splitlines() if not linea[:1].isspace())


def rutas_modificadas(porcelana: str) -> list[str]:
    """Repo-relative paths of `git status --porcelain` (v1); for a rename, the new path."""
    rutas = []
    for linea in (porcelana or "").splitlines():
        ruta = linea[3:].strip()
        if " -> " in ruta:
            ruta = ruta.split(" -> ", 1)[1]
        if ruta:
            rutas.append(ruta)
    return rutas


def describir_cambios_locales(rutas: tuple[str, ...] | list[str]) -> str:
    """«La copia tiene cambios locales en archivos con seguimiento: a, b y 3 más.»"""
    nombradas = ", ".join(rutas[:MAX_RUTAS])
    resto = f" y {len(rutas) - MAX_RUTAS} más" if len(rutas) > MAX_RUTAS else ""
    return f"La copia tiene cambios locales en archivos con seguimiento: {nombradas}{resto}."


def _cambios_locales(git: Ejecutor) -> tuple[str, ...]:
    """Tracked files with local changes; never the untracked ones. () if git does not answer."""
    salida = git(["status", "--porcelain", "--untracked-files=no"])
    return tuple(rutas_modificadas(salida.salida)) if salida.codigo == 0 else ()


def _git_ok(git: Ejecutor, *args: str, que: str) -> str:
    salida = git(list(args))
    if salida.codigo != 0:
        raise _Fallo(f"{que} falló ({salida.codigo}): {resumir(salida.error or salida.salida) or 'sin detalle'}.",
                     recordar=False)
    return salida.salida.strip()


def _es_ancestro(git: Ejecutor, a: str, b: str) -> bool:
    salida = git(["merge-base", "--is-ancestor", a, b])
    if salida.codigo in (0, 1):
        return salida.codigo == 0
    raise _Fallo(f"git merge-base falló ({salida.codigo}): {resumir(salida.error) or 'sin detalle'}.",
                 recordar=False)


def commit_actual(git: Ejecutor | None = None) -> str | None:
    """The local HEAD, or None if git does not answer."""
    salida = (git or git_por_defecto)(["rev-parse", "HEAD"])
    sha = salida.salida.strip()
    return sha if salida.codigo == 0 and _RE_SHA.match(sha) else None


# --- robot/state/actualizacion.json: the last failed update ------------------------------------


def _ruta_memoria() -> Path:
    return config.STATE_DIR / "actualizacion.json"


def leer_memoria() -> dict[str, str] | None:
    """{"commit", "en", "motivo"} of the last failed update, or None. An unreadable file
    counts as none (with a warning): the next attempt rewrites it."""
    ruta = _ruta_memoria()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        datetime.fromisoformat(datos["en"])
        if not isinstance(datos["commit"], str) or not isinstance(datos.get("motivo", ""), str):
            raise TypeError
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        log.warning("No se pudo leer %s: se toma como si no hubiera una actualización fallida.", ruta)
        return None
    return datos


def _recordar(commit: str, momento: datetime, motivo: str) -> None:
    ruta = _ruta_memoria()
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        temporal = ruta.with_name(f".{ruta.name}.{os.getpid()}.tmp")
        datos = {"commit": commit, "en": momento.isoformat(), "motivo": motivo}
        temporal.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
        os.replace(temporal, ruta)
    except OSError:
        log.warning("No se pudo guardar %s; se reintenta el minuto siguiente.", ruta, exc_info=True)


def _olvidar() -> None:
    try:
        _ruta_memoria().unlink()
    except FileNotFoundError:
        pass
    except OSError:
        log.warning("No se pudo borrar %s.", _ruta_memoria(), exc_info=True)


def actualizar(
    commit: str | None, *, git: Ejecutor | None = None, ahora: Callable[[], datetime] = config.ahora
) -> Resultado:
    """Brings the local copy to `commit` (the deployed one) by fast-forward. Never raises for
    an expected failure: it returns a Resultado with FALLO (or ESPERA) and the reason."""
    git = git or git_por_defecto
    if commit is None:
        log.debug("La API no informa un commit desplegado: no hay nada que actualizar.")
        return Resultado(AL_DIA)
    if not _RE_SHA.match(commit):
        return Resultado(FALLO, motivo="El commit desplegado no tiene el formato de un SHA de 40 caracteres.")
    antes: str | None = None
    cambios: tuple[str, ...] = ()
    try:
        antes = _git_ok(git, "rev-parse", "HEAD", que="git rev-parse HEAD")
        if antes == commit:
            log.debug("La copia del robot ya está en el commit desplegado %s.", commit[:12])
            _olvidar()
            return Resultado(AL_DIA, antes, antes)
        previo = leer_memoria()
        if previo is not None and previo["commit"] == commit:
            desde = ahora() - datetime.fromisoformat(previo["en"])
            if desde < REINTENTO:
                log.debug("La actualización a %s falló hace %s; se reintenta pasada una hora.",
                          commit[:12], str(desde).split(".")[0])
                return Resultado(ESPERA, antes, antes, previo.get("motivo", ""))
        rama = _git_ok(git, "rev-parse", "--abbrev-ref", "HEAD", que="git rev-parse --abbrev-ref HEAD")
        if rama != RAMA:
            raise _Fallo(f"La copia del robot no está en {RAMA} (está en {rama}).")
        _git_ok(git, "fetch", "--quiet", REMOTO, RAMA, que=f"git fetch {REMOTO} {RAMA}")
        if git(["cat-file", "-e", f"{commit}^{{commit}}"]).codigo != 0:
            raise _Fallo(f"El commit {commit[:12]} no existe en {REMOTO}/{RAMA}.")
        if not _es_ancestro(git, commit, f"{REMOTO}/{RAMA}"):
            raise _Fallo(f"El commit {commit[:12]} no está en {REMOTO}/{RAMA}.")
        if _es_ancestro(git, commit, "HEAD"):
            log.debug("La copia del robot (%s) va adelante del commit desplegado %s: no se toca.",
                      antes[:12], commit[:12])
            _olvidar()
            return Resultado(AL_DIA, antes, antes)
        if not _es_ancestro(git, "HEAD", commit):
            raise _Fallo(f"Ir de {antes[:12]} a {commit[:12]} no es un avance rápido (la copia local se desvió).")
        if _git_ok(git, "diff", "--name-only", "HEAD", commit, "--", REQUISITOS, que="git diff"):
            raise _Fallo("requirements.txt cambió: el coordinador debe actualizar el robot a mano "
                         "(pip install -r requirements.txt y git pull --ff-only).")
        # Only to name them: git's own refusal decides (a change that does not overlap the
        # deploy does not stop a fast-forward).
        cambios = _cambios_locales(git)
        salida = git(["merge", "--ff-only", "--quiet", commit])
        if salida.codigo != 0:
            motivo = f"git merge --ff-only se negó: {resumir(_sin_rutas(salida.error or salida.salida)) or 'sin detalle'}."
            raise _Fallo(f"{motivo} {describir_cambios_locales(cambios)}" if cambios else motivo)
        despues = _git_ok(git, "rev-parse", "HEAD", que="git rev-parse HEAD")
        if despues != commit:
            raise _Fallo(f"Después del merge, HEAD quedó en {despues[:12]} y no en {commit[:12]}.")
    except _Fallo as exc:
        if exc.recordar:
            _recordar(commit, ahora(), str(exc))
        return Resultado(FALLO, antes, antes, str(exc), recordado=exc.recordar, cambios_locales=cambios)
    _olvidar()
    return Resultado(ACTUALIZADO, antes, commit, cambios_locales=cambios)


# --- complementos.toml ------------------------------------------------------------------------


@dataclass(frozen=True)
class Complemento:
    id: str
    modo: str  # one of MODOS_COMPLEMENTO: the run_robot.py option without the dashes
    argumentos: tuple[str, ...]


Validar = Callable[[str, list[str]], Any]


def cargar_complementos(validar: Validar, ruta: Path | None = None) -> tuple[list[Complemento], list[str]]:
    """The valid entries of complementos.toml, in order, and the problems found.

    `validar(modo, argumentos)` raises ValueError if run_robot would not accept them
    (run_robot.plan_complemento). An invalid entry is skipped, never marked done; a file
    that cannot be read gives no entries. A missing file is just no entries.
    """
    ruta = ruta or RUTA_COMPLEMENTOS
    try:
        datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        log.debug("No hay %s: no hay complementos.", ruta.name)
        return [], []
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        return [], [f"{ruta.name} no se pudo leer: {resumir(str(exc))}"]
    crudas = datos.get("complemento", [])
    if not isinstance(crudas, list):
        return [], [f"{ruta.name}: «complemento» debe ser una lista de tablas [[complemento]]."]
    otras = sorted(set(datos) - {"complemento"})
    problemas = [f"{ruta.name}: claves desconocidas {', '.join(otras)}."] if otras else []

    ids = [c.get("id") for c in crudas if isinstance(c, dict)]
    repetidos = {i for i in ids if isinstance(i, str) and ids.count(i) > 1}
    validas: list[Complemento] = []
    for numero, cruda in enumerate(crudas, start=1):
        try:
            validas.append(_complemento(cruda, repetidos, validar))
        except ValueError as exc:
            nombre = cruda.get("id") if isinstance(cruda, dict) and isinstance(cruda.get("id"), str) else None
            problemas.append(f"Complemento {nombre or f'#{numero}'}: {exc}")
    return validas, problemas


def _complemento(cruda: Any, repetidos: set[str], validar: Validar) -> Complemento:
    if not isinstance(cruda, dict):
        raise ValueError("cada [[complemento]] debe ser una tabla.")
    otras = sorted(set(cruda) - _CLAVES_COMPLEMENTO)
    if otras:
        raise ValueError(f"claves desconocidas: {', '.join(otras)} (van id, modo y argumentos).")
    id_ = cruda.get("id")
    if not isinstance(id_, str) or not id_.strip() or id_ != id_.strip():
        raise ValueError("el id debe ser un texto no vacío, sin espacios al principio ni al final.")
    if id_ in repetidos:
        raise ValueError("id repetido: ninguna de sus entradas corre.")
    modo = cruda.get("modo")
    if modo not in MODOS_COMPLEMENTO:
        raise ValueError(f"modo {modo!r} no permitido (solo {', '.join(MODOS_COMPLEMENTO)}).")
    argumentos = cruda.get("argumentos", [])
    if not isinstance(argumentos, list) or not all(isinstance(a, str) for a in argumentos):
        raise ValueError("argumentos debe ser una lista de textos.")
    validar(modo, list(argumentos))
    return Complemento(id_, modo, tuple(argumentos))


# --- robot/state/complementos.json ------------------------------------------------------------


class EstadoIlegible(RuntimeError):
    """complementos.json exists but cannot be read: nothing is pending until it is fixed."""


def _ruta_estado() -> Path:
    return config.STATE_DIR / "complementos.json"


def leer_estado() -> dict[str, dict[str, Any]]:
    """{id: {"estado": "hecho" | "fallido", "commit", "en", "motivo"}}. {} if there is none."""
    ruta = _ruta_estado()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise EstadoIlegible(
            f"No se pudo leer {ruta}: {exc.__class__.__name__}. Mientras no se arregle (o se borre, "
            "y los complementos vuelven a correr), no corre ningún complemento."
        ) from exc
    if not isinstance(datos, dict) or not all(isinstance(v, dict) for v in datos.values()):
        raise EstadoIlegible(f"{ruta} no tiene la forma esperada; no corre ningún complemento.")
    return datos


def marcar(id_: str, *, hecho: bool, commit: str | None, momento: datetime, motivo: str = "") -> None:
    """Records a complement as done or failed at `commit`. Written atomically (tmp + replace)."""
    try:
        estado = leer_estado()
    except EstadoIlegible:
        estado = {}  # this write fixes it
    estado[id_] = {
        "estado": "hecho" if hecho else "fallido",
        "commit": commit,
        "en": momento.isoformat(),
        "motivo": resumir(motivo),
    }
    ruta = _ruta_estado()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f".{ruta.name}.{os.getpid()}.tmp")
    temporal.write_text(json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    os.replace(temporal, ruta)


def pendientes(
    entradas: list[Complemento], estado: dict[str, dict[str, Any]], commit: Callable[[], str | None]
) -> list[Complemento]:
    """Entries not done and not failed at the current commit. `commit()` (the local HEAD) is
    only asked when an entry failed before; if it is unknown, the failed one waits."""
    actual: list[str | None] = []

    def head() -> str | None:
        if not actual:
            actual.append(commit())
        return actual[0]

    lista: list[Complemento] = []
    for c in entradas:
        previo = estado.get(c.id)
        if previo is None:
            lista.append(c)
        elif previo.get("estado") == "fallido":
            sha = head()
            if sha is not None and previo.get("commit") != sha:
                lista.append(c)
    return lista
