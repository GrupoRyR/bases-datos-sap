# Contrato del robot

Versión 1. Lo implementan dos sesiones en paralelo: «Datos y API» (el servidor, `app/Modules/Sap`) y «Robot» (el cliente, `robot/`). Después de fusionarlo **no se cambia sin avisar al usuario**: cualquier cambio se propone, el usuario lo aprueba y las dos sesiones lo aplican en el mismo PR o en PR encadenados. Manda `docs/plan-bases-sap.md`; si este documento choca con el plan, se corrige este.

## 1. Términos

| Término | Qué es | Valores |
|---|---|---|
| Empresa | Empresa de SAP | `SGX` (esquema `SEGUREX`), `SDC` (esquema `HBT_SDERIVADOS`) |
| Conjunto | Grupo de datos con su propia base MySQL | `MAESTROS` (`maestros_sap`), `CARTERA` (`cartera_sap`), `VENTAS` (`ventas_sap`), `PEDIDOS` (también en `ventas_sap`, §11), `PRODUCCION` (también en `ventas_sap`, solo `SGX`, §12) |
| Parte | Tabla lógica dentro de un conjunto (§5, §6, §10, §11 y §12) | `clientes`, `proveedores`, `direcciones`, `contactos`, `articulos`, `grupos_articulos`, `marcas`, `precios`, `vendedores`, `grupos_clientes`, `condiciones_pago`, `municipios`, `cartera`, `ventas`, `pedidos`, `produccion_terminado`, `produccion_carga_planta`, `produccion_costos`, `produccion_despiece`, `produccion_rutas`, `produccion_costeo_teorico` |
| Corrida | Un envío completo del robot: iniciar, lotes y cerrar (§4) | Tipo `completa`, `solicitud` o `historico` (solo `VENTAS`, §10.4) |
| Lote | Hasta 1.000 filas de una sola parte | Numerados desde 1 en cada corrida |
| Solicitud | Pedido de actualización de una app o del panel (§7) | Estados en §7.2 |

Solo existen los conjuntos y partes de esta tabla. Las tablas que van solo a la carpeta (plan §5) **nunca** se envían: la API responde 422 a cualquier conjunto o parte desconocidos.

Nombres: las rutas y los valores de negocio van en español, como el plan; las llaves del sobre JSON (`run_id`, `rows`…) van en inglés, como el código; las columnas de datos van en español y en `snake_case`, como las columnas de MySQL del plan §4 y como el gestor de cartera, para que el gestor pueda leer de aquí sin traducir nombres.

## 2. Transporte

- Base: `https://<subdominio>/api/robot/v1`. Solo HTTPS. Todas las rutas del robot son `POST`, sin query string.
- Las rutas de este documento (`/api/robot/v1/*` y `/api/v1/*` de §7.4) son exactas. El módulo `Sap` las sirve con `apiPrefix()` vacío, no bajo el `/api/sap` por defecto (`docs/arquitectura.md`).
- Cuerpo JSON en UTF-8 (`Content-Type: application/json`). Puede ir comprimido con `Content-Encoding: gzip`; el robot comprime por defecto.
- Límite: 10 MB por petición tal como viaja y 40 MB descomprimida. La API responde 413 antes de revisar la firma si se pasa.
- Límite de ritmo: 120 peticiones por minuto por IP. Pasado eso, 429 con `Retry-After`.
- Horas: ISO 8601 con zona (`2026-10-23T10:42:05-05:00`). Fechas: `AAAA-MM-DD`. Zona de referencia: `America/Bogota`.

## 3. Firma HMAC-SHA256

Cada petición del robot lleva:

| Encabezado | Valor |
|---|---|
| `X-Robot-Key` | Id de la llave, p. ej. `r2026a` (`A-Z a-z 0-9 _ -`, hasta 32) |
| `X-Robot-Timestamp` | Segundos Unix (UTC), entero |
| `X-Robot-Nonce` | 32 caracteres hexadecimales en minúscula (16 bytes al azar), uno nuevo por petición |
| `X-Robot-Signature` | `sha256=` + HMAC-SHA256 en hexadecimal minúscula |

Cadena canónica en UTF-8, campos unidos por `\n`, sin salto final:

```text
{timestamp}
{nonce}
POST
{ruta}
{sha256 en hexadecimal del cuerpo tal como viaja (los bytes gzip si va comprimido)}
```

`{ruta}` es la ruta desde la raíz de la app, con `/` inicial y sin dominio ni query string: `/api/robot/v1/corridas/42/lotes`. En Laravel es `'/'.$request->path()`, que ya descuenta un subdirectorio.

La API rechaza, antes de descomprimir o leer el JSON:

1. Encabezados faltantes o mal formados, o una llave desconocida.
2. Un `timestamp` a más de **300 segundos** (5 minutos) de la hora del servidor, hacia atrás o hacia adelante.
3. Una firma que no coincide (comparación en tiempo constante).
4. Un `nonce` ya usado con la misma llave en los últimos 10 minutos (repetición). El nonce se guarda solo después de validar la firma, para que un tercero no pueda gastar nonces ajenos.

Todas las fallas responden 401 `{"message": "Firma inválida."}`, el mismo texto, y quedan en el log con el motivo, el id de la llave y la IP; nunca con el secreto. Si el robot recibe 401 no reintenta la misma petición: firma una nueva con otro nonce y otra hora.

Una petición con query string responde 400 antes de revisar la firma (§2) y no gasta el nonce.

Llaves: `ROBOT_HMAC_KEYS="id:secreto,id2:secreto2"` en el `.env` del servidor y la del robot en el suyo. Secretos de al menos 32 bytes al azar. Para rotar: se agrega la nueva junto a la vieja, el robot pasa a la nueva y luego se quita la vieja.

Vector de prueba (las dos sesiones lo usan en sus pruebas): secreto `robot-secreto-de-prueba`, timestamp `1792152000`, nonce `9f86d081884c7d659a2feaa0c55ad015`, ruta `/api/robot/v1/corridas` y cuerpo `{"conjunto":"CARTERA"}` (sin espacios, sin gzip). El SHA-256 del cuerpo es `c04ff2072e7cfb7c308adf681b5c060ec271b48124895c3310a9a49e912091b9` y la firma `sha256=29d3895ed1dec41dc0c471b2a3e0b148e975b479698a86a13833814b661e0dd2`.

## 4. Corridas

Una corrida lleva un conjunto de una empresa. Los datos de una corrida no se ven en MySQL hasta que se cierra bien: al cerrar, la API aplica todo en una sola transacción por conjunto. Si la corrida falla o vence, no cambia nada.

### 4.1 Iniciar: `POST /api/robot/v1/corridas`

```json
{
  "conjunto": "MAESTROS",
  "empresa": "SGX",
  "tipo": "solicitud",
  "partes": {"clientes": "cambios", "direcciones": "cambios", "contactos": "cambios"},
  "solicitudes": [118, 121],
  "fecha_corte": null,
  "extraida_en": "2026-10-23T10:41:30-05:00"
}
```

- `tipo`: `completa` (la nocturna de las 02:00), `solicitud` (atiende solicitudes) o `historico` (carga manual de un mes de `VENTAS` anterior a la ventana nocturna, §10.4). `historico` solo existe en `VENTAS`: en los demás conjuntos, 422. Trae todas las partes en modo `todo`, como la `completa`, y no atiende solicitudes.
- `partes`: cada parte que traerá la corrida y su modo:
  - `todo`: llegan todas las filas que hay en SAP. Al cerrar, las filas de esa parte y empresa que no llegaron quedan inactivas (`activo = false`). Nunca se borran.
  - `cambios`: llegan solo las filas que cambiaron (§5.1). Al cerrar, no se inactiva nada por ausencia.
