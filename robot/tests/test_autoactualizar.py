"""Self-update of the robot (T6b): autoactualizar.py, the per-minute check and --tras-despliegue.

Everything runs with fakes: a fake git that models a tiny commit graph, a fake command
runner for pip, a fake launcher for the new process and the fake API of fake_api.py.
"""
from __future__ import annotations

import json
import logging
import sys
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import autoactualizar
import config
import revisar_solicitudes
import run_robot
from api import ApiError
from autoactualizar import ACTUALIZADO, AL_DIA, FALLO, Salida
from conftest import AHORA
from test_complemento import _datos_de_junio
from test_historico import _no_dormir, _Reloj
from test_run_robot import _estado, _main

A, B, C, X = "a" * 40, "b" * 40, "c" * 40, "e" * 40  # A <- B <- C on origin/main; X diverges
CANDADO = "robot.lock"


class GitFalso:
    """A tiny repository: commits with one parent each, HEAD, the branch and origin/main.

    The commits in `remotos` only become known after `git fetch`. Any command the robot
    is not expected to run (git status, git pull, git reset...) fails the test.
    """

    def __init__(
        self,
        *,
        head: str = A,
        rama: str = "main",
        padres: dict[str, str | None] | None = None,
        remotos: tuple[str, ...] = (B, C),
        origin: str = C,
        cambiados: tuple[str, ...] = (),
        fetch_error: str = "",
        merge_error: str = "",
        merge_no_mueve: bool = False,
        rev_parse_error: bool = False,
    ) -> None:
        self.head = head
        self.rama = rama
        self.padres = padres if padres is not None else {A: None, B: A, C: B, X: A}
        self.remotos = set(remotos)
        self.conocidos = set(self.padres) - self.remotos
        self.origin_local = head
        self.origin = origin
        self.cambiados = cambiados
        self.fetch_error = fetch_error
        self.merge_error = merge_error
        self.merge_no_mueve = merge_no_mueve
        self.rev_parse_error = rev_parse_error
        self.comandos: list[list[str]] = []

    def _ref(self, ref: str) -> str | None:
        sha = {"HEAD": self.head, "origin/main": self.origin_local}.get(ref, ref)
        return sha if sha in self.conocidos else None

    def _ancestro(self, a: str, b: str) -> bool:
        actual: str | None = b
        while actual is not None:
            if actual == a:
                return True
            actual = self.padres.get(actual)
        return False

    def __call__(self, args: list[str]) -> Salida:
        args = list(args)
        self.comandos.append(args)
        match args:
            case ["rev-parse", "HEAD"]:
                if self.rev_parse_error:
                    return Salida(128, "", "fatal: not a git repository")
                return Salida(0, self.head + "\n")
            case ["rev-parse", "--abbrev-ref", "HEAD"]:
                return Salida(0, self.rama + "\n")
            case ["fetch", "--quiet", "origin", "main"]:
                if self.fetch_error:
                    return Salida(128, "", self.fetch_error)
                self.conocidos |= self.remotos
                self.origin_local = self.origin
                return Salida(0)
            case ["cat-file", "-e", objeto]:
                sha = objeto.removesuffix("^{commit}")
                return Salida(0) if sha in self.conocidos else Salida(128, "", "fatal: Not a valid object name")
            case ["merge-base", "--is-ancestor", a, b]:
                ra, rb = self._ref(a), self._ref(b)
                if ra is None or rb is None:
                    return Salida(128, "", "fatal: Not a valid commit name")
                return Salida(0 if self._ancestro(ra, rb) else 1)
            case ["diff", "--name-only", "HEAD", _, "--", ruta]:
                return Salida(0, "".join(f"{c}\n" for c in self.cambiados if c == ruta))
            case ["show", objeto] if objeto.endswith(":robot/requirements.txt"):
                return Salida(0, "hdbcli==9.9.9\npython-dotenv==1.2.4\n")
            case ["merge", "--ff-only", "--quiet", sha]:
                if self.merge_error:
                    return Salida(1, "", self.merge_error)
                if not self.merge_no_mueve:
                    self.head = sha
                return Salida(0)
        raise AssertionError(f"comando de git inesperado: {args}")

    def hizo(self, primero: str) -> bool:
        return any(c[0] == primero for c in self.comandos)


class ComandosFalsos:
    """Fake runner for pip: records every command and answers `codigo`."""

    def __init__(self, codigo: int = 0, error: str = "") -> None:
        self.codigo = codigo
        self.error = error
        self.comandos: list[list[str]] = []
        self.requisitos: list[str] = []

    def __call__(self, cmd: list[str]) -> Salida:
        self.comandos.append(list(cmd))
        if "-r" in cmd:
            self.requisitos.append(Path(cmd[cmd.index("-r") + 1]).read_text(encoding="utf-8"))
        return Salida(self.codigo, "", self.error)


class LanzadorFalso:
    """Fake launcher: records the command and whether the lock was already free."""

    def __init__(self, error: OSError | None = None) -> None:
        self.lanzados: list[tuple[list[str], Path]] = []
        self.candado_suelto: list[bool] = []
        self.error = error

    def __call__(self, cmd: list[str], cwd: Path) -> None:
        self.candado_suelto.append(not (config.STATE_DIR / CANDADO).exists())
        if self.error is not None:
            raise self.error
        self.lanzados.append((list(cmd), cwd))


