# Feature: Bases SAP robot

## Objective

Build the Python robot of «Bases de datos SAP» (plan §9, session 3): it extracts SAP Business One data from both companies through the Sophos VPN, keeps CSV backups in `BASES_SAP_CSV_DIR` and sends MAESTROS and CARTERA to the app API with HMAC signatures, following `docs/contrato-robot.md` exactly.

## Problem and why

Today three robots (gestor de cartera, CarteraWeb-ETL, CxPWeb-ETL) each pull their own slice of SAP. The plan replaces them with one robot that feeds a central MySQL store through the app, plus a folder archive of the tables no app uses yet.

## Scope and constraints

- Zone: `robot/**` and its tests. The user also authorized one Python job in `.github/workflows/ci.yml` (that job only). This feature document lives in `odd/tasks/` like the cimientos one.
- Never connect to SAP, the VPN, the real app or any real database; never send real email. Tests use fakes.
- Never read or write any `.env`; the robot ships `robot/.env.example` and the user fills `robot/.env`.
- Never commit SAP data. Archive-only categories (plan §5) never reach the API.
- Never select password columns from `OUSR`, nor ID, salary or bank fields from `OHEM`, nor `OCRB`. List columns one by one; never `SELECT *` on SAP tables.
- The contract is shared with «Datos y API»: do not change it. Any mismatch found is reported to the user.
- Gestor de cartera repo is read only: its `etl/queries/cartera.sql` is copied verbatim.
- Base template: skill `robot-sap-hana` (`plantilla/etl/*`): copy and adapt, do not rewrite.
- Delivery: stacked PRs to `main` (cimientos precedent), about 400 changed lines each where the work allows; SQL-only slices may exceed it. RDD is off (global). Each PR: `code-review` skill, sync with `main`, local `pytest` green, CI green, merge only with user approval via `gh pr merge <n> --merge --delete-branch`.

## Design

### Layout

```text
robot/
  .env.example          robot settings (no secrets)
  LEEME.md              install, settings, modes, scheduled tasks, VALIDAR checklist
  pytest.ini            testpaths = tests, pythonpath = etl
  requirements.txt      hdbcli, python-dotenv (production)
  requirements-dev.txt  python-dotenv, pytest (CI and local tests; no hdbcli)
  etl/                  flat modules, like the template (from config import ...)
    config.py registro.py vpn.py hana.py notificar.py     template, adapted
    firma.py            HMAC-SHA256 signing (contract §3)
    api.py              API client (contract §4 and §7.3)
    esquema.py          partes, columns, types, keys, value serialization
    consultas.py        query loading per schema, incremental/IN/COUNT wrappers
    carpeta.py          CSV layout and retention under BASES_SAP_CSV_DIR
    trabajos.py         jobs from taken requests or the nightly run
    extraccion.py       phase 1 (VPN up): all SAP reads
    envio.py            phase 2 (VPN down): CSV and API runs
    archivo.py          archive-only categories (fotos and registros)
    catalogo.py         --catalogo
    diagnostico.py      --diagnostico
    bloqueo.py          lock file and blocked time windows
    run_robot.py        CLI: --completa, --archivo, --catalogo, --diagnostico
    revisar_solicitudes.py   short script run every minute
  queries/
    maestros/<parte>.sql                 shared by both schemas
    maestros/<ESQUEMA>/<parte>.sql       per-schema override (precios)
    cartera/cartera.sql                  verbatim copy from gestor de cartera
    catalogo/*.sql  diagnostico/*.sql
    archivo/<CARPETA>/<TABLA>.sql
  scripts/instalar_tarea.ps1
  tests/
```

### Settings (`robot/.env`)