- En una corrida `completa` todas las partes del conjunto van, y van en modo `todo`. Única excepción: `SDC` (Derivados) todavía no tiene una lista de precios pública, así que su corrida `completa` de `MAESTROS` puede omitir `precios`; al cerrar no se inactiva nada por esa ausencia. `SGX` siempre la envía.
- `empresa`: `SGX` o `SDC`. `PRODUCCION` es solo de `SGX`: una corrida de `SDC` da 422 (§12).
- `solicitudes`: ids de las solicitudes que atiende (§7). Vacío en una corrida `completa` sin solicitudes. Cada id debe estar `tomada`, ser de la misma empresa y conjunto, y pedir partes incluidas en `partes`; si no, 422.
- `fecha_corte`: solo en `CARTERA`; en los demás conjuntos, 422 (también en `PEDIDOS` y `PRODUCCION`, §11 y §12). En la `completa` nocturna, el día anterior; en una `solicitud`, hoy.
- `ventana_desde`: solo en `VENTAS` y `PRODUCCION`, donde es obligatoria; en los demás conjuntos, 422 (también en `PEDIDOS`, §11). El primer día de la ventana que trajo la consulta, calculado en HANA (§10.1). En `VENTAS` va entre hoy menos 40 días y mañana (§10.1), salvo en una corrida `historico`, donde es el primer día de un mes (§10.4); en `PRODUCCION`, entre `2026-01-01` y mañana (§12.3).
- `ventana_hasta`: el último día que trae una corrida `historico` (§10.4), obligatorio en ella. En cualquier otro tipo, 422.
- `extraida_en`: cuándo terminó la consulta a SAP.

Respuesta 201: `{"run_id": 42, "estado": "abierta", "abierta_hasta": "2026-10-23T11:11:30-05:00"}`.

Una corrida abierta que pasa **30 minutos sin recibir lotes** queda `vencida`, se descartan sus lotes y sus solicitudes pasan a `vencida`. No puede haber dos corridas abiertas del mismo conjunto y empresa: la segunda recibe 409 con el `run_id` de la abierta.

### 4.2 Lotes: `POST /api/robot/v1/corridas/{run_id}/lotes`

```json
{
  "batch": 3,
  "parte": "clientes",
  "columns": ["codigo", "nombre", "nit", "activo", "actualizado_en_sap"],
  "rows": [
    ["C800123456", "Ferretería La Llave SAS", "800123456-1", true, "2026-10-23T09:15:02-05:00"]
  ]
}
```

- `batch`: entero desde 1, consecutivo en la corrida (no por parte). Hasta **1.000 filas** por lote y una sola parte.
- `columns`: exactamente las columnas de la parte (§5, §6, §10, §11 o §12), en cualquier orden y sin repetir. Cada fila de `rows` es una lista con un valor por columna, en ese orden. **Excepciones de transición:** un lote de `VENTAS` puede omitir `ganancia_bruta`; uno de `clientes` o `proveedores`, `contacto_principal`, y uno de `contactos`, `telefono_2` (§5.2). La API acepta ambos encabezados, con y sin esa columna, y guarda `null` cuando falta. Cualquier otra columna que falte o sobre sigue dando 422. Existen porque el robot del PC de TI se actualiza después del servidor y la corrida de las 02:00 no debe fallar entre los dos.
- Valores: enteros como número JSON; montos como texto decimal con punto, hasta 2 decimales y sin separador de miles (`"1234567.89"`), con `-` si son negativos; cantidades y tasas (solo en `VENTAS`, `PEDIDOS` y `PRODUCCION`, §10, §11 y §12) igual que los montos pero con hasta 6 decimales (`"2.500000"`); booleanos como `true`/`false`; fechas `"AAAA-MM-DD"`; horas ISO 8601 con zona; texto hasta 4.000 caracteres, recortado; `null` si falta. Las columnas obligatorias no pueden llegar nulas ni vacías.
- Una llave (§5, §6, §10, §11 y §12) no puede repetirse en la corrida, ni dentro del lote ni entre lotes.

Respuestas:

| Estado | Cuándo | Cuerpo |
|---|---|---|
| 201 | Lote nuevo aceptado | `{"batch": 3, "rows": 1000}` |
| 200 | Mismo `batch` reenviado con el mismo cuerpo (mismo SHA-256) | `{"batch": 3, "rows": 1000, "duplicate": true}` |
| 409 | Mismo `batch` con otro cuerpo, o corrida que ya no está abierta | `{"message": ..., "estado": "cerrada"}` |
| 422 | Parte que no está en `partes`, columnas o valores inválidos, llave repetida, fila anterior a `ventana_desde` (§10.1 y §12.3) o posterior a `ventana_hasta` (§10.4) | `{"message": ..., "errors": {"rows.12.codigo": [...]}}`, máximo 50 llaves |

Un 422 no cierra la corrida: el robot corrige o la marca fallida (§4.4). Ante un error de red o un 5xx, el robot reenvía el mismo lote tal cual (mismo cuerpo, firma nueva) hasta 3 veces con espera creciente.

### 4.3 Cerrar: `POST /api/robot/v1/corridas/{run_id}/cerrar`

```json
{
  "batches": 7,
  "filas": {"clientes": 6120, "direcciones": 9034, "contactos": 4410},
  "conteo_sap": {"clientes": 6120, "direcciones": 9034, "contactos": 4410}
}
```

- `batches` y `filas`: lo que el robot envió. Si la API no tiene todos los lotes del 1 al `batches` o las filas no cuadran, responde 409 con `{"faltan": [4, 5]}` y la corrida sigue abierta para que el robot los reenvíe.
- `conteo_sap`: **obligatorio en una corrida `completa` o `historico`** y prohibido en las de `solicitud`. Por cada parte, el `COUNT(*)` en SAP con los mismos filtros de la extracción, hecho en la misma conexión justo después de extraer. La API lo guarda y, solo en la `completa`, arma con él el conteo diario del plan §6. Por cada parte calcula cuatro números: `sap` (el `conteo_sap` que envió el robot), `recibidas` (todas las filas que llegaron en los lotes), `activas_recibidas` (las recibidas con `activo = true`; en una parte sin columna `activo`, como `direcciones`, `cartera`, `ventas`, `pedidos` o las de `PRODUCCION`, todas las recibidas cuentan como activas) y `activas_mysql` (las filas de la empresa en MySQL después de aplicar: las de `activo = true` en MAESTROS, todas las líneas en CARTERA, en VENTAS las de la ventana (§10.2) o, en una `historico`, las del rango (§10.4), todas las líneas en PEDIDOS (§11.3) y, en PRODUCCION, las de la ventana en las partes de movimiento y todas en los maestros (§12.3)). SAP envía también las filas inactivas, que quedan en MySQL con `activo = false`: por eso `activas_mysql` se compara con `activas_recibidas` y no con `recibidas`.
- `cuadra` es verdadero cuando `sap == recibidas` **y** `activas_mysql == activas_recibidas`. En CARTERA, VENTAS, PEDIDOS y PRODUCCION `activas_recibidas == recibidas`, así que la regla no cambia.
- Al cerrar, la API aplica en una transacción: inserta o actualiza por llave, pone `sincronizado_en` y, en las partes `todo`, inactiva lo que no llegó. En `CARTERA` reemplaza la cartera actual de la empresa y, en la corrida `completa`, guarda además la foto del día con `fecha_corte` (§6). En `VENTAS` reemplaza solo la ventana de la empresa (§10.2). En `PEDIDOS` reemplaza todos los pedidos de la empresa (§11.3). En `PRODUCCION` reemplaza la ventana en las partes de movimiento y todas las filas en los maestros (§12.3).
- Una parte `todo` con 0 filas no se aplica y la corrida falla (422): una lectura vacía de SAP nunca vacía una tabla.

Respuesta 200:

```json
{
  "run_id": 42,
  "estado": "cerrada",
  "aplicada_en": "2026-10-23T10:43:10-05:00",
  "conteo": {"clientes": {"sap": 6120, "recibidas": 6120, "activas_recibidas": 6098, "activas_mysql": 6098, "cuadra": true}}
}
```

`conteo` solo viene en una corrida `completa` o `historico`. En la `completa`, que no cuadre no hace fallar la corrida: queda registrado para el panel y cuenta contra los 14 días de estabilidad. En la `historico`, que `sap` no sea igual a `recibidas` sí la hace fallar sin aplicar nada (§10.4), y no entra en el conteo diario ni en la estabilidad.

### 4.4 Fallar: `POST /api/robot/v1/corridas/{run_id}/fallar`

