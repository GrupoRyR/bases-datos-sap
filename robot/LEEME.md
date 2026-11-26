# Robot de Bases de datos SAP

Saca los datos maestros, la cartera, las ventas y los pedidos abiertos de SAP Business One (Segurex, SGX, y Soluciones y Derivados, SDC) por la VPN Sophos, guarda un respaldo en CSV y los envía a la app. El contrato con la app está en `docs/contrato-robot.md`.

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

3. Los precios salen de la lista pública de cada empresa, buscada por **número** (no por nombre): `HANA_SGX_LISTA_PRECIOS` (por defecto `1`) y `HANA_SDC_LISTA_PRECIOS` (vacía: Derivados todavía no tiene lista pública). Sin número, esa empresa manda su MAESTROS sin la parte `precios` (contrato §4.1): la nocturna no falla y no consulta precios. Una solicitud de solo precios de esa empresa falla al instante, en la nocturna o en la revisión de cada minuto, con un mensaje que dice qué variable poner; no arrastra a las solicitudes de todo MAESTROS de la misma empresa. Cuando Derivados defina su lista, pon su número en `HANA_SDC_LISTA_PRECIOS` y los precios vuelven solos.
4. La cartera sale de las cuentas contables de cada empresa: `HANA_SGX_CUENTAS_CARTERA` (por defecto `13050505,13050510,13051005`; la 13050510 es «Deudores comerciales difícil cobro» y con ella la cartera cuadra con el informe de cartera por edades de SAP) y `HANA_SDC_CUENTAS_CARTERA` (por defecto `13050501,13051005`), separadas por coma y solo dígitos. Casi nunca hay que tocarlas.
5. Las ventas (facturas, notas débito y notas crédito de clientes) salen de la consulta del gestor de cartera, copiada en `queries\ventas\ventas.sql` con una sola columna propia más: `Ganancia bruta` (`GrssProfit` de `INV1`/`RIN1`, con signo), que cuadra con la del Análisis de ventas de SAP al peso. No llevan variables: en Derivados el robot cambia el id del pedido de la app (`U_SGX_IdPedidoApp`, que solo existe en Segurex) por un vacío.
6. Los pedidos abiertos (líneas de pedidos de clientes con cantidad pendiente) salen de `queries\pedidos\pedidos.sql`. Tampoco llevan variables: en Derivados el robot cambia el id del pedido de la app (`U_SGX_IdPedidoApp`) y la familia (`U_GSP_FAMILIA`), que solo existen en Segurex, por un vacío.

7. La carpeta de los CSV es `BASES_SAP_CSV_DIR`. Si no la pones, el robot usa `C:\Users\Claude\Documents\CEREBRO\SAP\BASES_DE_DATOS`, la carpeta real del PC de TI. En cualquier otro PC ponla siempre a mano, con una ruta **fuera del repo**: los CSV traen datos de SAP y nunca se suben a Git.

El `.env` nunca se sube a Git. Los CSV quedan en `BASES_SAP_CSV_DIR`, fuera del repo.

### Cifrado con HANA (TLS)

La conexión a HANA va cifrada con TLS, como en el robot del gestor de cartera. Dos variables, las dos encendidas por defecto:

- `HANA_ENCRYPT`: cifra la conexión.
- `HANA_SSL_VALIDATE`: comprueba el certificado del servidor.

Solo `false`, `0`, `no` o `n` las apagan; vacía, ausente o con un valor que no se entiende (por ejemplo `ture`), quedan encendidas, para que un error de tipeo no apague el cifrado.

Hoy producción corre con `HANA_SSL_VALIDATE=false`: HANA no tiene un certificado disponible, así que la conexión va cifrada pero sin validar el certificado, expuesta a un intermediario activo. El robot lo deja en el log como advertencia en cada ejecución. `HANA_ENCRYPT=false` solo si el servidor no soporta TLS, y avisa a TI: el tráfico entre la VPN y HANA viajaría en claro (también queda como advertencia).