def _prohibida(*args, **kwargs):
    raise AssertionError("no debía llamarse")


def _escribir_complementos(texto: str) -> None:
    autoactualizar.RUTA_COMPLEMENTOS.parent.mkdir(parents=True, exist_ok=True)
    autoactualizar.RUTA_COMPLEMENTOS.write_text(texto, encoding="utf-8")


def _validar(modo: str, argumentos: list[str]):
    return run_robot.plan_complemento(modo, argumentos, lambda: AHORA)


# --- api.version() (contract §13.1: POST /version, {"commit": sha | null}) -------------------


@pytest.fixture
def cliente_api(escenario):
    return escenario.cliente, escenario.servidor


def test_version_devuelve_el_commit_desplegado_con_un_post_firmado(cliente_api):
    cliente, servidor = cliente_api
    servidor.commit_desplegado = C
    assert cliente.version() == C
    [peticion] = servidor.peticiones
    assert (peticion.nombre, peticion.ruta, peticion.status, peticion.datos) == (
        "version", "/api/robot/v1/version", 200, {})
    assert "x-robot-signature" in peticion.headers  # the fake API verified it


def test_version_null_es_none(cliente_api):
    cliente, servidor = cliente_api
    assert cliente.version() is None


@pytest.mark.parametrize("valor", ["abc", C.upper(), C[:39], C + "0", 12, ["x"], ""])
def test_version_con_un_valor_raro_es_un_error(cliente_api, valor):
    cliente, servidor = cliente_api
    servidor.commit_desplegado = valor
    with pytest.raises(ApiError):
        cliente.version()


def test_version_sin_la_llave_commit_es_un_error(cliente_api):
    cliente, servidor = cliente_api
    servidor.programar_fallas("version", status=200, datos={"otro": 1})
    with pytest.raises(ApiError):
        cliente.version()


# --- actualizar() ----------------------------------------------------------------------------


def test_sin_commit_del_servidor_no_toca_git():
    git = GitFalso()
    resultado = autoactualizar.actualizar(None, git=git, comando=_prohibida)
    assert resultado.estado == AL_DIA
    assert git.comandos == []


def test_commit_igual_al_local_no_hace_fetch_ni_merge():
    git = GitFalso()
    resultado = autoactualizar.actualizar(A, git=git, comando=_prohibida)
    assert (resultado.estado, resultado.antes, resultado.despues) == (AL_DIA, A, A)
    assert git.comandos == [["rev-parse", "HEAD"]]


def test_avance_rapido_hace_fetch_y_merge_ff_only_y_verifica_head():
    git = GitFalso()
    resultado = autoactualizar.actualizar(C, git=git, comando=_prohibida)
    assert (resultado.estado, resultado.antes, resultado.despues, resultado.requisitos) == (ACTUALIZADO, A, C, False)
    assert git.comandos == [
        ["rev-parse", "HEAD"],
        ["rev-parse", "--abbrev-ref", "HEAD"],
        ["fetch", "--quiet", "origin", "main"],
        ["cat-file", "-e", f"{C}^{{commit}}"],
        ["merge-base", "--is-ancestor", C, "origin/main"],
        ["merge-base", "--is-ancestor", C, "HEAD"],
        ["merge-base", "--is-ancestor", "HEAD", C],
        ["diff", "--name-only", "HEAD", C, "--", "robot/requirements.txt"],
        ["merge", "--ff-only", "--quiet", C],
        ["rev-parse", "HEAD"],
    ]
    assert git.head == C
    # Untracked files never stop it: git status is never asked.
    assert not git.hizo("status")


def test_fuera_de_main_no_hace_fetch_ni_merge():
    git = GitFalso(rama="feat/otra")
    resultado = autoactualizar.actualizar(C, git=git, comando=_prohibida)
    assert resultado.estado == FALLO
    assert "no está en main" in resultado.motivo and "feat/otra" in resultado.motivo
    assert not git.hizo("fetch") and not git.hizo("merge")


def test_commit_que_no_esta_en_origin_main_no_se_mezcla():
    # X exists only locally (an old branch): it is not on origin/main.
    git = GitFalso(padres={A: None, B: A, C: B, X: A}, remotos=(B, C))
    git.conocidos.add(X)
    resultado = autoactualizar.actualizar(X, git=git, comando=_prohibida)
    assert resultado.estado == FALLO and "origin/main" in resultado.motivo
    assert not git.hizo("merge")


def test_commit_desconocido_tras_el_fetch_falla():
    desconocido = "d" * 40
    git = GitFalso()
    resultado = autoactualizar.actualizar(desconocido, git=git, comando=_prohibida)
    assert resultado.estado == FALLO and "no existe" in resultado.motivo
    assert not git.hizo("merge")


def test_sin_avance_rapido_no_se_mezcla():
    # Local HEAD X diverged from origin/main (A <- X, A <- B <- C).
    git = GitFalso(head=X)
    resultado = autoactualizar.actualizar(C, git=git, comando=_prohibida)
    assert resultado.estado == FALLO and "avance rápido" in resultado.motivo
    assert not git.hizo("merge")