`{"error": "VPN no conectó en 3 intentos"}` (hasta 1.000 caracteres, sin secretos ni datos de SAP). La corrida queda `fallida`, se descartan sus lotes y sus solicitudes pasan a `fallida` con ese mensaje. Respuesta 200 `{"run_id": 42, "estado": "fallida"}`.

### 4.5 Estados de una corrida

`abierta` → `cerrada` | `fallida` | `vencida`. Solo `abierta` recibe lotes, cierre o falla; lo demás responde 409.

## 5. MAESTROS

Cada fila en MySQL lleva además `empresa` (de la corrida) y `sincronizado_en` (lo pone la API). La llave única en MySQL es empresa + la llave de la tabla.

### 5.1 Qué trae cada parte

| Parte | Origen en SAP | Llave | Modo en una `solicitud` |
|---|---|---|---|
| `clientes` | `OCRD` con `CardType = 'C'` | `codigo` | `cambios` |
| `proveedores` | `OCRD` con `CardType = 'S'` | `codigo` | `cambios` |
| `direcciones` | `CRD1` de los socios enviados en la misma corrida | `codigo_socio`, `tipo`, `nombre` | igual que su socio |
| `contactos` | `OCPR` de los socios enviados en la misma corrida | `contacto_id` | igual que su socio |
| `articulos` | `OITM` | `codigo` | `cambios` |
| `grupos_articulos` | `OITB` | `codigo` | `todo` |
| `marcas` | `OMRC` | `codigo` | `todo` |
| `precios` | `ITM1` de la lista PÚBLICA (`OPLN`) | `articulo_codigo` | `todo` |
| `vendedores` | `OSLP` | `codigo` | `todo` |
| `grupos_clientes` | `OCRG` con `GroupType = 'C'` (canal) | `codigo` | `todo` |
| `condiciones_pago` | `OCTG` | `codigo` | `todo` |
| `municipios` | `@HBT_MUNICIPIO` | `codigo` | `todo` |

- **Cambios.** En modo `cambios` el robot trae las filas con `actualizado_en_sap >= desde`, donde `desde` lo da la API al tomar la solicitud (§7.3). Si `desde` es `null`, trae todo. Que se repita una fila ya enviada no hace daño: se actualiza por llave.
- **`actualizado_en_sap`** une `UpdateDate` y `UpdateTS` (entero `HHMMSS`) en una hora con zona `-05:00`. Si `UpdateTS` es nulo, se toma `00:00:00`; si `UpdateDate` es nulo, se usa `CreateDate`.
- **Direcciones y contactos.** Por cada socio enviado en la corrida llegan **todas** sus direcciones y contactos; los que tenía en MySQL y no llegaron quedan inactivos, aunque la parte vaya en modo `cambios`. No se envían direcciones ni contactos de un socio que no vino en la corrida.
- **`activo`.** Socios y artículos: `false` si `validFor = 'N'` o `frozenFor = 'Y'`. Contactos: `Active = 'Y'`. Vendedores: `Active = 'Y'`. Catálogos sin bandera: `true`.

### 5.2 Columnas

Obligatorias en **negrita**. Montos, texto decimal; banderas, booleano.

| Parte | Columnas (origen) |
|---|---|
| `clientes` y `proveedores` | **`codigo`** (`CardCode`), **`nombre`** (`CardName`), `nombre_extranjero` (`CardFName`), `nit` (`LicTradNum`), `grupo_codigo` (`GroupCode`), `vendedor_codigo` (`SlpCode`, `-1` si no tiene), `condicion_pago_codigo` (`GroupNum`), `lista_precios_codigo` (`ListNum`), `telefono` (`Phone1`), `telefono_2` (`Phone2`), `celular` (`Cellular`), `correo` (`E_Mail`), `ciudad` (`City`), `limite_credito` (`CreditLine`), `socio_vinculado` (`ConnBP`), **`activo`**, **`actualizado_en_sap`**, `creado_en_sap` (`CreateDate`), `contacto_principal` (`CntctPrsn`: el **nombre** del contacto principal, no su id; cuadra con `nombre` de `contactos`) |
| `direcciones` | **`codigo_socio`** (`CardCode`), **`tipo`** (`AdresType`: `B` facturación, `S` envío), **`nombre`** (`Address`), `calle` (`Street`), `barrio` (`Block`), `ciudad` (`City`), `municipio_codigo` (`County`), `departamento` (`State`), `pais` (`Country`), `codigo_postal` (`ZipCode`) |
| `contactos` | **`contacto_id`** (`CntctCode`), **`codigo_socio`** (`CardCode`), **`nombre`** (`Name`), `nombres` (`FirstName`), `apellidos` (`LastName`), `cargo` (`Position`), `telefono` (`Tel1`), `celular` (`Cellolar`), `correo` (`E_MailL`), **`activo`**, `telefono_2` (`Tel2`) |
| `articulos` | **`codigo`** (`ItemCode`), **`nombre`** (`ItemName`), `nombre_extranjero` (`FrgnName`), `grupo_codigo` (`ItmsGrpCod`), `marca_codigo` (`FirmCode`), `unidad_venta` (`SalUnitMsr`), `codigo_barras` (`CodeBars`), `inventariable` (`InvntItem`), `de_venta` (`SellItem`), `de_compra` (`PrchseItem`), **`activo`**, **`actualizado_en_sap`**, `creado_en_sap` (`CreateDate`) |
| `grupos_articulos` | **`codigo`** (`ItmsGrpCod`), **`nombre`** (`ItmsGrpNam`), **`activo`** |
| `marcas` | **`codigo`** (`FirmCode`), **`nombre`** (`FirmName`), **`activo`** |
| `precios` | **`articulo_codigo`** (`ItemCode`), **`lista_codigo`** (`PriceList`), **`lista_nombre`** (`OPLN.ListName`), `precio` (`Price`), `moneda` (`Currency`), **`activo`** |
| `vendedores` | **`codigo`** (`SlpCode`, mayor o igual a 0), **`nombre`** (`SlpName`), `correo` (`Email`), `celular` (`Mobil`), **`activo`** |
| `grupos_clientes` | **`codigo`** (`GroupCode`), **`nombre`** (`GroupName`), **`activo`** |
| `condiciones_pago` | **`codigo`** (`GroupNum`), **`nombre`** (`PymntGroup`), `dias_extra` (`ExtraDays`), `meses_extra` (`ExtraMonth`), **`activo`** |
| `municipios` | **`codigo`** (`Code`), **`nombre`** (`Name`), **`activo`** |

Por validar con datos reales (plan §4), antes de la primera carga: que `UpdateTS` exista en `OITM`; el nombre exacto de la lista PÚBLICA en `OPLN` de cada empresa; que `@HBT_MUNICIPIO` exista en Derivados y qué columnas trae además de `Code` y `Name`; que `CRD1.County` guarde el código de municipio, y que cambiar una dirección o un contacto mueva `UpdateDate` del socio. Si algo no cuadra, se propone el cambio de este documento al usuario (encabezado del documento).

## 6. CARTERA

Una sola parte, `cartera`, siempre en modo `todo`. Origen: la consulta `etl/queries/cartera.sql` del gestor de cartera, copiada tal cual. Las columnas son las de su `etl/esquema.py` (lote `cartera`), con los mismos nombres:

**`codigo_sn`**, `slp_code`, `email_asesor`, `nombre_sn`, `nit`, `grupo`, `municipio`, `cuenta_visible`, `tipo_doc`, **`documento`**, `documento_base`, `referencia_1`, `no_referencia`, `asesor`, `total_plazos`, `no_plazo`, `condicion_pago`, `fecha_contabilizacion`, **`fecha_vencimiento`**, `fecha_documento`, **`dias`**, `limite_credito`, `importe_original`, `base_gravable`, `saldo_base`, `saldo_vencido`, `valor_abonado`, `sin_vencer`, `valor_cheques`, `d_0_30`, `d_31_60`, `d_61_90`, `d_91_120`, `d_121_150`, `d_151_180`, `d_mas_180`, **`saldo`**, `rango`.

Tipos: `slp_code`, `total_plazos`, `no_plazo` y `dias`, enteros; las `fecha_*`, fechas; `limite_credito` a `saldo` y las edades `d_*`, montos; lo demás, texto.

