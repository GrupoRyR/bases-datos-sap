# Automatic deploy (pilot)

## Objective

Merging a PR into `main` deploys the server, with QA before and after, and no command typed or output pasted by the user (ticket `20261125-centro-001`, accepted 2026-11-27). After each deploy, the robot updates itself and runs the complements it needs, and a read-only comparison against SAP closes the deploy.

## Problem and why

Today the coordinator deploys by SSH with the user's own key (alias `cartera-cpanel`). That key is a full shell on a cPanel account that hosts several apps and their `.env` files. The pilot replaces it with a forced-command key that GitHub Actions uses, and replaces the SAP report the user downloads by hand with a robot comparison mode.

## Scope and constraints

- Base zone (`deploy/`, `.github/`, `tests/Deploy/`, `docs/arquitectura.md` §12): approved by the user when they accepted the pilot.
- `app/Modules/Sap/**`: Datos y API. `robot/**`: Robot.
- Any change to `docs/contrato-robot.md` needs the user's yes before its PR merges.
- Only the user creates and installs keys, stores the GitHub secret, sets secrets on the server and authorizes the first runner test (`ping`) and the first real deploy through the workflow.
- No agent reads a `.env`, a key or a secret; no agent runs anything remote.
- GrupoRyR is a personal account (GitHub Free): the deploy key is a repository secret, so the server must refuse to deploy any commit that is not already on `origin/main`.

## Design

- Forced command: `restrict,command="bash ~/bases-sap/deploy/despachar.sh"` in `authorized_keys`. The dispatcher reads `$SSH_ORIGINAL_COMMAND` and accepts only:
  - `ping`, which answers `ok`;
  - `pendientes`;
  - `previsualizar`;
  - `puede-desplegar`;
  - `desplegar <sha>`;
  - `estado`.
- `desplegar <sha>`:
  - takes a lock;
  - runs `git fetch`;
  - checks that `<sha>` is on `origin/main` and is a fast-forward of HEAD;
  - checks `puede-desplegar`;
  - runs `deploy/deploy.sh`;
  - checks that HEAD equals `<sha>`;
  - never prints the `.env`.
- `puede-desplegar` (artisan command in Sap, read-only) refuses to deploy:
  - within `slot_margin_minutes` of a blocked slot;
  - in the nightly window 01:45 to 02:15;
  - while any robot run is open.

  The robot retries a 5xx only 3 times in 14 s (`robot/etl/api.py`), so a deploy in the middle of a run would fail that run.
- `deploy.yml`, on push to `main`:
  1. `composer audit --locked --no-dev`;
  2. `puede-desplegar`;
  3. `previsualizar`, with its SQL going to the job summary;
  4. `desplegar ${{ github.sha }}`;
  5. `/up` with retries, plus a smoke check (`/` answers 302, `public/build` manifest assets answer 200);
  6. `estado`;
  7. the job summary.

  It never retries; a failure says which step failed and how to revert.
- Rollback: the deploy is in place (`git pull`). With no migration in the release, the dispatcher can return to the previous commit. With migrations, it only reports and stops (decision pending, see T7).
- `.env` without `nano`: `deploy/env-cambios` (non-secret `KEY=value`) is applied with an allowlist versioned in the repo; `set-secret <KEY>` on the server reads the value without echo, and only the user runs it.
- After the deploy (robot side, design to agree with Robot and Datos y API): the robot checks the server's deployed commit, runs `git pull --ff-only` outside slots and runs, then runs the complements that commit declares. `--comparar` is a read-only mode that compares SAP counts and totals per company and month with the same aggregates from the API.

## Tasks

- [x] T1 `sap:puede-desplegar` artisan command (slots, nightly window, open runs), with tests. Route: Datos y API session. PR #96, merged at `579dd79`. Follow-ups (same timezone in both windows, reject an empty window, document that the guard cannot see the robot's extraction phase) go in a later PR.
- [x] T2 Phase 0: `deploy/despachar.sh` (all orders; `desplegar` guarded), `tests/Deploy` tests with stubs, `.github/workflows/deploy-ping.yml` (`workflow_dispatch`, `ping` only), docs §12 with the user's one-time steps. Route: delegated writer.
- [ ] T3 User: create the key, install the forced-command line, store the `BASES_SAP_DEPLOY_KEY` secret and the `known_hosts` variable, then authorize one `ping` run. If the runner cannot reach port 22, switch to the server-pull cron design (research §2.3 b').
- [ ] T4 `deploy.yml` (Phase 1) on push to `main`. Route: delegated writer, after T1 to T3. It carries two review items from #98. First, `estado` must count only the errors since the deploy, not the whole day. Second, only the timestamp and exception class of each error line may reach the Actions log, never the message, because it can hold SAP data.
- [ ] T5 `deploy/env-cambios`, the allowlist and `set-secret`. Route: delegated writer.
- [ ] T6 Robot self-update and post-deploy complements; deployed-version endpoint. Route: Robot and Datos y API. The user approved the contract change on 2026-11-27 («Ambas piezas»). `deploy.sh` writes the deployed commit to `storage/app/deploy/commit` (git-ignored); `POST /api/robot/v1/version` reads it.
- [ ] T7 Robot `--comparar` read-only mode and its aggregates endpoint, as the last step of each deploy and complement. Route: Robot and Datos y API, approved 2026-11-27. The `/totales` shape is fixed by the coordinator: groups by month (VENTAS), `actual` (CARTERA) or part (MAESTROS), with `filas`, `sumas` and `nulos`. Counts must match exactly; sums must match after rounding.
- [ ] T8 Five deploys in a row with no user commands (success criterion).

## Acceptance

- `composer lint` and `composer test` green, the robot tests green, and the dispatcher tests cover every order and every refusal.
- The `ping` run from a GitHub runner answers `ok`.
- Five deploys in a row through the workflow, with no command or output from the user.

## Progress

- 2026-11-27: the ticket was accepted, and the coordinator made the first deploy by hand (`6a9323c`). The answers to the ticket questions are in the ticket's history.
- 2026-11-27: T2 done in `d982bf8` (dispatcher, `DEPLOY_REF` in `deploy.sh`, `tests/Feature/Deploy/DispatcherTest.php`) and `63d63b5` (`deploy-ping.yml`, docs §12). Dispatcher tests RED (35 failed, script missing) then GREEN (35 passed, 145 assertions); `composer lint` green; `composer test` 948 passed, 2 skipped, on Windows. shellcheck is not installed locally.

- 2026-11-27: coordinator review of T2 added two things. A lock older than 30 minutes is taken over, because nobody can remove it with a forced-command key: test RED (exit 75), then GREEN. `deploy.sh` now records the deployed commit. Dispatcher tests: 36 passed. `composer lint` green.
- 2026-11-27: the `/code-review` of #98 found one important issue. A retry after a half-failed deploy said `already deployed`, because HEAD moves before migrate. It is fixed by also requiring `storage/app/deploy/commit` to equal the sha (test RED, then GREEN). `estado` now uses the Bogota date. Dispatcher tests: 37 passed.

## Next step

PR for T2. Then the coordinator deploys #96 and this branch by hand so the server has the dispatcher and the guard, and the user does T3.