def test_copia_local_adelante_del_servidor_no_hace_nada():
    git = GitFalso(head=C, remotos=())
    resultado = autoactualizar.actualizar(B, git=git, comando=_prohibida)
    assert resultado.estado == AL_DIA
    assert not git.hizo("merge")


def test_merge_rechazado_por_git_falla_con_su_motivo_resumido():
    error = ("error: Your local changes to the following files would be overwritten by merge:\n"
             "\trobot/etl/run_robot.py\nPlease commit your changes or stash them before you merge.\nAborting\n")
    git = GitFalso(merge_error=error)
    resultado = autoactualizar.actualizar(C, git=git, comando=_prohibida)
    assert resultado.estado == FALLO
    assert "merge --ff-only" in resultado.motivo and "robot/etl/run_robot.py" in resultado.motivo
    assert "\n" not in resultado.motivo
    assert git.head == A


def test_merge_que_no_mueve_head_falla():
    git = GitFalso(merge_no_mueve=True)
    resultado = autoactualizar.actualizar(C, git=git, comando=_prohibida)
    assert resultado.estado == FALLO and "HEAD" in resultado.motivo


def test_fetch_fallido_no_muestra_credenciales_de_la_url():
    git = GitFalso(fetch_error="fatal: unable to access 'https://usuario:token-secreto@github.com/x/y.git/'")
    resultado = autoactualizar.actualizar(C, git=git, comando=_prohibida)
    assert resultado.estado == FALLO
    assert "token-secreto" not in resultado.motivo and "github.com" in resultado.motivo


def test_commit_con_formato_invalido_falla_sin_tocar_git():
    git = GitFalso()
    resultado = autoactualizar.actualizar("main; rm -rf", git=git, comando=_prohibida)
    assert resultado.estado == FALLO
    assert git.comandos == []


@pytest.fixture
def venv(tmp_path, monkeypatch) -> Path:
    """A fake venv: Scripts/pythonw.exe (what the scheduled task runs) and Scripts/python.exe."""
    scripts = tmp_path / "venv" / "Scripts"
    scripts.mkdir(parents=True)
    for nombre in ("python.exe", "pythonw.exe"):
        (scripts / nombre).write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(scripts / "pythonw.exe"))
    return scripts


def test_si_cambia_requirements_instala_con_python_exe_antes_del_merge(venv):
    git = GitFalso(cambiados=("robot/requirements.txt",))
    pip = ComandosFalsos()
    resultado = autoactualizar.actualizar(C, git=git, comando=pip)
    assert resultado.estado == ACTUALIZADO and resultado.requisitos
    [cmd] = pip.comandos
    assert cmd[:4] == [str(venv / "python.exe"), "-m", "pip", "install"]
    assert cmd[4] == "-r" and Path(cmd[5]).name == "requirements.txt"
    # The deployed requirements.txt, read from the commit with git show.
    assert pip.requisitos == ["hdbcli==9.9.9\npython-dotenv==1.2.4\n"]
    assert ["show", f"{C}:robot/requirements.txt"] in git.comandos
    assert git.comandos.index(["show", f"{C}:robot/requirements.txt"]) < git.comandos.index(
        ["merge", "--ff-only", "--quiet", C])


def test_si_solo_cambia_requirements_dev_no_instala_nada(venv):
    git = GitFalso(cambiados=("robot/requirements-dev.txt",))
    resultado = autoactualizar.actualizar(C, git=git, comando=_prohibida)
    assert resultado.estado == ACTUALIZADO and not resultado.requisitos


def test_si_pip_falla_no_se_mezcla_y_falla(venv):
    git = GitFalso(cambiados=("robot/requirements.txt",))
    pip = ComandosFalsos(codigo=1, error="ERROR: Could not find a version that satisfies hdbcli==9.9.9")
    resultado = autoactualizar.actualizar(C, git=git, comando=pip)
    assert resultado.estado == FALLO and "pip" in resultado.motivo
    assert not git.hizo("merge") and git.head == A


def test_python_consola_cambia_pythonw_por_python(venv, tmp_path):
    assert autoactualizar.python_consola() == venv / "python.exe"
    sola = tmp_path / "sola"
    sola.mkdir()
    (sola / "pythonw.exe").write_text("", encoding="utf-8")
    assert autoactualizar.python_consola(sola / "pythonw.exe") == sola / "pythonw.exe"  # no sibling


def test_git_real_corre_en_la_raiz_del_repo_sin_preguntar_credenciales(monkeypatch):
    llamadas = []
    monkeypatch.setattr(autoactualizar, "correr",
                        lambda cmd, **kw: llamadas.append((cmd, kw)) or Salida(0, "ok"))
    assert autoactualizar.ejecutar_git(["rev-parse", "HEAD"]) == Salida(0, "ok")
    [(cmd, kw)] = llamadas
    assert cmd == ["git", "-C", str(config.ROBOT_DIR.parent), "rev-parse", "HEAD"]
    assert kw["env"]["GIT_TERMINAL_PROMPT"] == "0"
    assert kw["timeout"] == autoactualizar.TIMEOUT_GIT_S