- **Llave.** La consulta no trae un id único de línea, así que la cartera no tiene llave natural: la llave es la corrida. Cada cierre bueno reemplaza **toda** la cartera de esa empresa en una transacción. No se valida llave repetida.
- **Nunca vacía.** Un cierre con 0 filas falla (§4.3) y la cartera anterior se queda.
- **`fecha_corte` de la cartera actual.** `v_cartera` trae al final `fecha_corte`: el día contra el que la consulta cuenta los `dias`, que es la fecha en Bogotá de `extraida_en` (§4.1). Es hoy tanto en la `completa` como en una `solicitud`; **no** es la `fecha_corte` de la corrida, que en la `completa` es el día anterior y solo la lleva la foto. Así, en las dos vistas, `dias` = `fecha_corte` − `fecha_vencimiento`. Las líneas guardadas antes de esta columna la tienen `null` hasta el siguiente cierre.
- **Foto diaria.** En la corrida `completa` de las 02:00 la API guarda además una copia con `fecha_corte` (el día anterior). Hay una foto por empresa y día; si llega otra del mismo día, reemplaza a la anterior. Las fotos no se borran.
- Las demás corridas de cartera (por solicitud) solo reemplazan la cartera actual.

## 7. Solicitudes

### 7.1 Qué se puede pedir

| Conjunto | `parte` | Partes que trae la corrida |
|---|---|---|
| `CARTERA` | `null` | `cartera` |
| `VENTAS` | `null` | `ventas` |
| `PEDIDOS` | `null` | `pedidos` |
| `PRODUCCION` | `null` | `produccion_terminado`, `produccion_carga_planta`, `produccion_costos`, `produccion_despiece`, `produccion_rutas`, `produccion_costeo_teorico` |
| `MAESTROS` | `null` | Todas, cada una en su modo de §5.1 |
| `MAESTROS` | `clientes` | `clientes`, `direcciones`, `contactos` |
| `MAESTROS` | `proveedores` | `proveedores`, `direcciones`, `contactos` |
| `MAESTROS` | `articulos` | `articulos`, `grupos_articulos`, `marcas` |
| `MAESTROS` | `precios` | `precios` |
| `MAESTROS` | `vendedores` | `vendedores` |
| `MAESTROS` | `catalogos` | `grupos_clientes`, `condiciones_pago`, `municipios` |

Cada solicitud es de una empresa (`SGX` o `SDC`). `PRODUCCION` solo se pide para `SGX`: una solicitud de `SDC` da 422 (§12). Una solicitud de `MAESTROS` completo de `SDC` se atiende sin `precios` en la corrida (§4.1); una solicitud de solo `precios` sí los necesita en `partes`, y el robot la falla si la empresa no tiene lista.

### 7.2 Estados

| Estado | Significa |
|---|---|
| `pendiente` | Lista para que el robot la tome |
| `en_cola` | Espera su hora (`correr_desde`): por los 3 minutos, por una franja bloqueada o porque una igual está tomada |
| `tomada` | El robot la tomó y está trabajando (`tomada_en`) |
| `terminada` | Su corrida cerró bien (`terminada_en`) |
| `fallida` | Su corrida falló (`error`) |
| `vencida` | Lleva más de 30 minutos `tomada` sin terminar. Si su corrida cierra bien después, los datos se aplican igual, pero la solicitud se queda `vencida`: es la señal de que tardó demasiado (plan §6) |

Al llegar una solicitud, la API decide así. «Una igual» es de la misma empresa, conjunto y parte; «una hermana», de la misma empresa y conjunto, con cualquier parte (la espera es **por conjunto y empresa**):

1. Si hay una igual `pendiente` o `en_cola`, la nueva **se une** a esa: no se crea otra, se agrega quién pidió y se responde la existente.
2. Si hay una hermana `tomada`, la nueva queda `en_cola` y su hora se fija cuando esa termine: 3 minutos después si termina bien, de inmediato si falla o vence.
3. Si la última hermana `terminada` terminó hace menos de **3 minutos**, la nueva queda `en_cola` con `correr_desde` = esa hora + 3 minutos.
4. Si no, queda `pendiente` con `correr_desde` = ahora.
5. Franjas bloqueadas: si `correr_desde` cae a 15 minutos o menos (antes o después) de una hora de `BASES_SAP_FRANJAS_BLOQUEADAS` (`00:00,05:00,06:00,12:00,12:30` en Bogotá, mientras existan los otros robots), se corre al final de la franja: por ejemplo, 11:50 pasa a 12:45. La solicitud queda `en_cola` y la app muestra esa hora.

Una solicitud nunca se rechaza por estas reglas. `fallida` y `vencida` no se reintentan solas: quien la necesite vuelve a pedirla.

### 7.3 El robot toma solicitudes: `POST /api/robot/v1/solicitudes/tomar`

El robot pregunta cada minuto, sin VPN. Cuerpo: `{"max": 20}`. La API pasa a `tomada`, en una transacción, las solicitudes con `correr_desde` cumplido (las `en_cola` cuya hora ya pasó cuentan como `pendiente`), las más viejas primero, y las devuelve:

```json
{
  "solicitudes": [
    {"id": 118, "empresa": "SGX", "conjunto": "MAESTROS", "parte": "clientes",
     "desde": {"clientes": "2026-10-23T09:58:00-05:00"},
     "solicitada_en": "2026-10-23T10:40:12-05:00"}
  ]
}
```

- Si no hay, `{"solicitudes": []}` y el robot termina sin subir la VPN.
- `desde`: por cada parte en modo `cambios`, el mayor `actualizado_en_sap` que hay en MySQL para esa empresa (`null` si no hay filas: el robot trae todo).
- El robot agrupa las solicitudes tomadas por empresa y conjunto en una corrida (§4.1) y la empieza dentro de los 30 minutos siguientes; si no, vencen.
- La corrida `completa` de las 02:00 no necesita solicitudes. Si al iniciarla hay solicitudes tomadas de ese conjunto y empresa, el robot las incluye en `solicitudes`.

### 7.4 API para las apps

El botón del panel crea solicitudes por dentro (contratos de `Sap`), con las mismas reglas de §7.2 y sin llave. Las apps no usan HMAC: cada app tiene su llave, que se crea en el panel, se muestra una sola vez y se puede revocar. Va en `Authorization: Bearer <llave>`. Una llave revocada o desconocida recibe 401. Base: `https://<subdominio>/api/v1`.

- `POST /api/v1/solicitudes` con `{"empresa": "SGX", "conjunto": "MAESTROS", "parte": "clientes", "solicitado_por": {"correo": "ana@segurex.com", "nombre": "Ana Ruiz"}}`. Responde 201 si creó una solicitud o 200 si se unió a una existente, con la solicitud: `id`, `estado`, `correr_desde`, `empresa`, `conjunto`, `parte`. La app es la que pidió (por su llave); `solicitado_por` es la persona y queda registrado.
- `GET /api/v1/solicitudes/{id}`: la solicitud con `estado`, `correr_desde`, `tomada_en`, `terminada_en` y `error`. Una app solo ve las solicitudes a las que se unió.
- `GET /api/v1/estado?empresa=SGX&conjunto=CARTERA`: por cada parte, la última hora en que se aplicó una corrida (`actualizado_en`), para mostrar «Datos actualizados a las 10:42».

## 8. Quién hace qué

| Tema | Datos y API (sesión 2) | Robot (sesión 3) |
|---|---|---|
| Firma | Verifica (§3), guarda nonces | Firma cada petición |
| Corridas | Guarda lotes, aplica al cerrar, inactiva, compara el conteo | Extrae, arma lotes de hasta 1.000 filas, cierra o falla |
| Solicitudes | Recibe de las apps, une, encola, aplica franjas, vence | Pregunta cada minuto y las atiende |
| Horarios | Vence corridas y solicitudes (scheduler) | Nocturna a las 02:00, preguntas cada minuto, fotos de la carpeta |

## 9. Variables de entorno

