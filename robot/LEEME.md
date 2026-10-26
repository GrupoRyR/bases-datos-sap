# Robot de Bases de datos SAP

Saca los datos maestros y la cartera de SAP Business One (Segurex, SGX, y Soluciones y Derivados, SDC) por la VPN Sophos, guarda un respaldo en CSV y los envía a la app. El contrato con la app está en `docs/contrato-robot.md`.

Corre en el PC de TI con Windows y Python 3.14.

## Cómo trabaja

Cada ejecución tiene dos fases, a propósito:

1. **Con VPN:** conecta Sophos, hace todas las consultas a SAP HANA y baja la VPN.
2. **Sin VPN:** escribe los CSV en `BASES_SAP_CSV_DIR` y envía las corridas a la app.

El perfil de la VPN es de túnel completo: mientras está arriba no hay internet. Por eso la VPN solo se usa mientras se consulta SAP, y nunca se habla con la app con la VPN arriba.

La VPN también la usan otros robots (cartera y cuentas por pagar). Para no bajarles el túnel:

- El robot no corre a 15 minutos o menos de sus horas: **00:00, 05:00, 06:00, 12:00 y 12:30** (Bogotá, `BASES_SAP_FRANJAS_BLOQUEADAS`).
- Un candado (`robot\state\robot.lock`) deja correr un solo proceso del robot a la vez. Si un proceso murió sin soltarlo, a las 3 horas se da por vencido y se toma.

## Instalación

Desde la carpeta `robot\`:

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Configuración

1. Copia `.env.example` como `.env` en la carpeta `robot\`.
2. TI llena las credenciales: la VPN, HANA (un usuario por empresa), la llave de la API y, si quieres alertas, el correo.

El `.env` nunca se sube a Git. Los CSV quedan en `BASES_SAP_CSV_DIR`, fuera del repo.

## Primera ejecución con SAP real

Antes de programar las tareas, corre esto desde `robot\etl` (no envía nada a la app):

```powershell
..\.venv\Scripts\python.exe run_robot.py --catalogo
..\.venv\Scripts\python.exe run_robot.py --diagnostico
```

Con lo que dejan en `_CATALOGO` y `_DIAGNOSTICO`, revisa lo que las consultas marcan como `VALIDAR CON DATOS REALES`:

- [ ] `OITM` tiene la columna `UpdateTS` (hora del cambio, `HHMMSS`).
- [ ] El nombre exacto de la lista **PÚBLICA** en `OPLN` de cada empresa (`_DIAGNOSTICO\<empresa>\listas_precios`).
- [ ] `@HBT_MUNICIPIO` existe en Derivados y trae los municipios.
- [ ] `CRD1.County` guarda el código del municipio.
- [ ] `activo`: que `validFor = 'N'` o `frozenFor = 'Y'` marque de verdad a los socios y artículos inactivos.
- [ ] En Derivados, que las cuentas de cartera de la consulta sean las correctas.
- [ ] Los nombres de columna del archivo (`queries\archivo`) contra `_CATALOGO\<empresa>\columnas`.
- [ ] El tamaño de `ADOC`, `ADO1`, `AJDT` y `AJD1` en `_CATALOGO\<empresa>\tablas` antes de activar `BASES_SAP_ARCHIVO_HISTORIAL_DOCUMENTOS`.

Si algo no cuadra, corrige la consulta en `robot\queries` y vuelve a correr el diagnóstico.

La primera vez, los registros del archivo (auditoría y tasas de cambio) traen **todo el historial** con la VPN arriba. Para que eso no caiga en la nocturna, córrelos una vez a mano, en una hora tranquila y fuera de las franjas:

```powershell
..\.venv\Scripts\python.exe run_robot.py --archivo registros
```

Desde ahí, cada noche solo se suman los días nuevos.

## Modos

Todos se corren desde `robot\etl` con el Python del `.venv`.

| Comando | Qué hace | Usa la API |
|---|---|---|
| `run_robot.py --completa` | Nocturna: MAESTROS y CARTERA de las dos empresas, la foto diaria de cartera y los registros del archivo. Toma también las solicitudes listas | Sí |
| `run_robot.py --archivo fotos` | Domingo: fotos de las tablas del archivo y el catálogo | No |
| `run_robot.py --archivo registros` | Solo los registros del archivo (auditoría y tasas de cambio) | No |
| `run_robot.py --catalogo` | Solo el catálogo de tablas y columnas | No |
| `run_robot.py --diagnostico` | Extrae MAESTROS y CARTERA con sus conteos; no envía nada | No |
| `revisar_solicitudes.py` | Toma hasta 20 solicitudes de la app y las corre; sin solicitudes no sube la VPN | Sí |

Opciones de `run_robot.py`:

- `--empresa SGX` o `--empresa SDC`: solo esa empresa (se puede repetir). Por defecto, las dos.
- `--sin-vpn`: no maneja la VPN; úsalo si ya la conectaste a mano.
- `--forzar`: corre `--completa` o `--archivo` aunque sea dentro de una franja bloqueada. Sin él, si arrancan dentro de una franja (por ejemplo, el PC prendió tarde), esperan a que pase. Úsalo solo si sabes que los otros robots no están corriendo.

Si el robot está ocupado (otra ejecución tiene el candado), `--completa` y `--archivo` esperan hasta 20 minutos; `--catalogo` y `--diagnostico` salen enseguida y te piden intentar de nuevo en unos minutos.

Códigos de salida: `0` todo bien, `1` algún fallo, `2` configuración incompleta, `130` cancelado con Ctrl+C.

## Tareas programadas

Desde `robot\`, en PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\instalar_tarea.ps1
powershell -ExecutionPolicy Bypass -File scripts\instalar_tarea.ps1 -Desinstalar
```

