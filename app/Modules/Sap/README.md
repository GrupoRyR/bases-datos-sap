# Módulo Sap

Los datos de SAP y todo lo que los mueve: los conjuntos MAESTROS, CARTERA, VENTAS, PEDIDOS y PRODUCCION, la recepción de lo que envía el robot (corridas y lotes), las solicitudes de actualización y la API que llaman las apps.

| Qué | Valor |
|---|---|
| Dueña | Sesión «Datos y API» |
| Rutas web | `/sap/*`, nombres `sap.*` |
| Rutas API | `/api/robot/v1/*` y `/api/v1/*`, exactas como dice el contrato (`apiPrefix()` vacío), nombres `sap.api.*` |
| Migraciones | `2026_11_02_*` |
| Conexiones | `maestros`, `cartera` y `ventas` para las tablas de cada conjunto (PEDIDOS y PRODUCCION también van en `ventas`); `app` para el resto (solicitudes, corridas, lotes, comparaciones) |
| Puede usar | Contratos de Core |

Lo que Panel necesite leer de aquí lo publica Sap en `App\Modules\Sap\Contracts`. El contrato con el robot está en `docs/contrato-robot.md` y no cambia sin avisarle al usuario.

## Contratos para el panel

Cada uno se implementa en `Application\Panel` (o `Application\Apps`) y se registra en `SapServiceProvider`. Recorren `Company::cases()`, `Dataset::cases()` y `Part::forDataset()`, así que un conjunto nuevo aparece sin cambiarlos. Las horas vuelven como `CarbonImmutable` en hora de Bogotá.

- `DatasetStatuses::all()`: por empresa y conjunto, la última vez que se aplicó, las filas en MySQL por parte (activas si la tabla tiene `activo`) y la última corrida.
- `Stability::current()`: el contador de días estables del plan (§6) y los últimos 14 días con lo que falló en cada uno; el criterio 4 (correcciones a mano) no se puede medir.
- `RequestHistory::page()`: las solicitudes de la más nueva a la más vieja, con quién pidió cada una (app o panel), filtrables por empresa y conjunto.
- `MasterLookup::search()`: busca clientes, proveedores o artículos en su vista por código, nombre o NIT; devuelve solo campos de identificación (Ley 1581) y como máximo 25 filas.
- `ClientAppKeys`: además de `issue` y `revoke`, `all()` lista las apps sin su hash y `rotate()` da una llave nueva (la anterior recibe 401 de inmediato y una app revocada vuelve a funcionar).

Las reglas completas están en `docs/arquitectura.md`.

## Partes y columnas

`Contracts\Enums\Part` nombra cada parte del contrato (§1, §5, §6, §10 y §11) con su conjunto, su llave y sus columnas (`Domain\Columns\PartColumns`). El valor de cada caso es el nombre del contrato, que es también la tabla (`clientes`) y, con `v_`, la vista (`v_clientes`). Cambiar una columna es cambiar el contrato: primero lo aprueba el usuario.

## Tablas y vistas

| Conjunto | Conexión | Tablas | Vistas |
|---|---|---|---|
| MAESTROS | `maestros` | Una por parte: `clientes`, `proveedores`, `direcciones`, `contactos`, `articulos`, `grupos_articulos`, `marcas`, `precios`, `vendedores`, `grupos_clientes`, `condiciones_pago`, `municipios` | `v_<tabla>` |
| CARTERA | `cartera` | `cartera` (actual) y `cartera_fotos` (una foto por empresa y `fecha_corte`) | `v_cartera`, `v_cartera_fotos` |
| VENTAS | `ventas` | `ventas` (una fila por línea de factura o nota crédito) | `v_ventas` |
| PEDIDOS | `ventas` | `pedidos` (una fila por línea abierta de pedido de clientes) | `v_pedidos` |
| PRODUCCION | `ventas` | Una por parte, solo de `SGX`: `produccion_terminado`, `produccion_carga_planta` y `produccion_costos` (movimiento); `produccion_despiece`, `produccion_rutas` y `produccion_costeo_teorico` (maestros) | `v_<tabla>` |

