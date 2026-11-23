"""Tareas programadas de los otros robots: se lanzan por nombre y se espera a que terminen."""
from __future__ import annotations

import subprocess
from datetime import timedelta

import pytest

from tareas import TareasWindows

UNA_HORA = timedelta(minutes=60)


class PowerShellFalso:
    """Reemplaza subprocess.run: anota cada comando y responde según el cmdlet.

    `estados` son las respuestas de `.State`, una por consulta (la última se repite).
    """

    def __init__(
        self,
        *,
        estados: list[str] | None = None,
        resultado: str = "0",
        inicio: tuple[int, str] = (0, ""),
        error: Exception | None = None,
    ) -> None:
        self.estados = list(estados or ["Ready"])
        self.resultado = resultado
        self.inicio = inicio
        self.error = error
        self.comandos: list[list[str]] = []
        self.opciones: list[dict] = []

    def __call__(self, cmd: list[str], **opciones: object) -> subprocess.CompletedProcess:
        self.comandos.append(list(cmd))
        self.opciones.append(opciones)
        if self.error is not None:
            raise self.error
        script = cmd[-1]
        if "Start-ScheduledTask" in script:
            codigo, error = self.inicio
            return subprocess.CompletedProcess(cmd, codigo, "", error)
        if "Get-ScheduledTaskInfo" in script:
            return subprocess.CompletedProcess(cmd, 0, f"{self.resultado}\r\n", "")
        if "Get-ScheduledTask" in script:
            estado = self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]
            return subprocess.CompletedProcess(cmd, 0, f"{estado}\r\n", "")
        raise AssertionError(f"Comando inesperado: {script}")

    def scripts(self) -> list[str]:
        return [c[-1] for c in self.comandos]


def _tareas(ps: PowerShellFalso, reloj) -> TareasWindows:
    return TareasWindows(ejecutar=ps, dormir=reloj.sleep, reloj=reloj.monotonic)


def test_lanza_la_tarea_espera_a_que_termine_y_lee_su_resultado(reloj):
    ps = PowerShellFalso(estados=["Running", "Queued", "Ready"])

    assert _tareas(ps, reloj).correr("SAP HANA - todo", UNA_HORA) is None

    assert ps.scripts() == [
        "$ErrorActionPreference = 'Stop'; Start-ScheduledTask -TaskName 'SAP HANA - todo'",
        "$ErrorActionPreference = 'Stop'; (Get-ScheduledTask -TaskName 'SAP HANA - todo').State",
        "$ErrorActionPreference = 'Stop'; (Get-ScheduledTask -TaskName 'SAP HANA - todo').State",
        "$ErrorActionPreference = 'Stop'; (Get-ScheduledTask -TaskName 'SAP HANA - todo').State",
        "$ErrorActionPreference = 'Stop'; (Get-ScheduledTaskInfo -TaskName 'SAP HANA - todo').LastTaskResult",
    ]
    assert reloj.esperas == [30, 30, 30]


def test_corre_powershell_sin_shell_ni_ventana(reloj):
    ps = PowerShellFalso()

    _tareas(ps, reloj).correr("Publicador", UNA_HORA)

    assert ps.comandos[0][:4] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"]
    assert all("shell" not in opciones for opciones in ps.opciones)
    assert all(opciones["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0) for opciones in ps.opciones)
    assert all(opciones["timeout"] for opciones in ps.opciones)


def test_escapa_las_comillas_del_nombre(reloj):
    ps = PowerShellFalso()

    _tareas(ps, reloj).correr("Robot de l'IA", UNA_HORA)

    assert all("-TaskName 'Robot de l''IA'" in script for script in ps.scripts())


def test_si_no_se_puede_lanzar_da_el_motivo(reloj):
    ps = PowerShellFalso(inicio=(1, "Start-ScheduledTask : No se encuentra la tarea.\r\n   en línea:1\r\n"))

    motivo = _tareas(ps, reloj).correr("SAP HANA - todo", UNA_HORA)

    assert motivo == "No se pudo lanzar la tarea SAP HANA - todo: Start-ScheduledTask : No se encuentra la tarea."
    assert len(ps.comandos) == 1


def test_si_sigue_corriendo_pasado_el_limite_da_el_motivo(reloj):
    ps = PowerShellFalso(estados=["Running"])

    motivo = _tareas(ps, reloj).correr("SAP HANA - todo", timedelta(minutes=5))

    assert motivo == "La tarea SAP HANA - todo sigue corriendo después de 5 minutos"
    assert sum(reloj.esperas) == 5 * 60
    assert not any("LastTaskResult" in script for script in ps.scripts())


def test_un_resultado_distinto_de_cero_da_el_motivo(reloj):
    ps = PowerShellFalso(resultado="2147942401")

    motivo = _tareas(ps, reloj).correr("Publicador", UNA_HORA)

    assert motivo == "La tarea Publicador terminó con código 2147942401"


@pytest.mark.parametrize("error", [
    OSError("powershell.exe no existe"),
    subprocess.TimeoutExpired(["powershell.exe"], 60),
])
def test_si_powershell_falla_da_el_motivo_sin_reventar(reloj, error):
    ps = PowerShellFalso(error=error)

    motivo = _tareas(ps, reloj).correr("Publicador", UNA_HORA)

    assert motivo is not None and motivo.startswith("No se pudo lanzar la tarea Publicador: ")


def test_si_no_puede_leer_el_estado_da_el_motivo(reloj):
    class SinEstado(PowerShellFalso):
        def __call__(self, cmd, **opciones):
            if "(Get-ScheduledTask " in cmd[-1]:
                self.comandos.append(list(cmd))
                return subprocess.CompletedProcess(cmd, 1, "", "Acceso denegado.")
            return super().__call__(cmd, **opciones)

    motivo = _tareas(SinEstado(), reloj).correr("Publicador", UNA_HORA)

    assert motivo == "No se pudo revisar la tarea Publicador: Acceso denegado."
