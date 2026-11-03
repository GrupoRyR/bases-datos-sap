# Feature: Bases SAP security audit fixes

## Objective

Fix the code findings of the 2026-11-03 security audit of `main` at `db50da3`, one PR at a time.

## Scope and constraints

- The user approved the seven-PR plan on 2026-11-03, including the base-zone PRs.
- Every PR branches from the latest `main`. It merges only after `composer format`, `composer lint`, `composer test`, robot `pytest`, `code-review`, green CI and the user's approval.
- Do not read `.env` files and do not connect to SAP, HANA, the VPN or real databases. The user runs the real HANA check with `--diagnostico` after the PR 1 merge.
- Decisions:
  - S-01: option B. Encrypt the HANA connection; validation stays on by default and is turned off in `.env` because there is no HANA certificate. Mirror `GrupoRyR/gestor-cartera`.
  - S-07: no code change, kept as IT item T-03.
  - S-14: no change, risk accepted.

## Tasks

| ID | PR | Findings | Route | Status |
|---|---|---|---|---|
| T1 | 1 Robot TLS and logs | S-01, S-02, S-13, S-19 | delegated writer (4+ robot files) | in progress |
| T2 | 2 Robot guards | S-15, S-16, S-17, S-20 | pending | pending |
| T3 | 3 Sap signature and limits | S-08, S-09, S-11, S-21 if small | pending | pending |
| T4 | 4 Core Entra oid and guests | S-10 | pending | pending |
| T5 | 5 Base HTTPS, CSP, headers | S-03, S-04, S-12 | pending | pending |
| T6 | 6 Log redaction and rotation | S-05 | pending | pending |
| T7 | 7 Dependencies | S-06, S-18 | pending | pending |

## Acceptance

- T1:
  - `HANA_ENCRYPT` and `HANA_SSL_VALIDATE` default to true and turn off only with `false`, `0` or `no`.
  - `dbapi.connect` receives `encrypt` and `sslValidateCertificate`.
  - Every run logs a warning when the connection is unencrypted or unvalidated.
  - A TLS error adds a hint.
  - SMTP verifies the certificate.
  - The log uses the safe API rejection text.
  - Every secret is registered for redaction when the config loads.
- T3: before the merge, ask the user to confirm that the production and robot HMAC secrets are at least 32 bytes.
- T4: existing users keep access, the `oid` is stored on their next sign-in, and B2B guests are rejected as in the gestor.
- T5:
  - The CSP uses a nonce, following the gestor-cartera pattern.
  - The HTTPS redirect does not affect local.
  - Panel screenshots are taken before the merge.
- T7: pytest goes to 9 only if every test stays green.

## Progress

### T1

Branch `fix/robot-tls-logs`, route: delegated writer. Robot suite went from 677 to 707 passing tests (30 new).

- S-01, `d8d37d9 fix(robot): encrypt the HANA connection`:
  - `config._bool_seguro` copies the gestor's helper. Only `false`, `0`, `no` or `n` turn a flag off; an empty, missing or unknown value keeps it on. Adding `n` is a deviation from the acceptance line above: the gestor accepts it too.
  - `HanaConfig` gets `encrypt` and `validar_certificado`, loaded from `HANA_ENCRYPT` and `HANA_SSL_VALIDATE`. There is no `HANA_SSL_TRUSTSTORE`.
  - `hana.conectar` passes `encrypt` and `sslValidateCertificate` to `dbapi.connect`. It logs the mode once per run, behind a module flag, because the robot connects once per company. It warns when the certificate is not validated or the connection is unencrypted.
  - A TLS-looking error (ssl, tls, certificate, handshake) gets `AYUDA_TLS` appended, but only when encryption is on.
  - `--diagnostico` ends with `Conexión a HANA: <mode>.`, and `LEEME.md` gains a TLS section.
  - RED: 24 failed, 91 passed in `test_config.py`, `test_hana.py` and `test_run_robot.py`. GREEN: 115 passed. Full suite: 702 passed.
- S-02, `b88763a fix(robot): verify the SMTP certificate`:
  - `ssl.create_default_context()` goes to `SMTP_SSL` (port 465) and to `starttls` (port 587).
  - RED: 2 failed, 6 passed in `test_notificar.py`. GREEN: 8 passed. Full suite: 704 passed.
- S-13 and S-19, `d1acb89 fix(robot): keep API text out of the log and register secrets at load`:
  - `envio` logs `_mensaje(exc)` instead of the raw exception in three places: failed send, failed open-to-fail and failed `/fallar`.
  - `registro.registrar_secretos(cfg)` registers the VPN password, the HANA password of each company, the robot secret and the SMTP password. `run_robot.main` calls it right after `cargar_config`.
  - RED: 3 failed, 69 passed in `test_envio.py`, `test_registro.py` and `test_run_robot.py`. GREEN: full suite 707 passed.
- Pending:
  - `revisar_solicitudes.main` also calls `cargar_config`, but it is outside T1's edit surface. It still relies on the registration each component already does: `vpn`, `hana`, `api` and `notificar`.
  - `robot/.env.example` needs the two TLS variables. The parent handles it.

## Next step

T1: implement on `fix/robot-tls-logs`.
