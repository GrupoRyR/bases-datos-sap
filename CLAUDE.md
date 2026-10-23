# Bases de datos SAP — rules for agents

Central store of SAP Business One master data for the Grupo RYR apps (Segurex SGX and Soluciones y Derivados SDC): Laravel 13, PHP 8.3, MySQL on GoDaddy and Microsoft Entra ID, fed by a Python robot that runs on the TI PC.

The «Bases SAP: cimientos» session expands this file with module zones, provider hooks and the local protections of `main`. Until then, these rules apply.

## Read first

- `docs/plan-bases-sap.md`: scope, decisions, schedules, folder layout and sessions. It is the source of truth.
- `docs/arquitectura.md` and `docs/contrato-robot.md`, once «cimientos» writes them. The robot contract is shared by two parallel sessions: never change it without the user's approval.

## Hard rules

- Write only inside the zone your session owns (plan §9). If you need anything else, stop and ask the user.
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

## Conventions

- UI text: Spanish, informal "tú", sentence case. Code, identifiers and comments: English.
- Commits: Conventional Commits, one work unit per commit, tests and docs with the code, no co-author or AI attribution lines.
- PRs: about 400 changed lines; use chained PRs for larger work.
- Tests first when a runnable test with a clear expected result exists.

## Skills

Load the ones that apply before working: `work-unit-commits`, `chained-pr`, `frontend-marca-sgx-sydc`, `robot-sap-hana`, `cpanel-deploy`.
