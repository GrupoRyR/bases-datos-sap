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

## Ingreso con Microsoft

| Ruta | Nombre | Quién |
|---|---|---|
| `GET /login` | `core.login` | Invitados: botón «Entrar con Microsoft». |
| `GET /auth/microsoft` | `core.auth.redirect` | Invitados: lleva a Microsoft. |
| `GET /auth/microsoft/callback` | `core.auth.callback` | Invitados: vuelve de Microsoft. Debe coincidir con `MICROSOFT_REDIRECT_URI`. |
| `GET /` | `core.inicio` | Usuarios con rol. Sin rol, van a `/sin-acceso`. |
| `GET /sin-acceso` | `core.sin-acceso` | Usuarios sin rol: les dice que pidan acceso a TI. |
| `POST /logout` | `core.logout` | Usuarios. |

- El driver `microsoft` de Socialite se registra en `CoreServiceProvider` y **no se construye sin `MICROSOFT_TENANT_ID`**: sin inquilino aceptaría cuentas de cualquier directorio (`common`). La app arranca igual; solo falla el ingreso.
- `Application\Auth\SignInWithMicrosoft` revisa el inquilino (`tid`), busca al usuario por `microsoft_id` y luego por correo, rechaza cuentas cruzadas e inactivos, crea a los nuevos sin rol y da `admin_ti` a los correos de `CORE_ADMIN_EMAILS`. Todo rechazo muestra el mismo mensaje; el motivo queda en la auditoría (`core.auth.rejected`).
- Auditoría: `core.user.created`, `core.user.role_changed`, `core.auth.rejected`, `core.auth.signed_in` y `core.auth.signed_out`.
- Las pruebas nunca llaman a Microsoft: usan `Tests\Modules\Core\Support\FakeIdentityProvider::install($this->app)`.

### Ingreso de prueba (solo en local)

Para recorrer el panel en tu equipo sin Microsoft:

1. `php artisan migrate --seed` con `APP_ENV=local`: `CoreDemoSeeder` crea «Admin TI de prueba» y «Consulta de prueba» (`@example.test`).
2. Abre `/dev/entrar` y elige un usuario.

Las rutas `core.dev.*` solo existen en `local`; el controlador además responde 404 fuera de `local` y a cualquier petición que no venga de `127.0.0.1` o `::1` (nunca confía en encabezados reenviados), y el ingreso es un POST con CSRF. Queda en la auditoría como `core.auth.signed_in` con `method: demo`.

## Usuarios y roles

Los usuarios (`App\Models\User`, tabla `users`) entran solo con Microsoft: no hay contraseñas. Nunca se borran; un usuario inactivo (`is_active = false`) sale de la sesión en su siguiente petición.

| Rol (`App\Modules\Core\Contracts\Enums\Role`) | Valor | Para qué |
|---|---|---|
| Admin TI | `admin_ti` | Administra todo: solicitudes, apps conectadas y usuarios. |
| Consulta | `consulta` | Solo mira el panel. |

Quien entra por primera vez queda **sin rol** y no ve nada hasta que TI le dé uno.

### Permisos para Sap y Panel

No compares roles: pregunta por estos permisos (gates) con `can:` en la ruta, `@can` en la vista o `Gate::allows()`.

| Permiso | Quién lo tiene |
|---|---|
| `core.consultar` | Todo usuario activo con un rol. |
| `core.administrar` | Solo Admin TI activo. |

```php
Route::middleware(['auth', 'can:core.administrar'])->post('solicitudes', …);
```

### Dar o quitar un rol

```bash
php artisan core:rol ana.gomez@segurex.com admin_ti   # o consulta
php artisan core:rol ana.gomez@segurex.com ninguno    # quita el rol
```

El usuario tiene que haber entrado una vez con Microsoft. Cada cambio queda en la auditoría (`core.user.role_changed`).

Para el primer administrador, pon su correo en `CORE_ADMIN_EMAILS` (separados por comas): al entrar con Microsoft recibe `admin_ti`. Esa lista nunca le quita el rol a nadie.

## Auditoría

`App\Modules\Core\Contracts\AuditLogger` guarda cada acción que hay que poder rastrear en `audit_logs` (conexión `app`). Pídelo por inyección y llama:

```php
$audit->record('sap.request.created', 'request', $request->id, ['dataset' => 'maestros']);
```

- La acción es `<clave-del-módulo>.<entidad>.<verbo>` en minúsculas, p. ej. `core.user.role_changed`. Otro formato lanza `InvalidArgumentException`.
- Core agrega solo el usuario que ingresó (ninguno para el robot, la consola o el programador), la IP de la petición y la hora.
- Nunca pongas secretos, tokens ni contraseñas en el contexto. Como red de seguridad, las llaves que parecen secretos (`password`, `secret`, `token`) se guardan como `[redacted]`.
- Las filas no se cambian ni se borran.
