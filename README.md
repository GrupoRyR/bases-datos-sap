# Bases de datos SAP

Almacén central de los datos maestros de SAP Business One para las apps del Grupo RYR (Segurex SGX y Soluciones y Derivados SDC). Un robot en Python, que corre en el PC de TI, extrae los datos de SAP y los publica aquí; las apps los leen desde MySQL. El alcance, las decisiones y las sesiones de trabajo están en [docs/plan-bases-sap.md](docs/plan-bases-sap.md).

## Requisitos

- PHP 8.3 con `pdo_mysql` y `pdo_sqlite`
- Composer 2
- Node.js 22 o superior con npm
- MySQL 8 (solo para correr la app; las pruebas locales usan SQLite en memoria)

## Instalación

```bash
composer install
cp .env.example .env    # lo haces tú y llenas los valores locales
php artisan key:generate
npm install
```

## Comandos

```bash
composer format   # da formato al código con Pint
composer lint     # Pint en modo revisión y Larastan
composer test     # corre las pruebas de Pest
npm run build     # compila los assets (public/build nunca se sube al repo)
```

## Protección de main

Los cambios llegan a `main` solo por pull request. El hook `.githooks/pre-push` bloquea cualquier push a `main`, y `.claude/settings.json` impide a los agentes hacer push a `main`, forzar un push o saltarse los hooks.

Activa el hook una vez por clon: `git config core.hooksPath .githooks`