La prueba real es `run_robot.py --diagnostico`. Si el resumen no trae fallos de HANA, la conexión cifrada funciona. Al final muestra el modo configurado (`Modo TLS configurado para HANA: cifrado sí, validación de certificado no.`). Si la conexión falla por TLS, el error en `robot\logs\robot.log` explica qué cambiar. El correo solo dice que revises el log.

## Primera ejecución con SAP real

Antes de programar las tareas, corre esto desde `robot\etl` (no envía nada a la app):

```powershell
..\.venv\Scripts\python.exe run_robot.py --catalogo
..\.venv\Scripts\python.exe run_robot.py --diagnostico
```

Con lo que dejan en `_CATALOGO` y `_DIAGNOSTICO`, revisa lo que las consultas marcan como `VALIDAR CON DATOS REALES`:

- [ ] `OITM` tiene la columna `UpdateTS` (hora del cambio, `HHMMSS`).
- [ ] El número de la lista de precios **pública** en `OPLN` de cada empresa (`_DIAGNOSTICO\<empresa>\listas_precios`). Segurex: la 1 (`LISTA PUBLICO`). Derivados todavía no tiene una definida.
- [ ] `@HBT_MUNICIPIO` existe en Derivados y trae los municipios.
- [ ] `CRD1.County` guarda el código del municipio.
- [ ] `activo`: que `validFor = 'N'` o `frozenFor = 'Y'` marque de verdad a los socios y artículos inactivos.
- [ ] La cartera de Derivados (cuentas 13050501 y 13051005) da las mismas cifras que el informe de cartera de SAP. Segurex usa 13050505, 13050510 y 13051005 (suma 3.629.899.418,80 en el informe de cartera por edades de SAP). La consulta es una sola (`queries\cartera\cartera.sql`) y el robot se queda con las cuentas de cada empresa.
- [ ] Las ventas de cada empresa (`_DIAGNOSTICO\<empresa>\ventas`) contra el informe de ventas de SAP, por mes de `fecha_contabilizacion`, y lo que la consulta marca como `VALIDAR CON DATOS REALES` (el campo `U_SGX_IdPedidoApp` en Segurex, el pedido, el costo y el precio de lista). El resumen muestra el `ventana_desde` que dio HANA.
- [ ] Los pedidos de cada empresa (`_DIAGNOSTICO\<empresa>\pedidos`) contra el informe estándar de pedidos de cliente pendientes de SAP, sacado a la misma hora: líneas, pedidos y valor pendiente (`total_pendiente`), con los pedidos en otra moneda aparte. Y lo que la consulta marca como `VALIDAR CON DATOS REALES`: `U_SGX_IdPedidoApp` en `ORDR` y `U_GSP_FAMILIA` en `OITM` de Segurex, `LineTotal` y `GrssProfit` en pesos en un pedido en otra moneda, y `unitMsr` lleno en las dos empresas.
- [ ] PRODUCCION (`_DIAGNOSTICO\SGX\produccion_*`) contra las consultas originales del tablero, como dice el §12 del contrato, y lo que las consultas marcan como `VALIDAR CON DATOS REALES`: que `BELNR_ID`, `BELPOS_ID` y `POS_ID` sean enteros, que el despiece y las rutas no repitan su llave, qué deja una entrada de producto terminado anulada y cuánto tarda la consulta de costos.
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
| `run_robot.py --completa` | Nocturna: MAESTROS, CARTERA, VENTAS y PEDIDOS de las dos empresas, PRODUCCION de Segurex, la foto diaria de cartera y los registros del archivo. Toma también las solicitudes listas | Sí |
| `run_robot.py --archivo fotos` | Domingo: fotos de las tablas del archivo y el catálogo | No |
| `run_robot.py --archivo registros` | Solo los registros del archivo (auditoría y tasas de cambio) | No |
| `run_robot.py --catalogo` | Solo el catálogo de tablas y columnas | No |
| `run_robot.py --carga-produccion --desde AAAA-MM-DD` | Una vez, a mano: PRODUCCION de Segurex desde esa fecha (ver «Producción») | Sí |
| `run_robot.py --historico-ventas --desde AAAA-MM` | Una vez, a mano: VENTAS mes por mes antes de la ventana nocturna (ver «Histórico de ventas») | Sí |
| `run_robot.py --kilos-ventas --desde AAAA-MM` | A mano: llena los kilos de VENTAS mes por mes, como el histórico. Solo Derivados (ver «Kilos de ventas») | Sí |
| `run_robot.py --diagnostico` | Extrae MAESTROS, CARTERA, VENTAS, PEDIDOS y PRODUCCION (solo Segurex) con sus conteos; no envía nada | No |
| `revisar_solicitudes.py` | Toma hasta 20 solicitudes de la app (MAESTROS, CARTERA, VENTAS, PEDIDOS o PRODUCCION) y las corre; sin solicitudes no sube la VPN | Sí |

