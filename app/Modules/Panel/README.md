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

Las reglas completas están en `docs/arquitectura.md`.
