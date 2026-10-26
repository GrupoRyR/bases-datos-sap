<#
.SYNOPSIS
    Registra el robot de Bases de datos SAP en el Programador de tareas de Windows.

.DESCRIPTION
    Crea tres tareas que corren con pythonw.exe (sin ventana) desde robot\.venv
    y con carpeta de trabajo robot\etl:

      BasesSAP-Solicitudes  cada minuto      revisar_solicitudes.py
      BasesSAP-Nocturna     cada dia 02:00   run_robot.py --completa
      BasesSAP-Domingo      domingo 03:00    run_robot.py --archivo fotos

    Las horas evitan las franjas en que los otros robots usan la misma VPN
    (00:00, 05:00, 06:00, 12:00 y 12:30, +/- 15 minutos): si dos robots se
    solapan, uno le baja el tunel al otro. La revision de cada minuto se salta
    sola esas franjas, y un candado (robot\state\robot.lock) evita que dos
    procesos del robot corran a la vez: la nocturna y la del domingo esperan
    hasta 20 minutos a que termine una revision de solicitudes.

    Si el equipo estaba apagado a la hora, la tarea corre en cuanto arranca
    (StartWhenAvailable).

.PARAMETER Desinstalar
    Elimina las tres tareas en lugar de crearlas.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\instalar_tarea.ps1
    powershell -ExecutionPolicy Bypass -File scripts\instalar_tarea.ps1 -Desinstalar
#>
[CmdletBinding()]
param(
    [switch]$Desinstalar
)

$ErrorActionPreference = "Stop"

$Raiz    = Split-Path -Parent $PSScriptRoot
$EtlDir  = Join-Path $Raiz "etl"
$PythonW = Join-Path $Raiz ".venv\Scripts\pythonw.exe"

function Hora([string]$Texto) {
    return [datetime]::ParseExact($Texto, "HH:mm", $null)
}

$Tareas = @(
    @{
        Nombre      = "BasesSAP-Solicitudes"
        Script      = "revisar_solicitudes.py"
        Argumentos  = ""
        Disparador  = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
        Limite      = New-TimeSpan -Minutes 45
        Reintentos  = $false
        Horario     = "cada minuto (salta las franjas bloqueadas)"
        Descripcion = "Revisa cada minuto las solicitudes de la app de Bases de datos SAP y las corre."
    },
    @{
        Nombre      = "BasesSAP-Nocturna"
        Script      = "run_robot.py"
        Argumentos  = "--completa"
        Disparador  = New-ScheduledTaskTrigger -Daily -At (Hora "02:00")
        Limite      = New-TimeSpan -Hours 3
        Reintentos  = $true
        Horario     = "cada dia a las 02:00"
        Descripcion = "Corrida completa nocturna de Bases de datos SAP: MAESTROS y CARTERA de SGX y SDC."
    },
    @{
        Nombre      = "BasesSAP-Domingo"
        Script      = "run_robot.py"
        Argumentos  = "--archivo fotos"
        Disparador  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At (Hora "03:00")
        Limite      = New-TimeSpan -Hours 3
        Reintentos  = $true
        Horario     = "cada domingo a las 03:00"
        Descripcion = "Fotos semanales del archivo y catalogo de Bases de datos SAP (solo carpeta)."
    }
)

if ($Desinstalar) {
    foreach ($t in $Tareas) {
        if (Get-ScheduledTask -TaskName $t.Nombre -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $t.Nombre -Confirm:$false
            Write-Host "Tarea '$($t.Nombre)' eliminada." -ForegroundColor Yellow
        } else {
            Write-Host "La tarea '$($t.Nombre)' no existia." -ForegroundColor Yellow
        }
    }
    return
}

# --- Comprobaciones previas -------------------------------------------------
if (-not (Test-Path $PythonW)) {
    throw "No se encontro el entorno virtual en $PythonW.`nCrealo desde la carpeta robot con:`n  py -3.14 -m venv .venv`n  .venv\Scripts\python.exe -m pip install -r requirements.txt"
}
foreach ($t in $Tareas) {
    $Ruta = Join-Path $EtlDir $t.Script
    if (-not (Test-Path $Ruta)) { throw "No se encontro $Ruta" }
}

# Solo se comprueba que exista; el script nunca lo lee.
$EnvFile = Join-Path $Raiz ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Warning "No existe $EnvFile. Las tareas quedaran registradas pero fallaran hasta que TI lo llene (copia .env.example)."
}

# Se ejecuta como el usuario actual, solo con sesion iniciada: asi no hay que
# guardar la contrasena de Windows. Para que corra con la sesion cerrada, usa
# el Programador de tareas -> "Ejecutar tanto si el usuario inicio sesion como
# si no" (pedira la contrasena del usuario).
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

foreach ($t in $Tareas) {
    $Script    = Join-Path $EtlDir $t.Script
    $Argumento = ("`"$Script`" " + $t.Argumentos).Trim()
    $Accion    = New-ScheduledTaskAction -Execute $PythonW -Argument $Argumento -WorkingDirectory $EtlDir

    $Opciones = @{
        StartWhenAvailable         = $true
        DontStopOnIdleEnd          = $true
        AllowStartIfOnBatteries    = $true
        DontStopIfGoingOnBatteries = $true
        MultipleInstances          = "IgnoreNew"
        ExecutionTimeLimit         = $t.Limite
    }
    if ($t.Reintentos) {
        # La de cada minuto no reintenta: el minuto siguiente ya es otro intento.
        $Opciones.WakeToRun       = $true
        $Opciones.RestartCount    = 2
        $Opciones.RestartInterval = New-TimeSpan -Minutes 10
    }
    $Ajustes = New-ScheduledTaskSettingsSet @Opciones

    if (Get-ScheduledTask -TaskName $t.Nombre -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $t.Nombre -Confirm:$false
        Write-Host "Tarea anterior '$($t.Nombre)' eliminada para reemplazarla." -ForegroundColor DarkGray
    }

    Register-ScheduledTask `
        -TaskName    $t.Nombre `
        -Action      $Accion `
        -Trigger     $t.Disparador `
        -Settings    $Ajustes `
        -Principal   $Principal `
        -Description $t.Descripcion | Out-Null

    Write-Host "Tarea '$($t.Nombre)' registrada: $($t.Script) $($t.Argumentos), $($t.Horario)." -ForegroundColor Green
}

Write-Host ""
Write-Host "Ejecuta: $PythonW"
Write-Host "Carpeta: $EtlDir"
Write-Host ""
Write-Host "Para lanzar una ahora mismo y ver el resultado:" -ForegroundColor Cyan
Write-Host "  Start-ScheduledTask -TaskName BasesSAP-Nocturna"
Write-Host "  Get-Content logs\robot.log -Tail 30"