Opciones de `run_robot.py`:

- `--empresa SGX` o `--empresa SDC`: solo esa empresa (se puede repetir). Por defecto, las dos.
- `--sin-vpn`: no maneja la VPN; úsalo si ya la conectaste a mano.
- `--forzar`: corre `--completa`, `--carga-produccion`, `--historico-ventas`, `--kilos-ventas` o `--archivo` aunque sea dentro de una franja bloqueada. Sin él, si arrancan dentro de una franja (por ejemplo, el PC prendió tarde), esperan a que pase. Úsalo solo si sabes que los otros robots no están corriendo.
- `--desde` y `--hasta`: solo para `--carga-produccion` (`--desde AAAA-MM-DD`), `--historico-ventas` y `--kilos-ventas` (`--desde AAAA-MM`, `--hasta AAAA-MM`).

Si el robot está ocupado (otra ejecución tiene el candado), `--completa`, `--carga-produccion`, `--historico-ventas`, `--kilos-ventas` y `--archivo` esperan hasta 20 minutos; `--catalogo` y `--diagnostico` salen enseguida y te piden intentar de nuevo en unos minutos.

Códigos de salida: `0` todo bien, `1` algún fallo, `2` configuración incompleta, `130` cancelado con Ctrl+C.

## Ventas

Cada corrida de VENTAS (la nocturna o una solicitud) trae el mes en curso más los últimos 7 días del mes anterior, por `fecha_contabilizacion` (`DocDate`), y la app reemplaza solo esa ventana; lo anterior no se toca (contrato §10).

- El primer día de la ventana (`ventana_desde`) lo calcula HANA con la misma expresión de la consulta, en la misma conexión, antes y después de extraer. Nunca se usa el reloj del PC.
- Si cambió entre las dos lecturas (la extracción cruzó la medianoche), se repite la extracción una vez; si vuelve a cambiar, esa corrida falla.
- Si alguna fila trae una `fecha_contabilizacion` anterior a `ventana_desde`, la corrida falla antes de enviar nada.
- `kilos` es el peso de la línea, con el signo de `cantidad` (ver «Kilos de ventas»). Solo Derivados lo trae; en Segurex va vacío.
- `codigo_envio` es la última columna: el código de la dirección de envío del documento (`ShipToCode` de la factura o la nota crédito; en Derivados, el CEDI). Lo traen las dos empresas; va vacío si el documento no tiene dirección de envío.
- `ganancia_bruta` es la ganancia de cada línea según SAP (`GrssProfit`), con signo negativo en las notas crédito. No se calcula con el costo de inventario (`costo_total`), que se desvía cerca de 0,5 % de lo que muestra SAP. Para revisarla, suma `ganancia_bruta` del 01 al 16/11/2026 en el CSV de `VENTAS\<empresa>`: SGX 294.070.622,59 y SDC 604.768.247,13.
- Si la extracción falla antes de que HANA dé la ventana (por ejemplo, no conectó la VPN), la corrida no se puede abrir para marcarla fallida: el fallo va al correo y sus solicitudes vencen solas en la app.