def test_correr_un_comando_que_no_existe_no_lanza():
    salida = autoactualizar.correr(["no-existe-este-comando-xyz"], timeout=5)
    assert salida.codigo != 0 and salida.error


def test_correr_devuelve_codigo_y_salida():
    salida = autoactualizar.correr([sys.executable, "-c", "print('hola')"], timeout=30)
    assert (salida.codigo, salida.salida.strip()) == (0, "hola")


def test_lanzar_proceso_desprendido_sin_ventana_ni_consola(monkeypatch, tmp_path):
    vistos = []

    class PopenFalso:
        def __init__(self, cmd, **kw):
            vistos.append((cmd, kw))

    monkeypatch.setattr(autoactualizar.subprocess, "Popen", PopenFalso)
    autoactualizar.lanzar_proceso(["python", "run_robot.py", "--tras-despliegue"], tmp_path)
    [(cmd, kw)] = vistos
    assert cmd == ["python", "run_robot.py", "--tras-despliegue"]
    assert kw["cwd"] == tmp_path
    import subprocess
    assert kw["stdin"] == kw["stdout"] == kw["stderr"] == subprocess.DEVNULL
    if sys.platform == "win32":
        for bandera in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
            assert kw["creationflags"] & getattr(subprocess, bandera)


def test_comando_tras_despliegue_usa_el_mismo_python_y_run_robot():
    cmd = autoactualizar.comando_tras_despliegue()
    assert cmd == [sys.executable, str(config.BASE_DIR / "run_robot.py"), "--tras-despliegue"]


# --- complementos.toml -----------------------------------------------------------------------


def test_el_complementos_toml_del_repo_se_lee_y_no_tiene_entradas_activas():
    ruta = config.ROBOT_DIR / "complementos.toml"
    datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
    assert datos.get("complemento", []) == []
    assert autoactualizar.cargar_complementos(_validar, ruta) == ([], [])
    assert b"\r\n" not in ruta.read_bytes()


def test_complementos_validos_en_orden():
    _escribir_complementos(
        '[[complemento]]\nid = "kilos-2025"\nmodo = "complemento-ventas"\n'
        'argumentos = ["--desde", "2026-06"]\n\n'
        '[[complemento]]\nid = "kilos-sdc"\nmodo = "complemento-ventas"\n'
        'argumentos = ["--desde", "2026-07", "--empresa", "SDC"]\n'
    )
    entradas, problemas = autoactualizar.cargar_complementos(_validar)
    assert problemas == []
    assert [(c.id, c.modo, c.argumentos) for c in entradas] == [
        ("kilos-2025", "complemento-ventas", ("--desde", "2026-06")),
        ("kilos-sdc", "complemento-ventas", ("--desde", "2026-07", "--empresa", "SDC")),
    ]


def test_sin_archivo_o_vacio_no_hay_complementos():
    assert autoactualizar.cargar_complementos(_validar) == ([], [])
    _escribir_complementos("# nada\n")
    assert autoactualizar.cargar_complementos(_validar) == ([], [])


def test_archivo_mal_formado_no_da_complementos_y_lo_reporta():
    _escribir_complementos('[[complemento]\nid = "x"\n')
    entradas, [problema] = autoactualizar.cargar_complementos(_validar)
    assert entradas == [] and "complementos.toml" in problema


@pytest.mark.parametrize("texto, motivo", [
    ('[[complemento]]\nid = "x"\nmodo = "complemento-ventas"\nargumentos = ["--desde", "2026-06"]\n'
     '[[complemento]]\nid = "x"\nmodo = "complemento-ventas"\nargumentos = ["--desde", "2026-07"]\n', "repetido"),
    ('[[complemento]]\nid = ""\nmodo = "complemento-ventas"\nargumentos = ["--desde", "2026-06"]\n', "id"),
    ('[[complemento]]\nid = "x"\nmodo = "completa"\nargumentos = []\n', "modo"),
    ('[[complemento]]\nid = "x"\nmodo = "complemento-ventas"\nargumentos = ["--desde", "2026-06", "--forzar"]\n',
     "--forzar"),
    ('[[complemento]]\nid = "x"\nmodo = "complemento-ventas"\nargumentos = ["--desde", "2026-06", "--sin-vpn"]\n',
     "--sin-vpn"),
    ('[[complemento]]\nid = "x"\nmodo = "complemento-ventas"\nargumentos = ["--desde", "2026-06", "--completa"]\n',
     "--completa"),
    ('[[complemento]]\nid = "x"\nmodo = "complemento-ventas"\nargumentos = ["--desde", "2026-06", "--forz"]\n',
     "--forz"),
    ('[[complemento]]\nid = "x"\nmodo = "complemento-ventas"\nargumentos = "--desde 2026-06"\n', "lista"),
    ('[[complemento]]\nid = "x"\nmodo = "complemento-ventas"\nargumentos = ["--desde", 2026]\n', "lista"),
    ('[[complemento]]\nid = "x"\nmodo = "complemento-ventas"\nargumentos = []\n', "--desde"),
    ('[[complemento]]\nid = "x"\nmodo = "complemento-ventas"\nargumentos = ["--desde", "2024-12"]\n', "2025-01"),
    ('[[complemento]]\nid = "x"\nmodo = "complemento-ventas"\nargumentos = ["--desde", "2026-06"]\notro = 1\n',
     "otro"),
])
def test_entrada_invalida_se_salta_y_se_reporta(texto, motivo):
    _escribir_complementos(
        texto + '[[complemento]]\nid = "buena"\nmodo = "complemento-ventas"\nargumentos = ["--desde", "2026-09"]\n'
    )
    entradas, problemas = autoactualizar.cargar_complementos(_validar)
    assert [c.id for c in entradas] == ["buena"]
    assert problemas and any(motivo in p for p in problemas), problemas