- VPN and HANA: template names (`SOPHOS_*`, `HANA_HOST`, `HANA_PORT`, `HANA_TIMEOUT`). One HANA user per company: `HANA_SGX_USER`, `HANA_SGX_PASSWORD`, `HANA_SGX_SCHEMA` (default `SEGUREX`), `HANA_SDC_USER`, `HANA_SDC_PASSWORD`, `HANA_SDC_SCHEMA` (default `HBT_SDERIVADOS`).
- API: `BASES_SAP_API_URL`, `BASES_SAP_ROBOT_KEY_ID`, `BASES_SAP_ROBOT_SECRET` (contract §9).
- Folder: `BASES_SAP_CSV_DIR`, default `C:\Users\Claude\Documents\CEREBRO\SAP\BASES_DE_DATOS`.
- Windows: `BASES_SAP_FRANJAS_BLOQUEADAS` (default `00:00,05:00,06:00,12:00,12:30`), margin 15 minutes.
- Alerts: template `ALERTA_SMTP_*` and `ALERTA_DESTINATARIOS` (TI mailbox, plan §10 pending).
- `BASES_SAP_ARCHIVO_HISTORIAL_DOCUMENTOS` (default off): enables `ADOC`, `ADO1`, `AJDT`, `AJD1` only after the user saw their size in the catalog (plan §5).

### Time

Bogotá has no DST, so the robot uses a fixed `UTC-05:00` offset (`BOGOTA`) instead of `zoneinfo`, which needs the `tzdata` package on Windows.

### Two phases (skill rule 1)

Phase 1, VPN up: connect, one HANA connection per company, every query of every job (data plus `COUNT(*)` for nightly runs), then VPN down in `finally`. Phase 2, VPN down: CSV files, then API runs. Everything extracted in one invocation shares one VPN session. Asking the API for requests (`/solicitudes/tomar`) always happens without VPN, before phase 1.

### MAESTROS queries

- Aliases are the contract column names (`AS "codigo"`), so the mapping is identity; the cartera query keeps the gestor's labels and maps through `esquema` like the gestor does.
- `actualizado_en_sap` is a SQL `TIMESTAMP`: `ADD_SECONDS(CAST(IFNULL("UpdateDate","CreateDate") AS TIMESTAMP), <UpdateTS HHMMSS as seconds, 0 if null or if UpdateDate is null>)`; Python formats it with `-05:00`.
- `activo` comes as `'Y'`/`'N'` from SQL (contract §5.1 rules) and is serialized as a boolean.
- Incremental (`cambios`): the robot wraps the file: `SELECT X.* FROM (<file>) X WHERE X."actualizado_en_sap" >= ?` with `desde` converted to Bogotá local time. `desde = null` means no filter. The file itself has explicit columns; the wrapper only projects them.
- Direcciones and contactos: the files return rows of partners with `CardType IN ('C','S')`. If every partner parte of the run is `todo`, the file runs unfiltered and Python keeps rows of sent partners; otherwise the wrapper filters `X."codigo_socio" IN (?, …)` in chunks of 500 codes taken from the partners actually extracted.
- `COUNT(*)` for `conteo_sap` (nightly only): `SELECT COUNT(*) FROM (<file>) X`, same connection, right after the data.
- Per-schema overrides: `queries/maestros/<ESQUEMA>/<parte>.sql` wins over `queries/maestros/<parte>.sql` (used for `precios`, whose list name may differ per company).
- Marked `VALIDAR CON DATOS REALES` in the SQL: `UpdateTS` in `OITM`, the PÚBLICA list name in `OPLN`, `@HBT_MUNICIPIO` in Derivados, `CRD1.County` as municipality code, the `validFor`/`frozenFor` meaning of `activo`, and the cartera accounts in Derivados.

### Values (contract §4.2)

Types: `TEXTO` (trimmed to 4,000), `ENTERO` (JSON number), `MONTO` (decimal text, 2 decimals, half up), `FECHA` (`AAAA-MM-DD`), `HORA` (ISO 8601 with `-05:00`), `BOOL` (`Y`/`N`, `1`/`0`, bool). Before sending, the robot fails the run with a clear message if a required column is null or empty, a key repeats inside the run, or a `todo` parte has 0 rows (the API would answer 422).

### Runs (contract §4)

