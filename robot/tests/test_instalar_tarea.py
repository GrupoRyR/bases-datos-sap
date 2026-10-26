"""scripts/instalar_tarea.ps1: nunca se ejecuta en las pruebas; solo se revisa y se analiza."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "instalar_tarea.ps1"
POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


def test_registra_las_tres_tareas():
    texto = SCRIPT.read_text(encoding="utf-8")
    for esperado in (
        "BasesSAP-Solicitudes", "BasesSAP-Nocturna", "BasesSAP-Domingo",
        "revisar_solicitudes.py", "--completa", "--archivo fotos", "pythonw.exe",
        "-RepetitionInterval (New-TimeSpan -Minutes 1)", "-DaysOfWeek Sunday",
        '"IgnoreNew"', "-Desinstalar", "StartWhenAvailable",
    ):
        assert esperado in texto, esperado
    # Solo comprueba que el .env exista; nunca lo lee.
    usos_env = [linea for linea in texto.splitlines() if "EnvFile" in linea]
    assert usos_env and all(
        any(permitido in linea for permitido in ("Join-Path", "Test-Path", "Write-Warning"))
        for linea in usos_env
    ), usos_env
    # PowerShell 5.1 lee un .ps1 sin BOM como ANSI: el script va solo en ASCII.
    assert texto.isascii()


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell no está instalado")
def test_powershell_lo_analiza_sin_errores():
    ruta = str(SCRIPT).replace("'", "''")
    comando = (
        "$errores = $null; "
        f"$null = [System.Management.Automation.Language.Parser]::ParseFile('{ruta}', [ref]$null, [ref]$errores); "
        "if ($errores.Count) { $errores | ForEach-Object { $_.ToString() }; exit 1 } else { exit 0 }"
    )
    resultado = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", comando],
        capture_output=True, text=True, timeout=120,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