- Cada fila de MAESTROS lleva `empresa`, sus columnas del contrato, `activo`, `actualizado_en_sap` (solo la traen clientes, proveedores y artículos), `sincronizado_en` y `corrida_id`. Es única por empresa y llave. Nunca se borra: lo que deja de llegar queda inactivo.
- CARTERA no tiene llave natural: cada cierre bueno reemplaza toda la cartera de la empresa en una transacción.
- VENTAS es única por empresa, `tipo_objeto`, `doc_entry` y `linea`, con un índice por empresa y `fecha_contabilizacion` para la ventana. Cada cierre bueno reemplaza solo la ventana de la empresa; lo anterior no se toca nunca.
- PEDIDOS es única por empresa, `doc_entry` y `linea`. Cada cierre bueno reemplaza todos los pedidos de la empresa: es una foto de lo abierto en SAP.
- PRODUCCION es solo de `SGX` (contrato §12). `produccion_terminado` es única por empresa, `doc_entry` y `linea`; `produccion_costeo_teorico`, por empresa y `codigo_articulo`; las otras cuatro no tienen llave. Las de movimiento tienen un índice por empresa y `fecha`: cada cierre bueno reemplaza solo su ventana. Los maestros se reemplazan completos.
- Las vistas listan sus columnas una por una y nunca muestran `id` ni `corrida_id`. Para cambiar una vista se agregan columnas al final en una migración nueva; nunca se renombra ni se quita una, porque las apps leen de ellas.
- Los textos van como `varchar` con el largo de SAP; las horas, en hora de Bogotá; los montos, `decimal(19,2)`; las cantidades y tasas de VENTAS (`cantidad`, `trm`) y de PEDIDOS (`cantidad_pedida`, `cantidad_pendiente`, `descuento_documento`, `trm`), y las cantidades y horas de PRODUCCION, `decimal(19,6)`.

## Peticiones del robot

Toda ruta del robot va en el grupo de middleware `sap.robot` (`SapServiceProvider`), en este orden:

1. `throttle:sap-robot`: 120 peticiones por minuto por IP; después, 429 con `Retry-After`.
2. `LimitRobotPayload`: 413 si el cuerpo pasa de 10 MB tal como viaja, antes de mirar la firma.
3. `VerifyRobotSignature`: HMAC-SHA256 del contrato (§3) con las llaves de `ROBOT_HMAC_KEYS`. Toda falla responde 401 `Firma inválida.` y queda en el log con el motivo, la llave y la IP. El nonce se guarda en `robot_nonces` solo después de validar la firma; el programador borra los de más de 10 minutos.
4. `DecodeRobotBody`: descomprime gzip por partes (413 si pasa de 40 MB, 400 si está dañado), exige un objeto JSON (400) y deja el texto en el atributo `robot_body` para comparar lotes por su SHA-256.

Los límites están en `config/sap.php` (`sap.robot.*`).

## Corridas

Una corrida lleva un conjunto de una empresa (`robot_runs`, contrato §4). Estados: `abierta` → `cerrada`, `fallida` o `vencida` (`Domain\Runs\RunState`).