- Nightly `--completa` (02:00): MAESTROS and CARTERA for SGX and SDC, every parte in `todo`, `conteo_sap` on close, CARTERA with `fecha_corte` = yesterday and the daily photo `CARTERA\<emp>\historico\<yesterday>.csv`. It first takes pending requests (`tomar`) and attaches the ids to the matching run. It also appends the nightly archive registros in the same VPN session.
- Request runs: requests are grouped by company and conjunto (§7.3). Partes per §7.1, union over the group; `clientes`, `proveedores`, `articulos` in `cambios`, `direcciones` and `contactos` follow their partner (`cambios`), the rest `todo`. `desde` per parte is the oldest of the group, or `null` if any request has `null`. CARTERA `fecha_corte` = today.
- Batches: up to 1,000 rows, one parte each, numbered from 1 per run, gzip by default. Network error or 5xx: resend the same body (new signature) up to 3 times with growing wait. 429: wait `Retry-After`. 401: no retry, clear error about the key or the clock. Close 409 with `faltan`: resend those batches and close once more.
- Failure after a run opened: `/fallar` with a short message (no secrets, no SAP data). Failure before the run opened (VPN, HANA) on a job with requests or the nightly run: open the run and fail it right away, so the requests become `fallida` with the reason. One failing job never stops the others; one email to TI lists every failure; exit code 1.

### Folder (`BASES_SAP_CSV_DIR`, its `LEEME.md`)

- `MAESTROS\<SGX|SDC>\<parte>\aaaa-mm-dd_hhmm.csv` and `CARTERA\<emp>\cartera\aaaa-mm-dd_hhmm.csv`: one per run, deleted after 90 days by the date in the name.
- `CARTERA\<emp>\historico\aaaa-mm-dd.csv`: daily photo, never deleted.
- Archive fotos (Sunday 03:00): `<CARPETA>\<emp>\<TABLA>\aaaa-mm-dd.csv`, kept 52 weeks. Registros (nightly): `<CARPETA>\<emp>\<TABLA>\aaaa-mm.csv` by the row's month, appended, never deleted. The registro watermark is the last date in the newest monthly file (the folder's `LEEME.md` says the robot uses the files to know what it already took); each night takes rows after that date up to yesterday, whole days only.
- `_CATALOGO\<emp>\{tablas,campos_usuario,tablas_usuario,columnas}\aaaa-mm-dd.csv` (Sunday and `--catalogo`). `columnas` lists `SYS.TABLE_COLUMNS` for every table the robot reads, to confirm the `VALIDAR` items.
- `_DIAGNOSTICO\<emp>\<parte>\aaaa-mm-dd_hhmm.csv` and `_DIAGNOSTICO\resumen\aaaa-mm-dd_hhmm.csv` (filas, conteo SAP, activos, error per parte) plus the `OPLN` list names; 90 days.
- CSV: UTF-8 with BOM, `;` separator, header with the contract column names (template).

### Archive

Registry in `archivo.py`: carpeta, table, SQL file, mode (`foto` or `registro`), date column for registros, `grande` flag (history tables, off by default). Every SQL lists columns one by one and is marked `VALIDAR CON DATOS REALES` (names from SAP B1 docs, to be confirmed with `columnas`). `@HBT_*` tables are discovered in `SYS.TABLES` and read with a column list built from `SYS.TABLE_COLUMNS`, skipping password-like names. Archive extraction is fail-soft per table: errors go to the log and the final email, the other tables continue. `ORTT` is a nightly registro; the rest of `CONTABILIDAD` is a Sunday foto. `LICENCIAS` is manual.

### Request check (every minute)

`revisar_solicitudes.py`: inside a blocked window (±15 minutes) it exits without asking the API; otherwise it takes the lock (`robot/state/robot.lock`, exclusive create, stale after 3 hours), asks `tomar` with `max: 20`, exits if empty, else runs the request jobs. The nightly and Sunday runs wait up to 20 minutes for the lock instead of skipping. `scripts/instalar_tarea.ps1` registers three tasks: every minute, nightly 02:00 and Sunday 03:00.

## Tasks

