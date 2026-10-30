# Feature: Bases SAP ventas

## Objective

Add the VENTAS dataset (plan §4, session 5b): the robot extracts invoice and credit note lines from both companies with the gestor de cartera query, and the app replaces only the query window per company in `ventas_sap`, keeping every earlier row untouched.

## Problem and why

Comisiones in the gestor de cartera needs sales lines. The user moved VENTAS into the first version (2026-10-29) so it counts toward the 14-day stability window together with MAESTROS and CARTERA. Commissions need frozen history, so earlier months are never rewritten.

## Scope and constraints

- Zone: the VENTAS dataset in `app/Modules/Sap/**` and `tests/Modules/Sap/**`, migrations `2026_11_02_` after the existing ones, the VENTAS part of `robot/**`, and contract §10 (plus the VENTAS lines it needs in §1, §4 and §7.1).
- MAESTROS and CARTERA behave exactly as before.
- The query is copied from gestor de cartera `etl/queries/ventas.sql` at main `9e2f877`, read only, unchanged, with its `@id_pedido_app` marker (SDC gets `CAST(NULL AS NVARCHAR(254))`).
- The window start is computed in HANA on the extraction connection, never with the PC clock.
- Never connect to SAP, the VPN or real databases; never read or edit any `.env`.
- Delivery: stacked PRs to `main`, about 400 changed lines each. Each PR: `code-review`, sync with `main`, `composer format`, `composer lint`, `composer test`, robot `pytest`, green CI, and the user's approval before `gh pr merge <n> --merge --delete-branch`.

## Design

- Contract §10: one parte `ventas`, mode `todo`, key `tipo_objeto` + `doc_entry` + `linea`, `ventana_desde` on run start (VENTAS only), `cantidad` and `trm` with up to 6 decimals.
- Window column: `fecha_contabilizacion` (`DocDate`), the column the query filters on. Deleting by `fecha_documento` (`TaxDate`) would duplicate or lose rows at the window edge.
- API guard: `ventana_desde` between today minus 40 days and tomorrow; batch rows before `ventana_desde` are rejected.
- Close: delete company rows with `fecha_contabilizacion >= ventana_desde` and insert the received rows in one transaction; 0 rows fails the run.
- Nightly count: `COUNT(*)` of the query; MySQL side counts the company rows inside the window.
- CSV: `VENTAS\<empresa>\aaaa-mm-dd_hhmm.csv`, deleted after 90 days.

## Tasks

