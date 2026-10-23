# Plan: Bases de datos SAP

Fuente de verdad del proyecto. Lo aprobó el usuario (TI, Segurex) el 23 de octubre de 2026, punto por punto. Si algo aquí choca con una orden o con otro documento, manda este archivo; si necesitas cambiarlo, pídeselo al usuario.

## 1. Qué es

Edward (CEO del Grupo RYR) pidió que los datos de SAP Business One se saquen una sola vez, se mantengan al día y queden en un solo lugar para todas las apps. Así un cliente o un producto nuevo en SAP aparece en todas las apps sin pasos a mano.

**Un solo robot para todo.** Con el tiempo reemplaza a todos los robots que hay hoy (el del gestor de cartera, CarteraWeb-ETL y CxPWeb-ETL), que dejan de existir.

«Bases de datos SAP» tiene dos partes:

1. **Datos en MySQL**, organizados en **conjuntos**. En la primera versión: MAESTROS (clientes, proveedores, artículos y catálogos) y CARTERA (facturas abiertas y saldos). Las apps los leen con un usuario de solo lectura.
2. **Respaldo en carpeta.** Otras tablas de SAP que hoy no usa ninguna app (auditoría, usuarios y permisos, contabilidad…). Se guardan en CSV en el PC de TI, ordenadas, y **no** se suben a MySQL.

Empresas:

| Código | Empresa | Esquema HANA |
|---|---|---|
| SGX | Segurex LATAM SAS | `SEGUREX` |
| SDC | Soluciones y Derivados de Colombia SAS | `HBT_SDERIVADOS` |

Las dos están en el mismo servidor HANA, cada una con su usuario de base de datos.

### Conjuntos

Cada conjunto tiene su carpeta en `C:\Users\Claude\Documents\CEREBRO\SAP\BASES_DE_DATOS` y, si va a MySQL, su propia base.

| Conjunto | Qué trae | Base MySQL | Cuándo entra |
|---|---|---|---|
| MAESTROS | Clientes, proveedores, artículos, lista de precios pública, vendedores y catálogos | `maestros_sap` | Primera versión |
| CARTERA | Facturas abiertas y saldos, y una foto por día | `cartera_sap` | Primera versión |
| VENTAS, RECAUDOS, CRUCES | Lo que usa Comisiones en el gestor de cartera | Se define al moverlos | Cuando el gestor de cartera pase al robot único |
| CUENTAS_POR_PAGAR | Lo que hoy trae CxPWeb-ETL | Se define al moverlo | Cuando esa app se mude a GoDaddy |
| EXISTENCIAS | Inventario disponible, para el gestor de clientes que incluirá Toma de pedidos | Se define al planearlo | Segunda versión |

## 2. Cómo funciona

```text
SAP HANA ──VPN──> Robot (PC de TI) ──HTTPS + HMAC──> App «Bases de datos SAP» (GoDaddy) ──> MySQL (una base por conjunto) ──solo lectura──> Apps
                       │
                       └──> Carpeta de CSV (respaldo de todo, en el PC de TI)
```

- **Robot** en Python, en el PC de TI. Usa la VPN Sophos solo mientras consulta SAP y la baja antes de enviar. La VPN manda todo el tráfico del PC por el túnel, así que cada actualización corta su internet normal unos segundos; más adelante conviene mover el robot a un equipo que llegue a SAP sin VPN.
- **App** Laravel en GoDaddy. Recibe los datos del robot por HTTPS con firma HMAC, guarda las solicitudes de actualización y muestra un panel.
- **El robot pregunta, la app no llama.** La app está en internet y no puede entrar a la red interna, así que el robot le pregunta cada minuto si hay trabajo.

### El botón «Actualizar datos»

Cada app tiene su propio botón, y el botón dice qué actualizar: en la pantalla de cartera del gestor de cartera, CARTERA; en Toma de pedidos, los clientes. El panel de Bases de datos SAP tiene además uno para TI.

1. Alguien toca el botón. La app llama a la API de Bases de datos SAP con su propia llave, nunca a SAP.
2. Bases de datos SAP guarda la solicitud: quién, desde qué app, qué actualizar (un conjunto completo, como CARTERA, o una parte de MAESTROS, como clientes) y de qué empresa.
3. Si ya hay una solicitud pendiente igual, la nueva se une a esa. Si la última igual terminó hace menos de 3 minutos, la nueva queda en cola y corre al cumplirse los 3 minutos. Nunca se rechaza.
4. El robot pregunta cada minuto, sin VPN, si hay solicitudes. Si no hay, se cierra.
5. Si hay, sube la VPN, trae de SAP solo eso y baja la VPN.
6. Guarda el CSV y envía los datos.
7. La app muestra «Datos actualizados a las 10:42». Por ejemplo, el asesor ve su cartera al día; el robot trae la de toda la empresa, pero cada asesor sigue viendo solo la suya.

