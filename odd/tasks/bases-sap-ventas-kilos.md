# VENTAS kilos

## Objective

The Panel needs the weight in kilos of every VENTAS line from 2025 on (ticket `20261125-panel-006`, order `20261125-bases-sap-015`).

## Problem and why

VENTAS has no weight. Lines already loaded, including the frozen history that Comisiones reads, must get their kilos without any other value changing.

## Scope and constraints

- Zone: `app/Modules/Sap/**`, `tests/Modules/Sap/**`, `docs/contrato-robot.md`, `docs/guia-apps.md`; the only Panel exception is the run-type label (`complemento`, first `kilos`).
- The robot side (the SAP expression, «Tot KG» of «AnálisisVentas-1») is order `20261125-bases-sap-016`, stacked on top.
- No other column of a stored line changes; no insert, no delete.

## Design

- `kilos`: omittable quantity, last VENTAS column; `v_ventas` exposes it at the end.
- `codigo_envio`: omittable text up to 50 (OINV/ORIN.ShipToCode; in SDC the CEDI), after `kilos`; `v_ventas` exposes it at the end.
- Run type `complemento` (VENTAS only; first built as `kilos`, renamed in K3): historico month rules, reduced header (key, `fecha_contabilizacion`, `kilos`, `codigo_envio`), close updates only `kilos` and `codigo_envio` and fails without changes on a count mismatch or on lines that do not match MySQL (`sobran`/`faltan`). No 409; repeatable. Not counted as last update.
- A `null` value of `kilos` or `codigo_envio` is accepted in the complemento run, as in `completa`; both columns are required in its header.

## Tasks

- [x] K1 Column `kilos`, migration `2026_11_02_000017`, contract §4.2 and §10, guide §1.4. Route: inline (writer had been the previous session). PR #92, branch `feat/sap-ventas-kilos-columna`, commit `33f794f`.
- [x] K2 Run `kilos`: `RunType::Weights`, `StartRun`, reduced header (`Run::columnsOf`), `ApplyKilos`, `CloseRun`, `CountRun`, `DatabaseDatasetStatuses`, Panel label, contract §10.5, guide. Route: delegated writer (2+ non-trivial files). Branch `feat/sap-ventas-kilos-corrida`, stacked on K1, commit `4dff59c`.
- [x] K3 Rename the run to `complemento` and fill `codigo_envio` too (user-approved): `RunType::Complement`, `PartColumns::salesComplement()`, `ApplyComplemento` (one `UPDATE` per 200 lines with a CASE per column), messages, Panel label `Complemento`, `ComplementoRunTest`, contract §1, §4.1-§4.3, §10 and §10.5, guide §1.4, Sap README. Route: delegated writer (2+ non-trivial files). Branch `feat/sap-ventas-kilos-corrida`.
- [x] K4 Column `codigo_envio` (OINV/ORIN.ShipToCode), migration `2026_11_02_000018`, contract §4.2 and §10, guide §1.4. On PR #92, commit `c99ba81`, merged into the K2 branch.

## Acceptance

The order's test list (section 5) passes; `composer lint` and `composer test` green.

## Progress

- K1: RED observed by reverting `PartColumns`; GREEN 883 tests, 2 skipped; lint green.
- K2: RED 17 failures and 1 error before the code; GREEN Sap and Panel label tests; full suite and lint at commit time.
- K3: RED 22 failing tests (unknown tipo `complemento`, reduced header, label, dataset statuses) before the code; GREEN Sap and Panel label tests (542 passed, 1 skipped); full suite and lint green.
- RDD is off globally: ordinary checks only.

## Next step

The user merges #92, then the K2+K3 PR; the Robot agent stacks order 016 on top, sending `kilos` and `codigo_envio` in the nightly run and the `complemento` run.