| ID | Task | Branch | Route | Status |
|---|---|---|---|---|
| V1 | Contract §10 VENTAS and this feature document | `docs/contrato-ventas` | inline (one doc file) | merged (#33) |
| V2 | App: `ventas` connection, table and `v_ventas`, batch rules, window apply, requests, nightly count | `feat/sap-ventas-esquema`, `feat/sap-ventas` | delegated writer | merged (#34, #35) |
| V3 | Robot: query copy, HANA window, nightly run, requests, `--diagnostico`, CSV and retention | `feat/robot-ventas-consulta`, `feat/robot-ventas` | delegated writer (writer trigger: 2+ non-trivial files in `robot/**`) | #40 merged, #41 merging |

## Acceptance

- Contract §10 approved by the user; the panel session can build on it.
- App and robot tests green with fakes; CI green.
- The user runs `--diagnostico` and compares with SAP before the final merge.

## Progress

### V1

- Contract section written; documentation only, structural readback.

### V2

Route: delegated writer (writer trigger: 2+ non-trivial files). Branch `feat/sap-ventas`, stacked on `docs/contrato-ventas`. Test first: the VENTAS tests were written and seen failing before the code.

| Commit | Message | Changed lines |
|---|---|---|
| `d224cec` | feat(sap): add the VENTAS dataset schema and batch types | +314 −24 (18 files) |
| `e20e473` | feat(sap): require the VENTAS window on run start and in batches | +255 −6 (6 files) |
| `c496006` | feat(sap): replace only the VENTAS window on close | +262 −24 (9 files) |

About 885 changed lines in total: over the 400-line budget for one PR, so it needs chained PRs (for example the first commit, then the other two).

- `ventas` connection (`ventas_sap`) in `config/database.php`, `tests/TestCase.php`, `phpunit.xml`, CI and `docs/arquitectura.md` §4.
- `Dataset::Ventas`, `Part::Sales` (key `tipo_objeto`, `doc_entry`, `linea`), `ColumnType::Quantity` (up to 6 decimals, `decimal(19,6)`), the 34 columns of §10.
- Migrations `2026_11_02_000008_create_ventas_tables` (table `ventas`, unique key, index `empresa` + `fecha_contabilizacion`, view `v_ventas`) and `2026_11_02_000009_add_ventana_desde_to_robot_runs_table`.
- `StartRun`: `ventana_desde` required in VENTAS (date, today minus 40 days to tomorrow, today in Bogota), refused elsewhere; `fecha_corte` refused in VENTAS. `ReceiveBatch`: 422 `rows.N.fecha_contabilizacion` before the window. `ApplyVentas`: deletes the company's window and inserts the received lines in one transaction. `CountRun`: `activas_mysql` counts the window. Requests: VENTAS whole only. README updated.

Checks (2026-10-29, Bogota time):

- `composer format`: passed.
- `composer lint`: passed (Pint and Larastan, 0 errors).
- `php artisan test tests/Modules/Sap` (12:47): 305 tests, 304 passed, 1 skipped (the MySQL-only key case test), 0 failed.
- `composer test` (12:47): 507 tests, 505 passed, 2 skipped, 0 failed.
- Earlier runs at 12:18 and 12:30 had 2 failures in `StartRunTest` (Derivados MAESTROS requests). They failed the same way on the base commit: those tests do not freeze the clock, so within 15 minutes of the 12:00 and 12:30 blocked slots the request is queued instead of taken. After 12:45 all 26 `StartRunTest` cases pass. This is flaky and existed before V2; V2 did not cause it.

### V3

Branch `feat/robot-ventas`, cut from `main` with contract §10. Test first: RED observed for each unit before the code, then GREEN.

- `2bf6541` feat(robot): add the VENTAS query, its company marker and schema. `robot/queries/ventas/ventas.sql` is the gestor file at `9e2f877` byte for byte (same git blob `c768a24`, checked by a test). `consultas.sql_id_pedido_app` reuses the gestor regex: SGX runs as is, SDC gets `CAST(NULL AS NVARCHAR(254))`, and a missing, repeated or unrecognized marker fails before running. Parte `ventas` with the 34 contract columns and the new `cantidad` type (6 decimals, half up, no `-0.000000`). 7 files, +443 −21 (the copied SQL is 154 of them).
- `abdb32d` feat(robot): send VENTAS runs with the HANA window, nightly and on request. `SELECT ADD_DAYS(CURRENT_DATE, -6 - DAYOFMONTH(CURRENT_DATE)) FROM DUMMY` before and after the query on the extraction connection; one retry if it changed, then the job fails. `ventana_desde` only on VENTAS `iniciar`; rows before it fail the job. Nightly: MAESTROS, CARTERA and VENTAS per company, with `conteo_sap.ventas`. VENTAS requests map to `{"ventas": "todo"}`. CSV `VENTAS\<empresa>\aaaa-mm-dd_hhmm.csv`, 90-day retention. LEEME updated. 18 files, +480 −83 (about 560 changed lines, mostly tests: the nightly lists in existing tests grew from 4 to 6 runs).
- `e4d1b3e` feat(robot): show the HANA window of VENTAS in the diagnostic. 2 files, +75 −8.
- Checks: `robot/.venv/Scripts/python.exe -m pytest` → 677 passed (baseline 618). The bare `python -m pytest` of the system Python has no pytest installed; the robot venv is the runner.
- Known behavior: a VENTAS job that fails before HANA returns the window (VPN or connection failure) cannot open a run to mark it failed, because `ventana_desde` is mandatory and never comes from the PC clock. The failure goes to the email and its requests expire in the API.
- Pending: native review, push and PR (user decisions); the user runs `--diagnostico` against SAP.

## Next step

The user ran `--diagnostico` on `8b166f0` and it matched SAP per customer and month in both companies (2026-10-30). Merge #41; then V1 to V3 are done.