| ID | Task | Branch | Route | Status |
|---|---|---|---|---|
| T1 | Robot base from the template (config, logging, VPN, HANA, alerts), requirements, pytest setup, `.env.example`, CI Python job | `feat/robot-base` | delegated writer (2+ non-trivial files) | PR #14 open |
| T2 | HMAC signing with the contract vector and the API client with retries, gzip and a fake API | `feat/robot-api` | delegated writer | PR #15 open |
| T3 | Parte schema, value serialization, MAESTROS, CARTERA, catalog and diagnostic queries, query loader | `feat/robot-consultas` | delegated writer | PR #16 open |
| T4 | Jobs, two-phase extraction and sending, folder layout and retention, nightly run and cartera photo | `feat/robot-corridas` | delegated writer | PR #19 open |
| T5 | Archive categories (fotos, registros), `--archivo`, `--catalogo`, `--diagnostico` | `feat/robot-archivo` | delegated writer | PR #21 open |
| T6 | Lock, blocked windows, request check script, scheduled tasks script, robot `LEEME.md` | `feat/robot-solicitudes` | delegated writer | PR open |

## Acceptance

- `python -m pytest` green in `robot/` locally and in the CI job; every test uses fakes.
- The contract HMAC vector reproduces the documented signature.
- No query file has `SELECT *`; `OUSR` and `OHEM` queries list only allowed columns; nothing reads `OCRB`.
- Archive categories never reach the API client.
- Each PR: `code-review` findings fixed, CI green, user approves the merge.

## Checks

- `cd robot && python -m pytest` (Python 3.14 locally and in CI).
- PowerShell parse check of `robot/scripts/instalar_tarea.ps1`.

## Progress

Decision (user, 2026-10-26): `robot/` keeps Spanish identifiers and comments like the template, an exception to the CLAUDE.md conventions.

### T1 (done, PR #14)

- Route: delegated writer. Commits `76281cc`, `c1252a2`, `5b90528`, review fixes `5d1f52c`.
- Test first: tests failed with `ModuleNotFoundError` before the modules existed; review fixes had RED tests first.
- `code-review` (high): 4 fixed (HANA error mapping, traceback redaction, invalid numbers, SMTP 465), 1 no change (Spanish code, user decision).
- Checks: `python -m pytest` 52 passed locally; CI robot job green.

### T2 (done, PR #15)

- Route: delegated writer. Commits `ab59c91`, `8d07930`, review fixes `26377ce`.
- Contract HMAC vector reproduced. `code-review` (high): 4 fixed (lost responses on iniciar/cerrar/fallar, 422 detail, redirects).
- Checks: `python -m pytest` 100 passed locally.

### T3 (done)

- Route: delegated writer. Commits `d17232f`, `79a9cd7`, `601f4d9`.
- Checks: `python -m pytest` 269 passed locally.
- Contract notes for «Datos y API»: `precios.activo` has no rule (robot sends `true`); `municipios.codigo` and `direcciones.municipio_codigo` have no type (robot sends text); `direcciones` has no `activo` column, so the API keeps its own.

- `code-review` (high): 1 fixed (case-insensitive keys), 1 no change (trim collisions already caught), 1 skipped (one bad SAP row fails the parte, as the contract requires).

### T4 (done, PR #19)

- Route: delegated writer. Commits `25fa139`, `5d8d287`, `70cdbf0`; review fixes `8d608bc` (HANA text kept out of /fallar), `32f4bef` (nightly takes requests after extraction).
- Checks: `python -m pytest` 353 passed locally.

### T5 (done, PR #21)

- Route: delegated writer. Archive SQL, archive/catalog/diagnostic modules and modes in three commits.
- `code-review` (high): 1 fixed by docs (load the registro history once by hand), 1 skipped pending the user (back-dated registro rows, e.g. a late ORTT rate).
- Checks: `python -m pytest` 525 passed locally.

### T6 (done)

- Route: delegated writer. Lock and windows, the every-minute script, scheduled tasks and the full `robot/LEEME.md`; follow-ups: wait out a blocked window instead of skipping the run, retry the lock while Windows deletes it.
- `code-review` (high): 1 fixed (lock PermissionError), 1 skipped (a long request run can reach the next window; the 15-minute margin is the guard).
- Checks: `python -m pytest` 576 passed locally; PowerShell parse check of `instalar_tarea.ps1` with 0 errors.

## Next step

User reviews and approves the merges bottom-up (#14 first, retargeting each next PR to `main`). Then the user runs `--catalogo` and `--diagnostico` against real SAP (plan §9, session 4) and the VALIDAR items are fixed.
