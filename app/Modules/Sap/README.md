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
