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
| Permiso solo en las bases que usa la app | `maestros_sap` (clientes, artículos, catálogos…), `cartera_sap` (cartera y fotos diarias), `ventas_sap` (líneas de facturas y notas crédito, pedidos abiertos y producción de Segurex). |
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
| | `v_pedidos` (una fila por línea abierta de pedido de clientes) | `doc_entry`, `linea` |
| | `v_produccion_terminado` (solo SGX) | `doc_entry`, `linea` |
| | `v_produccion_carga_planta`, `v_produccion_costos` (solo SGX) | sin llave |
| | `v_produccion_despiece`, `v_produccion_rutas` (solo SGX) | sin llave |
| | `v_produccion_costeo_teorico` (solo SGX) | `codigo_articulo` |

Las columnas son las de `contrato-robot.md` (§5.2, §6, §10, §11 y §12), con estas reglas:

- **`empresa`** es `SGX` o `SDC`. Filtra siempre por empresa: un mismo código puede existir en las dos.
- **`activo`** (maestros): nunca se borran filas. Lo que se inactiva en SAP, o deja de llegar en la corrida completa, queda con `activo = 0`. Muestra solo los activos salvo que la pantalla necesite el histórico (por ejemplo, el cliente de una factura vieja).
- **Columnas nuevas al final.** `v_clientes` y `v_proveedores` traen `contacto_principal` (`OCRD.CntctPrsn`): el **nombre** del contacto principal, no su id; para hallarlo, compáralo con `nombre` de `v_contactos` del mismo socio. `v_contactos` trae `telefono_2` (`OCPR.Tel2`). Las dos van después de `sincronizado_en` y quedan `null` hasta que el robot las envíe.
- **`actualizado_en_sap`** es la última modificación en SAP (solo en clientes, proveedores y artículos); **`sincronizado_en`**, cuándo lo escribió el robot. Horas de Bogotá.
- **`fecha_corte` de `v_cartera`** (al final de la vista) es el día contra el que se cuentan sus `dias`: la fecha de extracción de la última corrida, hoy después de la nocturna. No es la `fecha_corte` de `v_cartera_fotos`, que es el día anterior. En las dos vistas, `dias` = `fecha_corte` − `fecha_vencimiento`.
- **`v_cartera_fotos`**: la foto de cada día con `dias` contados a la `fecha_corte`. Úsala para la circularización y el histórico.
- Una vista solo crece: se agregan columnas al final, nunca se renombra ni se quita una. Lista tus columnas (`get([...])`), no uses `select *`.
- Clientes, contactos y cartera tienen datos personales (Ley 1581 de 2012): muéstralos solo a quien los necesite.

#### `v_ventas` (`ventas_sap`)

Una fila por línea de factura de clientes (incluidas las notas débito) o de nota crédito. Además de `empresa` y `sincronizado_en`, trae estas columnas de `contrato-robot.md` §10, en este orden: `tipo_objeto` (13 factura, 14 nota crédito), `doc_entry`, `numero_documento`, `linea`, `clase_documento` (`factura`, `nota_debito` o `nota_credito`), `estado_documento` (`anulado`, `anulacion`, `cerrado` o `abierto`), `fecha_documento`, `fecha_contabilizacion`, `slp_code`, `vendedor`, `canal`, `codigo_cliente`, `cliente`, `nit`, `ciudad`, `pedido`, `id_pedido_app`, `oc_cliente`, `ciudad_envio`, `direccion_envio`, `marca`, `familia`, `codigo_articulo`, `descripcion`, `cantidad`, `costo_unitario`, `costo_total`, `precio_lista`, `precio_unitario`, `total`, `iva`, `ganancia_bruta`, `moneda`, `trm`, `comentarios`. Al final, después de `sincronizado_en`, trae `kilos` y `codigo_envio`.

