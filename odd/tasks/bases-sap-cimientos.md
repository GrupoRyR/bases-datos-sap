# Feature: Bases SAP cimientos

## Objective

Lay the foundation of «Bases de datos SAP» (plan §9, session 1) so the «Datos y API», «Robot» and «Panel» sessions can work in parallel.

## Scope and constraints

- Zone: skeleton, CI, push protections, `CLAUDE.md`, `docs/arquitectura.md`, `docs/contrato-robot.md`, Core module, migrations `2026_11_01_`.
- No SAP, VPN, GoDaddy or real databases; no `.env` reads or edits (propose `.env.example` lines).
- Delivery: stacked PRs to main, about 400 changed lines each; merge bottom-up, retargeting the next PR to `main` before each merge.
- RDD: off (global). Each PR runs the `code-review` skill, syncs with `main`, passes `composer format`, `composer lint`, `composer test` and green CI before merge.

## Tasks

| ID | Task | Branch | Route | Status |
|---|---|---|---|---|
| T1 | Skeleton: Laravel 13, PHP 8.3, three MySQL connections (app, maestros, cartera), Pest, Pint, Larastan, CI with MySQL 8, pre-push hook and `.claude/settings.json` guards | `feat/esqueleto` | delegated writer (many files) | pending |
| T2 | Module zones `app/Modules/{Core,Sap,Panel}` with base provider, migration prefixes, architecture tests, `CLAUDE.md` and `docs/arquitectura.md` | `feat/modulos` | delegated writer | pending |
| T3 | Robot contract `docs/contrato-robot.md` | `docs/contrato-robot` | inline (one document) | pending |
| T4 | Microsoft Entra ID sign-in, roles admin TI and consulta, local-only demo login | `feat/ingreso-microsoft` | delegated writer | pending |
| T5 | Segurex brand base: tokens, layout, logo, dark mode | `feat/diseno-base` | delegated writer | pending |

## Acceptance

- Each PR: CI green (lint, tests on MySQL 8), `code-review` findings fixed, merged with `gh pr merge <n> --merge --delete-branch` after user approval.

## Progress

- Not started.

## Next step

- T1.