| Dónde | Variable | Para qué |
|---|---|---|
| Servidor | `ROBOT_HMAC_KEYS` | Llaves del robot, `id:secreto` separadas por comas |
| Servidor | `BASES_SAP_FRANJAS_BLOQUEADAS` | Horas bloqueadas, por defecto `00:00,05:00,06:00,12:00,12:30` |
| Robot | `BASES_SAP_API_URL` | Base de la app, p. ej. `https://<subdominio>` |
| Robot | `BASES_SAP_ROBOT_KEY_ID`, `BASES_SAP_ROBOT_SECRET` | Su llave |
| Robot | `BASES_SAP_CSV_DIR` | Carpeta de CSV, fuera del repo |

## 10. VENTAS

Una sola parte, `ventas`, siempre en modo `todo`. Una fila por línea de factura de clientes (`OINV`/`INV1`, incluidas las notas débito) o de nota crédito de clientes (`ORIN`/`RIN1`). Origen: la consulta `etl/queries/ventas.sql` del gestor de cartera (main `9e2f877`), copiada tal cual, salvo `ganancia_bruta`, que no sale de esa consulta y el robot debe añadir (`GrssProfit` de `INV1` y `RIN1`). Las columnas son las de su `etl/esquema.py` (lote `ventas`) más `ganancia_bruta`, con los mismos nombres y en este orden:

**`tipo_objeto`**, **`doc_entry`**, **`numero_documento`**, **`linea`**, **`clase_documento`**, **`estado_documento`**, **`fecha_documento`**, **`fecha_contabilizacion`**, **`slp_code`**, `vendedor`, `canal`, **`codigo_cliente`**, `cliente`, `nit`, `ciudad`, `pedido`, `id_pedido_app`, `oc_cliente`, `ciudad_envio`, `direccion_envio`, `marca`, `familia`, `codigo_articulo`, `descripcion`, **`cantidad`**, `costo_unitario`, `costo_total`, `precio_lista`, `precio_unitario`, **`total`**, `iva`, `ganancia_bruta`, `moneda`, `trm`, `comentarios`.

| Tipo | Columnas |
|---|---|
| Entero | `tipo_objeto` (13 factura, 14 nota crédito), `doc_entry`, `numero_documento`, `linea`, `slp_code` (`-1` si no tiene) |
| Fecha | `fecha_documento` (`TaxDate`, solo referencia), `fecha_contabilizacion` (`DocDate`, la fecha de la factura y la que define el mes de la venta) |
| Cantidad o tasa, hasta 6 decimales | `cantidad`, `trm` |
| Monto | `costo_unitario`, `costo_total`, `precio_lista`, `precio_unitario`, `total`, `iva`, `ganancia_bruta` |
| Texto | Las demás. `clase_documento`: `factura`, `nota_debito` o `nota_credito`. `estado_documento`: `anulado`, `anulacion`, `cerrado` o `abierto` |

- **Signo.** Las notas crédito llegan con `cantidad`, `costo_total`, `total`, `iva` y `ganancia_bruta` negativos: la suma de `total` es la venta neta. Los precios y costos unitarios van sin signo.
- **`ganancia_bruta`** (`GrssProfit` de `INV1`/`RIN1`) es opcional en el encabezado del lote (§4.2): hasta que el robot la envíe, la API la guarda `null`. El margen es `SUM(ganancia_bruta) / SUM(total)`; `costo_total` no sirve para márgenes (plan §4).
- **Llave.** `tipo_objeto` + `doc_entry` + `linea`, única por empresa. No puede repetirse en la corrida (§4.2).
- **`id_pedido_app`** (`OINV.U_SGX_IdPedidoApp`) solo existe en `SGX`. Para `SDC` el robot cambia la expresión marcada `-- @id_pedido_app` por `CAST(NULL AS NVARCHAR(254))`, así que en Derivados siempre llega `null`. Las notas crédito también lo traen `null`.
- Las apps leen la vista `v_ventas`, en `ventas_sap`.

### 10.1 Ventana

- La consulta trae los documentos con `DocDate` (la columna `fecha_contabilizacion`) desde `ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))` hasta hoy: el mes en curso más los últimos 7 días del mes anterior. Por ejemplo, el 16/10 y el 01/10 la ventana empieza el 24/09. `CURRENT_DATE` es la fecha del servidor HANA.
- El robot calcula ese día con la misma expresión, en HANA y en la misma conexión de la extracción (`SELECT ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE)) FROM DUMMY`), nunca con el reloj del PC, y lo envía al iniciar como `ventana_desde` (§4.1). Lo pide antes y después de la consulta: si cambió porque la extracción cruzó la medianoche, repite la extracción una vez y, si vuelve a cambiar, falla.
- La ventana va siempre por `fecha_contabilizacion`, que es la que filtra la consulta. `fecha_documento` (`TaxDate`) puede caer antes o después de `DocDate`: si la app borrara por ella, en el borde de la ventana quedarían filas repetidas o se perderían.
- La API responde 422 si `ventana_desde` falta, no es una fecha, es posterior a mañana o anterior a hoy menos 40 días (la fórmula llega como máximo a 37), y en un lote si una fila trae `fecha_contabilizacion` anterior a `ventana_desde`. Así un error del robot nunca alcanza meses ya cerrados.

### 10.2 Cierre

- Al cerrar, en una transacción, la API borra las filas de `VENTAS` de esa empresa con `fecha_contabilizacion` desde `ventana_desde` y escribe las recibidas, con `sincronizado_en`. **Nada anterior a `ventana_desde` se toca nunca**: es el histórico congelado que usa Comisiones (plan §4).
- **Nunca vacía.** Un cierre con 0 filas falla (§4.3) y la ventana anterior se queda.
- No hay columna `activo`: dentro de la ventana, una línea que ya no está en SAP desaparece con el reemplazo; fuera de ella, nada cambia. Un documento de un mes anterior que se anule o corrija en SAP fuera de la ventana no se actualiza.
- No hay foto diaria ni `fecha_corte`: la corrida `completa` de las 02:00 y las de solicitud hacen lo mismo.
- **Conteo nocturno.** En la corrida `completa`, `conteo_sap.ventas` es el `COUNT(*)` de la misma consulta, en la misma conexión, justo después de extraer: las filas de la ventana. En la respuesta (§4.3), `activas_mysql` son las filas de la empresa en MySQL con `fecha_contabilizacion` desde `ventana_desde`, después de aplicar.

### 10.3 Carpeta

`VENTAS\<empresa>\aaaa-mm-dd_hhmm.csv` dentro de `BASES_SAP_CSV_DIR`, uno por corrida, con las columnas de este contrato. Se borran a los 90 días, como los de MAESTROS y CARTERA.

### 10.4 Corrida `historico`

Carga una vez, a mano, los meses anteriores a la ventana nocturna que `v_ventas` todavía no tiene. Las columnas, las reglas de notas crédito y anulaciones y la consulta son las de §10, cambiando solo el filtro de `DocDate` por el rango. La corrida `completa` y las de `solicitud` no cambian.

- **Rango.** `ventana_desde` es el día 1 de un mes, desde `2025-01-01`, el inicio acordado de la carga. `ventana_hasta` es un día de ese mismo mes, desde `ventana_desde` hasta su último día. Si no, 422.
- **Antes de la ventana nocturna.** `ventana_hasta` es anterior al día en que empieza hoy la ventana nocturna, con la fórmula de §10.1 calculada en el servidor con hoy en Bogotá. Si no, 422. Así la carga nunca se cruza con la de las 02:00: el mes en curso, o el anterior si la ventana ya entra en él, solo se carga hasta el día antes de la ventana.
  - El servidor calcula ese límite con hoy en Bogotá y el robot con `CURRENT_DATE` de HANA. En el borde de fin de mes pueden diferir en un día. Si el último tramo recibe 422 por `ventana_hasta`, se repite con el límite que trae el mensaje (el día anterior al inicio de la ventana que dice).