## Histórico de ventas

La nocturna solo trae la ventana (el mes en curso más los últimos 7 días del anterior). Los meses de antes se cargan **una vez, a mano**, con el histórico (contrato §10.4):

```powershell
.venv\Scripts\python.exe etl\run_robot.py --historico-ventas --desde 2025-01
```

- Cada mes es un tramo y cada tramo, una corrida `historico` de VENTAS con su rango: del día 1 al último día del mes. El mes en que empieza la ventana nocturna llega solo hasta el día antes (el 24/11/2026 la ventana empieza el 25/10, así que octubre va del 01/10 al 24/10 y noviembre no se toca). Lo demás lo trae la nocturna.
- `--hasta AAAA-MM`: último mes. Por defecto, el mes en que empieza la ventana. `--empresa SGX` o `--empresa SDC`: solo esa empresa; por defecto, las dos.
- La consulta es la misma de la nocturna (`queries\ventas\ventas.sql`, que no cambia): el robot solo cambia el filtro de `DocDate` por el rango del tramo. La ventana la da HANA cuando la VPN ya está arriba.
- Primero extrae todos los tramos con la VPN arriba (consulta y `COUNT(*)` de cada tramo, en la misma conexión), baja la VPN y luego envía tramo por tramo: empresa por empresa, del mes más viejo al más nuevo.
- Cada tramo con ventas queda en `VENTAS\<empresa>\historico\<desde>_<hasta>.csv` (por ejemplo `2025-01-01_2025-01-31.csv`). La retención de 90 días no los borra.

Cuándo correrlo: con la API del histórico ya desplegada, fuera de las franjas y con tiempo, por ejemplo un día entre semana en la tarde. Respeta las franjas de los otros robots y espera el candado, como la nocturna. Además, antes de subir la VPN estima cuánto la va a tener arriba: unos 5 minutos fijos más 2 por cada mes de cada empresa (`MINUTOS_FIJOS` y `MINUTOS_POR_TRAMO` en `etl\historico.py`). Desde enero de 2025 son unos 22 meses por empresa, cerca de hora y media. Si eso no alcanza a terminar antes de la siguiente franja, espera a que la franja pase y vuelve a mirar; si ningún hueco del día alcanza, falla sin subir la VPN y te pide correrlo por partes con `--hasta`. Es una estimación: si en la práctica tarda más, sube esas dos cifras. Como puede pasar de las 3 horas de vigencia del candado, lo renueva en cada tramo.

Todos los tramos quedan en memoria hasta que baja la VPN. Si el PC se queda corto, córrelo por partes, por ejemplo un año a la vez con `--hasta`.

Al final, el log trae un resumen por empresa:

- `cargado del … al …`: la primera y la última `fecha_contabilizacion` de los tramos que la app cerró bien.
- `vacíos`: meses sin ventas en SAP. No se envían: la app nunca recibe una corrida vacía.
- `ya cargados`: meses en los que la app ya tenía ventas de esa empresa. La app responde 409 y no abre nada, así que repetir un mes ya cargado no hace daño: puedes volver a correr todo el comando sin miedo.
- `fallidos`: meses que no se cargaron, con el motivo. Un tramo que falla no frena a los demás; la corrida que alcanzó a abrirse queda fallida y el mes sigue vacío en la app. Vuelve a correr el comando: los meses cargados responden «ya cargado» y solo se cargan los que faltan.

Sale con `1` si algún tramo falló (y avisa por correo, como la nocturna) y con `0` si no. `robot\state\ultima_ejecucion.json` lista cada tramo con su estado, sin datos de SAP.

## Kilos de ventas

Llena la columna `kilos` de VENTAS en los meses que la app ya tiene. La corre **a mano** el coordinador o el usuario, no una tarea programada:

```powershell
.venv\Scripts\python.exe etl\run_robot.py --kilos-ventas --desde 2025-01
```

Los kilos son la columna «Tot KG» de la consulta guardada «AnálisisVentas-1» de Derivados: en las facturas, `INV1.Quantity * OITM.NumInSale`, y en las notas crédito lo mismo por `-1`. En `queries\ventas\ventas.sql` es la columna `"Kilos"`, antes del código de envío, marcada con `-- @kilos`: `X."Quantity" * T4."NumInSale" * X."Signo"`, con el mismo signo de `cantidad` y `OITM` unida por el artículo sin perder líneas. Una línea sin artículo o sin `NumInSale` sale con `kilos` vacío. La nocturna, las solicitudes y el histórico también la envían.

- **Solo Derivados.** En Segurex no está confirmado que `NumInSale` sean kilos, así que el robot cambia la expresión marcada por un `NULL` y Segurex envía `kilos` vacío.
- **Puede no cuadrar con el informe de SAP.** «AnálisisVentas-1» solo toma las facturas de las series 4, 118 y 120; `ventas.sql` no filtra por serie (trae todas las facturas y notas crédito). Los totales de kilos de un mes pueden ser mayores que los del informe.
- Si alguien quita la columna de la consulta, el modo no corre: el robot sale con `2` (configuración) antes de esperar el candado o subir la VPN, guarda el motivo en el estado y no envía nada. Nunca manda kilos inventados.

Cómo corre el modo:

- Va como el histórico: un tramo por mes, de `--desde` a `--hasta`, hasta el día antes de la ventana nocturna. `--desde` va desde `2025-01` (contrato §10.5); uno anterior no corre. `--hasta AAAA-MM` funciona igual. La ventana la da HANA cuando la VPN ya está arriba.
- Solo corre en Derivados (`SDC`), por lo mismo: sin `--empresa` corre solo `SDC`, y `--empresa SGX` no corre: el robot sale con un error de los argumentos. La lista de empresas con kilos está en `EMPRESAS_CON_KILOS` (`etl\consultas.py`) y manda en la consulta y en el modo.
- Con la VPN arriba trae de cada tramo solo la llave de la venta (`tipo_objeto`, `doc_entry`, `linea`), `fecha_contabilizacion` y `kilos`, con el `COUNT(*)` en la misma conexión. Luego baja la VPN y envía cada tramo como una corrida `kilos`, del mes más viejo al más nuevo.
- No escribe CSV: el respaldo de esas ventas ya es el del histórico.
- Un tramo sin ventas en SAP no se envía. Una línea sin peso en SAP va con `kilos` vacío y la app lo guarda vacío. Un tramo que falla no frena a los demás; si la corrida alcanzó a abrirse, queda fallida.
- La app solo cambia `kilos` de las líneas que ya tiene. Si las del tramo no cuadran con las suyas, el cierre falla y el motivo dice cuántas `sobran` (llegaron y la app no las tiene) y cuántas `faltan` (la app las tiene y no llegaron). Suele querer decir que ese mes cambió en SAP después del histórico.
- Repetir un mes no hace daño: vuelve a escribir los mismos kilos. Si algo falló, vuelve a correr el comando.

Cuándo correrlo: con la API de la corrida `kilos` desplegada, fuera de las franjas. Respeta las franjas de los otros robots y espera el candado, como el histórico. Antes de subir la VPN estima cuánto la va a tener arriba: 2 minutos fijos más 10 segundos por cada mes de cada empresa (`SEGUNDOS_FIJOS` y `SEGUNDOS_POR_TRAMO` en `etl\kilos.py`). Sale del histórico real del 24/11/2026, que tuvo la VPN arriba 78 segundos para 22 meses de las dos empresas, con mucha holgura: desde enero de 2025, solo Derivados, son unos 5 minutos y medio. Si no cabe antes de la siguiente franja, espera a que pase.

