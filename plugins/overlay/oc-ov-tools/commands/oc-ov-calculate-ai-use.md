---
description: Record AI usage for a ticket implemented in an Opencell OVERLAY repository. Thin alias over /oc-be-tools:oc-be-calculate-ai-use, which owns the shared cross-team analyzer and contract; overlay work is recorded as the backend domain, with two extra artifact categories.
argument-hint: "[--working | --commit <ref>] [--run <RUN_ID>]"
---

# Record overlay AI usage

This command is deliberately **thin**. The measurement logic — the four sources (sub-agent manifests,
first-pass snapshots, session transcript, file-history), the analyzer, and the cross-team record
contract — lives in `/oc-be-tools:oc-be-calculate-ai-use` and must not be forked.

## What to run

```
/oc-be-tools:oc-be-calculate-ai-use [--working | --commit <ref>] [--run <RUN_ID>]
```

It detects the repository and applies the overlay categories automatically.

---

## Overlay work is BACKEND

Areas are defined by **discipline, not repository**. Java and xhtml work is backend whether it lands
in `opencell-core` or in an overlay repo, so overlay records use the ordinary backend identity:

| | value |
|---|---|
| record `domain` | **`backend`** — key `backend/<accountId>/<name>` |
| code tag | **`ai_Dev_back`** |
| test tag | **`ai_test_back_dev`** |
| review tag | **`ai_code_review_back`** |

**Do not invent an `overlay` domain or `*_overlay` tags.** `/oc-ai-report` and `/oc-time-report`
filter on `AREAS = ["backend", "frontend", "qa"]` and drop anything else silently, so a new domain
would produce records that are written correctly and never reported. Frontend is a separate
repository (`opencell-portal`) and out of scope here.

## Two extra artifact categories

Overlay repos produce two artifact kinds core does not, and they are worth counting separately
*within* the backend domain:

| `cat` key | Matches | Why it is distinct |
|---|---|---|
| `scr` | the overlay **script** module | ScriptInstances are deployed as source to a live server and never compiled into the war |
| `rpt` | `.jrxml` files | Jasper templates, compiled outside the Maven build |

These sit alongside the existing backend keys `prod`, `mig`, `test`, `pm`. The cross-team contract
allows `cat` sub-keys to differ; the `domain` and record-key layout must not.

Category patterns the analyzer applies (see the `## Repo profile` section of
`oc-be-calculate-ai-use.md`):

- overlay script module + `.java` → `script`
- `.jrxml` → `report`
- `/db_resources/` + `.xml` → `migration` — the overlay path has **no** `changelog/` segment, so
  core's pattern alone would miss every overlay changeset
- overlay postman folder → `postman`

## Ticket projects

Overlay tickets are raised in **`INTRD`** (the same project as core work) and in **`MACRD`**
(*MACO R&D*). Both are in scope for `/oc-ai-report` and `/oc-time-report` — pass
`--project INTRD,MACRD`, which is the default.

The ticket key therefore says nothing about which codebase the work landed in. That does not affect
the domain (backend either way), but it does mean the **repository** decides module paths, categories
and which review command applies.

> **Known edge case.** Because core and overlay share the `backend/<accountId>/` key prefix, one
> developer recording *both* core and overlay work against the *same* ticket would have the second run
> upsert over the first. Record the ticket once, from the repo where the bulk of the work happened,
> or split the work across tickets.

## Field mechanics (verified against live tickets)

**`customfield_10613`** — multi-value **free text**, not a fixed option list. Never overwrite it: read
the current array, append, write back the whole array; if the read fails, skip the write rather than
clobbering it. Values in use: `ai_Dev_Front`, `ai_test_front_dev`, `ai_code_review_Front`,
`ai_Dev_back`, `ai_test_back_dev`, `ai_code_review_back`, `ai_test_case_QA`, `ai-tech-design`.
Because the field accepts anything, a misspelling silently creates a second useless label — two
strays already exist (`ai_review_code_back`, `test_design`).

**`customfield_10745`** — one shared JSON document per ticket across all teams, stored with the
**rich-text (ADF) renderer**: `doc` → `codeBlock` → `text` holding the JSON string. Write a plain
string first and fall back to the ADF wrapper; accept either form on read. Schema
`opencell.ai-usage/v1`, `records` keyed `<domain>/<accountId>/<name>`. Never replace the document —
delete only this caller's own `<domain>/<accountId>/` key and keep every other key intact.
