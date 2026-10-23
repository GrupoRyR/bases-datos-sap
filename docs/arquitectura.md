# Arquitectura de Bases de datos SAP

Cómo está armado el código: quién es dueño de cada carpeta, cómo se carga un módulo, qué puede usar cada módulo de los demás, en qué base vive cada tabla y cómo se prueba. Es tan obligatorio como `CLAUDE.md`. Si algo de aquí no coincide con el código, manda el código y se corrige este documento.

El alcance, las decisiones y las sesiones están en [`plan-bases-sap.md`](plan-bases-sap.md); aquí se citan por sección (§3, §9…).

## Ruta rápida según tu sesión

| Si eres… | Lee primero |
|---|---|
| Datos y API | §1, §2, §3, §4, §5 y [`contrato-robot.md`](contrato-robot.md) |
| Robot | §1, §4 (bases y vistas) y [`contrato-robot.md`](contrato-robot.md) |
| Panel | §1, §2, §3 y §5 |
| Cualquiera, antes de un PR | §6, §7 y §8 |

## 1. Mapa del repositorio y dueños

```
app/
  Models/User.php          ← identidad compartida (cimientos)
  Modules/Core/            ← ingreso, usuarios y roles, auditoría, layout (cimientos)
  Modules/Sap/             ← datos, robot, solicitudes y API (Datos y API)
  Modules/Panel/           ← panel de TI (Panel)
  Providers/               ← AppServiceProvider y ModulesServiceProvider (cimientos)
  Support/Modules/         ← cargador de módulos (cimientos)
  Support/Navigation/      ← NavItem y NavRegistry (cimientos)
bootstrap/  config/  routes/  database/   ← base (cimientos)
robot/                     ← robot en Python (Robot)
tests/
  Architecture/            ← reglas de fronteras (cimientos)
  Fixtures/Modules/Demo/   ← módulo de ejemplo de las pruebas (cimientos)
  Modules/<Modulo>/        ← pruebas de cada módulo
docs/                      ← plan, arquitectura y contrato del robot
```

Cada sesión escribe solo en su zona (§9 del plan):

| Sesión | Zona | Migraciones |
|---|---|---|
| Cimientos | Esqueleto, CI, protecciones, `CLAUDE.md`, `docs/arquitectura.md`, `docs/contrato-robot.md`, `app/Modules/Core/**`, `tests/Modules/Core/**` | `2026_11_01_*` |
| Datos y API | `app/Modules/Sap/**`, `tests/Modules/Sap/**` | `2026_11_02_*` |
| Robot | `robot/**` y sus pruebas | — |
| Panel | `app/Modules/Panel/**`, `tests/Modules/Panel/**` | `2026_11_03_*` |

Todo lo que no está en una zona es de la base: `bootstrap/`, `config/`, `routes/`, `app/Providers/`, `app/Support/`, `database/` (raíz), `tests/TestCase.php`, `tests/Pest.php`, `tests/Architecture/`, `tests/Fixtures/`, `composer.json`, `package.json` y sus lockfiles, `phpunit.xml`, `phpstan.neon`, `.github/`, `.githooks/` y `.claude/`. Si necesitas cambiar algo de ahí, detente y pídelo al usuario.

## 2. Anatomía de un módulo

### 2.1 Carpetas

```
app/Modules/<Modulo>/
  Providers/<Modulo>ServiceProvider.php   ← obligatorio: final, extiende ModuleServiceProvider
  Contracts/              ← lo único que otros módulos pueden usar (§3)
  Http/Controllers/  Http/Requests/
  routes/web.php  routes/api.php
  database/migrations/  database/seeders/  database/factories/
  resources/views/  resources/lang/es/    ← "<clave>::…"
  config/<clave>.php
  README.md
```

- El nombre de la carpeta es el nombre del módulo en PascalCase. La **clave** es ese nombre en minúsculas (`Sap` → `sap`) y nombra rutas, vistas, traducciones y configuración.
- Crea una carpeta solo cuando tenga un archivo. Hoy cada módulo tiene su proveedor y su `README.md`.

### 2.2 Qué carga la base sin que hagas nada