def _c(id_: str) -> autoactualizar.Complemento:
    return autoactualizar.Complemento(id_, "complemento-ventas", ("--desde", "2026-06"))


def test_pendientes_sin_hecho_ni_fallo_en_este_commit():
    momento = AHORA
    autoactualizar.marcar("hecho", hecho=True, commit=A, momento=momento)
    autoactualizar.marcar("fallo-aqui", hecho=False, commit=C, momento=momento, motivo="La API rechazó (422).")
    autoactualizar.marcar("fallo-antes", hecho=False, commit=A, momento=momento, motivo="x")
    estado = autoactualizar.leer_estado()
    assert estado["hecho"]["estado"] == "hecho" and estado["fallo-aqui"]["motivo"] == "La API rechazó (422)."
    entradas = [_c("nuevo"), _c("hecho"), _c("fallo-aqui"), _c("fallo-antes")]
    assert [c.id for c in autoactualizar.pendientes(entradas, estado, lambda: C)] == ["nuevo", "fallo-antes"]
    # Without knowing HEAD, a failed one is not retried (never every minute).
    assert [c.id for c in autoactualizar.pendientes(entradas, estado, lambda: None)] == ["nuevo"]


def test_el_estado_de_los_complementos_se_escribe_completo_y_fuera_de_git():
    autoactualizar.marcar("x", hecho=True, commit=C, momento=AHORA)
    ruta = config.STATE_DIR / "complementos.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    assert datos["x"] == {"estado": "hecho", "commit": C, "en": AHORA.isoformat(), "motivo": ""}
    assert not list(config.STATE_DIR.glob("*.tmp"))
    gitignore = (config.ROBOT_DIR.parent / ".gitignore").read_text(encoding="utf-8")
    assert "robot/state/" in gitignore


def test_estado_ilegible_lanza():
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    (config.STATE_DIR / "complementos.json").write_text("{roto", encoding="utf-8")
    with pytest.raises(autoactualizar.EstadoIlegible):
        autoactualizar.leer_estado()


# --- La revisión de cada minuto --------------------------------------------------------------


def _revisar(e, *, git=None, comando=_prohibida, lanzar=None, ahora=None, **kwargs) -> int:
    kwargs.setdefault("fabrica_api", lambda cfg_api: e.nuevo_cliente(cfg_api))
    kwargs.setdefault("fabrica_vpn", lambda cfg_vpn: e.vpn)
    kwargs.setdefault("conectar", e.hana.conectar)
    return revisar_solicitudes.main(
        [], ahora=ahora or e.ahora, git=git if git is not None else GitFalso(), comando=comando,
        lanzar=lanzar if lanzar is not None else LanzadorFalso(), **kwargs,
    )


def _nombres(e) -> list[str]:
    return [p.nombre for p in e.servidor.peticiones]


@pytest.mark.parametrize("desplegado", [None, A])
def test_sin_commit_nuevo_la_revision_sigue_como_siempre(entorno, correos, desplegado):
    e = entorno
    e.servidor.commit_desplegado = desplegado
    git, lanzar = GitFalso(), LanzadorFalso()
    assert _revisar(e, git=git, lanzar=lanzar) == 0
    assert _nombres(e) == ["version", "tomar"]
    assert not git.hizo("fetch") and not git.hizo("merge")
    assert lanzar.lanzados == []
    assert correos == []


def test_commit_nuevo_actualiza_suelta_el_candado_y_lanza_el_proceso_nuevo(entorno, correos, caplog):
    e = entorno
    e.servidor.commit_desplegado = C
    git, lanzar = GitFalso(), LanzadorFalso()
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _revisar(e, git=git, lanzar=lanzar) == 0
    assert ["merge", "--ff-only", "--quiet", C] in git.comandos and git.head == C
    assert lanzar.lanzados == [(autoactualizar.comando_tras_despliegue(), config.BASE_DIR)]
    assert lanzar.candado_suelto == [True]
    assert _nombres(e) == ["version"]  # this minute does not take requests: the new code does
    assert not (config.STATE_DIR / CANDADO).exists()
    assert any("actualizado" in m and A[:12] in m and C[:12] in m for m in caplog.messages)
    assert correos == []


