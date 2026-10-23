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
| T4 | Microsoft Entra ID sign-in, roles admin TI and consulta, local-only demo login | `feat/ingreso-microsoft` | delegated writer | done (local checks) |
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

### T4 (done, local checks)

- Route: delegated writer (triggers: 4+ files to read from the gestor reference, 2+ non-trivial files to write).
- Stacked on `origin/docs/contrato-robot` (`093d752`). Reference: the gestor's Entra ID sign-in, copied without companies, SAP advisors or spatie/laravel-permission.
- Commits on `feat/ingreso-microsoft`, in two groups for two chained PRs:
  - Group A, users, roles and audit (no Microsoft yet):
    - `130a250` feat(core): add the audit log contract
    - `2741b22` feat(core): add users, roles and the role command
  - Group B, Microsoft sign-in and local demo sign-in:
    - `6de4e70` feat(core): sign in with Microsoft Entra ID
    - `97c17d9` feat(core): add the local-only demo sign-in
- What exists now:
  - `users` moved to Core (`2026_11_01_000001`) without passwords: `microsoft_id`, `role`, `is_active`, `last_signed_in_at`; `password_reset_tokens` dropped. `audit_logs` (`2026_11_01_000002`).
  - `Role` enum (`admin_ti`, `consulta`), gates `core.consultar` and `core.administrar`, `CORE_ADMIN_EMAILS`, `php artisan core:rol <correo> <admin_ti|consulta|ninguno>`, `EnsureUserIsActive` on the web group.
  - `AuditLogger` contract with `DatabaseAuditLogger` (user, IP, time; secret-looking keys redacted).
  - Socialite `microsoft` driver registered by Core, fail-closed without `MICROSOFT_TENANT_ID`; `SignInWithMicrosoft`; routes `core.login`, `core.auth.redirect`, `core.auth.callback`, `core.inicio`, `core.sin-acceso`, `core.logout`; bare views for T5 to restyle; welcome page removed.
  - Demo sign-in `/dev/entrar` (local only, loopback only, POST with CSRF) and `CoreDemoSeeder`.
- Decisions:
  - The audit is written before the users move (commit order) so `core:rol` can audit from its first commit.
  - Every rejected sign-in (tenant, identity mismatch, inactive) shows the same message; the reason is only in the audit log.
  - A user matched by Microsoft object id signs in even if Entra now reports another e-mail; the stored e-mail is kept and the bootstrap-admin check uses the e-mail Microsoft vouches for.
  - `core.auth.signed_in` is audited by the controller after `Auth::login()`, so the entry names the user as the actor.
- Test first:
  - Group A: audit logger tests (9) failed with the missing contract, then passed. Users, gates, command, config and middleware tests (33) failed (no columns, no states, no `core:rol`, no `core.admins`), then passed.
  - Group B: sign-in, driver, identity, login, logout and home tests (59) failed (welcome page at `/`, 404 on Core routes, missing classes), then passed. Demo sign-in and seeder tests (18) failed (routes not defined, seeder missing), then passed.
- Verification (local, Windows, PHP 8.3.35), each commit green on its own:
  - `composer format`: pint passed, no changes.
  - `composer lint`: pint passed; phpstan level 6 passed, 0 errors.
  - `composer test`: 168 tests, 167 passed, 1 skipped (MySQL-only distinct-database check).
- Size (changed lines, added plus removed, without `composer.lock`):
  - Group A: 1,021 (code 544, tests 429, docs 48).
  - Group B: 1,939 (code 1,059, tests 855, docs 25), plus 537 lines of `composer.lock` for Socialite.
  - Both are over the 400-line advisory, mostly tests; group B can split again at its commit boundary (sign-in, then demo sign-in).
- Proposed `.env.example` lines (the user copies them in):

  ```dotenv
  # Microsoft Entra ID sign-in (app registration of the TI panel).
  # The tenant is required: without it nobody can sign in (never "common").
  MICROSOFT_CLIENT_ID=
  MICROSOFT_CLIENT_SECRET=
  MICROSOFT_TENANT_ID=
  MICROSOFT_REDIRECT_URI="${APP_URL}/auth/microsoft/callback"
  # Comma-separated e-mails that become admin TI when they sign in.
  CORE_ADMIN_EMAILS=
  ```

- Pending for the parent: `docs/arquitectura.md` §2.4 still says `routes/web.php` shows the welcome page at `/`; it is now gone.

## Next step

- T3: green CI on PR #4, user approval, merge.
- T4: `code-review`, then two chained PRs (group A, then group B) after T3 merges.