Estados de una solicitud: pendiente, en cola, tomada, terminada, fallida, vencida (tomada y sin terminar en 30 minutos).

Cada app decide qué roles ven el botón. En Toma de pedidos: gerentes, administradores de ventas y TI. Queda registrado quién pidió.

No se usa MCP: las apps hablan con la API. Si más adelante un agente de IA necesita pedir actualizaciones o consultar datos, se le pone un MCP encima de la misma API.

### Horarios

- **Revisión de solicitudes:** cada minuto.
- **Corrida completa:** cada noche a las 02:00 (MAESTROS y CARTERA, con la foto diaria de cartera).
- **Fotos de la carpeta:** cada domingo a las 03:00.
- **Franjas bloqueadas:** mientras existan los otros robots, usan la VPN a las 00:00, 05:00, 06:00, 12:00 y 12:30. Si una solicitud cae a 15 minutos o menos de esas horas, espera, y la app dice a qué hora corre.

## 3. Alojamiento

- **Repo:** `GrupoRyR/bases-datos-sap`, privado. Código en `C:\Users\Claude\Documents\PROYECTOS_CLAUDE\PAGINAS_WEB\BASES_DATOS_SAP`.
- **Bases en GoDaddy**, porque cPanel da permisos por base y no por tabla:
  - `bases_sap`: la app (solicitudes, corridas, usuarios del panel, apps conectadas, auditoría).
  - Una base por conjunto que va a MySQL: `maestros_sap` y `cartera_sap`. Cada app recibe permiso solo en las que usa.
- **Un usuario MySQL de solo lectura por app y por agente**, para poder cortar uno sin tocar los demás. Cada app tiene además su propia llave para pedir actualizaciones.
- **MySQL remoto** abierto solo para las IP que autorice el usuario (para conectar un agente o una app fuera de GoDaddy), con conexión cifrada. Nunca abierto a cualquier IP.
- **Panel:** ingreso con la cuenta de Microsoft (Entra ID) y marca de Segurex, porque el panel es de TI.

## 4. Datos que van a MySQL (primera versión)

### MAESTROS (`maestros_sap`)

| Parte | Tablas de SAP | Cómo se actualiza |
|---|---|---|
| Clientes | `OCRD` (CardType C), `CRD1` direcciones, `OCPR` contactos | Solo los que cambiaron (`UpdateDate`, `UpdateTS`); de esos, se traen de nuevo direcciones y contactos |
| Proveedores | `OCRD` (CardType S), `CRD1`, `OCPR` | Igual que clientes |
| Artículos | `OITM`, `OITB` grupos, `OMRC` marcas | Solo los que cambiaron |
| Lista de precios pública | `OPLN`, `ITM1` | **Solo la lista PÚBLICA**; completa cada noche y con el botón |
| Vendedores | `OSLP` | Completa |
| Grupos de clientes (canal) | `OCRG` | Completa |
| Condiciones de pago | `OCTG` | Completa |
| Municipios | `@HBT_MUNICIPIO` | Completa |

- Cada fila lleva empresa (SGX o SDC), código de SAP, activo, `actualizado_en_sap` y `sincronizado_en`. Llave única: empresa + código.
- Lo que se borra o se inactiva en SAP queda marcado como inactivo. Nunca se borran filas, para no romper las apps.

### CARTERA (`cartera_sap`)

| Parte | Origen | Cómo se actualiza |
|---|---|---|
| Cartera actual | La consulta `etl/queries/cartera.sql` del gestor de cartera, copiada tal cual (ya incluye asesor, correo del asesor y valor antes de impuestos) | Completa cada vez, con el botón y cada noche; se reemplaza en una sola transacción y nunca queda vacía |
| Foto diaria | La misma consulta | Una por día, en la corrida de las 02:00, con fecha de corte del día anterior; no se borra. La usan la circularización (cierre de mes) y el historial |

### Para todos los conjuntos

- Las apps leen vistas estables (`v_clientes`, `v_articulos`, `v_cartera`…), no las tablas.
- Clientes, contactos y cartera tienen datos personales: aplica la Ley 1581 de 2012 (habeas data).
- **Validar con datos reales** antes de cargar: `UpdateTS` en `OITM`, el nombre exacto de la lista PÚBLICA en `OPLN` de cada empresa, si `@HBT_MUNICIPIO` existe en Derivados, y que la consulta de cartera funcione igual en el esquema de Derivados.

