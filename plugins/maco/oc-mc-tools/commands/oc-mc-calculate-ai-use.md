---
description: Record AI usage for a ticket implemented in opencell-maco-project. Thin alias over /oc-be-tools:oc-be-calculate-ai-use, which owns the shared cross-team analyzer and contract; MACO work is recorded as the backend domain, with its own module categories.
argument-hint: "[--working | --commit <ref>] [--run <RUN_ID>]"
---

# Record MACO AI usage

This command is deliberately **thin**. The measurement logic — the four sources (sub-agent manifests,
first-pass snapshots, session transcript, file-history), the analyzer, and the cross-team record
contract — lives in `/oc-be-tools:oc-be-calculate-ai-use` and **must not be forked**. One reporting
tool reads every team's data from one Jira field; a divergent copy silently produces records that
are written correctly and never reported.

## What to run

```
/oc-be-tools:oc-be-calculate-ai-use [--working | --commit <ref>] [--run <RUN_ID>]
```

Apply the MACO profile below when interpreting its module paths and categories.

---

## MACO work is BACKEND

Areas are defined by **discipline, not repository**. MACO is Java/Spring backend work, so its records
use the ordinary backend identity:

| | value |
|---|---|
| record `domain` | **`backend`** — key `backend/<accountId>/<name>` |
| code tag | **`ai_Dev_back`** |
| test tag | **`ai_test_back_dev`** |
| review tag | **`ai_code_review_back`** |

**Do not invent a `maco` domain or `*_maco` tags.** `/oc-ai-report` and `/oc-time-report` filter on
`AREAS = ["backend", "frontend", "qa"]` and drop anything else silently.

## MACO artifact categories

MACO has a different module layout from `opencell-core`, so the category matcher needs its own rows.
These sit alongside the existing backend keys and reuse them wherever the meaning is the same:

| `cat` key | Matches in `opencell-maco-project` | Note |
|---|---|---|
| `prod` | `maco-model/`, `maco-dto/`, `maco-repository/`, `maco-service/`, `maco-rest-api/src/main/`, `maco-exception/`, `maco-spring-config/` + `.java` | ordinary production code |
| `bat` | `maco-batch-processing/` + `.java` | Spring Batch readers/processors/writers/config — the largest module after the DTOs, and worth counting apart from ordinary services |
| `mig` | `maco-db-sql-scripts/src/main/resources/db/` + `.sql` | **Flyway**, not Liquibase — the core `/db_resources/` + `.xml` pattern matches nothing here |
| `test` | `maco-rest-api/src/test/` + `.java` | all MACO tests live in this one module, whatever layer they exercise |
| `pm` | `maco-env-config/` + `.postman_collection.json` / `.postman_environment.json` | Postman environments and the Keycloak client setup collection |

Two MACO specifics the analyzer must not get wrong:

- **Migrations are `.sql` under `db/postgres/`.** A matcher keyed on Liquibase XML counts zero
  migrations for every MACO ticket.
- **Tests are not identifiable by module.** `maco-rest-api` holds both production controllers and the
  entire test suite, so `test` must be matched on the `src/test/` path segment, not the module name.

## Test counting

MACO tests are **JUnit 4** — count `@Test`-annotated methods in
`maco-rest-api/src/test/**/*.java`. There is no Arquillian and no separate unit/integration split to
reconcile; `@Ignore`d tests are **not** counted.

## Ticket projects

MACO tickets are raised in **`MACRD`** (*MACO R&D*), which is also used for overlay work — so the
ticket key does not identify the codebase. The **repository** decides module paths and categories.
`MACRD` is already in scope for `/oc-ai-report` and `/oc-time-report` (default
`--project INTRD,MACRD`).

> **Known edge case.** MACO, core and overlay all share the `backend/<accountId>/` record-key prefix,
> so one developer recording work from **two** of those repos against the **same** ticket would have
> the second run upsert over the first. Record the ticket once, from the repo holding the bulk of the
> work, or split the work across tickets.

## Field mechanics (shared contract — do not diverge)

**`customfield_10613`** — multi-value **free text**, not a fixed option list. Never overwrite it: read
the current array, append, write back the whole array; if the read fails, skip the write rather than
clobbering it. Values in use: `ai_Dev_Front`, `ai_test_front_dev`, `ai_code_review_Front`,
`ai_Dev_back`, `ai_test_back_dev`, `ai_code_review_back`, `ai_test_case_QA`, `ai-tech-design`.
Because the field accepts anything, a misspelling silently creates a second useless label.

**`customfield_10745`** — one shared JSON document per ticket across all teams, stored with the
**rich-text (ADF) renderer**: `doc` → `codeBlock` → `text` holding the JSON string. Write a plain
string first and fall back to the ADF wrapper; accept either form on read. Schema
`opencell.ai-usage/v1`, `records` keyed `<domain>/<accountId>/<name>`. Never replace the document —
delete only this caller's own `<domain>/<accountId>/` key and keep every other key intact.

## Where the manifests come from

`/oc-mc-implement` creates `.claude/cache/ai-stats/{TICKET}-{yyyymmdd-HHMMSS}/` and passes each
builder a manifest path; the builders (`oc-mc-entity-builder`, `oc-mc-service-builder`,
`oc-mc-batch-builder`, `oc-mc-api-builder`, `oc-mc-test-generator`) write `{phase}.json` plus
`snapshots/{phase}.diff` as their final actions. Without those, sub-agent work is undercounted and
its retention is unmeasurable — a sub-agent's `Write`/`Edit` calls never reach the main session
transcript.

Resolve the run directory by **`{TICKET}-*` prefix**, not "newest directory", so a developer who
switched tickets in one checkout cannot have another ticket's manifests attributed here.

These directories must be git-ignored in `opencell-maco-project`.
