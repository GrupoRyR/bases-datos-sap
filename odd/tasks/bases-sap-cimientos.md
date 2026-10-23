# Feature: Bases SAP cimientos

## Objective

Lay the foundation of «Bases de datos SAP» (plan §9, session 1) so the «Datos y API», «Robot» and «Panel» sessions can work in parallel.

## Scope and constraints

- Zone: skeleton, CI, push protections, `CLAUDE.md`, `docs/arquitectura.md`, `docs/contrato-robot.md`, Core module, migrations `2026_11_01_`.
- No SAP, VPN, GoDaddy or real databases; no `.env` reads or edits (propose `.env.example` lines).
- Delivery: stacked PRs to main, about 400 changed lines each; merge bottom-up, retargeting the next PR to `main` before each merge.
- RDD: off (global). Each PR runs the `code-review` skill, syncs with `main`, passes `composer format`, `composer lint`, `composer test` and green CI before merge.

## Tasks

| ID | Task | Branch | Route | Status |
|---|---|---|---|---|
| T1 | Skeleton: Laravel 13, PHP 8.3, three MySQL connections (app, maestros, cartera), Pest, Pint, Larastan, CI with MySQL 8, pre-push hook and `.claude/settings.json` guards | `feat/esqueleto` | delegated writer (many files) | done (local checks) |
| T2 | Module zones `app/Modules/{Core,Sap,Panel}` with base provider, migration prefixes, architecture tests, `CLAUDE.md` and `docs/arquitectura.md` | `feat/modulos` | delegated writer | done (local checks) |
| T3 | Robot contract `docs/contrato-robot.md` | `docs/contrato-robot` | inline (one document) | pending |
| T4 | Microsoft Entra ID sign-in, roles admin TI and consulta, local-only demo login | `feat/ingreso-microsoft` | delegated writer | pending |
| T5 | Segurex brand base: tokens, layout, logo, dark mode | `feat/diseno-base` | delegated writer | pending |

## Acceptance

- Each PR: CI green (lint, tests on MySQL 8), `code-review` findings fixed, merged with `gh pr merge <n> --merge --delete-branch` after user approval.

## Progress

### T1 (done, local checks)

- Route: delegated writer (trigger: 2+ non-trivial files, skeleton plus tooling).
- Commits on `feat/esqueleto`:
  - `3ea9fc8` build: scaffold Laravel 13 with Pest, Pint and Larastan
  - `44dfd88` feat(db): add app, maestros and cartera connections
  - `eda0c69` ci: run lint, tests on MySQL 8 and the asset build
  - `8ed529e` chore: block pushes to main, force pushes and --no-verify
- Test first: `tests/Feature/DatabaseConnectionsTest.php` failed before the config change (RED: default was `sqlite`, connections `app`, `maestros`, `cartera` not configured), then passed (GREEN).
- Verification (local, Windows, PHP 8.3.35, Node 24):
  - `composer format`: pint passed, no changes.
  - `composer lint`: pint passed; phpstan level 6 passed, 0 errors.
  - `composer test`: 13 tests, 12 passed, 1 skipped (MySQL-only distinct-database check, runs in CI).
  - `npm install && npm run build`: 0 vulnerabilities, build OK; `public/build` is git-ignored.
  - Pre-push hook: push to `refs/heads/main` exits 1, branch push exits 0.
- Pending: CI on GitHub (MySQL 8 run of the connections test), `code-review`, PR. The user enables the hook with `git config core.hooksPath .githooks`.
- Size: about 600 authored lines without lock files and Laravel boilerplate; the skeleton itself adds about 2,000 generated lines. One PR is proposed because the skeleton cannot be split usefully.

### T2 (done, local checks)

- Route: delegated writer (triggers: 4+ files to read from the gestor reference, 2+ non-trivial files to write).
- Stacked on `origin/feat/esqueleto` (`769fd14`); rebased onto it after that fix landed. The `DatabaseSeeder` conflict kept the module-seeder version, which also seeds no users.
- Commits on `feat/modulos`:
  - `354b39f` feat(modules): add module registry and base provider
  - `7dce4f5` feat(modules): add Core, Sap and Panel zones with architecture tests
  - `3d140ad` docs: document the architecture and the module rules for agents
- Test first:
  - Provider, seeder and navigation tests (16) failed with missing classes (RED), then passed (GREEN).
  - Module skeleton, transaction and connection tests failed (RED: no modules, no `config/modules.php`, only `app` in the test transaction), then passed (GREEN).
  - Arch rules proven by temporary violations, reverted: Panel using Sap internals, Sap using Panel contracts, Core using Sap contracts, `App\Support` using a module, and a Sap migration with Core's prefix each failed; Panel using only Sap contracts passed.
  - Larastan `configDirectories`: `env()` in `app/Modules/Sap/config/sap.php` passed and in another module file failed (temporary files, removed).
- Decisions:
  - The `api` middleware group is built into Laravel 13 (`Middleware::getMiddlewareGroups()`), so `bootstrap/app.php` is unchanged; the Demo `/api/demo/status` test proves module API routes answer.
  - `Tests\TestCase` wipes `maestros` and `cartera` before `migrate:fresh`, which only wipes the default connection; otherwise a second migration in one run would find dataset tables.
  - The allowed cross-module map (`$mayUse`) lives in `tests/Architecture/ModulesTest.php`; a new module fails until it gets a row.
  - `tests/Modules/README.md` exists because PHPUnit fails on a suite directory that does not exist.
- Verification (local, Windows, PHP 8.3.35), each commit green on its own:
  - `composer format`: pint passed, no changes.
  - `composer lint`: pint passed; phpstan level 6 passed, 0 errors.
  - `composer test`: 50 tests, 49 passed, 1 skipped (MySQL-only distinct-database check).
- Pending: CI on MySQL 8 (the connection test runs DDL there, which commits and forces the next test to migrate again), `code-review`, PR.
- Size: about 1,460 changed lines against `origin/feat/esqueleto` (1,448 added, 15 removed): about 550 copied from the gestor's proven loader, 470 tests and fixtures, 320 docs. Over the 400-line advisory; it can split as (a) loader and (b) zones plus docs if the user wants chained PRs.

## Next step

- T1: push `feat/esqueleto`, open the PR, run `code-review`, wait for green CI and the user's approval.
- T2: push `feat/modulos`, open the PR against `feat/esqueleto` (retarget to `main` after T1 merges), run `code-review`, wait for green CI and the user's approval.
