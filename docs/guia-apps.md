# Guía para las apps

Cómo una app del Grupo RYR usa «Bases de datos SAP»: **lee** los datos de SAP desde vistas de MySQL con su usuario de solo lectura y **pide** datos frescos con el botón «Actualizar datos» por la API, con su propia llave. Ninguna app se conecta a SAP ni a la VPN.

El detalle de la API está en [`contrato-robot.md`](contrato-robot.md) §7; el alcance, en [`plan-bases-sap.md`](plan-bases-sap.md).

## Ruta rápida

1. Pídele a TI el **usuario MySQL de solo lectura** de tu app (permiso en `maestros_sap`, `cartera_sap`, `ventas_sap` o las que uses) y la **llave de la API** de tu app.
2. Agrega la conexión de Laravel y lee las vistas `v_*` (sección 1).
3. Pon el botón «Actualizar datos» en cada pantalla, diciendo qué actualiza (sección 2).
4. Muestra «Datos actualizados a las 10:42» con `GET /api/v1/estado` (sección 2.4).

## 1. Leer los datos

### 1.1 Qué pedirle a TI

| Qué | Para qué |
|---|---|
| Usuario MySQL de solo lectura, uno por app | Leer las vistas. Si se corta uno, las demás apps siguen. |
| Permiso solo en las bases que usa la app | `maestros_sap` (clientes, artículos, catálogos…), `cartera_sap` (cartera y fotos diarias), `ventas_sap` (líneas de facturas y notas crédito). |
| Si la app no está en GoDaddy: su IP fija | TI abre MySQL remoto solo para esa IP, con conexión cifrada (SSL). |

cPanel da permisos por base, no por tabla, así que el usuario también podría ver las tablas. **Lee siempre las vistas**, nunca las tablas: las tablas pueden cambiar y las vistas no.

### 1.2 Conexión de Laravel

En `config/database.php` de tu app, una conexión por base que uses:

```php
'sap_maestros' => [
    'driver' => 'mysql',
    'host' => env('SAP_DB_HOST', '127.0.0.1'),
    'port' => env('SAP_DB_PORT', '3306'),
    'database' => env('SAP_DB_MAESTROS', 'maestros_sap'),
    'username' => env('SAP_DB_USERNAME'),
    'password' => env('SAP_DB_PASSWORD'),
    'charset' => 'utf8mb4',
    'collation' => 'utf8mb4_unicode_ci',
    'strict' => true,
    // Fuera de GoDaddy, con el certificado que entrega TI.
    'options' => extension_loaded('pdo_mysql') ? array_filter([
        (PHP_VERSION_ID >= 80500 ? \Pdo\Mysql::ATTR_SSL_CA : \PDO::MYSQL_ATTR_SSL_CA) => env('SAP_DB_SSL_CA'),
    ]) : [],
],

'sap_cartera' => [
    // Igual, con 'database' => env('SAP_DB_CARTERA', 'cartera_sap').
],

'sap_ventas' => [
    // Igual, con 'database' => env('SAP_DB_VENTAS', 'ventas_sap').
],
```

Y en el `.env` de tu app (los valores los da TI; nunca van al repositorio):

```dotenv
SAP_DB_HOST=
SAP_DB_USERNAME=
SAP_DB_PASSWORD=
SAP_DB_MAESTROS=maestros_sap
SAP_DB_CARTERA=cartera_sap
SAP_DB_VENTAS=ventas_sap
SAP_DB_SSL_CA=
```

### 1.3 Leer una vista

```php
use Illuminate\Support\Facades\DB;

$clientes = DB::connection('sap_maestros')->table('v_clientes')
    ->where('empresa', 'SGX')
    ->where('activo', true)
    ->orderBy('nombre')
    ->get(['codigo', 'nombre', 'nit', 'vendedor_codigo', 'actualizado_en_sap']);

// Cartera de un asesor: el robot trae la de toda la empresa; la app filtra.
$cartera = DB::connection('sap_cartera')->table('v_cartera')
    ->where('empresa', 'SGX')
    ->where('email_asesor', $user->email)
    ->get();

// Ventas de un mes (por fecha de contabilización) y su margen.
$ventas = DB::connection('sap_ventas')->table('v_ventas')
    ->where('empresa', 'SGX')
    ->whereBetween('fecha_contabilizacion', ['2026-11-01', '2026-11-30'])
    ->selectRaw('SUM(total) AS venta_neta')
    ->selectRaw('SUM(CASE WHEN ganancia_bruta IS NOT NULL THEN ganancia_bruta END) AS ganancia_bruta')
    ->selectRaw('SUM(CASE WHEN ganancia_bruta IS NOT NULL THEN total END) AS venta_con_ganancia')
    ->first();

// Margen = ganancia_bruta / venta_con_ganancia, si venta_con_ganancia no es 0 (ver 1.4).
```

Nunca escribas en estas bases: el usuario es de solo lectura y los datos los pone el robot.

### 1.4 Vistas

