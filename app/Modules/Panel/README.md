# Módulo Panel

El panel de TI: estado de las corridas y las solicitudes, el botón «Actualizar datos» de TI, las llaves de las apps conectadas y el contador de días estables.

| Qué | Valor |
|---|---|
| Dueña | Sesión «Panel» |
| Rutas web | `/panel/*`, nombres `panel.*` |
| Rutas API | `/api/panel/*`, nombres `panel.api.*` |
| Migraciones | `2026_11_03_*`, en la conexión `app` |
| Puede usar | Contratos de Core y de Sap |

Panel lee los datos de Sap solo por `App\Modules\Sap\Contracts`, nunca por sus modelos o tablas.

## Pantallas

Todas piden sesión y un rol (`core.consultar`); las que cambian datos piden además `core.administrar`. El menú las registra todas en `PanelServiceProvider` y muestra cada una apenas existe su ruta.

| Pantalla | Ruta | Nombre | Permiso |
|---|---|---|---|
| Estado | `GET /panel` | `panel.estado` | `core.consultar` |
| Solicitudes | `GET /panel/solicitudes` | `panel.solicitudes` | `core.consultar` |
| Actualizar datos | `GET`, `POST /panel/actualizar` | `panel.actualizar`, `panel.actualizar.store` | `core.administrar` |
| Consulta | `GET`, `POST /panel/consulta` | `panel.consulta`, `panel.consulta.buscar` | `core.consultar` |
| Apps conectadas | `GET`, `POST /panel/apps`; `POST /panel/apps/{app}/llave` y `/revocar` | `panel.apps`, `panel.apps.store`, `panel.apps.rotate`, `panel.apps.revoke` | `core.administrar` |

**Solicitudes** muestra el historial de `RequestHistory`, 25 por página y la más reciente primero, con los filtros opcionales `empresa` y `conjunto` (un valor desconocido se ignora).

**Actualizar datos** pide con `UpdateRequests`, con las mismas reglas que las apps: se une a una igual o queda en cola, nunca se rechaza. Lo audita como `panel.request.placed` solo con los códigos de lo pedido. Sus opciones salen de `Support\UpdateOptions`: cada conjunto completo más las partes de `RequestScope::forDataset`, con valor `MAESTROS` o `MAESTROS:clientes`.

**Consulta** busca clientes, proveedores o artículos con `MasterLookup` (las partes buscables están en `Support\LookupPage::PARTS`), en una empresa o en las dos, hasta `MasterLookup::MAX_RESULTS` filas. El término puede ser un NIT o un nombre (Ley 1581): va solo en el cuerpo del `POST`, los resultados y los errores se pintan desde ese mismo `POST` (sin redirección y sin guardar nada en la sesión), toda respuesta lleva `Cache-Control: no-store` y el término no se audita ni va al log. El `GET` ignora su query string, así que ninguna búsqueda sale de una URL.

**Apps conectadas** crea, rota y revoca las llaves de las apps con `ClientAppKeys` (`docs/contrato-robot.md`, §7.4). La lista muestra solo el prefijo de cada llave. Una llave nueva o rotada se muestra una sola vez, en la respuesta del mismo `POST` con `Cache-Control: no-store`; nunca pasa por la sesión, la auditoría ni el log. Rotar mata la llave anterior al instante y reactiva una app revocada; revocar pide confirmación en un `<details>`. Se audita como `panel.app.created`, `panel.app.key_rotated` y `panel.app.revoked`, con el nombre y el prefijo de la llave.

Las etiquetas de empresas, conjuntos, partes, partes de solicitud, estados de solicitud y corridas salen de `resources/lang/es/etiquetas.php` por `Support\Labels`; un valor sin etiqueta se muestra tal cual, así un conjunto nuevo (VENTAS) aparece sin tocar el panel. `Support\Formats` da los números con puntos de miles y las horas de Bogotá.

Las reglas completas están en `docs/arquitectura.md`.
