# Pruebas de los módulos

Cada módulo guarda aquí sus pruebas, en `tests/Modules/<Modulo>/Unit` y `tests/Modules/<Modulo>/Feature`. Corren en la suite `Modules` de `phpunit.xml` y extienden `Tests\TestCase`, como todas.

| Carpeta | Dueña |
|---|---|
| `tests/Modules/Core/**` | Sesión «cimientos» |
| `tests/Modules/Sap/**` | Sesión «Datos y API» |
| `tests/Modules/Panel/**` | Sesión «Panel» |

Este archivo existe para que la carpeta no quede vacía: PHPUnit falla si una suite apunta a una carpeta que no existe.

Mientras trabajas, corre solo tu módulo: `php artisan test tests/Modules/Sap`. Las reglas están en `docs/arquitectura.md`.
