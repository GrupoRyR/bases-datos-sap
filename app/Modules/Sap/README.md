# Módulo Sap

Los datos de SAP y todo lo que los mueve: los conjuntos MAESTROS y CARTERA, la recepción de lo que envía el robot (corridas y lotes), las solicitudes de actualización y la API que llaman las apps.

| Qué | Valor |
|---|---|
| Dueña | Sesión «Datos y API» |
| Rutas web | `/sap/*`, nombres `sap.*` |
| Rutas API | `/api/robot/v1/*` y `/api/v1/*`, exactas como dice el contrato (`apiPrefix()` vacío), nombres `sap.api.*` |
| Migraciones | `2026_11_02_*` |
| Conexiones | `maestros` y `cartera` para las tablas de cada conjunto; `app` para el resto (solicitudes, corridas, lotes) |
| Puede usar | Contratos de Core |

Lo que Panel necesite leer de aquí lo publica Sap en `App\Modules\Sap\Contracts`. El contrato con el robot está en `docs/contrato-robot.md` y no cambia sin avisarle al usuario.

Las reglas completas están en `docs/arquitectura.md`.

## Partes y columnas

`Contracts\Enums\Part` nombra cada parte del contrato (§1, §5 y §6) con su conjunto, su llave y sus columnas (`Domain\Columns\PartColumns`). El valor de cada caso es el nombre del contrato, que es también la tabla (`clientes`) y, con `v_`, la vista (`v_clientes`). Cambiar una columna es cambiar el contrato: primero lo aprueba el usuario.

## Tablas y vistas

| Conjunto | Conexión | Tablas | Vistas |
|---|---|---|---|
| MAESTROS | `maestros` | Una por parte: `clientes`, `proveedores`, `direcciones`, `contactos`, `articulos`, `grupos_articulos`, `marcas`, `precios`, `vendedores`, `grupos_clientes`, `condiciones_pago`, `municipios` | `v_<tabla>` |
| CARTERA | `cartera` | `cartera` (actual) y `cartera_fotos` (una foto por empresa y `fecha_corte`) | `v_cartera`, `v_cartera_fotos` |

- Cada fila de MAESTROS lleva `empresa`, sus columnas del contrato, `activo`, `actualizado_en_sap` (solo la traen clientes, proveedores y artículos), `sincronizado_en` y `corrida_id`. Es única por empresa y llave. Nunca se borra: lo que deja de llegar queda inactivo.
- CARTERA no tiene llave natural: cada cierre bueno reemplaza toda la cartera de la empresa en una transacción.
- Las vistas listan sus columnas una por una y nunca muestran `id` ni `corrida_id`. Para cambiar una vista se agregan columnas al final en una migración nueva; nunca se renombra ni se quita una, porque las apps leen de ellas.
- Los textos van como `varchar` con el largo de SAP; las horas, en hora de Bogotá; los montos, `decimal(19,2)`.

## Peticiones del robot

Toda ruta del robot va en el grupo de middleware `sap.robot` (`SapServiceProvider`), en este orden:

1. `throttle:sap-robot`: 120 peticiones por minuto por IP; después, 429 con `Retry-After`.
2. `LimitRobotPayload`: 413 si el cuerpo pasa de 10 MB tal como viaja, antes de mirar la firma.
3. `VerifyRobotSignature`: HMAC-SHA256 del contrato (§3) con las llaves de `ROBOT_HMAC_KEYS`. Toda falla responde 401 `Firma inválida.` y queda en el log con el motivo, la llave y la IP. El nonce se guarda en `robot_nonces` solo después de validar la firma; el programador borra los de más de 10 minutos.
4. `DecodeRobotBody`: descomprime gzip por partes (413 si pasa de 40 MB, 400 si está dañado), exige un objeto JSON (400) y deja el texto en el atributo `robot_body` para comparar lotes por su SHA-256.

Los límites están en `config/sap.php` (`sap.robot.*`).

## Corridas

Una corrida lleva un conjunto de una empresa (`robot_runs`, contrato §4). Estados: `abierta` → `cerrada`, `fallida` o `vencida` (`Domain\Runs\RunState`).

- `POST /api/robot/v1/corridas` (`Application\Runs\StartRun`): valida conjunto, empresa, tipo, partes y modos (una corrida `completa` trae todas las partes en `todo`; solo clientes, proveedores y artículos, con sus direcciones y contactos, van en `cambios`), `fecha_corte` solo en CARTERA y `extraida_en` con zona. Responde 201 con `abierta_hasta`.
- Solo una corrida abierta por conjunto y empresa: lo asegura el índice único de `abierta_lock`. La segunda recibe 409 con el `run_id` de la abierta.
- `POST /api/robot/v1/corridas/{id}/fallar` (`FailRun`): la marca `fallida` con el error del robot y descarta sus lotes.
- Una corrida que pasa 30 minutos sin lotes queda `vencida`: al tocarla, al iniciar otra del mismo conjunto y empresa, y con `php artisan sap:vencer`, que el programador corre cada minuto.
- Los errores del robot se responden con `Http\Exceptions\RobotRequestRejected`: 422 con `errors` (máximo 50), 409 con `estado` o `run_id`, 404 si la corrida no existe. El repositorio no trae mensajes de validación en español, así que el módulo escribe los suyos.

## Lotes

