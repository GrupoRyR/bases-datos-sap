# Contrato del robot

Versión 1. Lo implementan dos sesiones en paralelo: «Datos y API» (el servidor, `app/Modules/Sap`) y «Robot» (el cliente, `robot/`). Después de fusionarlo **no se cambia sin avisar al usuario**: cualquier cambio se propone, el usuario lo aprueba y las dos sesiones lo aplican en el mismo PR o en PR encadenados. Manda `docs/plan-bases-sap.md`; si este documento choca con el plan, se corrige este.

## 1. Términos

| Término | Qué es | Valores |
|---|---|---|
| Empresa | Empresa de SAP | `SGX` (esquema `SEGUREX`), `SDC` (esquema `HBT_SDERIVADOS`) |
| Conjunto | Grupo de datos con su propia base MySQL | `MAESTROS` (`maestros_sap`), `CARTERA` (`cartera_sap`) |
| Parte | Tabla lógica dentro de un conjunto (§5 y §6) | `clientes`, `proveedores`, `direcciones`, `contactos`, `articulos`, `grupos_articulos`, `marcas`, `precios`, `vendedores`, `grupos_clientes`, `condiciones_pago`, `municipios`, `cartera` |
| Corrida | Un envío completo del robot: iniciar, lotes y cerrar (§4) | Tipo `completa` o `solicitud` |
| Lote | Hasta 1.000 filas de una sola parte | Numerados desde 1 en cada corrida |
| Solicitud | Pedido de actualización de una app o del panel (§7) | Estados en §7.2 |

Solo existen los conjuntos y partes de esta tabla. Las tablas que van solo a la carpeta (plan §5) **nunca** se envían: la API responde 422 a cualquier conjunto o parte desconocidos.

Nombres: las rutas y los valores de negocio van en español, como el plan; las llaves del sobre JSON (`run_id`, `rows`…) van en inglés, como el código; las columnas de datos van en español y en `snake_case`, como las columnas de MySQL del plan §4 y como el gestor de cartera, para que el gestor pueda leer de aquí sin traducir nombres.

## 2. Transporte

- Base: `https://<subdominio>/api/robot/v1`. Solo HTTPS. Todas las rutas del robot son `POST`, sin query string.
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

- `tipo`: `completa` (la nocturna de las 02:00) o `solicitud` (atiende solicitudes).
- `partes`: cada parte que traerá la corrida y su modo:
  - `todo`: llegan todas las filas que hay en SAP. Al cerrar, las filas de esa parte y empresa que no llegaron quedan inactivas (`activo = false`). Nunca se borran.
  - `cambios`: llegan solo las filas que cambiaron (§5.1). Al cerrar, no se inactiva nada por ausencia.
- En una corrida `completa` todas las partes del conjunto van, y van en modo `todo`.
- `solicitudes`: ids de las solicitudes que atiende (§7). Vacío en una corrida `completa` sin solicitudes. Cada id debe estar `tomada`, ser de la misma empresa y conjunto, y pedir partes incluidas en `partes`; si no, 422.
- `fecha_corte`: solo en `CARTERA`. En la `completa` nocturna, el día anterior; en una `solicitud`, hoy.
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
- `columns`: exactamente las columnas de la parte (§5 o §6), en cualquier orden y sin repetir. Cada fila de `rows` es una lista con un valor por columna, en ese orden.
- Valores: enteros como número JSON; montos como texto decimal con punto, hasta 2 decimales y sin separador de miles (`"1234567.89"`); booleanos como `true`/`false`; fechas `"AAAA-MM-DD"`; horas ISO 8601 con zona; texto hasta 4.000 caracteres, recortado; `null` si falta. Las columnas obligatorias no pueden llegar nulas ni vacías.
- Una llave (§5 y §6) no puede repetirse en la corrida, ni dentro del lote ni entre lotes.

Respuestas:

| Estado | Cuándo | Cuerpo |
|---|---|---|
| 201 | Lote nuevo aceptado | `{"batch": 3, "rows": 1000}` |
| 200 | Mismo `batch` reenviado con el mismo cuerpo (mismo SHA-256) | `{"batch": 3, "rows": 1000, "duplicate": true}` |
| 409 | Mismo `batch` con otro cuerpo, o corrida que ya no está abierta | `{"message": ..., "estado": "cerrada"}` |
| 422 | Parte que no está en `partes`, columnas o valores inválidos, llave repetida | `{"message": ..., "errors": {"rows.12.codigo": [...]}}`, máximo 50 llaves |

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
- `conteo_sap`: **obligatorio en una corrida `completa`** y prohibido en las demás. Por cada parte, el `COUNT(*)` en SAP con los mismos filtros de la extracción, hecho en la misma conexión justo después de extraer. La API lo guarda y lo compara con las filas recibidas y con las filas activas en MySQL después de aplicar; con eso arma el conteo diario del plan §6.
- Al cerrar, la API aplica en una transacción: inserta o actualiza por llave, pone `sincronizado_en` y, en las partes `todo`, inactiva lo que no llegó. En `CARTERA` reemplaza la cartera actual de la empresa y, en la corrida `completa`, guarda además la foto del día con `fecha_corte` (§6).
- Una parte `todo` con 0 filas no se aplica y la corrida falla (422): una lectura vacía de SAP nunca vacía una tabla.