- **El mes de una venta** lo da `fecha_contabilizacion` (`DocDate`), no `fecha_documento`.
- **Venta neta** = `SUM(total)`: las notas crédito llegan con `cantidad`, `total`, `iva` y `ganancia_bruta` negativos, así que la suma ya las descuenta.
- **Margen** = `SUM(ganancia_bruta) / SUM(total)`, **solo sobre las filas donde `ganancia_bruta IS NOT NULL`** (en el divisor también). `ganancia_bruta` viene de `GrssProfit` de SAP y cuadra con su «Ganancia bruta»; es `null` en las líneas cargadas antes de que el robot la enviara, y mezclarlas bajaría el margen.
- **`kilos`** es el peso de la línea en kilos («Tot KG» de la consulta «AnálisisVentas-1» de SAP), con hasta 6 decimales. Lleva el signo de `cantidad`: es negativo en las notas crédito, así que `SUM(kilos)` ya da los kilos netos. Es `null` en las líneas cargadas antes de que el robot lo enviara; los meses de 2025 en adelante se llenan con la corrida `kilos` (contrato §10.5). Si sumas kilos de un período, revisa antes que no queden filas con `kilos IS NULL`.
- **`codigo_envio`** es el código de la dirección de envío del documento (`ShipToCode` de SAP); en `SDC` es el CEDI. Es `null` en las líneas cargadas antes de que el robot lo enviara.
- **`costo_total` nunca se usa para márgenes**: es el costo de inventario y no cuadra con la ganancia bruta de SAP (plan §4).
- **Historia**: la nocturna empezó el 2026-10-25, y los meses anteriores llegan con la carga histórica (contrato §10.4), mes por mes, desde el primero que se cargue. Cada corrida nocturna reemplaza solo la ventana actual, que es el mes en curso más los últimos 7 días del mes anterior. **Lo anterior a la ventana nunca cambia**: ni la nocturna ni la carga histórica lo tocan, y la carga histórica solo llena meses que estaban vacíos. La única excepción es la corrida `kilos` (contrato §10.5), que llena solo `kilos` de las líneas ya cargadas, de 2025 en adelante, sin tocar ninguna otra columna.
- `id_pedido_app` solo existe en `SGX`; en `SDC` siempre es `null`.

#### `v_pedidos` (`ventas_sap`)

Una fila por línea abierta de pedido de clientes. Es una **foto del estado abierto** en el momento de la extracción, no un acumulado de un período: cada cierre bueno reemplaza todas las líneas de la empresa, así que lo que ya se facturó o se cerró en SAP desaparece. Llave: `empresa`, `doc_entry` y `linea`. Además de `empresa` y `sincronizado_en`, trae estas columnas de `contrato-robot.md` §11.2, en este orden: `doc_entry`, `numero_pedido`, `linea`, `fecha_pedido`, `fecha_compromiso`, `fecha_entrega_linea`, `dias`, `rango`, `dias_atraso`, `slp_code`, `vendedor`, `canal`, `codigo_cliente`, `cliente`, `nit`, `ciudad`, `id_pedido_app`, `oc_cliente`, `direccion_envio`, `comentarios`, `codigo_articulo`, `descripcion`, `linea_articulo`, `familia`, `marca`, `bodega`, `unidad`, `cantidad_pedida`, `cantidad_pendiente`, `precio_lista`, `precio_unitario`, `descuento_documento`, `total_pendiente`, `ganancia_bruta_pendiente`, `moneda`, `trm`.

- **Valor pendiente** = `SUM(total_pendiente)`, en pesos. **Margen** = `SUM(ganancia_bruta_pendiente) / SUM(total_pendiente)`, como en VENTAS. No hay columnas de costo.
- `cantidad_pedida` y `cantidad_pendiente` van en unidades de venta (las del precio); `precio_lista` y `precio_unitario`, en la moneda de la línea.
- `dias` cuenta desde `fecha_pedido` y `rango` lo agrupa: `Hasta 30 dias`, `De 31 a 60 dias`, `De 61 a 90 dias` o `Mas de 90 dias`. `dias_atraso` cuenta desde `fecha_compromiso`: es negativo si aún no vence.
- `id_pedido_app` y `familia` solo existen en `SGX`; en `SDC` siempre son `null`.

#### `v_produccion_*` (`ventas_sap`)

