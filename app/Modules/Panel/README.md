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
| Solicitudes (pendiente) | `GET /panel/solicitudes` | `panel.solicitudes` | `core.consultar` |
| Actualizar datos (pendiente) | `GET`, `POST /panel/actualizar` | `panel.actualizar` | `core.administrar` |
| Consulta (pendiente) | `GET /panel/consulta` | `panel.consulta` | `core.consultar` |
| Apps conectadas (pendiente) | `/panel/apps` | `panel.apps` | `core.administrar` |

Las etiquetas de empresas, conjuntos, partes y corridas salen de `resources/lang/es/etiquetas.php` por `Support\Labels`; un valor sin etiqueta se muestra tal cual, así un conjunto nuevo (VENTAS) aparece sin tocar el panel. `Support\Formats` da los números con puntos de miles y las horas de Bogotá.

Las reglas completas están en `docs/arquitectura.md`.