- `POST /api/robot/v1/corridas` (`Application\Runs\StartRun`): valida conjunto, empresa, tipo, partes y modos (una corrida `completa` trae todas las partes en `todo`, salvo que la `completa` de MAESTROS de `SDC` puede omitir `precios` porque Derivados no tiene lista pública; solo clientes, proveedores y artículos, con sus direcciones y contactos, van en `cambios`), `fecha_corte` solo en CARTERA, `ventana_desde` solo en VENTAS y PRODUCCION, PRODUCCION solo de `SGX` (`Dataset::companies()`) y `extraida_en` con zona. Responde 201 con `abierta_hasta`.
- `ventana_desde` (contrato §10.1 y §12.3) es obligatoria en VENTAS, una fecha entre hoy menos 40 días y mañana, y en PRODUCCION, entre `2026-01-01` y mañana, con hoy en Bogotá. La corrida la guarda (`robot_runs.ventana_desde`) para sus lotes, su cierre y su conteo.
- Una corrida `historico` (contrato §10.4) solo es de VENTAS: trae `ventana_desde` el día 1 de un mes, desde `2025-01-01`, y `ventana_hasta` (`robot_runs.ventana_hasta`) en ese mes y antes del inicio de la ventana nocturna de hoy. Si la empresa ya tiene ventas en el rango, 409. Sus lotes rechazan filas fuera del rango; su cierre exige `conteo_sap` y falla sin aplicar nada si no es igual a las filas recibidas; si cuadra, inserta sin borrar y no escribe `daily_counts`. Las corridas `historico` no cuentan como última actualización ni última corrida del conjunto (`DatabaseDatasetStatuses`).
- Una corrida `complemento` (contrato §10.5) solo es de VENTAS y lleva el mismo rango que la `historico`, pero abre aunque el rango ya tenga ventas (no hay 409). Sus lotes traen solo `tipo_objeto`, `doc_entry`, `linea`, `fecha_contabilizacion`, `kilos` y `codigo_envio`, estos dos obligatorios en el encabezado aunque su valor puede ser `null` (`PartColumns::salesComplement()`, vía `Run::columnsOf()`). Su cierre exige `conteo_sap` igual a las filas recibidas y que las llaves recibidas sean exactamente las de la empresa en el rango; si no, falla sin aplicar nada (422 con `sobran` y `faltan`). Si cuadra, `ApplyComplemento` cambia solo `kilos` y `codigo_envio` por llave, con un `UPDATE` por bloque de 200 líneas, sin tocar `sincronizado_en` ni `corrida_id`. Tampoco escribe `daily_counts` ni cuenta como última actualización.
- Solo una corrida abierta por conjunto y empresa: lo asegura el índice único de `abierta_lock`. La segunda recibe 409 con el `run_id` de la abierta.
- `POST /api/robot/v1/corridas/{id}/fallar` (`FailRun`): la marca `fallida` con el error del robot y descarta sus lotes.
- Una corrida que pasa 30 minutos sin lotes queda `vencida`: al tocarla, al iniciar otra del mismo conjunto y empresa, y con `php artisan sap:vencer`, que el programador corre cada minuto.
- Los errores del robot se responden con `Http\Exceptions\RobotRequestRejected`: 422 con `errors` (máximo 50), 409 con `estado` o `run_id`, 404 si la corrida no existe. El repositorio no trae mensajes de validación en español, así que el módulo escribe los suyos.

## Lotes

`POST /api/robot/v1/corridas/{id}/lotes` (`Application\Runs\ReceiveBatch`, contrato §4.2) guarda el lote en `robot_batches` hasta que la corrida cierra; nada llega a las tablas de los conjuntos, así que un lote rechazado deja todo como estaba.

- `batch` es entero desde 1, consecutivo en la corrida; el mismo `batch` con el mismo cuerpo (SHA-256 del JSON ya descomprimido) responde 200 con `duplicate`, y con otro cuerpo, 409.
- `Domain\Batches\BatchRows` exige exactamente las columnas de la parte, en cualquier orden y sin repetir, y un valor por columna. Revisa tipos (enteros JSON, montos como texto con punto y hasta 2 decimales, cantidades y tasas de VENTAS con hasta 6, booleanos, fechas, horas con zona), obligatorias no nulas ni vacías, texto de hasta 4.000 caracteres (el opcional se recorta al largo de su columna; la llave que no cabe se rechaza) y devuelve las filas en el orden de columnas de la parte, con las horas en Bogotá.
- Una llave no se repite en la corrida, ni en el lote ni entre lotes (`robot_batch_keys`); CARTERA no tiene llave.
- En una parte con ventana (`Part::windowColumn()`: `fecha_contabilizacion` en VENTAS, `fecha` en el movimiento de PRODUCCION), una fila anterior a la `ventana_desde` de la corrida rechaza el lote (422, `rows.N.<columna>`): el cierre nunca alcanza fechas fuera de la ventana.
- Un 422 cuenta en `lotes_rechazados` y la corrida sigue abierta. Cada lote aceptado extiende `abierta_hasta` 30 minutos.
- El lote se guarda con la fila de la corrida bloqueada, así que no se cruza con su cierre ni con su vencimiento.

## Cierre

`POST /api/robot/v1/corridas/{id}/cerrar` (`Application\Runs\CloseRun`, contrato §4.3):