Al final, el log trae un resumen por empresa: cuántos tramos quedaron `llenos`, `vacíos` (sin ventas en SAP) y `fallidos`, y cuáles, con el motivo de los fallidos y sin valores de SAP. Sale con `1` si algún tramo falló (y avisa por correo) y con `0` si no. `robot\state\ultima_ejecucion.json` lista cada tramo con su estado.

## Pedidos

Cada corrida de PEDIDOS (la nocturna o una solicitud) trae todas las líneas abiertas de los pedidos de clientes de la empresa, y la app reemplaza todos sus pedidos por los recibidos: lo que ya se facturó o se cerró desaparece (contrato §11).

- Entra una línea si el pedido está abierto y no anulado, y la línea está abierta con cantidad pendiente (`OpenCreQty > 0`). No se filtra por bodega, lista de precios ni dirección.
- Las cantidades van en unidades de venta. `total_pendiente` y `ganancia_bruta_pendiente` son la parte abierta de la línea, en pesos; el margen es `SUM(ganancia_bruta_pendiente) / SUM(total_pendiente)`.
- `linea_articulo` es el grupo de artículos (`OITB`); `familia` es `U_GSP_FAMILIA`, solo en Segurex. En VENTAS, en cambio, `familia` es el grupo de artículos.
- Nunca se envía vacía: si una empresa llega con 0 pedidos abiertos, la corrida falla y los pedidos anteriores se quedan.
- La nocturna manda `conteo_sap.pedidos`, el `COUNT(*)` de la misma consulta en la misma conexión.

## Producción

PRODUCCION (contrato §12) trae los datos del tablero «Producción mes a mes» de Segurex, en seis partes. Es **solo de Segurex**: las tablas BEAS de las órdenes de producción no existen en Derivados, así que la nocturna, las solicitudes y el diagnóstico no la piden para SDC.

- Las consultas están en `queries\produccion`, copiadas de las del tablero con los cambios del §12: la ventana de VENTAS en vez del rango fijo, una fila por línea de entrada en el producto terminado, sin el nombre de quien reportó, los nombres del contrato y los montos con 2 decimales.
- Movimiento (`produccion_terminado`, `produccion_carga_planta`, `produccion_costos`): traen las filas con `fecha` desde el primer día de la ventana, el mismo de VENTAS. El robot pide `ventana_desde` a HANA antes y después de extraer y, si alguna fila trae una `fecha` anterior, la corrida falla antes de enviar nada. La app reemplaza solo la ventana.
- Maestros (`produccion_despiece`, `produccion_rutas`, `produccion_costeo_teorico`): todas las filas cada vez; la app las reemplaza todas.
- `produccion_costos` envía también las filas de `Material intermedio` (lo que la planta fabricó y vuelve a entrar como insumo). El panel las excluye al sumar el costo.
- Nunca se envía una parte vacía: si una llega con 0 filas, falla la corrida de PRODUCCION y no cambia nada.

### Carga inicial

Una vez, a mano y con la API de PRODUCCION ya desplegada, para que el panel tenga desde el primer día los meses que ya usa el tablero:

```powershell
.venv\Scripts\python.exe etl\run_robot.py --carga-produccion --desde 2026-08-01
```