## 5. Tablas que solo van a la carpeta

Nunca se envían a la app ni a MySQL. Carpeta: `C:\Users\Claude\Documents\CEREBRO\SAP\BASES_DE_DATOS` (variable `BASES_SAP_CSV_DIR`). Su `LEEME.md` es el índice para el usuario.

| Carpeta | Qué guarda | Tablas de SAP | Cada cuánto |
|---|---|---|---|
| `_CATALOGO` | Todas las tablas de cada empresa con filas y tamaño, y los campos y tablas de usuario. Va primero: muestra todo lo que existe | `SYS.M_TABLES`, `CUFD`, `OUTB` | Cada domingo |
| `AUDITORIA` | Ingresos a SAP (entradas, fallidos, salidas), ingresos de soporte, historial de cambios de socios, artículos, usuarios, documentos y asientos, documentos en aprobación | `USR5`, `OSUL`, `ACRD`, `ACR1`, `AITM`, `AUSR`, `ADOC`, `ADO1`, `AJDT`, `AJD1`, `OWDD`, `WDD1` | Cada noche, sumando lo nuevo |
| `USUARIOS_Y_PERMISOS` | Usuarios sin contraseñas, permisos adicionales por usuario y por grupo, árbol de permisos | `OUSR` (columnas sin claves), `USR3`, `UGR1`, `OUPT`, `UPT1` | Cada domingo |
| `LICENCIAS` | Asignación de licencias. No está en la base: vive en un archivo del servidor de licencias. TI la exporta a mano desde «Administración de licencias» | — | Cada mes |
| `CONTABILIDAD` | Plan de cuentas, centros de costo, normas de reparto, proyectos, períodos, monedas, tasas de cambio, impuestos y retenciones | `OACT`, `OPRC`, `OOCR`, `OPRJ`, `OFPR`, `OCRN`, `ORTT`, `OSTC`, `OWHT` | Cada domingo; tasas de cambio cada noche |
| `BANCOS` | Bancos, cuentas bancarias propias y formas de pago. Las cuentas bancarias de clientes y proveedores (`OCRB`) quedan fuera: ninguna app las usa y un archivo con ellas sería blanco de fraude | `ODSC`, `DSC1`, `OPYM` | Cada domingo |
| `INVENTARIO` | Bodegas, unidades de medida, listas de materiales y precios especiales | `OWHS`, `OUOM`, `OUGP`, `OITT`, `ITT1`, `OSPP`, `SPP1` | Cada domingo |
| `ORGANIZACION` | Empresa, sucursales, departamentos, cargos, territorios, sectores y empleados (solo nombre, cargo, área y correo) | `OADM`, `OBPL`, `OUDP`, `OHPS`, `OTER`, `OIND`, `OHEM` | Cada domingo |
| `VENTAS_Y_CRM` | Actividades, oportunidades, formas de envío, países y departamentos | `OCLG`, `OOPR`, `OPR1`, `OSHP`, `OCRY`, `OCST` | Cada domingo |
| `CONFIGURACION` | Series, campos y tablas de usuario, objetos de usuario, consultas guardadas del Query Manager, alertas y tablas del add-on HBT | `NNM1`, `CUFD`, `UFD1`, `OUTB`, `OUDO`, `OUQR`, `OQCN`, `OALT`, `@HBT_*` | Cada domingo |

Estructura: `<CARPETA>\<SGX o SDC>\<tabla>\<archivo>.csv` (`LICENCIAS` no lleva empresa).

- **Fotos** (cada domingo): `aaaa-mm-dd.csv`, estado completo de ese día. Se guardan 52 semanas.
- **Registros** (cada noche): `aaaa-mm.csv`, un archivo por mes al que se suman las filas nuevas. No se borran.
- **MAESTROS y CARTERA:** `aaaa-mm-dd_hhmm.csv`, uno por corrida, se borran a los 90 días. La foto diaria de cartera va en `CARTERA\<empresa>\historico\aaaa-mm-dd.csv` y no se borra.

Reglas:

- Los nombres de tabla salen de la documentación de SAP Business One y se confirman con el catálogo antes de la primera extracción. Si el historial de documentos y asientos (`ADOC`, `ADO1`, `AJDT`, `AJD1`) resulta muy grande, se le avisa al usuario con las cifras antes de extraerlo.
- Los permisos estándar de SAP vienen codificados en un solo campo de `OUSR` y no se pueden leer por SQL; los adicionales y por grupo sí.
- Nunca se extraen contraseñas de `OUSR`, cédula, salario o cuentas bancarias de `OHEM`, ni la tabla `OCRB`. Las columnas se listan una por una; nunca `SELECT *`.
- La carpeta no se comparte ni se sincroniza con OneDrive: tiene datos personales y registros de acceso.