Los datos del tablero «Producción mes a mes»: órdenes de producción de BEAS, costos y maestros de fabricación. Son **solo de `SGX`**, pero filtra siempre por `empresa` igual que en las demás vistas. Además de `empresa` y `sincronizado_en`, cada vista trae estas columnas de `contrato-robot.md` §12.2, en este orden:

| Vista | Columnas | Llave (con `empresa`) |
|---|---|---|
| `v_produccion_terminado` | `doc_entry`, `numero_documento`, `linea`, `fecha`, `grupo`, `familia`, `codigo_articulo`, `articulo`, `nro_ot`, `posicion`, `cantidad`, `valor` | `doc_entry`, `linea` |
| `v_produccion_carga_planta` | `fecha`, `area`, `linea_producto`, `linea_negocio`, `etapa`, `puesto_trabajo`, `nro_ot`, `posicion`, `operacion`, `codigo_articulo`, `nombre_articulo`, `unidad`, `unidades`, `unidades_no_conformes`, `horas`, `almacen`, `estado_ot` | Sin llave: dos reportes iguales del mismo día son legítimos |
| `v_produccion_costos` | `fecha`, `concepto`, `area`, `linea_producto`, `linea_negocio`, `etapa`, `material_consumido`, `grupo_material`, `codigo_material`, `nro_ot`, `posicion`, `codigo_articulo`, `nombre_articulo`, `puesto_trabajo`, `costo` | Sin llave: un reporte da varias filas |
| `v_produccion_despiece` | `padre`, `hijo`, `cantidad`, `merma` | Sin llave: un mismo par `padre`-`hijo` puede repetirse |
| `v_produccion_rutas` | `codigo_articulo`, `operacion`, `area`, `puesto`, `tiempo`, `cantidad_base`, `factor_merma` | Sin llave |
| `v_produccion_costeo_teorico` | `codigo_articulo`, `articulo`, `familia`, `posiciones`, `cantidad`, `material_soll`, `fabricacion_soll`, `total_soll`, `total_ist` | `codigo_articulo` |

- **Cómo se cargan** (§12.3). Las tres de movimiento (`terminado`, `carga_planta` y `costos`) reemplazan en cada cierre solo las filas con `fecha` desde la `ventana_desde` de la corrida, que es la misma de VENTAS (el mes en curso más los últimos 7 días del mes anterior); lo anterior se queda. La historia empieza en la carga inicial, desde el 2026-08-01. Los tres maestros (`despiece`, `rutas` y `costeo_teorico`) se reemplazan completos.
- **Costo de producción** = `SUM(costo)` de `v_produccion_costos` **sin las filas `concepto = 'Material intermedio'`**: son material que la propia planta fabricó y vuelve a entrar como insumo (recirculación interna); el tablero las excluye del total. Los conceptos son exactamente `Mano de obra directa`, `Costo variable`, `Costo fijo`, `Material comprado` y `Material intermedio`.
- `v_produccion_terminado` trae una fila por línea de la entrada a bodega, sin agrupar: suma `cantidad` y `valor` por día y artículo.
- En `v_produccion_rutas`, el tiempo unitario de una operación es `tiempo / cantidad_base`. En `v_produccion_carga_planta`, `horas` ya viene en horas y `estado_ot` es `J` o `N`.
- `v_produccion_despiece` y `v_produccion_rutas` no tienen llave: agrupa o suma, no supongas una fila por par.

#### Nombres que cambian entre vistas

- **`familia`** es `OITM.U_GSP_FAMILIA` en `v_pedidos`, `v_produccion_terminado` y `v_produccion_costeo_teorico`. En `v_ventas`, `familia` es otro dato (el grupo del artículo, `OITB.ItmsGrpNam`); en `v_pedidos` ese grupo es `linea_articulo`.
- **`linea`** es siempre el número de línea del documento (`v_ventas`, `v_pedidos`, `v_produccion_terminado`). La «Linea» del tablero de producción, la línea de producto, es **`linea_producto`**, no `linea`.

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
| Pedidos pendientes | `PEDIDOS` | `null` (trae la parte `pedidos`) |
| Producción mes a mes (solo Segurex) | `PRODUCCION` | `null` (trae las seis partes) |

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