- **Solo un rango vacío.** Si la empresa ya tiene alguna fila de `VENTAS` con `fecha_contabilizacion` entre `ventana_desde` y `ventana_hasta`, la apertura responde 409 y no abre nada. Así nunca se toca el histórico congelado de Comisiones (§10.2), y repetir un mes ya cargado no hace daño.
- **Lotes.** Una fila con `fecha_contabilizacion` fuera del rango da 422.
- **Cierre.** En una transacción, la API inserta las filas recibidas, con `sincronizado_en`, sin borrar nada. El mes queda completo o vacío, nunca a medias. Mientras la corrida está abierta, ninguna otra corrida de `VENTAS` de la empresa puede abrir (§4.1), así que el rango sigue vacío hasta el cierre.
- **Nunca vacía.** Un cierre con 0 filas falla (§4.3) y el rango queda vacío.
- **Conteo.** `conteo_sap.ventas` es el `COUNT(*)` del rango, en la misma conexión, justo después de extraer. **Si no es igual a las filas recibidas, el cierre falla (422 en `conteo_sap.ventas`), la corrida queda `fallida` y no se aplica nada:** un mes cargado a medias no se podría volver a cargar. Si cuadra, la respuesta trae `conteo` con `cuadra`, como en la `completa`; `activas_mysql` son las filas de la empresa en el rango. No entra en el conteo diario ni en la estabilidad.

## 11. PEDIDOS

Una sola parte, `pedidos`, siempre en modo `todo`. Una fila por línea abierta de pedido de clientes (`ORDR`/`RDR1`) de cada empresa. Es una foto del estado abierto en el momento de la extracción, no un acumulado de un período. Se guarda en `ventas_sap` (conexión `ventas`, sin base nueva) y las apps leen la vista `v_pedidos`. Primera app que la lee: Panel Consolidado.

### 11.1 Filtro de SAP

Una línea entra si cumple todo:

- `ORDR."DocStatus" = 'O'`
- `ORDR."CANCELED" = 'N'`
- `RDR1."LineStatus" = 'O'`
- `RDR1."OpenCreQty" > 0`

Sin filtro por bodega, lista de precios ni dirección. Solo LEFT JOIN a `OCRD`, `OSLP`, `OCRG`, `OITM`, `OITB` y `OMRC`. Prohibido unir `CRD1`, `OITW`, `ITM1`, `OPLN` o `RDR12` (multiplican o pierden líneas).

`OpenCreQty` y `OpenQty` van en unidades de venta (las del precio). `OpenInvQty` va en unidades de inventario y nunca se usa para valorar: en el pedido 3859 de SDC daba 10.000 contra 400 (`NumInSale` 25).

### 11.2 Columnas

Cada fila en MySQL lleva además `empresa` y `sincronizado_en`. Obligatorias en **negrita**. En este orden:

| # | Columna | Tipo | Origen o regla |
|---|---|---|---|
| 1 | **`doc_entry`** | entero | `ORDR.DocEntry` |
| 2 | **`numero_pedido`** | entero | `ORDR.DocNum` |
| 3 | **`linea`** | entero | `RDR1.LineNum` |
| 4 | **`fecha_pedido`** | fecha | `ORDR.DocDate` |
| 5 | **`fecha_compromiso`** | fecha | `ORDR.DocDueDate` |
| 6 | `fecha_entrega_linea` | fecha | `RDR1.ShipDate` |
| 7 | **`dias`** | entero | `DAYS_BETWEEN(DocDate, CURRENT_DATE)` |
| 8 | **`rango`** | texto | Por `dias`: `Hasta 30 dias` (≤ 30), `De 31 a 60 dias`, `De 61 a 90 dias`, `Mas de 90 dias` (> 90). Textos ASCII exactos |
| 9 | **`dias_atraso`** | entero | `DAYS_BETWEEN(DocDueDate, CURRENT_DATE)`: negativo si aún no vence |
| 10 | **`slp_code`** | entero | `ORDR.SlpCode`, `-1` si no tiene |
| 11 | `vendedor` | texto | `OSLP.SlpName` |
| 12 | `canal` | texto | `OCRG.GroupName` del cliente (la «unidad de negocio» del panel) |
| 13 | **`codigo_cliente`** | texto | `ORDR.CardCode` |
| 14 | `cliente` | texto | `ORDR.CardName` |
| 15 | `nit` | texto | `OCRD.LicTradNum` |
| 16 | `ciudad` | texto | `OCRD.City` |
| 17 | `id_pedido_app` | texto | `ORDR.U_SGX_IdPedidoApp`, marca `-- @id_pedido_app`; en SDC el robot pone `CAST(NULL AS NVARCHAR(254))` |
| 18 | `oc_cliente` | texto | `ORDR.NumAtCard` |
| 19 | `direccion_envio` | texto | `ORDR.Address2` |
| 20 | `comentarios` | texto | `ORDR.Comments` |
| 21 | **`codigo_articulo`** | texto | `RDR1.ItemCode` |
| 22 | `descripcion` | texto | `RDR1.Dscription` |
| 23 | `linea_articulo` | texto | `OITB.ItmsGrpNam` (la «Línea» del panel) |
| 24 | `familia` | texto | `OITM.U_GSP_FAMILIA`, marca `-- @familia`; en SDC el robot pone `CAST(NULL AS NVARCHAR(100))` |
| 25 | `marca` | texto | `OMRC.FirmName` |
| 26 | `bodega` | texto | `RDR1.WhsCode` |
| 27 | `unidad` | texto | `RDR1.unitMsr` |
| 28 | **`cantidad_pedida`** | cantidad | `RDR1.Quantity` |
| 29 | **`cantidad_pendiente`** | cantidad | `RDR1.OpenCreQty` |
| 30 | `precio_lista` | monto | `RDR1.PriceBefDi`, en la moneda de la línea |
| 31 | `precio_unitario` | monto | `RDR1.Price`, en la moneda de la línea |
| 32 | `descuento_documento` | tasa | `ORDR.DiscPrcnt` |
| 33 | **`total_pendiente`** | monto | En pesos: `ROUND(LineTotal * OpenCreQty / Quantity * (1 - IFNULL(DiscPrcnt,0)/100), 2)`; 0 si `TaxOnly = 'Y'` o `Quantity = 0` |
| 34 | `ganancia_bruta_pendiente` | monto | En pesos: `ROUND(GrssProfit * OpenCreQty / Quantity, 2)`; 0 si `TaxOnly = 'Y'` o `Quantity = 0` |
| 35 | `moneda` | texto | `ORDR.DocCur` |
| 36 | `trm` | tasa | `ORDR.DocRate` |

Formatos del §4.2: montos con hasta 2 decimales; cantidades y tasas con hasta 6.

- **Margen.** `SUM(ganancia_bruta_pendiente) / SUM(total_pendiente)`, igual que VENTAS. No hay columnas de costo.
- **Llave.** `doc_entry` + `linea`, única por empresa. No puede repetirse en la corrida (§4.2).
- **Nombres.** En VENTAS la columna `familia` es `OITB.ItmsGrpNam`; en PEDIDOS ese dato es `linea_articulo` y `familia` es `U_GSP_FAMILIA`. VENTAS no se cambia (lo usa Comisiones); la guía de apps lo aclara.

### 11.3 Corridas y cierre

- `fecha_corte` y `ventana_desde` no aplican: si llegan, 422.
- Al cerrar, en una transacción, la API **reemplaza todas** las filas de PEDIDOS de esa empresa por las recibidas, con `sincronizado_en`. Lo que ya se facturó o se cerró desaparece con el reemplazo.
- **Nunca vacía.** Un cierre con 0 filas falla (§4.3) y los pedidos anteriores se quedan. Riesgo aceptado: si una empresa queda de verdad sin pedidos abiertos, la corrida falla y avisa.
- Sin columna `activo`, sin ventana y sin foto diaria. La corrida `completa` de las 02:00 y las de solicitud hacen lo mismo.
- **Conteo nocturno.** `conteo_sap.pedidos` es el `COUNT(*)` de la misma consulta, en la misma conexión, justo después de extraer. `activas_recibidas` = `recibidas`; `activas_mysql` = las filas de la empresa en MySQL después de aplicar.
- **Solicitudes (§7.1).** `PEDIDOS` | `null` | `pedidos`.
- Sin variables de entorno nuevas.

### 11.4 Carpeta

`PEDIDOS\<empresa>\aaaa-mm-dd_hhmm.csv` dentro de `BASES_SAP_CSV_DIR`, uno por corrida. Se borran a los 90 días.