`POST /api/robot/v1/corridas/{id}/lotes` (`Application\Runs\ReceiveBatch`, contrato §4.2) guarda el lote en `robot_batches` hasta que la corrida cierra; nada llega a MAESTROS ni a CARTERA, así que un lote rechazado deja todo como estaba.

- `batch` es entero desde 1, consecutivo en la corrida; el mismo `batch` con el mismo cuerpo (SHA-256 del JSON ya descomprimido) responde 200 con `duplicate`, y con otro cuerpo, 409.
- `Domain\Batches\BatchRows` exige exactamente las columnas de la parte, en cualquier orden y sin repetir, y un valor por columna. Revisa tipos (enteros JSON, montos como texto con punto y hasta 2 decimales, booleanos, fechas, horas con zona), obligatorias no nulas ni vacías, texto de hasta 4.000 caracteres (el opcional se recorta al largo de su columna; la llave que no cabe se rechaza) y devuelve las filas en el orden de columnas de la parte, con las horas en Bogotá.
- Una llave no se repite en la corrida, ni en el lote ni entre lotes (`robot_batch_keys`); CARTERA no tiene llave.
- Un 422 cuenta en `lotes_rechazados` y la corrida sigue abierta. Cada lote aceptado extiende `abierta_hasta` 30 minutos.
- El lote se guarda con la fila de la corrida bloqueada, así que no se cruza con su cierre ni con su vencimiento.

## Cierre

`POST /api/robot/v1/corridas/{id}/cerrar` (`Application\Runs\CloseRun`, contrato §4.3):

1. Valida `batches` y `filas` (un número por cada parte de la corrida); `conteo_sap` es obligatorio en una corrida `completa` y prohibido en las demás.
2. Si falta algún lote del 1 al `batches`, responde 409 con `faltan`; si las filas no cuadran con lo recibido, 409 con `faltan: []` y `filas`. La corrida sigue abierta.
3. Una parte en `todo` con 0 filas no se aplica: la corrida queda `fallida` (422) y los datos anteriores siguen.
4. Aplica en una transacción sobre la base del conjunto, con la fila de la corrida bloqueada:
   - MAESTROS (`Application\Apply\ApplyMaestros`): inserta o actualiza por empresa y llave, con `sincronizado_en` y `corrida_id`; en las partes `todo` inactiva lo que la corrida no trajo; por cada socio enviado, inactiva sus direcciones y contactos que no llegaron, aunque vayan en `cambios`. Nunca borra.
   - CARTERA (`ApplyCartera`): reemplaza toda la cartera de la empresa. En la corrida `completa` guarda además la foto de `fecha_corte` (reemplaza otra del mismo día) con `dias` recalculado como `fecha_corte - fecha_vencimiento`, porque la consulta cuenta los días hasta el día en que corre (plan §4).
5. Deja la corrida `cerrada` con `aplicada_en`, lotes, filas y conteo de SAP, y borra sus lotes.

Si la transacción falla, nada cambia y la corrida sigue abierta para reintentar el cierre, que es idempotente.

## Conteo diario

Al cerrar una corrida `completa`, `Application\Apply\CountRun` compara por parte el conteo de SAP que envía el robot (`conteo_sap`), las filas recibidas y las filas activas de la empresa en MySQL después de aplicar (en CARTERA, todas las líneas de la empresa). Si no cuadra, la corrida no falla: queda registrado.

- La respuesta del cierre trae `conteo` (solo en la `completa`) y la corrida lo guarda.
- `daily_counts` guarda el resultado del día (fecha de `extraida_en` en Bogotá), una fila por empresa y parte; si la corrida completa se repite el mismo día, la reemplaza. Es el criterio 3 de estabilidad del plan (§6), que el panel muestra; el panel lo leerá por un contrato de `Sap` cuando lo pida.
- Un día sin filas de una empresa (su corrida completa falló o venció) **no** es un día estable: el panel debe exigir las filas de todas las partes de cada empresa y cruzarlas con `robot_runs`.

## Solicitudes de actualización

Una solicitud pide un conjunto completo o una parte de MAESTROS (`Contracts\Enums\RequestScope`: `clientes`, `proveedores`, `articulos`, `precios`, `vendedores`, `catalogos`) de una empresa (contrato §7). Estados en `Contracts\Enums\RequestState`. Tablas: `update_requests`, `update_request_requesters` (quién pidió: app o panel, correo y nombre) y `client_apps`.

`Application\Requests\PlaceRequest` las ubica con un candado por empresa y conjunto (§7.2):

1. Si hay una igual `pendiente` o `en_cola`, la nueva se une a esa (se registra quién pidió).
2. Si hay una hermana `tomada`, queda `en_cola` sin hora (`correr_desde` nulo) hasta que esa termine.
3. Si la última hermana `terminada` terminó hace menos de 3 minutos, queda `en_cola` hasta 3 minutos después.
4. Si no, `pendiente` para ahora.
5. Si la hora cae a 15 minutos o menos de una franja bloqueada (`BASES_SAP_FRANJAS_BLOQUEADAS`, `Domain\Requests\BlockedSlots`), pasa al final de la franja y queda `en_cola`; las franjas que se tocan se encadenan (11:50 → 12:45).

Nunca se rechaza. El botón del panel usa el contrato `Contracts\UpdateRequests`.