Corre la completa de PRODUCCION de Segurex con `ventana_desde` = la fecha de `--desde` en vez de la que da HANA: las tres consultas de movimiento traen desde ese día. `--desde` va del 1 de enero de 2026 a hoy. Respeta las franjas de los otros robots (salvo con `--forzar`) y espera el candado, como la nocturna. Son unas 50 mil filas; la consulta de costos es la que más tarda.

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
| `VENTAS\<empresa>\aaaa-mm-dd_hhmm.csv` | Una por corrida | 90 días |
| `VENTAS\<empresa>\historico\aaaa-mm-dd_aaaa-mm-dd.csv` | Un tramo del histórico de ventas (ver «Histórico de ventas») | Siempre |
| `PEDIDOS\<empresa>\aaaa-mm-dd_hhmm.csv` | Una por corrida | 90 días |
| `PRODUCCION\SGX\<parte>\aaaa-mm-dd_hhmm.csv` | Una por parte y corrida | 90 días |
| `CARTERA\<empresa>\historico\aaaa-mm-dd.csv` | Foto diaria de cartera, con fecha de corte de ayer y los días de mora contados a esa fecha | Siempre |
| `<categoría>\<empresa>\<tabla>\aaaa-mm-dd.csv` | Foto del archivo (domingo) | 52 semanas |
| `<categoría>\<empresa>\<tabla>\aaaa-mm.csv` | Registros del archivo, por mes | Siempre |
| `_CATALOGO\<empresa>\<consulta>\aaaa-mm-dd.csv` | Catálogo | 52 semanas |
| `_DIAGNOSTICO\<empresa>\<parte>\…` y `_DIAGNOSTICO\resumen\…` | Diagnóstico | 90 días |
| `.<archivo>.<letras>.tmp`, en cualquier carpeta | Temporal de una escritura que se cortó (el robot se cerró a la mitad); trae datos de SAP | 1 día: lo borra la siguiente nocturna o revisión de solicitudes |

Cada CSV se escribe primero en un temporal que luego se renombra, así que nunca queda un archivo a medias. Un temporal con menos de un día no se toca, porque otra ejecución podría estar escribiéndolo. El log solo dice cuántos temporales se borraron.

Las categorías del archivo (`AUDITORIA`, `CONTABILIDAD`, `USUARIOS_Y_PERMISOS`, `CONFIGURACION`, …) solo van a esta carpeta: nunca se envían a la app.

Las tablas `@HBT_*` de `CONFIGURACION` se leen columna por columna y el robot salta las que parecen guardar credenciales, es decir, las que tienen `PASS`, `PWD`, `CLAVE`, `CONTRASE`, `TOKEN` o `SECRET` en el nombre, y las que tienen `KEY`, `APIKEY` o `PIN` como una parte entera del nombre (`U_PIN`, `U_API_KEY`, no `U_SHIPPING` ni `U_KEYWORD`). Cada columna saltada queda en el log.

## Registro y estado

- `robot\logs\robot.log`: el detalle de cada ejecución (rota a los 5 MB). Las contraseñas y el secreto de la API nunca se escriben: se marcan para ocultarlas apenas carga el `.env`. De un rechazo de la API solo queda el estado y los campos (`rows.12.codigo`), no su texto, que podría repetir un valor de SAP. Una revisión de solicitudes sin trabajo no escribe nada.
- Un cliente o proveedor que llega de SAP sin nombre no frena la corrida: se envía con su código como nombre y queda un aviso (`WARNING ... llegó sin nombre`) en el log, para que TI le ponga el nombre en SAP.
- `robot\state\ultima_ejecucion.json`: cómo terminó la última ejecución. Nunca lleva datos de SAP.
- `robot\state\robot.lock`: el candado, mientras el robot corre.

## Correos de fallo

Si llenas `ALERTA_SMTP_*` y `ALERTA_DESTINATARIOS`, el robot manda un correo con todos los fallos de cada ejecución. La app sigue con los últimos datos buenos de lo que falló.

La conexión al servidor de correo va cifrada (puerto 465, o 587 con STARTTLS) y comprueba su certificado: si el certificado no es válido para `ALERTA_SMTP_HOST`, el correo no sale y el error queda en el log.

Para no llenar el buzón, los avisos de la revisión de cada minuto tienen límite: la configuración incompleta avisa una vez al día y un error al tomar las solicitudes o uno inesperado, una vez por hora. El diagnóstico no avisa: lo corres tú y ves el resumen.

## Pruebas

Las pruebas usan simulaciones: no se conectan a SAP, a la VPN, a la app ni al correo, y nunca registran tareas.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
```
