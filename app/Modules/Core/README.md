# Módulo Core

Lo que comparten todas las pantallas: el ingreso con Microsoft (Entra ID), los usuarios y sus roles, el registro de auditoría y el layout.

| Qué | Valor |
|---|---|
| Dueña | Sesión «cimientos» |
| Rutas web | `/` (raíz), nombres `core.*` |
| Rutas API | `/api/core/*`, nombres `core.api.*` |
| Migraciones | `2026_11_01_*`, en la conexión `app` |
| Puede usar | Ningún otro módulo |

Lo que otro módulo necesite de Core lo publica Core en `App\Modules\Core\Contracts`. Sap y Panel solo pueden usar ese espacio de nombres.

Las reglas completas están en `docs/arquitectura.md`.
