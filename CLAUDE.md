# Bases de datos SAP — rules for agents

Central store of SAP Business One master data for the Grupo RYR apps (Segurex SGX and Soluciones y Derivados SDC): Laravel 13, PHP 8.3, MySQL on GoDaddy and Microsoft Entra ID, fed by a Python robot that runs on the TI PC.

## Read first

- `docs/plan-bases-sap.md`: scope, decisions, schedules, folder layout and sessions. It is the source of truth.
- `docs/arquitectura.md`: owners of each folder, module anatomy and provider hooks, the cross-module rule, databases and connections, tests, CI and the protections of `main`. Its rules are as binding as this file.
- `docs/contrato-robot.md`: the robot contract (signature, runs, batches, datasets and update requests). It is shared by two parallel sessions: never change it without the user's approval.

## Hard rules

- Write only inside the zone your session owns (plan §9 and the table below). If you need anything else, stop and ask the user.
- Never connect to SAP, the Sophos VPN, GoDaddy or any real database, and never send real email. Tests use fakes.
- Never read or edit any `.env`. Propose `.env.example` lines; the user copies them in.
- Never commit data extracted from SAP. CSV output lives outside the repo, in `BASES_SAP_CSV_DIR`.
- Never select password columns from `OUSR`, nor ID number, salary or bank fields from `OHEM`. List columns one by one; never `SELECT *` on SAP tables.
- Archive-only categories (plan §5) are written to CSV and never sent to the API or MySQL.
- The app never deletes master rows; rows missing from a full run are marked inactive.
- No secrets in the repository.
- Push your branch and open a PR against `main`. Never push to `main`, force push or use `--no-verify`.
- Merge your own PR only with `gh pr merge <number> --merge --delete-branch`, after running the `code-review` skill, syncing with `main`, passing local checks and getting green CI. The user approves every merge.
- Remote work (SSH, deploy, cPanel) only with the user's explicit authorization for that destination and operation.

## Module zones

| Session | Zone | Migration prefix |
|---|---|---|
| Cimientos | Skeleton, CI, protections, this file, `docs/arquitectura.md`, `docs/contrato-robot.md`, `app/Modules/Core/**`, `tests/Modules/Core/**` | `2026_11_01_` |
| Datos y API | `app/Modules/Sap/**`, `tests/Modules/Sap/**` | `2026_11_02_` |
| Robot | `robot/**` and its tests | — |
| Panel | `app/Modules/Panel/**`, `tests/Modules/Panel/**` | `2026_11_03_` |

Everything outside these zones (`bootstrap/`, `config/`, `routes/`, `app/Providers/`, `app/Support/`, `tests/TestCase.php`, `tests/Architecture/`, `composer.json`, lockfiles, `phpunit.xml`, `phpstan.neon`, `.github/`, `.githooks/`, `.claude/`) belongs to the base: ask the user before touching it.

## Provider hooks

- A module registers everything through its final `<Module>ServiceProvider`, which extends `App\Support\Modules\ModuleServiceProvider`: `registerModule()`, `bootModule()`, `schedule(Schedule)`, `navigation(NavRegistry)`, `webPrefix()` and `apiPrefix()`.
- The base already loads the module's config, migrations, views, translations and `routes/web.php` / `routes/api.php`.
- Never edit `bootstrap/providers.php`, `routes/*.php` or `routes/console.php` for a module.

## Cross-module rule

- A module uses another module only through that module's `App\Modules\<Other>\Contracts` namespace.
- Core uses no other module. Sap may use Core contracts. Panel may use Core and Sap contracts.
- `App\Support` uses no module except `App\Modules\Core\Contracts`. No `dd`, `dump`, `ray`, `var_dump` or `die` in `App`.
- `tests/Architecture/ModulesTest.php` enforces all of this. If you need a contract from another module, ask its owner.

## Migrations and connections

- Each module's migrations start with its reserved prefix (`config/modules.php`), e.g. `2026_11_02_000001_create_…`.
- MAESTROS tables live on the `maestros` connection and CARTERA tables on `cartera`; everything else on `app`. A migration or model on a dataset connection declares `protected $connection = 'maestros';` (or `'cartera'`).
- Consumer apps read stable `v_*` views with a read-only MySQL user, never the tables.

## Protections of `main`

GitHub does not enforce rules on this private repository, so `main` is protected locally:

- `.claude/settings.json` denies pushes to `main`, force pushes, `--no-verify`, changing `core.hooksPath` and merges through `gh api`, and asks the user before any `gh pr merge`.
- `.githooks/pre-push` rejects any push to `main`. The user enables it once per clone with `git config core.hooksPath .githooks`.
- Never try to work around them. If one blocks you, stop and tell the user.

## Conventions

- UI text: Spanish, informal "tú", sentence case. Code, identifiers and comments: English.
- Commits: Conventional Commits, one work unit per commit, tests and docs with the code, no co-author or AI attribution lines.
- PRs: about 400 changed lines; use chained PRs for larger work.
- Tests first when a runnable test with a clear expected result exists. Module tests go in `tests/Modules/<Module>/{Unit,Feature}`.

## Commands

- `composer format`: format with Pint.
- `composer lint`: Pint check and Larastan (level 6).
- `composer test`: Pest suite (SQLite in memory locally, MySQL 8 in CI).

## Skills

Load the ones that apply before working: `work-unit-commits`, `chained-pr`, `frontend-marca-sgx-sydc`, `robot-sap-hana`, `cpanel-deploy`.
