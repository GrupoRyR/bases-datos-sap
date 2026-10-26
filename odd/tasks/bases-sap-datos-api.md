# Feature: Bases SAP, datos y API (session 2)

## Objective

The Sap module: MAESTROS and CARTERA tables with stable `v_*` views, the robot ingest API of `docs/contrato-robot.md`, update requests for the apps and the robot, and `docs/guia-apps.md`.

## Scope and constraints

- Zone: `app/Modules/Sap/**`, `tests/Modules/Sap/**`, migrations `2026_11_02_`, plus `docs/guia-apps.md` (asked by the user) and this document.
- The robot contract does not change. Robot request routes are the contract's: `solicitudes/tomar` (query and take in one call); requests close through their run (`cerrar` / `fallar`).
- No SAP, no real databases, no `.env`. Tests first, invented data.
- Delivery: stacked PRs to `main`, each about 400 lines; code-review, sync with `main`, `composer format`, `lint`, `test` and green CI before each merge, which the user approves.
- Review: receipt-driven development is off (global), so ordinary checks only.

## Tasks

| Id | Task | Branch | Route | Status |
|---|---|---|---|---|
| T1a | Part catalog: companies, datasets, parts, keys and columns | `feat/sap-partes` | inline (spec fully known from the contract) | in progress |
| T1b | MAESTROS and CARTERA tables and `v_*` views | `feat/sap-tablas` | inline (mechanical, follows T1a) | in progress |
| T2 | Robot transport: size limit, rate limit, gzip, HMAC and nonces | `feat/sap-firma` | pending | pending |
| T3 | Runs: start, batches with validation, fail and expiry | `feat/sap-corridas` | pending | pending |
| T4 | Close: apply MAESTROS and CARTERA, inactivate, daily photo, daily counts | `feat/sap-cierre` | pending | pending |
| T5 | Update requests: app keys, join and queue rules, blocked slots, app API | `feat/sap-solicitudes` | pending | pending |
| T6 | Robot take, run link, request expiry | `feat/sap-tomar` | pending | pending |
| T7 | `docs/guia-apps.md` | `feat/sap-guia-apps` | pending | pending |

## Acceptance

- Every contract rule has a test with invented data; the whole suite passes on SQLite locally and MySQL 8 in CI.
- Masters are never deleted; a failed batch or run leaves earlier data intact; CARTERA is replaced in one transaction and never left empty.

## Proposed `.env.example` lines (the user copies them)

```dotenv
ROBOT_HMAC_KEYS=
BASES_SAP_FRANJAS_BLOQUEADAS="00:00,05:00,06:00,12:00,12:30"
```

## Progress

- 2026-10-26: document created; T1 started.