1. Valida `batches` y `filas` (un número por cada parte de la corrida); `conteo_sap` es obligatorio en una corrida `completa`, `historico` o `complemento` y prohibido en las de solicitud.
2. Si falta algún lote del 1 al `batches`, responde 409 con `faltan`; si las filas no cuadran con lo recibido, 409 con `faltan: []` y `filas`. La corrida sigue abierta.
3. Una parte en `todo` con 0 filas no se aplica: la corrida queda `fallida` (422) y los datos anteriores siguen.
4. Aplica en una transacción sobre la base del conjunto, con la fila de la corrida bloqueada:
   - MAESTROS (`Application\Apply\ApplyMaestros`): inserta o actualiza por empresa y llave, con `sincronizado_en` y `corrida_id`; en las partes `todo` inactiva lo que la corrida no trajo; por cada socio enviado, inactiva sus direcciones y contactos que no llegaron, aunque vayan en `cambios`. Nunca borra.
   - CARTERA (`ApplyCartera`): reemplaza toda la cartera de la empresa, con `fecha_corte` = la fecha en Bogotá de `extraida_en`, el día contra el que la consulta cuenta los `dias` (contrato §6). En la corrida `completa` guarda además la foto de `fecha_corte` (reemplaza otra del mismo día) con `dias` recalculado como `fecha_corte - fecha_vencimiento`, porque la consulta cuenta los días hasta el día en que corre (plan §4).
   - VENTAS (`ApplyVentas`, contrato §10.2): borra las filas de la empresa con `fecha_contabilizacion` desde `ventana_desde` y escribe las recibidas, con `sincronizado_en` y `corrida_id`. Lo anterior a la ventana es el histórico congelado de Comisiones y no se toca nunca; la `completa` y las de solicitud hacen lo mismo. La corrida `complemento` (`ApplyComplemento`, contrato §10.5) solo cambia `kilos` y `codigo_envio` de las líneas que ya están.
   - PEDIDOS (`ApplyPedidos`, contrato §11.3): borra todas las filas de la empresa y escribe las recibidas, con `sincronizado_en` y `corrida_id`. Lo que se facturó o se cerró en SAP desaparece; la `completa` y las de solicitud hacen lo mismo.
   - PRODUCCION (`ApplyProduccion`, contrato §12.3): en cada parte de movimiento borra las filas de la empresa con `fecha` desde `ventana_desde`; en cada maestro, todas. Luego escribe las recibidas, con `sincronizado_en` y `corrida_id`.
5. Deja la corrida `cerrada` con `aplicada_en`, lotes, filas y conteo de SAP, y borra sus lotes.

Si la transacción falla, nada cambia y la corrida sigue abierta para reintentar el cierre, que es idempotente.

## Conteo diario

Al cerrar una corrida `completa`, `Application\Apply\CountRun` compara por parte el conteo de SAP que envía el robot (`conteo_sap`), las filas recibidas (`recibidas`), las recibidas activas (`activas_recibidas`: las de `activo = true`; en una parte sin columna `activo`, todas) y las filas activas de la empresa en MySQL después de aplicar (`activas_mysql`; en CARTERA, todas las líneas de la empresa; en VENTAS, las de la empresa con `fecha_contabilizacion` desde `ventana_desde`; en PEDIDOS, todas las líneas de la empresa; en PRODUCCION, las de la ventana en el movimiento y todas en los maestros). `cuadra` es `sap == recibidas` y `activas_mysql == activas_recibidas`: SAP envía también las filas inactivas, que en MySQL no son activas. Si no cuadra, la corrida no falla: queda registrado.

- La respuesta del cierre trae `conteo` (solo en la `completa`) y la corrida lo guarda.
- `daily_counts` guarda el resultado del día (fecha de `extraida_en` en Bogotá), una fila por empresa y parte; si la corrida completa se repite el mismo día, la reemplaza. Es el criterio 3 de estabilidad del plan (§6), que el panel muestra; el panel lo leerá por un contrato de `Sap` cuando lo pida.
- Un día sin filas de una empresa (su corrida completa falló o venció) **no** es un día estable: el panel debe exigir las filas de todas las partes de cada empresa y cruzarlas con `robot_runs`. La excepción es `precios` de `SDC`: si la corrida completa no la trajo, esa parte no tiene fila en `daily_counts` y no cuenta contra la estabilidad. PRODUCCION solo se espera de `SGX`.