`App\Providers\ModulesServiceProvider` (en `bootstrap/providers.php`) descubre los módulos con `ModuleRegistry`, **Core primero** y el resto en orden alfabético, y registra el `<Modulo>ServiceProvider` de cada uno. El proveedor extiende `App\Support\Modules\ModuleServiceProvider`, que deduce el módulo de la carpeta donde vive y carga, si existen:

| Qué | Cómo queda |
|---|---|
| `config/<clave>.php` | `config('<clave>.*')`. Puede usar `env()`, como `config/`. |
| `database/migrations/` | Corre con `php artisan migrate`. |
| `resources/views/` y `resources/lang/` | `view('<clave>::vista')` y `__('<clave>::archivo.llave')`. |
| `routes/web.php` | Middleware `web`, prefijo `/<webPrefix()>`, nombres `<clave>.*`. |
| `routes/api.php` | Middleware `api`, prefijo `/api/<apiPrefix()>`, nombres `<clave>.api.*`. |

Con las rutas cacheadas (`php artisan optimize`), el proveedor no las vuelve a cargar. Los errores de `/api/*` siempre responden JSON (`bootstrap/app.php`).

### 2.3 Ganchos

`register()` y `boot()` son `final`. El módulo solo sobrescribe estos métodos:

| Gancho | Cuándo corre | Para qué |
|---|---|---|
| `registerModule()` | En `register()`, después de la configuración | Bindings, p. ej. la implementación de un contrato. |
| `bootModule()` | Al final de `boot()` | Policies, listeners, comandos de Artisan. |
| `schedule(Schedule)` | Al resolver `Schedule` | Tareas programadas. cPanel corre `schedule:run` cada minuto. |
| `navigation(NavRegistry)` | Al resolver `NavRegistry` | Entradas del menú. |
| `webPrefix()` / `apiPrefix()` | Al cargar rutas | Prefijo sin barras; por defecto la clave. |

Ejemplo (nombres de clases ilustrativos):

```php
final class SapServiceProvider extends ModuleServiceProvider
{
    protected function registerModule(): void
    {
        $this->app->singleton(MaestrosReader::class, EloquentMaestrosReader::class);
    }

    protected function bootModule(): void
    {
        $this->commands([VencerSolicitudes::class]);
    }

    protected function schedule(Schedule $schedule): void
    {
        $schedule->command('sap:vencer-solicitudes')->everyFiveMinutes()->withoutOverlapping();
    }
}
```

Nunca edites `bootstrap/providers.php`, `routes/*.php` ni `routes/console.php` para un módulo: todo entra por estos ganchos.

### 2.4 Los tres módulos

| Módulo | URL web | URL API | Migraciones | Dueña |
|---|---|---|---|---|
| Core | `/` (raíz), `core.*` | `/api/core/*`, `core.api.*` | `2026_11_01_*` | Cimientos |
| Sap | `/sap/*`, `sap.*` | `/api/sap/*`, `sap.api.*` | `2026_11_02_*` | Datos y API |
| Panel | `/panel/*`, `panel.*` | `/api/panel/*`, `panel.api.*` | `2026_11_03_*` | Panel |

Core sirve la raíz: sus rutas no pueden empezar con `/sap` ni `/panel`. Hoy `routes/web.php` todavía muestra la página de bienvenida en `/`; la quita la tarea del ingreso con Microsoft.

## 3. Regla entre módulos

Un módulo usa otro **solo por su espacio `App\Modules\<Otro>\Contracts`**, y solo si esta tabla lo permite:

| Módulo | Puede usar |
|---|---|
| Core | Ningún otro módulo |
| Sap | `App\Modules\Core\Contracts` |
| Panel | `App\Modules\Core\Contracts` y `App\Modules\Sap\Contracts` |

- Panel lee los datos de Sap por contratos (interfaces y objetos de datos), nunca por sus modelos, tablas o controladores.
- Si te falta un contrato de otro módulo, pídelo a su dueña: tú no lo escribes.
- `App\Support` no usa módulos, salvo `App\Modules\Core\Contracts`.
- En `App` no quedan `dd`, `dump`, `ray`, `var_dump` ni `die`.