| Base | Vista | Llave (con `empresa`) |
|---|---|---|
| `maestros_sap` | `v_clientes`, `v_proveedores` | `codigo` |
| | `v_direcciones` | `codigo_socio`, `tipo`, `nombre` |
| | `v_contactos` | `contacto_id` |
| | `v_articulos`, `v_grupos_articulos`, `v_marcas` | `codigo` |
| | `v_precios` (solo la lista PÚBLICA) | `articulo_codigo` |
| | `v_vendedores`, `v_grupos_clientes`, `v_condiciones_pago`, `v_municipios` | `codigo` |
| `cartera_sap` | `v_cartera` (la actual) | — |
| | `v_cartera_fotos` (una por empresa y `fecha_corte`) | — |
| `ventas_sap` | `v_ventas` (una fila por línea de factura o nota crédito) | `tipo_objeto`, `doc_entry`, `linea` |

Las columnas son las de `contrato-robot.md` (§5.2, §6 y §10), con estas reglas:

- **`empresa`** es `SGX` o `SDC`. Filtra siempre por empresa: un mismo código puede existir en las dos.
- **`activo`**: nunca se borran filas. Lo que se inactiva en SAP, o deja de llegar en la corrida completa, queda con `activo = 0`. Muestra solo los activos salvo que la pantalla necesite el histórico (por ejemplo, el cliente de una factura vieja).
- **`actualizado_en_sap`** es la última modificación en SAP (solo en clientes, proveedores y artículos); **`sincronizado_en`**, cuándo lo escribió el robot. Horas de Bogotá.
- **`v_cartera_fotos`**: la foto de cada día con `dias` contados a la `fecha_corte`. Úsala para la circularización y el histórico.
- Una vista solo crece: se agregan columnas al final, nunca se renombra ni se quita una. Lista tus columnas (`get([...])`), no uses `select *`.
- Clientes, contactos y cartera tienen datos personales (Ley 1581 de 2012): muéstralos solo a quien los necesite.

#### `v_ventas` (`ventas_sap`)

Una fila por línea de factura de clientes (incluidas las notas débito) o de nota crédito. Además de `empresa` y `sincronizado_en`, trae estas columnas de `contrato-robot.md` §10, en este orden: `tipo_objeto` (13 factura, 14 nota crédito), `doc_entry`, `numero_documento`, `linea`, `clase_documento` (`factura`, `nota_debito` o `nota_credito`), `estado_documento` (`anulado`, `anulacion`, `cerrado` o `abierto`), `fecha_documento`, `fecha_contabilizacion`, `slp_code`, `vendedor`, `canal`, `codigo_cliente`, `cliente`, `nit`, `ciudad`, `pedido`, `id_pedido_app`, `oc_cliente`, `ciudad_envio`, `direccion_envio`, `marca`, `familia`, `codigo_articulo`, `descripcion`, `cantidad`, `costo_unitario`, `costo_total`, `precio_lista`, `precio_unitario`, `total`, `iva`, `ganancia_bruta`, `moneda`, `trm`, `comentarios`.

- **El mes de una venta** lo da `fecha_contabilizacion` (`DocDate`), no `fecha_documento`.
- **Venta neta** = `SUM(total)`: las notas crédito llegan con `cantidad`, `total`, `iva` y `ganancia_bruta` negativos, así que la suma ya las descuenta.
- **Margen** = `SUM(ganancia_bruta) / SUM(total)`, **solo sobre las filas donde `ganancia_bruta IS NOT NULL`** (en el divisor también). `ganancia_bruta` viene de `GrssProfit` de SAP y cuadra con su «Ganancia bruta»; es `null` en las líneas cargadas antes de que el robot la enviara, y mezclarlas bajaría el margen.
- **`costo_total` nunca se usa para márgenes**: es el costo de inventario y no cuadra con la ganancia bruta de SAP (plan §4).
- **Historia**: empieza en la primera carga (ventana desde el 2026-10-25). Cada corrida nocturna reemplaza solo la ventana actual, que es el mes en curso más los últimos 7 días del mes anterior; lo anterior queda congelado y no se toca.
- `id_pedido_app` solo existe en `SGX`; en `SDC` siempre es `null`.

## 2. El botón «Actualizar datos»

### 2.1 Qué pide cada botón

Cada pantalla pide **solo lo que muestra**. Ejemplos:

| Pantalla | `conjunto` | `parte` |
|---|---|---|
| Cartera del gestor de cartera | `CARTERA` | `null` |
| Clientes en Toma de pedidos | `MAESTROS` | `clientes` (trae también direcciones y contactos) |
| Catálogo de productos | `MAESTROS` | `articulos` (con grupos y marcas) |
| Lista de precios | `MAESTROS` | `precios` |
| Vendedores | `MAESTROS` | `vendedores` |
| Canales, condiciones de pago, municipios | `MAESTROS` | `catalogos` |
| Todo MAESTROS | `MAESTROS` | `null` |
| Ventas y margen (mini panel de gerencia) | `VENTAS` | `null` (trae la parte `ventas`) |

El botón dice qué actualiza: «Actualizar cartera», «Actualizar clientes», no un «Actualizar» genérico.

**Cada app decide qué roles lo ven.** En Toma de pedidos, por ejemplo: gerentes, administradores de ventas y TI. Bases de datos SAP solo registra quién pidió.