## Solicitudes de actualización

Una solicitud pide un conjunto completo (CARTERA, VENTAS, PEDIDOS y PRODUCCION siempre van completos, con `parte` nula; PRODUCCION solo de `SGX`) o una parte de MAESTROS (`Contracts\Enums\RequestScope`: `clientes`, `proveedores`, `articulos`, `precios`, `vendedores`, `catalogos`) de una empresa (contrato §7). Estados en `Contracts\Enums\RequestState`. Tablas: `update_requests`, `update_request_requesters` (quién pidió: app o panel, correo y nombre) y `client_apps`.

`Application\Requests\PlaceRequest` las ubica con un candado por empresa y conjunto (§7.2):

1. Si hay una igual `pendiente` o `en_cola`, la nueva se une a esa (se registra quién pidió).
2. Si hay una hermana `tomada`, queda `en_cola` sin hora (`correr_desde` nulo) hasta que esa termine.
3. Si la última hermana `terminada` terminó hace menos de 3 minutos, queda `en_cola` hasta 3 minutos después.
4. Si no, `pendiente` para ahora.
5. Si la hora cae a 15 minutos o menos de una franja bloqueada (`BASES_SAP_FRANJAS_BLOQUEADAS`, `Domain\Requests\BlockedSlots`), pasa al final de la franja y queda `en_cola`; las franjas que se tocan se encadenan (11:50 → 12:45).

Nunca se rechaza. El botón del panel usa el contrato `Contracts\UpdateRequests`.

El candado usa la caché de Laravel: en producción `CACHE_STORE` debe ser `database` o `file` (compartida entre procesos), nunca `array`. Si el candado no llega en 10 segundos, la solicitud se ubica igual (nunca se rechaza) y queda un aviso en el log.

## API de las apps

Cada app tiene su llave (`client_apps`): `bsap_` y 48 caracteres al azar; se guarda solo su SHA-256 y sus primeros 12 caracteres. Se crea con `php artisan sap:app "Nombre"` (la muestra una vez) o desde el panel por el contrato `Contracts\ClientAppKeys` (`issue`, `revoke`, `all`, `rotate`). Va en `Authorization: Bearer <llave>`; una llave revocada o desconocida recibe 401 `Llave inválida.` (`Http\Middleware\AuthenticateClientApp`). Límite: 60 peticiones por minuto por llave (las apps del mismo servidor comparten IP).

| Ruta | Hace |
|---|---|
| `POST /api/v1/solicitudes` | Pide una actualización (`empresa`, `conjunto`, `parte`, `solicitado_por.correo` y `nombre`). 201 si creó una solicitud, 200 si se unió a una igual; responde `id`, `estado`, `correr_desde`, `empresa`, `conjunto`, `parte`. |
| `GET /api/v1/solicitudes/{id}` | La solicitud con `tomada_en`, `terminada_en`, `error` y `solicitada_en`. Una app solo ve las solicitudes a las que se unió; las demás dan 404. |
| `GET /api/v1/estado?empresa=SGX&conjunto=CARTERA` | Por cada parte, `actualizado_en`: la última vez que una corrida cerrada la aplicó (o `null`). |

## El robot y las solicitudes

- `POST /api/robot/v1/solicitudes/tomar` (`Application\Requests\TakeRequests`, contrato §7.3) pregunta y toma en una sola llamada: pasa a `tomada`, en una transacción y de la más vieja a la más nueva, hasta `max` (1 a 100, por defecto 20) solicitudes `pendiente` o `en_cola` cuya hora ya llegó. Las de una empresa y conjunto que ya tiene una tomada esperan, porque el robot no podría abrir otra corrida de ese conjunto. Por cada parte en modo `cambios` responde `desde` = el mayor `actualizado_en_sap` de la empresa en MySQL (`null` si no hay filas: trae todo); CARTERA, VENTAS, PEDIDOS y PRODUCCION no tienen partes en `cambios`, así que su `desde` va vacío. Lista vacía: no hay nada que hacer.
- Al iniciar una corrida, cada id de `solicitudes` debe estar `tomada`, ser de la misma empresa y conjunto y pedir solo partes que la corrida trae; si no, 422. La solicitud queda ligada a la corrida (`run_id`).
- Las solicitudes se cierran con su corrida (`Domain\Runs\RunFinished`, en la misma transacción, `SettleRequests`): cerrada → `terminada`; fallida → `fallida` con el error; vencida → `vencida`. Las hermanas que esperaban sin hora reciben la suya: 3 minutos después si terminó bien, de inmediato si falló o venció, y siempre fuera de las franjas bloqueadas.
- `sap:vencer` además vence las solicitudes que llevan 30 minutos `tomada`. Si su corrida cierra bien después, los datos se aplican igual y la solicitud se queda `vencida`: es la señal de que tardó demasiado.