Registra tres tareas con `pythonw.exe` (sin ventana), como el usuario actual y con la sesión iniciada:

| Tarea | Cuándo | Qué corre |
|---|---|---|
| `BasesSAP-Solicitudes` | Cada minuto | `revisar_solicitudes.py` |
| `BasesSAP-Nocturna` | Cada día a las 02:00 | `run_robot.py --completa` |
| `BasesSAP-Domingo` | Domingo a las 03:00 | `run_robot.py --archivo fotos` |

- Las horas quedan fuera de las franjas bloqueadas. La revisión de cada minuto se salta sola las franjas y, si otra ejecución tiene el candado, ese minuto no hace nada.
- La nocturna y la del domingo esperan hasta 20 minutos a que termine una revisión de solicitudes.
- Si el PC estaba apagado a la hora, la tarea corre en cuanto prende.

Para lanzar una ahora: `Start-ScheduledTask -TaskName BasesSAP-Nocturna`.

## Carpeta de CSV

Todo queda en `BASES_SAP_CSV_DIR` (UTF-8 con BOM, separador `;`):

| Ruta | Qué es | Se guarda |
|---|---|---|
| `MAESTROS\<empresa>\<parte>\aaaa-mm-dd_hhmm.csv` | Una por corrida | 90 días |
| `CARTERA\<empresa>\cartera\aaaa-mm-dd_hhmm.csv` | Una por corrida | 90 días |
| `CARTERA\<empresa>\historico\aaaa-mm-dd.csv` | Foto diaria de cartera, con fecha de corte de ayer y los días de mora contados a esa fecha | Siempre |
| `<categoría>\<empresa>\<tabla>\aaaa-mm-dd.csv` | Foto del archivo (domingo) | 52 semanas |
| `<categoría>\<empresa>\<tabla>\aaaa-mm.csv` | Registros del archivo, por mes | Siempre |
| `_CATALOGO\<empresa>\<consulta>\aaaa-mm-dd.csv` | Catálogo | 52 semanas |
| `_DIAGNOSTICO\<empresa>\<parte>\…` y `_DIAGNOSTICO\resumen\…` | Diagnóstico | 90 días |

Las categorías del archivo (`AUDITORIA`, `CONTABILIDAD`, `USUARIOS_Y_PERMISOS`, `CONFIGURACION`, …) solo van a esta carpeta: nunca se envían a la app.

## Registro y estado

- `robot\logs\robot.log`: el detalle de cada ejecución (rota a los 5 MB). Las contraseñas nunca se escriben. Una revisión de solicitudes sin trabajo no escribe nada.
- `robot\state\ultima_ejecucion.json`: cómo terminó la última ejecución. Nunca lleva datos de SAP.
- `robot\state\robot.lock`: el candado, mientras el robot corre.

## Correos de fallo

Si llenas `ALERTA_SMTP_*` y `ALERTA_DESTINATARIOS`, el robot manda un correo con todos los fallos de cada ejecución. La app sigue con los últimos datos buenos de lo que falló.

Para no llenar el buzón, los avisos de la revisión de cada minuto tienen límite: la configuración incompleta avisa una vez al día y un error al tomar las solicitudes o uno inesperado, una vez por hora. El diagnóstico no avisa: lo corres tú y ves el resumen.

## Pruebas

Las pruebas usan simulaciones: no se conectan a SAP, a la VPN, a la app ni al correo, y nunca registran tareas.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
```