### 2.2 Configuración

La llave la crea TI (`php artisan sap:app "Nombre de la app"` o el panel) y se muestra una sola vez. En el `.env` de tu app:

```dotenv
BASES_SAP_API_URL=https://<subdominio>
BASES_SAP_API_KEY=
```

Y en `config/services.php` de tu app:

```php
'bases_sap' => [
    'url' => env('BASES_SAP_API_URL'),
    'key' => env('BASES_SAP_API_KEY'),
],
```

La llave va solo en el servidor de tu app. Nunca en el navegador, en JavaScript ni en el repositorio.

### 2.3 Pedir la actualización

```php
use Illuminate\Support\Facades\Http;

$respuesta = Http::baseUrl(config('services.bases_sap.url'))
    ->withToken(config('services.bases_sap.key'))
    ->acceptJson()
    ->timeout(10)
    ->post('/api/v1/solicitudes', [
        'empresa' => 'SGX',
        'conjunto' => 'CARTERA',
        'parte' => null,
        'solicitado_por' => ['correo' => $user->email, 'nombre' => $user->name],
    ]);

$solicitud = $respuesta->json(); // id, estado, correr_desde, empresa, conjunto, parte
```

- **201**: se creó una solicitud. **200**: ya había una igual esperando y te uniste a ella. Las dos son éxito.
- Nunca se rechaza: si hace poco se actualizó o cae en una franja en que otros robots usan la VPN (00:00, 05:00, 06:00, 12:00 y 12:30, 15 minutos antes y después), queda `en_cola` y `correr_desde` dice a qué hora corre.
- Guarda el `id` (en la sesión o en tu base) para seguirla.

### 2.4 Seguirla y mostrar el resultado

Consulta `GET /api/v1/solicitudes/{id}` mientras esté `pendiente`, `en_cola` o `tomada`. Una app solo ve las solicitudes a las que se unió.

El límite es de **60 peticiones por minuto por llave**, compartido por todos los usuarios de tu app. Así que la consulta la hace **el servidor de tu app**, no cada navegador: guarda el estado de cada `id` en caché unos 30 segundos y que todas las pantallas lean de ahí. Como las solicitudes iguales se unen, muchos usuarios esperando la misma actualización comparten un solo `id` y una sola consulta.

| `estado` | Mensaje sugerido |
|---|---|
| `pendiente` | «Pedimos los datos a SAP. Suele tardar unos minutos.» |
| `en_cola` con `correr_desde` | «Se actualizará a las 12:45.» (la hora de `correr_desde`) |
| `en_cola` sin `correr_desde` | «Hay otra actualización en curso; esta sigue después.» |
| `tomada` | «Actualizando datos…» |
| `terminada` | «Datos actualizados.» Vuelve a leer las vistas. |
| `fallida` | «No se pudo actualizar. Inténtalo de nuevo más tarde.» (el detalle técnico está en `error`; no lo muestres al usuario) |
| `vencida` | «La actualización tardó demasiado. Inténtalo de nuevo.» |

`fallida` y `vencida` no se reintentan solas: quien la necesite vuelve a tocar el botón.

Para el texto «Datos actualizados a las 10:42», usa `GET /api/v1/estado?empresa=SGX&conjunto=CARTERA`: trae, por cada parte, `actualizado_en` (la última vez que se aplicó; `null` si nunca). Sirve aunque nadie haya tocado el botón, porque cuenta también la corrida de cada noche (02:00).

### 2.5 Errores

| Respuesta | Qué hacer |
|---|---|
| 401 `Llave inválida.` | La llave falta, está mal copiada o TI la revocó. Avísale a TI; no reintentes. |
| 422 | El cuerpo no cumple (empresa, conjunto, parte o correo). Revisa `errors`. |
| 429 | Más de 60 peticiones por minuto con tu llave. Espera lo que diga `Retry-After`. |
| Falla de red o 5xx | Muestra «No pudimos pedir la actualización» y deja tocar el botón otra vez. Los datos que ya muestras siguen siendo válidos. |

## Checklist antes de salir a producción

- [ ] La app lee vistas `v_*` con su propio usuario de solo lectura, filtrando por `empresa`.
- [ ] Ninguna credencial ni llave está en el repositorio.
- [ ] Cada botón dice qué actualiza y pide solo eso.
- [ ] Solo los roles que la app decidió ven el botón.
- [ ] La pantalla muestra «Datos actualizados a las …» y los estados de la tabla 2.4.
- [ ] Al terminar una solicitud, la pantalla vuelve a leer las vistas.

## Para TI

- Las vistas se crean con el usuario de MySQL que corre las migraciones de Bases de datos SAP y quedan a su nombre (`DEFINER`). **No borres ni renombres ese usuario**: las vistas dejarían de funcionar para todas las apps («The user specified as a definer does not exist»). Si hay que cambiarlo, primero se recrean las vistas con el usuario nuevo y después se borra el viejo.
- Para cortar una app: revoca su llave en el panel y quita su usuario MySQL en cPanel. Las demás no se enteran.