`tests/Architecture/ModulesTest.php` lo comprueba para cada módulo que encuentra. Un módulo nuevo necesita su fila en `$mayUse` de esa prueba.

## 4. Bases de datos y conexiones

Tres bases en el mismo servidor MySQL (§3 del plan), una conexión por base:

| Conexión | Base | Qué guarda |
|---|---|---|
| `app` (por defecto) | `bases_sap` | Solicitudes, corridas, lotes, usuarios del panel, apps conectadas, auditoría |
| `maestros` | `maestros_sap` | Tablas del conjunto MAESTROS |
| `cartera` | `cartera_sap` | Tablas del conjunto CARTERA |

- Una migración de un conjunto declara su conexión; el migrador la usa en `up()` y `down()`:

  ```php
  return new class extends Migration
  {
      protected $connection = 'maestros';

      public function up(): void
      {
          Schema::create('clientes', function (Blueprint $table) { /* … */ });
      }
  };
  ```

- Los modelos de un conjunto declaran `protected $connection = 'maestros';` (o `'cartera'`).
- **Las apps nunca leen tablas.** Leen vistas estables `v_*` (`v_clientes`, `v_articulos`, `v_cartera`…) con un usuario MySQL de solo lectura por app, con permiso solo en las bases que usa (§3 y §4 del plan).
- Nunca se borran filas de los maestros: lo que falta en una corrida completa queda inactivo.
- **Prefijos de migraciones:** cada módulo usa el suyo (`config/modules.php`) y numera con el sufijo: `2026_11_02_000001_create_…`. La base usa `0001_01_01_*`.
- **Seeders y factories:** `app/Modules/<Modulo>/database/seeders/` (`App\Modules\<Modulo>\Database\Seeders`) y `database/factories/` (`…\Database\Factories`). `composer.json` ya trae su entrada PSR-4. `DatabaseSeeder` corre `<Modulo>DatabaseSeeder` siempre y `<Modulo>DemoSeeder` solo en `local`, si existen.

## 5. Pruebas

Las pruebas de un módulo van en `tests/Modules/<Modulo>/Unit` y `tests/Modules/<Modulo>/Feature`; las de la base, en `tests/Unit`, `tests/Feature` y `tests/Architecture`. Son las suites `Unit`, `Feature`, `Modules` y `Architecture` de `phpunit.xml`, y todas extienden `Tests\TestCase`, que:

- usa `LazilyRefreshDatabase` en las tres conexiones: la primera consulta a cualquiera migra las bases de prueba y abre la transacción de la prueba en las tres;
- borra `maestros` y `cartera` antes de migrar, porque `migrate:fresh` solo borra la conexión por defecto;
- activa `Http::preventStrayRequests()`: toda llamada HTTP sin `Http::fake()` falla;
- llama `withoutVite()`: las vistas se pintan sin `public/build`.

En tu equipo las pruebas corren en SQLite en memoria (una base por conexión); CI las corre en MySQL 8 con tres bases. Evita SQL propio de un motor. Las pruebas nunca tocan SAP, la VPN, GoDaddy ni correo real.

## 6. Comandos

| Comando | Hace |
|---|---|
| `composer format` | Pint corrige el estilo. |
| `composer lint` | `pint --test` y Larastan nivel 6. `env()` solo vale en `config/` y `app/Modules/*/config/`. |
| `composer test` | `config:clear` y todas las suites. |
| `php artisan test tests/Modules/Sap` | Solo tu módulo, mientras trabajas. |

## 7. CI

`.github/workflows/ci.yml` corre en cada PR a `main` y en cada push a `main`. Un PR encadenado corre cuando lo cambias a `main` y lo sincronizas. Ningún PR se fusiona en rojo.

| Job | Qué hace |
|---|---|
| Lint | PHP 8.3, `composer lint`. |
| Tests | PHP 8.3 con MySQL 8; crea las tres bases de prueba y corre `composer test`. |
| Assets | Node 22, `npm ci` y `npm run build`. Solo comprueba que compila. |

## 8. Protecciones locales de `main`

GitHub no aplica reglas en este repositorio privado, así que `main` se protege en tu equipo:

