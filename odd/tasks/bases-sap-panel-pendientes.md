# Feature: Bases SAP panel follow-ups

## Objective

Close the four items the panel left open, with no logic changes outside them.

## Scope and constraints

- Branch `fix/panel-pendientes` from `main` at `d6993db`, one PR to `main`.
- The user authorized each item explicitly (2026-10-30), including the files outside this session's usual zone: the Sap contract `IssuedAppKey`, the panel views, a base UI component in `resources/views/components/ui/`, `odd/tasks/bases-sap-cimientos.md` and `StartRunTest`.
- Before merge: `composer format`, `composer lint`, `composer test`, robot `pytest`, `code-review`, green CI and the user's approval.

## Tasks

| ID | Task | Route | Status |
|---|---|---|---|
| P1 | `StartRunTest` runs on a fixed clock, outside the blocked slots | inline (one test file) | done |
| P2 | `IssuedAppKey` carries `keyPrefix`; the panel's new-key page uses it | inline (contract, two producers, one controller) | done |
| P3 | Base form field component (label, control, error) used by the panel forms | delegated writer (2+ non-trivial files) | pending |
| P4 | `bases-sap-cimientos.md` names the v2 brand PNG logo, not the SVG | inline (one doc) | pending |

## Acceptance

- `StartRunTest` passes at any wall-clock time, including 12:00 to 12:45 Bogota.
- The new-key page audits and shows the prefix from `IssuedAppKey`, with no extra lookup.
- The panel's text and select fields render through one component with the same markup and accessibility attributes as before.
- The cimientos document matches `resources/views/components/ui/logo.blade.php`.

## Progress

### P1

- `StartRunTest` froze the real second, so within 15 minutes of the 12:00 and 12:30 blocked slots a request was queued instead of taken, and two Derivados tests got 422. It now travels to 2026-10-23 10:45 Bogota.
- RED: the same file at 12:05 fails those 2 tests (24 of 26 pass). GREEN: at 10:45, 26 of 26 pass.

### P2

- `IssuedAppKey` gains `keyPrefix` (the stored first 12 characters). `AppKeys` and the panel fake fill it; the panel's new-key page audits `$issued->keyPrefix` instead of listing every app to find it again.
- RED: `ClientAppKeysTest` 2 of 4 failed (`Undefined property IssuedAppKey::$keyPrefix`). GREEN: `ClientAppKeysTest` and `ConnectedAppsTest`, 23 of 23. `composer lint` passed.

## Next step

P4, then P3.