def test_fuera_de_main_avisa_con_limite_y_atiende_las_solicitudes(entorno, correos):
    e = entorno
    e.servidor.commit_desplegado = C
    e.servidor.encolar_solicitud({"id": 7, "empresa": "SGX", "conjunto": "CARTERA", "parte": None, "desde": {}})
    git, lanzar = GitFalso(rama="hotfix"), LanzadorFalso()
    assert _revisar(e, git=git, lanzar=lanzar) == 0
    assert not git.hizo("fetch") and not git.hizo("merge")
    assert lanzar.lanzados == []
    assert e.servidor.estado_solicitudes == {7: "terminada"}
    assert [[etapa for etapa, _ in c] for c in correos] == [["AUTOACTUALIZAR"]]
    assert "no está en main" in correos[0][0][1]
    assert _revisar(e, git=GitFalso(rama="hotfix"), lanzar=lanzar) == 0  # next minute: no new email
    assert len(correos) == 1
    una_hora = lambda: AHORA + timedelta(hours=1, minutes=1)  # noqa: E731
    assert _revisar(e, git=GitFalso(rama="hotfix"), lanzar=lanzar, ahora=una_hora) == 0
    assert len(correos) == 2


@pytest.mark.parametrize("git, texto", [
    (lambda: GitFalso(head=X), "avance rápido"),
    (lambda: GitFalso(merge_error="error: The following untracked working tree files would be overwritten "
                                  "by merge:\n\trobot/etl/nuevo.py\nAborting"), "merge --ff-only"),
])
def test_fallo_de_la_actualizacion_avisa_y_no_lanza(entorno, correos, git, texto):
    e = entorno
    e.servidor.commit_desplegado = C
    lanzar = LanzadorFalso()
    assert _revisar(e, git=git(), lanzar=lanzar) == 0
    assert lanzar.lanzados == []
    assert _nombres(e) == ["version", "tomar"]
    [aviso] = correos
    assert aviso[0][0] == "AUTOACTUALIZAR" and texto in aviso[0][1]


def test_commit_desplegado_fuera_de_origin_main_avisa(entorno, correos):
    e = entorno
    e.servidor.commit_desplegado = X
    git = GitFalso()
    git.conocidos.add(X)
    assert _revisar(e, git=git) == 0
    assert not git.hizo("merge")
    assert "origin/main" in correos[0][0][1]


def test_copia_local_adelante_no_avisa(entorno, correos):
    e = entorno
    e.servidor.commit_desplegado = B
    lanzar = LanzadorFalso()
    assert _revisar(e, git=GitFalso(head=C, remotos=()), lanzar=lanzar) == 0
    assert lanzar.lanzados == [] and correos == []


def test_pip_que_falla_avisa_y_no_lanza(entorno, correos, venv):
    e = entorno
    e.servidor.commit_desplegado = C
    git, lanzar = GitFalso(cambiados=("robot/requirements.txt",)), LanzadorFalso()
    assert _revisar(e, git=git, comando=ComandosFalsos(codigo=1, error="sin red"), lanzar=lanzar) == 0
    assert lanzar.lanzados == [] and not git.hizo("merge")
    assert correos[0][0][0] == "AUTOACTUALIZAR" and "pip" in correos[0][0][1]


def test_pip_que_funciona_lanza_el_proceso_nuevo(entorno, correos, venv):
    e = entorno
    e.servidor.commit_desplegado = C
    pip, lanzar = ComandosFalsos(), LanzadorFalso()
    assert _revisar(e, git=GitFalso(cambiados=("robot/requirements.txt",)), comando=pip, lanzar=lanzar) == 0
    assert pip.comandos[0][0] == str(venv / "python.exe")
    assert len(lanzar.lanzados) == 1


def test_dentro_de_una_franja_no_pregunta_la_version(entorno, correos):
    e = entorno
    e.servidor.commit_desplegado = C
    a_las_12 = lambda: datetime(2026, 10, 26, 12, 5, tzinfo=config.BOGOTA)  # noqa: E731
    git = GitFalso()
    assert _revisar(e, git=git, ahora=a_las_12, fabrica_api=_prohibida) == 0
    assert e.servidor.peticiones == [] and git.comandos == []


def test_con_el_candado_ocupado_no_pregunta_la_version(entorno, correos, candado_ajeno):
    e = entorno
    e.servidor.commit_desplegado = C
    candado_ajeno()
    git = GitFalso()
    assert _revisar(e, git=git, fabrica_api=_prohibida) == 0
    assert e.servidor.peticiones == [] and git.comandos == []


@pytest.mark.parametrize("falla", [dict(status=404), dict(status=503, veces=4), dict(red=True, veces=4)])
def test_error_al_preguntar_la_version_no_frena_la_revision(entorno, correos, caplog, falla):
    e = entorno
    e.servidor.commit_desplegado = C
    e.servidor.programar_fallas("version", **falla)
    e.servidor.encolar_solicitud({"id": 9, "empresa": "SGX", "conjunto": "CARTERA", "parte": None, "desde": {}})
    git = GitFalso()
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _revisar(e, git=git) == 0
    assert e.servidor.estado_solicitudes == {9: "terminada"}
    assert not git.hizo("fetch")
    assert correos == []
    # The route may not exist yet on an older server: it must not fill robot.log.
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_version_con_formato_invalido_no_actualiza(entorno, correos):
    e = entorno
    e.servidor.commit_desplegado = "no-es-un-sha"
    git = GitFalso()
    assert _revisar(e, git=git) == 0
    assert git.comandos == []
    assert _nombres(e) == ["version", "tomar"]