| Protección | Qué hace |
|---|---|
| `.githooks/pre-push` | Rechaza cualquier push que cree, cambie o borre `main`. |
| `.claude/settings.json` (deny) | Push a `main`, push forzado, `--no-verify`, cambiar `core.hooksPath` y fusionar por `gh api`. |
| `.claude/settings.json` (ask) | `gh pr merge` pide aprobación al usuario. |

El usuario activa el hook una vez por clon: `git config core.hooksPath .githooks`. Nunca intentes saltarte estas protecciones; si una te bloquea, detente y avísale al usuario.

## 9. Contrato del robot

[`contrato-robot.md`](contrato-robot.md) define lo que el robot envía y lo que la API responde: firma HMAC, lotes, solicitudes y conteos. Lo comparten Datos y API y Robot, que trabajan en paralelo: **no cambia sin avisarle al usuario**, y un cambio va en su propio PR.

## 10. Diseño

El panel es de TI y lleva solo la marca de Segurex (§3 del plan). Las reglas salen de la skill `frontend-marca-sgx-sydc`:

- **Logo como imagen**, nunca el nombre en texto: `public/img/logo-segurex.svg` (la versión para fondo oscuro del gestor de cartera) con `<x-ui.logo />`, alto fijo y ancho automático, sobre el gris `bg-brand-dark`. El texto sobre ese gris va en blanco (`text-on-brand`): el naranja ahí no da contraste.
- **Tipografía Helvetica/Arial** en toda la interfaz. No se carga ninguna fuente externa ni CDN.
- **Colores solo por variables `--brand-*`**: ninguna vista lleva un hex. `tests/Feature/Design/AssetsTest.php` falla si una vista Blade trae un color de marca o una fuente externa.

**Tokens.** Viven en `resources/css/app.css`: las variables de marca en `:root[data-brand="segurex"]` y las neutras (`--ui-*`: fondo, superficie, texto, texto suave, bordes, foco, info, éxito, aviso y peligro), todas AA y con su contraste anotado. `@theme inline` las vuelve utilidades de Tailwind: `bg-surface`, `text-muted`, `border-line`, `bg-brand-button`, `text-brand-ink`, `bg-danger-bg`… La paleta por defecto de Tailwind está desactivada, así que solo existen estos colores.

**Modo oscuro.** Cada token se escribe una vez con `light-dark(claro, oscuro)`. Por defecto sigue al sistema; el botón «Tema» del encabezado (`resources/js/theme.js`) alterna sistema → claro → oscuro, lo guarda en `localStorage` y lo aplica con `<html data-theme="light|dark">`. Un script en el `<head>` lo aplica antes de pintar, sin parpadeo. Sin JavaScript, el botón no aparece y manda el sistema. Si una vista necesita algo distinto en oscuro, usa la variante `dark:`, que respeta la misma regla.

**Layouts.** Componentes anónimos en `resources/views/components/layouts/`:

| Componente | Para qué |
|---|---|
| `<x-layouts.app title="…">` | Páginas con sesión: encabezado con logo, tema, usuario y «Cerrar sesión» (si existe `core.logout`); menú de `NavRegistry` por grupos, barra inferior en el celular para los ítems `mobile`; mensajes de `session('status')` y `session('error')`. |
| `<x-layouts.guest title="…">` | Ingreso y «sin acceso»: tarjeta centrada bajo la franja gris del logo. |

**Componentes** en `resources/views/components/ui/`: `button` (`primary`, `secondary`, `danger`; con `href` es un enlace), `card`, `page-header`, `alert` (`info`, `success`, `warning`, `danger`), `empty`, `badge` y `logo`. Ejemplo:

```blade
<x-layouts.app title="Solicitudes">
    <x-ui.page-header title="Solicitudes" description="Lo que piden las apps.">
        <x-slot:actions><x-ui.button href="{{ route('panel.solicitudes.create') }}">Nueva solicitud</x-ui.button></x-slot:actions>
    </x-ui.page-header>

    <x-ui.empty description="Aún no llega ninguna." />
</x-layouts.app>
```

Textos en español, tuteando y en tipo oración; zonas táctiles de 44 px; foco visible; sin desplazamiento horizontal a 360 px.
