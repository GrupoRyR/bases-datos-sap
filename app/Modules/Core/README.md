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

## Auditoría

`App\Modules\Core\Contracts\AuditLogger` guarda cada acción que hay que poder rastrear en `audit_logs` (conexión `app`). Pídelo por inyección y llama:

```php
$audit->record('sap.request.created', 'request', $request->id, ['dataset' => 'maestros']);
```

- La acción es `<clave-del-módulo>.<entidad>.<verbo>` en minúsculas, p. ej. `core.user.role_changed`. Otro formato lanza `InvalidArgumentException`.
- Core agrega solo el usuario que ingresó (ninguno para el robot, la consola o el programador), la IP de la petición y la hora.
- Nunca pongas secretos, tokens ni contraseñas en el contexto. Como red de seguridad, las llaves que parecen secretos (`password`, `secret`, `token`) se guardan como `[redacted]`.
- Las filas no se cambian ni se borran.
