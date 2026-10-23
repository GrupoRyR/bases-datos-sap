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
| T1 | Skeleton: Laravel 13, PHP 8.3, three MySQL connections (app, maestros, cartera), Pest, Pint, Larastan, CI with MySQL 8, pre-push hook and `.claude/settings.json` guards | `feat/esqueleto` | delegated writer (many files) | merged (PR #1) |
| T2 | Module zones `app/Modules/{Core,Sap,Panel}` with base provider, migration prefixes, architecture tests, `CLAUDE.md` and `docs/arquitectura.md` | `feat/modulos-base`, `feat/modulos` | delegated writer | merged (PR #2, #3) |
| T3 | Robot contract `docs/contrato-robot.md` | `docs/contrato-robot` | inline (one document) | in review (PR #4) |
| T4 | Microsoft Entra ID sign-in, roles admin TI and consulta, local-only demo login | `feat/ingreso-microsoft` | delegated writer | pending |
| T5 | Segurex brand base: tokens, layout, logo, dark mode | `feat/diseno-base` | delegated writer | done (local checks) |

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
- Merged as PR #1 (`a84323c`) after `code-review` (fix `769fd14`: no demo user in the seeder, deny `git push *+*`, real driver test) and green CI. The user enables the hook with `git config core.hooksPath .githooks`.
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
- Split into two chained PRs after one slicing pass: #2 loader (`size:exception`, mostly tests) and #3 zones plus docs. `code-review` removed unused `ModuleRegistry::find()`, `NavRegistry::groupedFor()`/`mobileFor()` (`32fa146`). CI green on MySQL 8 for both; merged.
- Size: about 1,460 changed lines against `origin/feat/esqueleto` (1,448 added, 15 removed): about 550 copied from the gestor's proven loader, 470 tests and fixtures, 320 docs. Over the 400-line advisory; it can split as (a) loader and (b) zones plus docs if the user wants chained PRs.

### T3 (in review)

- Route: inline (one document; contract design needs the parent's context).
- `docs/contrato-robot.md`: HMAC with timestamp and nonce, runs and batches, MAESTROS parts and CARTERA columns, requests and states, apps API.
- `code-review` fixes (`850cc20`): 3-minute wait per dataset and company (not per part), expired requests stay `vencida` when their run closes later, exact routes served by `Sap` with an empty `apiPrefix()`.
- Open for the user: the nightly photo uses `fecha_corte` = yesterday while the copied query computes `dias` with today (plan §4).
- Verification: passive documentation; structural readback; `composer lint` and `composer test` green after syncing with `main`.

### T5 (done, local checks)

- Route: delegated writer (triggers: 2+ non-trivial files to write; reading the brand skills, NavRegistry and the layout needs prepared the write). Worktree `BASES_DATOS_SAP-worktrees/diseno`, branch `feat/diseno-base` from `main` (`63e9638`).
- Commits on `feat/diseno-base`:
  - `1b16d3a` feat(design): add Segurex tokens, fonts and dark mode
  - `badfe89` feat(design): add the base UI components
  - `8b9a4b3` feat(design): add the app and guest layouts with the logo
  - `0dbd044` docs: describe the design base
- Test first (Pest, `tests/Feature/Design/`):
  - `AssetsTest`: 5 of 6 failed before the change (RED: Instrument Sans in `app.css` and `vite.config.js`, no Helvetica, no brand variables, no module `@source`), then passed (GREEN).
  - `ComponentsTest`: 16 of 16 failed with missing components (RED), then passed.
  - `LayoutsTest`: 10 of 10 failed with missing layouts (RED), then passed; a logo-height test was added after the visual check found `h-8` and `h-7` on the same image.
- Decisions:
  - Dark tokens are written once with `light-dark()`; `color-scheme` follows the system and `data-theme="light|dark"` overrides it. Lightning CSS (Tailwind build) compiles it to `--lightningcss-light/dark` toggles, checked in the built CSS and in a browser.
  - Tailwind's default palette is removed (`--color-*: initial`), so only token utilities exist.
  - `welcome.blade.php` stays because `routes/web.php` still serves it; only its `@fonts` line was removed.
  - On phones and tablets the full menu is a `<details>` disclosure (works without JS); the sidebar shows from `lg`. NavItem icons are not rendered yet: there is no icon set.
- Verification (local, Windows, PHP 8.3, Node 24):
  - `composer format`: pint passed, no changes. `composer lint`: pint passed; phpstan level 6, 0 errors.
  - `composer test`: 83 tests, 82 passed, 1 skipped (MySQL-only check).
  - `npm run build`: OK; `public/build` is ignored and not staged.
  - Visual check (static render served locally, 360 px and 1280 px, light and dark): no horizontal scroll at 360 px, the toggle cycles sistema → claro → oscuro and the choice survives a reload.
- The logo PNG from the brand skill is corrupt (zlib data check fails), so the header uses the gestor de cartera's dark-background SVG (`public/img/logo-segurex.svg`) until the user provides a valid official file.
- Size: 822 changed lines against `main` (811 added, 11 removed): about 265 tests, 33 docs, 520 CSS, JS and Blade. Over the 400-line advisory; it can split as (a) tokens and components, (b) layouts and docs.

## Next step

- T3: green CI on PR #4, user approval, merge.
- T4: Entra ID sign-in and roles on `feat/ingreso-microsoft`, stacked on T3.