def test_sin_trabajo_y_sin_commit_nuevo_no_escribe_en_el_log(entorno, correos, caplog):
    e = entorno
    e.servidor.commit_desplegado = A
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _revisar(e) == 0
    assert [r for r in caplog.records if r.levelno >= logging.INFO] == []


_PENDIENTE = '[[complemento]]\nid = "kilos"\nmodo = "complemento-ventas"\nargumentos = ["--desde", "2026-06"]\n'


def test_complemento_pendiente_lanza_el_proceso_nuevo_sin_actualizar(entorno, correos):
    e = entorno
    _escribir_complementos(_PENDIENTE)
    lanzar = LanzadorFalso()
    assert _revisar(e, lanzar=lanzar) == 0
    assert len(lanzar.lanzados) == 1 and lanzar.candado_suelto == [True]
    assert _nombres(e) == ["version"]


def test_complemento_hecho_o_fallido_en_este_commit_no_lanza(entorno, correos):
    e = entorno
    _escribir_complementos(_PENDIENTE)
    lanzar = LanzadorFalso()
    autoactualizar.marcar("kilos", hecho=False, commit=A, momento=AHORA, motivo="x")
    assert _revisar(e, lanzar=lanzar) == 0
    autoactualizar.marcar("kilos", hecho=True, commit=A, momento=AHORA)
    assert _revisar(e, lanzar=lanzar) == 0
    assert lanzar.lanzados == []
    # A failure at an older commit is retried after the next deploy.
    autoactualizar.marcar("kilos", hecho=False, commit="9" * 40, momento=AHORA, motivo="x")
    assert _revisar(e, lanzar=lanzar) == 0
    assert len(lanzar.lanzados) == 1


def test_complemento_pendiente_que_no_cabe_antes_de_la_franja_espera_otro_minuto(entorno, correos):
    e = entorno
    _escribir_complementos(_PENDIENTE)
    lanzar = LanzadorFalso()
    a_las_4_43 = lambda: datetime(2026, 10, 26, 4, 43, tzinfo=config.BOGOTA)  # noqa: E731
    assert _revisar(e, lanzar=lanzar, ahora=a_las_4_43) == 0
    assert lanzar.lanzados == []
    assert _nombres(e) == ["version", "tomar"]


def test_complemento_invalido_avisa_con_limite_y_no_lanza(entorno, correos):
    e = entorno
    _escribir_complementos(_PENDIENTE.replace('"2026-06"]', '"2026-06", "--forzar"]'))
    lanzar = LanzadorFalso()
    assert _revisar(e, lanzar=lanzar) == 0
    assert _revisar(e, lanzar=lanzar) == 0
    assert lanzar.lanzados == []
    assert [[etapa for etapa, _ in c] for c in correos] == [["COMPLEMENTOS"]]
    assert "--forzar" in correos[0][0][1]


def test_si_no_se_puede_lanzar_avisa_y_sale_con_1(entorno, correos):
    e = entorno
    e.servidor.commit_desplegado = C
    lanzar = LanzadorFalso(error=OSError("sin permiso"))
    assert _revisar(e, lanzar=lanzar) == 1
    assert correos[0][0][0] == "AUTOACTUALIZAR"
    assert not (config.STATE_DIR / CANDADO).exists()


def test_error_inesperado_en_la_actualizacion_no_frena_la_revision(entorno, correos):
    e = entorno
    e.servidor.commit_desplegado = C

    def git_que_explota(args):
        raise RuntimeError("algo raro")

    assert _revisar(e, git=git_que_explota) == 0
    assert _nombres(e) == ["version", "tomar"]
    assert correos[0][0][0] == "AUTOACTUALIZAR" and "algo raro" not in correos[0][0][1]


# --- run_robot.py --tras-despliegue ---------------------------------------------------------


_DOS = (
    '[[complemento]]\nid = "kilos-sdc"\nmodo = "complemento-ventas"\n'
    'argumentos = ["--desde", "2026-06", "--empresa", "SDC"]\n\n'
    '[[complemento]]\nid = "kilos-sgx"\nmodo = "complemento-ventas"\n'
    'argumentos = ["--desde", "2026-06", "--empresa", "SGX"]\n'
)


@pytest.fixture
def comparacion(monkeypatch, entorno):
    """--tras-despliegue always ends with the comparison (T7b, tested in test_comparar.py): here
    it is replaced by a recorder, so these tests only see the complements. Each call records
    the companies and the API requests made before it."""
    llamadas: list[tuple[list[str], int]] = []

    def falsa(cfg, args, empresas, **kwargs):
        llamadas.append((list(empresas), len(entorno.servidor.peticiones)))
        return [], []

    monkeypatch.setattr(run_robot, "_comparar", falsa)
    return llamadas