### 11.5 Validación con SAP (antes de dar el conjunto por bueno)

- **Contra SAP, no contra archivos viejos.** El usuario saca el informe estándar de pedidos de cliente pendientes de SAP (líneas con cantidad abierta) a la misma hora de una corrida del robot y se comparan, por empresa, líneas, pedidos y valor pendiente. Los pedidos en otra moneda se revisan aparte.
- El `conteo_sap` nocturno solo prueba que no se pierden filas, no que la lógica esté bien.
- Los archivos `ia_Pendientes por facturar` que hoy lee el panel solo sirven para explicar las diferencias en la transición: bodegas distintas de PT, descuento, monedas y líneas repetidas.
- **Por validar con datos reales:** que `U_SGX_IdPedidoApp` exista en `ORDR` de SGX; que `U_GSP_FAMILIA` exista en `OITM` de SGX; que `LineTotal` y `GrssProfit` de `RDR1` vengan en pesos en un pedido en otra moneda; que `unitMsr` venga lleno en las dos empresas.

## 12. PRODUCCION

Los datos del tablero «Producción mes a mes» de Segurex: órdenes de producción de BEAS, costos y maestros de fabricación. Es **solo de `SGX`**: las tablas BEAS son de Segurex, así que la API responde 422 a una corrida o solicitud de `SDC`. Se guarda en `ventas_sap` (conexión `ventas`, sin base nueva ni variables de entorno nuevas). Cada parte tiene su tabla y su vista `v_<parte>`, con `empresa`, sus columnas y `sincronizado_en`. Primera app que las lee: Panel Consolidado.

