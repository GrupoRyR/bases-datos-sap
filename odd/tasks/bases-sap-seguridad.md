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
| T1 | 1 Robot TLS and logs | S-01, S-02, S-13, S-19 | delegated writer (4+ robot files) | done (#49, merged d0766af) |
| T2 | 2 Robot guards | S-15, S-16, S-17, S-20 | delegated writer (4+ robot files) | done (#50, merged 5a323c9) |
| T3 | 3 Sap signature and limits | S-08, S-09, S-11, S-21 if small | delegated writer (2+ Sap middleware, model and test files) | done (#51, merged 21697be) |
| T4 | 4 Core Entra oid and guests | S-10 | delegated writer (2+ Core auth, controller and test files) | in progress |
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
- S-19 in `revisar_solicitudes`, `fix(robot): register secrets at load in revisar_solicitudes`:
  - `revisar_solicitudes.main` also calls `registrar_secretos(cfg)` right after `cargar_config`.
  - RED: the new test failed, because in a blocked slot no component registers anything. GREEN: full suite 708 passed.
- `code-review` (high), 6 findings, `fix(robot): address review of the HANA TLS hint and diagnostic line`:
  - Fixed: the TLS hint leaves out `HANA_SSL_VALIDATE=false` when it is already off. The diagnostic line now says "Modo TLS configurado". `LEEME.md` says the hint is in `robot.log`, not in the email. The secret-registration comment is fixed. `_bool` and `_bool_seguro` share `_VERDADEROS`.
  - Not changed in code: a verified SMTP certificate can stop alerts if the mail server's certificate is private. After the merge, TI sends a test alert.
  - RED: 2 failed. GREEN: full suite 709 passed.
- Pending: `robot/.env.example` needs `HANA_ENCRYPT` and `HANA_SSL_VALIDATE`. The permission rules block it, so the user adds the lines.

### T2

Branch `fix/robot-guards` from `main` at `d0766af`, route: delegated writer. Robot suite went from 709 to 825 passing tests (116 new, most of them parametrized cases).

- S-15, `2379dbd fix(robot): skip more secret-looking @HBT columns`:
  - `archivo.RE_CLAVE` keeps `PASS`, `PWD`, `CLAVE` and `CONTRASE` and adds `TOKEN` and `SECRET` (also `SECRETO`) as substrings. `TOKEN` as a substring also skips names like `U_TOKENIZADO`; that is accepted.
  - `KEY`, `APIKEY`, `ACCESSKEY`, `PRIVATEKEY` and `PIN` match only as a whole `_`-separated name part, with optional trailing digits (`U_PIN2`). `U_SHIPPING`, `U_OPINION`, `U_KEYWORD`, `U_MONKEY`, `U_SPINE` and `U_Turkey` are still read. Adding `ACCESSKEY` and `PRIVATEKEY` goes slightly beyond the brief.
  - `LEEME.md` lists the skipped kinds under Carpeta de CSV. There was no `@HBT` section, so the note follows the archive-categories paragraph.
  - RED: 17 failed, 17 passed in `test_archivo.py -k es_clave`. GREEN: `test_archivo.py` 53 passed.
- S-16, `2ccc6e7 test(robot): forbid OHEM and OUSR sensitive columns in queries`:
  - `test_queries.columnas_sensibles(sql)` reads the `FROM` and `JOIN` tables of the comment-free SQL. For `OHEM` it forbids `govID`, `passportNo`, `salary`, `salaryUnit`, `bankCode`, `bankBranch`, `bankAcount`, `homeTel`, `homeStreet` and `birthDate` as whole words. For `OUSR` and `AUSR` it forbids any identifier containing `PASSWORD`.
  - It runs over every `.sql` in `robot/queries/**`, and seven unit cases cover the checker, including the false positives `salaryHistory`, another table and a comment.
  - RED: a temporary mutation added `T0."govID"` to `OHEM.sql` and `T0."PASSWORD4"` to `AUSR.sql`: 2 failed, 81 passed. The mutation was reverted. GREEN: `test_queries.py` 254 passed.
- S-17, `e1bcee5 fix(robot): purge orphaned temp files in the CSV folder`:
  - `Carpeta.purgar_temporales()` removes `.<name>.*.tmp` files (`PATRON_TEMPORAL`) anywhere under the CSV root whose modification time is more than one day old against the PC clock. Younger ones are kept, and so are other `*.tmp` files without the leading dot.
  - It never reads the contents. The log says only how many were removed, and an undeletable file is logged by path and does not stop the others.
  - `run_robot.ejecutar_trabajos` calls it after `purgar_corridas`, in its own `try`, so it runs in the nightly and in every request check that has work. A failure goes to the `CARPETA` failures.
  - `LEEME.md` gets a table row and a paragraph.
  - RED: 4 failed, in `test_carpeta.py` (missing method) and `test_run_robot.py` (orphan kept). GREEN: `test_carpeta.py` and `test_run_robot.py` 71 passed.
- S-20, `51526a3 docs(robot): document the default CSV folder`:
  - `LEEME.md` Configuración item 6 says `BASES_SAP_CSV_DIR` falls back to the TI PC folder and must be set explicitly, outside the repo, on any other PC. There is a one-line comment on `CSV_DIR_POR_DEFECTO`.
  - No behavior change, so there is no RED. Full suite: 825 passed.
- `code-review` (high), 3 findings, `test(robot): catch schema-qualified tables in the sensitive-column guard`:
  - Fixed: `_tablas_leidas` took the schema of `FROM "SEGUREX"."OHEM"` as the table, so the guard would not see it. RED: 1 failed. GREEN: full suite 826 passed.
  - Skipped:
    - camelCase `KEY`/`PIN` names such as `U_UserPin` are not skipped. Catching them would also skip innocent names.
    - the temp purge walks the CSV tree on every run with work. That costs little and the robot holds a single lock.

### T3

Branch `fix/sap-robot-hardening` from `main` at `5a323c9`, route: delegated writer. Full suite went from 658 to 670 passing tests (12 new, 2 skipped).

- S-08, `2acf05d fix(sap): reject robot requests with a query string`:
  - `VerifyRobotSignature` answers 400 `Las rutas del robot no llevan query string.` to any robot request with a query string, before the signature check, so it never burns a nonce. It logs `sap.robot.signature_rejected` with reason `query_string`, the key id and the IP.
  - The robot never sends one: `robot/etl/api.py` builds the URL as `BASES_SAP_API_URL` plus a fixed path.
  - Contract change, pending the user's confirmation on the PR: §3 gains one line saying a query string gets 400 and does not spend the nonce.
  - `RobotClient::post` takes a `query` that goes in the URL but not in the signature.
  - RED: 2 failing in `RobotTransportTest.php` (200 instead of 400, no warning logged), 35 passed. GREEN: 37 passed.
- S-09, `f5f5cd8 fix(sap): limit failed app-key attempts per IP`:
  - `AuthenticateClientApp` counts each 401 (missing, unknown or revoked key) under `sap-apps-fail|<ip>` for 60 seconds. Past `sap.apps.failed_auth_per_minute` (default 10, module config, no env var) it answers 429 `Demasiados intentos con una llave inválida.` with `Retry-After`, before any key lookup. A good key never counts.
  - Changed after code-review: the key is looked up first. A good key always goes through, even from an IP over the limit, because the apps on one server share its IP and one with a revoked key must not lock out the rest. Only that IP's bad keys get 429.
  - RED: 4 failed in `AppApiTest.php` (401 instead of 429), 17 passed. GREEN: 21 passed.
- S-11, `adf4efe fix(sap): ignore robot keys with a short secret`:
  - `VerifyRobotSignature::secretFor` is the only place that parses `ROBOT_HMAC_KEYS`. A pair whose secret is under 32 bytes (`strlen`) makes its key unknown (`unknown_key`) and logs `sap.robot.short_secret` with the key id only.
  - The test secrets grow to 35 and 34 bytes. The contract test vector keeps its 23-byte secret: it checks `RobotSignature::sign`, not the middleware.
  - RED: the 31-byte case got 200 and no warning was logged (2 failing of 40). With the check in place, 126 Sap tests failed with 401 until the test secret was lengthened. GREEN: Sap suite 342 passed, 1 skipped.
- S-21, `d6bfb18 refactor(sap): replace guarded with fillable on Sap models`:
  - `ClientApp` fills `nombre` only; `AppKeys::issue` force-fills the hash and prefix, as `rotate` already did. `Run` fills what `StartRun` sets. `UpdateRequest` fills what `PlaceRequest` sets. Everything else already used `forceFill` or query updates.
  - Four test fixtures that build finished runs use `Run::forceCreate`.
  - RED: 3 failed in the new `MassAssignmentTest.php`. GREEN: module suites 580 passed, 1 skipped.
- Checks: `composer format` passed, `composer lint` passed (Pint and Larastan, 0 errors), `composer test` 670 passed, 2 skipped.
- `code-review` (high), `fix(sap): let good app keys through an IP over the failed-key limit`: before this fix, a misconfigured app could lock out its sister apps on the same server. RED: the new good-key test got 429. GREEN: `composer test` 671 passed, 2 skipped; lint passed.

### T4

Branch `fix/core-entra-oid` from `main` at `21697be`, route: delegated writer. Full suite went from 671 to 686 passing tests (15 new, 2 skipped).

- S-10, `9b06b27 fix(core): reject Entra guest accounts at sign-in`:
  - `MicrosoftIdentity` gets `guest`. `fromGraph($profile, $tenantId, $guestClaim = false)` marks a guest when the `acct` claim is 1 or the user principal name contains `#EXT#` in any case, as in the gestor.
  - `SocialiteMicrosoftIdentityProvider` passes the optional `acct` claim of the id token (`1` or `"1"`).
  - `SignInWithMicrosoft::handle` throws `RejectionReason::Guest` right after the tenant check, before any lookup or write. It is audited as `core.auth.rejected` with reason `guest` and the e-mail, without tokens. A guest is never created, linked or promoted, even with an e-mail in `core.admins`.
  - The login page tells a guest `Las cuentas de invitado no pueden entrar. Entra con tu cuenta del Grupo RYR o habla con TI.` (`core::ingreso.invitado`, via `RejectionReason::messageKey()`). Every other reason keeps the one `rechazado` message. This is a deviation from "the same message for every reason": the guest message only describes the guest's own account, as in the gestor.
  - RED: 4 failed and 11 errors, 59 passed in `tests/Modules/Core/Feature/Auth` (guests signed in; `guest` was undefined). GREEN: Core suite 135 passed.
- Existing users keep access, no new commit: `MicrosoftCallbackTest` already pins it. "recognizes a registered user by e-mail in any case and links their Microsoft account" stores `microsoft_id` for a user without one and keeps their role. "recognizes a registered user by Microsoft id, even after an e-mail change" signs a linked user in by oid when `mail` changed.
- Checks: `composer format` passed, `composer lint` passed (Pint and Larastan, 0 errors), `composer test` 686 passed, 2 skipped.

## Next step

T4: `code-review`, push `fix/core-entra-oid` and open the PR. After the merge, IT can also set "Assignment required = Yes" on the Entra enterprise app (T-07).