def test_tras_despliegue_corre_los_complementos_pendientes_en_orden(entorno, correos, caplog, comparacion):
    e = entorno
    _datos_de_junio(e)
    _escribir_complementos(_DOS)
    with caplog.at_level(logging.INFO, logger="bases_sap"):
        assert _main(e, "--tras-despliegue", git=GitFalso(head=C), dormir=_no_dormir) == 0
    corridas = [(c.empresa, c.tipo, c.ventana_desde, c.estado) for c in e.servidor.corridas.values()]
    assert [c[:2] for c in corridas] == [("SDC", "complemento")] * 3 + [("SGX", "complemento")] * 4
    assert all(c[3] == "cerrada" for c in corridas)
    assert e.vpn.conexiones == 2  # one VPN session per complement, as the manual mode
    estado = autoactualizar.leer_estado()
    assert {k: (v["estado"], v["commit"]) for k, v in estado.items()} == {
        "kilos-sdc": ("hecho", C), "kilos-sgx": ("hecho", C)}
    final = _estado()
    assert (final["estado"], final["modo"]) == ("OK", "tras despliegue")
    assert [c["id"] for c in final["complementos"]] == ["kilos-sdc", "kilos-sgx"]
    assert any(m.startswith("Complemento kilos-sdc: hecho") for m in caplog.messages)
    assert correos == []
    assert not (config.STATE_DIR / CANDADO).exists()
    # The comparison runs once, of both companies, after both complements.
    assert comparacion == [(["SGX", "SDC"], len(e.servidor.peticiones))]
    # Done: the next run has nothing pending.
    assert _main(e, "--tras-despliegue", git=GitFalso(head=C), fabrica_vpn=_prohibida,
                 dormir=_no_dormir) == 0


def test_tras_despliegue_un_complemento_que_falla_no_frena_el_siguiente(entorno, correos, comparacion):
    e = entorno
    _datos_de_junio(e)
    _escribir_complementos(_DOS)
    e.servidor.programar_fallas("iniciar", status=409, datos={"message": "Ya tiene kilos."})
    assert _main(e, "--tras-despliegue", git=GitFalso(head=C), dormir=_no_dormir) == 1
    estado = autoactualizar.leer_estado()
    assert (estado["kilos-sdc"]["estado"], estado["kilos-sdc"]["commit"]) == ("fallido", C)
    assert "409" in estado["kilos-sdc"]["motivo"]
    assert estado["kilos-sgx"]["estado"] == "hecho"
    [aviso] = correos
    assert all("kilos-sdc" in mensaje for _, mensaje in aviso)
    assert len(comparacion) == 1  # a failed complement still lets the comparison run
    # Failed at this commit: not retried until the next deploy.
    assert _main(e, "--tras-despliegue", git=GitFalso(head=C), fabrica_vpn=_prohibida,
                 dormir=_no_dormir) == 0
    assert _main(e, "--tras-despliegue", git=GitFalso(head="9" * 40, padres={"9" * 40: None}),
                 dormir=_no_dormir) == 0
    assert autoactualizar.leer_estado()["kilos-sdc"]["estado"] == "hecho"


def test_tras_despliegue_sin_pendientes_solo_corre_la_comparacion(entorno, correos, comparacion):
    e = entorno
    assert _main(e, "--tras-despliegue", git=GitFalso(), fabrica_api=_prohibida, fabrica_vpn=_prohibida,
                 conectar=_prohibida, dormir=_no_dormir) == 0
    assert e.servidor.peticiones == [] and e.hana.ejecutadas == []
    assert comparacion == [(["SGX", "SDC"], 0)]
    assert correos == []


def test_tras_despliegue_dentro_de_una_franja_espera_a_que_pase(entorno, correos, comparacion):
    e = entorno
    _datos_de_junio(e)
    _escribir_complementos(_DOS)
    reloj = _Reloj(datetime(2026, 10, 26, 11, 50, tzinfo=config.BOGOTA), e.vpn)
    assert _main(e, "--tras-despliegue", git=GitFalso(head=C), ahora=reloj.ahora, dormir=reloj.dormir) == 0
    assert reloj.esperas == [56 * 60]  # until 12:46, past the 12:00 and 12:30 slots
    assert len(e.servidor.corridas) == 7


def test_tras_despliegue_espera_el_candado_como_los_programados(entorno, correos, candado_ajeno, comparacion):
    e = entorno
    _datos_de_junio(e)
    _escribir_complementos(_DOS)
    ruta = candado_ajeno()
    esperas: list[float] = []

    def dormir(segundos):
        esperas.append(segundos)
        if len(esperas) == 2:
            ruta.unlink()

    assert _main(e, "--tras-despliegue", git=GitFalso(head=C), dormir=dormir) == 0
    assert esperas == [10, 10]
    assert len(e.servidor.corridas) == 7


@pytest.mark.parametrize("extra", [["--forzar"], ["--desde", "2026-06"], ["--empresa", "SGX"]])
def test_tras_despliegue_no_lleva_otras_opciones(entorno, capsys, extra):
    with pytest.raises(SystemExit) as exc:
        _main(entorno, "--tras-despliegue", *extra, git=GitFalso())
    assert exc.value.code == 2
    assert "--tras-despliegue" in capsys.readouterr().err