Respuesta 200:

```json
{
  "run_id": 42,
  "estado": "cerrada",
  "aplicada_en": "2026-10-23T10:43:10-05:00",
  "conteo": {"clientes": {"sap": 6120, "recibidas": 6120, "activas_mysql": 6120, "cuadra": true}}
}
```

`conteo` solo viene en una corrida `completa`. Que no cuadre no hace fallar la corrida: queda registrado para el panel y cuenta contra los 14 días de estabilidad.

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
| `clientes` y `proveedores` | **`codigo`** (`CardCode`), **`nombre`** (`CardName`), `nombre_extranjero` (`CardFName`), `nit` (`LicTradNum`), `grupo_codigo` (`GroupCode`), `vendedor_codigo` (`SlpCode`, `-1` si no tiene), `condicion_pago_codigo` (`GroupNum`), `lista_precios_codigo` (`ListNum`), `telefono` (`Phone1`), `telefono_2` (`Phone2`), `celular` (`Cellular`), `correo` (`E_Mail`), `ciudad` (`City`), `limite_credito` (`CreditLine`), `socio_vinculado` (`ConnBP`), **`activo`**, **`actualizado_en_sap`**, `creado_en_sap` (`CreateDate`) |
| `direcciones` | **`codigo_socio`** (`CardCode`), **`tipo`** (`AdresType`: `B` facturación, `S` envío), **`nombre`** (`Address`), `calle` (`Street`), `barrio` (`Block`), `ciudad` (`City`), `municipio_codigo` (`County`), `departamento` (`State`), `pais` (`Country`), `codigo_postal` (`ZipCode`) |
| `contactos` | **`contacto_id`** (`CntctCode`), **`codigo_socio`** (`CardCode`), **`nombre`** (`Name`), `nombres` (`FirstName`), `apellidos` (`LastName`), `cargo` (`Position`), `telefono` (`Tel1`), `celular` (`Cellolar`), `correo` (`E_MailL`), **`activo`** |
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
- **Foto diaria.** En la corrida `completa` de las 02:00 la API guarda además una copia con `fecha_corte` (el día anterior). Hay una foto por empresa y día; si llega otra del mismo día, reemplaza a la anterior. Las fotos no se borran.
- Las demás corridas de cartera (por solicitud) solo reemplazan la cartera actual.

## 7. Solicitudes

### 7.1 Qué se puede pedir

| Conjunto | `parte` | Partes que trae la corrida |
|---|---|---|
| `CARTERA` | `null` | `cartera` |
| `MAESTROS` | `null` | Todas, cada una en su modo de §5.1 |
| `MAESTROS` | `clientes` | `clientes`, `direcciones`, `contactos` |
| `MAESTROS` | `proveedores` | `proveedores`, `direcciones`, `contactos` |
| `MAESTROS` | `articulos` | `articulos`, `grupos_articulos`, `marcas` |
| `MAESTROS` | `precios` | `precios` |
| `MAESTROS` | `vendedores` | `vendedores` |
| `MAESTROS` | `catalogos` | `grupos_clientes`, `condiciones_pago`, `municipios` |

Cada solicitud es de una empresa (`SGX` o `SDC`).

### 7.2 Estados

| Estado | Significa |
|---|---|
| `pendiente` | Lista para que el robot la tome |
| `en_cola` | Espera su hora (`correr_desde`): por los 3 minutos, por una franja bloqueada o porque una igual está tomada |
| `tomada` | El robot la tomó y está trabajando (`tomada_en`) |
| `terminada` | Su corrida cerró bien (`terminada_en`) |
| `fallida` | Su corrida falló (`error`) |
| `vencida` | Lleva más de 30 minutos `tomada` sin terminar |

Al llegar una solicitud, la API decide, para la misma empresa, conjunto y parte («una igual»):

1. Si hay una igual `pendiente` o `en_cola`, la nueva **se une** a esa: no se crea otra, se agrega quién pidió y se responde la existente.
2. Si hay una igual `tomada`, la nueva queda `en_cola` y su hora se fija cuando esa termine: 3 minutos después si termina bien, de inmediato si falla o vence.
3. Si la última igual `terminada` terminó hace menos de **3 minutos**, la nueva queda `en_cola` con `correr_desde` = esa hora + 3 minutos.
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
