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
| V1 | Contract §10 VENTAS and this feature document | `docs/contrato-ventas` | inline (one doc file) | PR open |
| V2 | App: `ventas` connection, table and `v_ventas`, batch rules, window apply, requests, nightly count | — | delegated writer | pending |
| V3 | Robot: query copy, HANA window, nightly run, requests, `--diagnostico`, CSV and retention | — | delegated writer | pending |

## Acceptance

- Contract §10 approved by the user; the panel session can build on it.
- App and robot tests green with fakes; CI green.
- The user runs `--diagnostico` and compares with SAP before the final merge.

## Progress

### V1

- Contract section written; documentation only, structural readback.

## Next step

User reviews the contract PR. Then V2 on a branch stacked on `docs/contrato-ventas`.