Origen: las seis consultas del tablero (`automatizacion-hana\tablero-produccion-sgx\consultas\`), copiadas con los cambios de esta sección y nada más.

### 12.1 Partes

Seis partes, todas siempre en modo `todo`:

| Parte | Consulta de origen | Tipo | Cómo se carga (§12.3) |
|---|---|---|---|
| `produccion_terminado` | `PT_FAMILIA_SGX` | Movimiento | Ventana |
| `produccion_carga_planta` | `CARGA_PLANTA_SGX` | Movimiento | Ventana |
| `produccion_costos` | `COSTOS_PRODUCCION_SGX_MATERIAL` | Movimiento | Ventana |
| `produccion_despiece` | `DESPIECE_MAESTRO_SGX` | Maestro | Reemplazo total |
| `produccion_rutas` | `RUTAS_MAESTRAS_SGX` | Maestro | Reemplazo total |
| `produccion_costeo_teorico` | `COSTEO_TEORICO_SGX` | Maestro | Reemplazo total |

### 12.2 Columnas

Obligatorias en **negrita**. En este orden. Formatos del §4.2: montos con hasta 2 decimales; cantidades y tasas con hasta 6. Los textos vacíos (`''`) de las consultas originales llegan `null`.

**`produccion_terminado`.** Producto terminado que entra a bodega desde una OT (`OIGN`/`IGN1`). Filtro: `IGN1.U_beas_belnrid > 0` y grupo del artículo que empieza por `PRODUCTO TERMINADO`. **Cambio frente al original:** una fila por línea de la entrada, sin `GROUP BY`; la suma por día y artículo da lo mismo que la consulta original.

| Columna | Tipo | Origen |
|---|---|---|
| **`doc_entry`** | entero | `OIGN.DocEntry` |
| **`numero_documento`** | entero | `OIGN.DocNum` |
| **`linea`** | entero | `IGN1.LineNum` |
| **`fecha`** | fecha | `OIGN.DocDate` |
| **`grupo`** | texto | `OITB.ItmsGrpNam`, `Sin grupo` si viene vacío |
| **`familia`** | texto | `OITM.U_GSP_FAMILIA`, `Sin familia` si viene vacío |
| **`codigo_articulo`** | texto | `IGN1.ItemCode` |
| `articulo` | texto | `IGN1.Dscription` |
| `nro_ot` | entero | `IGN1.U_beas_belnrid` |
| `posicion` | entero | `IGN1.U_beas_belposid` |
| **`cantidad`** | cantidad | `IGN1.Quantity` |
| **`valor`** | monto | `ROUND(IGN1.LineTotal, 2)` |

Llave: `doc_entry` + `linea`, única por empresa. No puede repetirse en la corrida (§4.2).

**`produccion_carga_planta`.** Una fila por reporte de producción de BEAS (`BEAS_ARBZEIT`) con su puesto (`BEAS_APLATZ`) y su posición de OT (`BEAS_FTPOS`). Filtro: `BEAS_ARBZEIT.CANCEL = 0`.

| Columna | Tipo | Origen |
|---|---|---|
| **`fecha`** | fecha | `CAST(BEAS_ARBZEIT.DocDate AS DATE)` |
| **`area`** | texto | `BEAS_APLATZ.GRUPPE` |
| **`linea_producto`** | texto | La regla de dos pasos de la consulta original («Linea»), copiada tal cual |
| **`linea_negocio`** | texto | `OITB.ItmsGrpNam`, `Sin grupo` si viene vacío |
| **`etapa`** | texto | `BEAS_FTPOS.GRUPPE`, `Sin etapa` si viene vacío |
| `puesto_trabajo` | texto | `BEAS_APLATZ.BEZ` |
| **`nro_ot`** | entero | `BEAS_ARBZEIT.BELNR_ID` |
| **`posicion`** | entero | `BEAS_ARBZEIT.BELPOS_ID` |
| **`operacion`** | entero | `BEAS_ARBZEIT.POS_ID` |
| **`codigo_articulo`** | texto | `BEAS_FTPOS.ItemCode` |
| `nombre_articulo` | texto | `BEAS_FTPOS.ItemName` |
| `unidad` | texto | `BEAS_FTPOS.ME_VERBRAUCH` |
| **`unidades`** | cantidad | `BEAS_ARBZEIT.MENGE_GUT` |
| `unidades_no_conformes` | cantidad | `BEAS_ARBZEIT.MENGE_SCHLECHT` |
| `horas` | cantidad | `BEAS_ARBZEIT.ZEIT / 60` (`ZEIT` viene en minutos) |
| `almacen` | texto | `BEAS_FTPOS.WhsCode` |
| `estado_ot` | texto | `BEAS_FTPOS.ABGKZ` (`J`/`N`) |

- Sin llave: dos reportes iguales del mismo día son legítimos. No se valida llave repetida.
- No lleva la columna «Reporto» de la consulta original (`DisplayName`, el nombre de quien reportó): el tablero no la usa y es un dato de una persona.

**`produccion_costos`.** Una fila por hecho de costo, con los conceptos de la consulta original: tres de transformación desde `BEAS_ARBZEIT` (con `CANCEL = 0`) y el material desde `OIGE`/`IGE1` ligado a una OT. Se descartan las filas de costo cero.

| Columna | Tipo | Origen |
|---|---|---|
| **`fecha`** | fecha | `BEAS_ARBZEIT.DocDate` o `OIGE.DocDate` |
| **`concepto`** | texto | `Mano de obra directa`, `Costo variable`, `Costo fijo`, `Material comprado` o `Material intermedio`. Textos exactos: cualquier otro da 422 |
| **`area`** | texto | `BEAS_APLATZ.GRUPPE`; en el material, `Material comprado (sin area)` o `Material intermedio (sin area)` |
| **`linea_producto`** | texto | La misma regla de `produccion_carga_planta` |
| **`linea_negocio`** | texto | Como en `produccion_carga_planta` |
| **`etapa`** | texto | Como en `produccion_carga_planta` |
| `material_consumido` | texto | `IGE1.Dscription`; en transformación, `Transformacion (no es material)` |
| `grupo_material` | texto | `OITB.ItmsGrpNam` del material consumido; `null` en transformación |
| `codigo_material` | texto | `IGE1.ItemCode`; `null` en transformación |
| **`nro_ot`** | entero | `BEAS_ARBZEIT.BELNR_ID` o `IGE1.U_beas_belnrid` |
| **`posicion`** | entero | `BEAS_ARBZEIT.BELPOS_ID` o `IGE1.U_beas_belposid` |
| **`codigo_articulo`** | texto | El artículo que se fabrica (`BEAS_FTPOS.ItemCode`) |
| `nombre_articulo` | texto | `BEAS_FTPOS.ItemName` |
| `puesto_trabajo` | texto | `BEAS_APLATZ.BEZ`; `null` en material |
| **`costo`** | monto | `ROUND(…, 2)` del costo de la consulta original |

- Sin llave (la consulta saca tres filas por reporte). No se valida llave repetida.
- **Recirculación interna.** Las filas `Material intermedio` **sí se envían**: son el material que la propia planta fabricó y vuelve a entrar como insumo. El panel las excluye al sumar el costo; con ellas puede mostrar el material que fluyó por producción y cuadrar contra SAP.

**`produccion_despiece`.** Todas las líneas de `BEAS_STL`.

| Columna | Tipo | Origen |
|---|---|---|
| **`padre`** | texto | `BEAS_STL.ItemCode` |
| **`hijo`** | texto | `BEAS_STL.ART1_ID` |
| **`cantidad`** | cantidad | `BEAS_STL.MENGE_VERBRAUCH` |
| `merma` | cantidad | `BEAS_STL.AUSSCHUSS` |

Sin llave hasta confirmar con SAP que `padre` + `hijo` no se repite (§12.5).

**`produccion_rutas`.** Todas las operaciones de `BEAS_APL`, con su puesto en `BEAS_APLATZ`.

| Columna | Tipo | Origen |
|---|---|---|
| **`codigo_articulo`** | texto | `BEAS_APL.ItemCode` |
| **`operacion`** | entero | `BEAS_APL.POS_ID` |
| `area` | texto | `BEAS_APLATZ.GRUPPE` |
| `puesto` | texto | `BEAS_APLATZ.BEZ` |
| `tiempo` | cantidad | `BEAS_APL.TEAPLATZ`, el tiempo de la operación para `cantidad_base` |
| `cantidad_base` | cantidad | `BEAS_APL.MENGE_JE`. El tiempo unitario es `tiempo / cantidad_base` |
| `factor_merma` | cantidad | `BEAS_APL.AUSSCHUSSFAKTOR` |

Sin llave hasta confirmar con SAP que `codigo_articulo` + `operacion` no se repite (§12.5).

**`produccion_costeo_teorico`.** Costo estándar (SOLL) por artículo de producto terminado, sumado sobre todas las posiciones de OT (`BEAS_FTPOS`) con `MENGE > 0` y grupo `PRODUCTO TERMINADO SEGUREX` o `PRODUCTO TERMINADO INAFER`. Sin filtro de fecha: es propiedad del artículo.

| Columna | Tipo | Origen |
|---|---|---|
| **`codigo_articulo`** | texto | `BEAS_FTPOS.ItemCode` |
| `articulo` | texto | `MAX(ItemName)` |
| **`familia`** | texto | `U_GSP_FAMILIA`, `Sin familia` si viene vacío |
| **`posiciones`** | entero | `COUNT(*)` |
| **`cantidad`** | cantidad | `SUM(MENGE)` |
| `material_soll` | monto | `SUM(MATERIAL_GK_SOLL)` |
| `fabricacion_soll` | monto | `SUM(FERTIGUNG_GK_SOLL)` |
| `total_soll` | monto | `SUM(SELBSTKOSTEN_GK_SOLL)` |
| `total_ist` | monto | `SUM(SELBSTKOSTEN_GK_IST)` |

Llave: `codigo_articulo`, única por empresa. No puede repetirse en la corrida (§4.2). Los montos van con `ROUND(…, 2)`.

**Nombres.**

- En VENTAS y PEDIDOS `linea` es el número de línea del documento. Aquí también (`produccion_terminado`); por eso la «Linea» del tablero, la línea de producto, se llama `linea_producto`.
- `familia` es `U_GSP_FAMILIA`, como en PEDIDOS. La guía de apps lo aclara.
- La lista de líneas de producto de `linea_producto` está escrita en la consulta. Una línea nueva en la planta cae en `Componente comun` hasta que se cambie la consulta.

### 12.3 Corridas y cierre

- **Ventana de movimiento.** Las tres partes de movimiento traen las filas con `fecha` desde el mismo día que VENTAS: `ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE))` hasta hoy. Reemplaza el `BETWEEN` fijo de las consultas originales. El robot calcula ese día en HANA, en la misma conexión, antes y después de extraer, como en §10.1, y lo envía como `ventana_desde`.
- **Carga inicial.** Una vez, a mano, el robot corre `PRODUCCION` con `ventana_desde` = `2026-08-01`, para que el panel tenga desde el primer día los tres meses que usa hoy. Por eso en `PRODUCCION` la API acepta `ventana_desde` entre `2026-01-01` y mañana (no el límite de 40 días de VENTAS): aquí no hay histórico congelado que proteger, porque todo sale otra vez de SAP.
- `ventana_desde` es obligatoria; si falta, no es una fecha o queda fuera de ese rango, 422. `fecha_corte` no aplica: si llega, 422. En un lote de una parte de movimiento, una fila con `fecha` anterior a `ventana_desde` da 422.
- **Cierre**, en una transacción:
  - Partes de movimiento: borra las filas de esa parte y empresa con `fecha` desde `ventana_desde` y escribe las recibidas. Lo anterior a `ventana_desde` no se toca.
  - Maestros: reemplaza todas las filas de la parte y empresa.
  - Todas llevan `sincronizado_en`. Sin columna `activo` ni foto diaria.
- **Nunca vacía.** Una parte con 0 filas hace fallar la corrida (§4.3) y no cambia nada. Riesgo aceptado: si la planta para del todo durante toda la ventana (por ejemplo, vacaciones colectivas de fin de año), la corrida falla y avisa hasta que haya movimiento.
- **Corrida nocturna.** Va en la `completa` de las 02:00, solo para `SGX`, con las seis partes.
- **Conteo nocturno.** `conteo_sap.<parte>` es el `COUNT(*)` de la misma consulta, en la misma conexión, justo después de extraer. `activas_recibidas` = `recibidas`. `activas_mysql` son las filas de la parte y empresa en MySQL después de aplicar: en movimiento, las que tienen `fecha` desde `ventana_desde`; en maestros, todas.
- **Solicitudes (§7.1).** `PRODUCCION` | `null` | las seis partes. Solo de `SGX`.
- **Volumen esperado.** Por ventana, hasta unas 14 mil filas de costos, 2.500 de carga de planta y pocas centenas de producto terminado; 5 mil filas de maestros. La carga inicial, unas 50 mil filas en total.

### 12.4 Carpeta

`PRODUCCION\SGX\<parte>\aaaa-mm-dd_hhmm.csv` dentro de `BASES_SAP_CSV_DIR`, uno por parte y corrida. Se borran a los 90 días.

### 12.5 Validación con SAP (antes de dar el conjunto por bueno)

- Después de la carga inicial, el usuario corre las tres consultas originales de movimiento con `BETWEEN '2026-08-01' AND '2026-10-31'`, como hoy, y se comparan por mes:
  - `produccion_terminado`: suma de `cantidad` y `valor` (las filas no se comparan, porque aquí van sin agrupar).
  - `produccion_carga_planta`: filas, `unidades` y `horas`.
  - `produccion_costos`: filas y `costo` por `concepto`. Octubre sin `Material intermedio` debe dar el total del tablero, 1.525.367.102,33, con diferencias de centavos por el redondeo por fila.
- Maestros: filas contra las consultas originales del mismo día (al hacer el tablero eran 3.486, 1.264 y 153).
- El `conteo_sap` nocturno solo prueba que no se pierden filas, no que la lógica esté bien.
- **Por validar con datos reales:**
  - que `BELNR_ID`, `BELPOS_ID` y `POS_ID` sean enteros;
  - que `padre` + `hijo` en `BEAS_STL` y `codigo_articulo` + `operacion` en `BEAS_APL` no se repitan; si no se repiten, pasan a ser llave;
  - si una entrada de producto terminado (`OIGN`) anulada deja dos filas que se anulan entre sí o una sola: la consulta original no filtra `CANCELED`;
  - cuánto tarda la consulta de costos en la ventana y en la carga inicial, por las franjas bloqueadas de la noche.