## Antes de desplegar

El despachador de despliegues corre `php artisan sap:puede-desplegar --no-ansi` (`Console\CanDeployCommand`) antes de cada despliegue, porque el modo mantenimiento a mitad de una corrida la mata: el robot reintenta un 5xx solo 3 veces en 14 segundos (`robot/etl/api.py`). Solo lee; no vence nada. Imprime `ok` y sale con 0, o imprime una línea con el primer motivo que aplica y sale con 1:

1. A 15 minutos o menos de una franja bloqueada, con la misma regla de `BlockedSlots` que las solicitudes: desde 15 minutos antes (incluido) hasta 15 minutos después (excluido).
2. Dentro de la ventana de la corrida nocturna en Bogotá (`sap.deploy.nightly_window`, `BASES_SAP_VENTANA_NOCTURNA_DESPLIEGUE`, por defecto `01:45-02:15`; `Domain\Deploy\NightlyWindow`): el inicio incluido y el fin excluido; si el fin va antes del inicio, cruza la medianoche. Una ventana mal escrita también rechaza.
3. Una corrida `abierta` que sigue dentro de su ventana de 30 minutos (`Run::isOpen()`), o una solicitud `tomada` que todavía no cumple los 30 minutos para vencer.

## Versión, totales y comparaciones

Rutas del robot del contrato §13, en el mismo grupo `sap.robot`. Ninguna cambia los datos de los conjuntos.

- `POST /api/robot/v1/version` (`Application\Deploy\DeployedCommit`, §13.1): responde `{"commit": "<sha>"}` con el commit que `deploy/deploy.sh` escribe después de un despliegue bueno en `sap.deploy.commit_file` (por defecto `storage/app/deploy/commit`, fuera del disco `local`, cuya raíz es `storage/app/private`), o `null` si el archivo falta o no trae exactamente un sha de 40 caracteres hexadecimales. Acepta mayúsculas y responde en minúscula. Nunca corre `git`: el robot solo se actualiza al commit que ya corre el servidor.
- `POST /api/robot/v1/totales` (`Application\Totals\ComputeTotals`, §13.2): solo lee. `Application\Totals\TotalsScope` valida `conjunto` (`MAESTROS`, `CARTERA` o `VENTAS`), `empresa` y, solo en VENTAS, `desde` y `hasta`. VENTAS da un grupo por mes de `fecha_contabilizacion` (`SUBSTR(..., 1, 7)`, igual en MySQL y SQLite) con `filas`, `sumas.total`, `sumas.cantidad` y `nulos.kilos` y `nulos.codigo_envio`; CARTERA, un grupo `actual` con la suma de `saldo`; MAESTROS, un grupo por parte con sus filas activas. Las sumas son exactas: en MySQL, `SUM` sobre las columnas `DECIMAL`; en SQLite, que guarda los decimales como `REAL`, la suma de cada valor llevado a entero de sus decimales. El resultado sale por bcmath como texto, nunca como `float`.
- `POST /api/robot/v1/comparaciones` (`Application\Totals\StoreComparison`, §13.3): guarda en `robot_comparisons` (conexión `app`) lo que el robot informa al comparar, con la llave que lo firmó, y responde 201 con su `id`. Nunca toca los datos de los conjuntos. El panel lo lee por `Contracts\Comparisons::latest()`: la última comparación de cada empresa y conjunto (`DatabaseComparisons`).