## 6. Cuándo se considera estable

Bases de datos SAP es estable cuando cumple esto **14 días seguidos** en producción:

1. Todas las corridas nocturnas terminan bien.
2. Toda solicitud de un botón, fuera de las franjas bloqueadas, termina en menos de 10 minutos.
3. Cada noche, las filas de cada conjunto en MySQL coinciden con las de SAP. El robot envía el conteo de SAP al cerrar la corrida completa y la app lo compara.
4. Nadie tuvo que corregir datos a mano.

El panel muestra el contador («Estable: 9 de 14 días»). Al llegar a 14, el gestor de cartera empieza a tomar maestros y cartera de aquí.

## 7. Qué cambia en las otras apps

- **Gestor de cartera:** sale a producción ya, con su robot actual, de forma temporal. Cuando Bases de datos SAP sea estable, toma maestros y cartera de aquí en vez de recibirlos de su robot. Después pasan al robot único VENTAS, RECAUDOS y CRUCES (sus consultas, ya probadas, se copian tal cual) y la carpeta `etl/` del gestor desaparece.
- **CarteraWeb-ETL** (el robot del visualizador viejo): se apaga cuando el gestor de cartera reemplace al visualizador.
- **CxPWeb-ETL:** se apaga cuando cuentas por pagar se mude a GoDaddy y su conjunto CUENTAS_POR_PAGAR entre al robot único.
- **Segunda versión:** EXISTENCIAS, para el gestor de clientes que incluirá Toma de pedidos. La frecuencia se define al planearla.

## 8. Seguridad

- Firma HMAC-SHA256 con marca de tiempo y nonce en todo lo que envía el robot; se rechazan repeticiones y relojes con más de 5 minutos de diferencia.
- Llaves por app, revocables desde el panel; se muestran una sola vez.
- Ningún secreto en el repo. Las credenciales viven solo en los `.env`, que llena el usuario.
- Las claves de HANA no se rotan (decisión del usuario del 23 de octubre de 2026).
- El agente «Ciberseguridad» revisa esta app antes de que salga a producción.

## 9. Sesiones y zonas

Máximo cuatro sesiones a la vez en el PC. Todas con Opus 5.5, esfuerzo alto. Las órdenes completas están en el plan publicado para el usuario.

| # | Sesión | Cuándo | Zona |
|---|---|---|---|
| 1 | Bases SAP: cimientos | Primero, sola | Esqueleto, CI, protecciones, `CLAUDE.md`, `docs/arquitectura.md`, `docs/contrato-robot.md`, módulo Core, migraciones `2026_11_01_` |
| 2 | Bases SAP: datos y API | Después de cimientos, junto con el robot | `app/Modules/Sap/**`, `tests/Modules/Sap/**`, migraciones `2026_11_02_` |
| 3 | Bases SAP: robot | Después de cimientos, junto con la API | `robot/**` y sus pruebas |
| 4 | Prueba con SAP real | La corre el usuario: `--catalogo` y `--diagnostico` | — |
| 5 | Bases SAP: panel | Después de la API de solicitudes | `app/Modules/Panel/**`, `tests/Modules/Panel/**`, migraciones `2026_11_03_` |
| 6 | Bases SAP: despliegue | Cuando TI entregue lo suyo | Lo que asigne el usuario |
| 7 | Gestor de cartera toma maestros y cartera de aquí | Cuando sea estable (sección 6) | Repo gestor-cartera |

El conteo nocturno de la sección 6 lo implementan la API (sesión 2: guarda y compara) y el robot (sesión 3: envía el conteo de SAP); el panel (sesión 5) lo muestra.

El robot copia la consulta de cartera del repo del gestor de cartera (`C:\Users\Claude\Documents\PROYECTOS_CLAUDE\PAGINAS_WEB\GESTOR_CARTERA\etl\queries\cartera.sql`) solo leyéndola; nunca cambia ese repo.

## 10. Pendiente de TI

- Confirmar que el plan de GoDaddy deja crear tres bases más (`bases_sap`, `maestros_sap`, `cartera_sap`), varios usuarios MySQL y MySQL remoto por IP.
- Las IP fijas desde las que se conectarían agentes o apps fuera de GoDaddy.
- Un subdominio con SSL.
- Registrar la app en Entra ID, o decidir si usa el registro del gestor de cartera.
- El buzón desde el que el robot avisa cuando falla y a quién le llega.
- Exportar cada mes la asignación de licencias a `LICENCIAS`.
- El cron de `schedule:run` cada minuto.
