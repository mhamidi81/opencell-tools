# Overlay database / Liquibase

> LAYERS OVER: oc-be-tools/guidelines/DATABASE_GUIDELINES.md
> CORE BASELINE: oc-be-tools 1.17.0
> PRECEDENCE: file locations and the current/rebuild contract REPLACE core; everything else applies.

## File locations — REPLACES core "File Structure"

Exactly **two** files, in the overlay war module:

```
<overlay-module>/src/main/resources/db_resources/current/overlay.xml
<overlay-module>/src/main/resources/db_resources/rebuild/overlay.xml
```

Note there is **no `changelog/` segment** in the source tree, unlike core. Never create a third
changelog file, never rename these, and never touch core's `changelog/current/structure.xml`.

## Why the names are fixed

Core ships **empty placeholders** inside `opencell-model.jar` at
`db_resources/changelog/{current,rebuild}/overlay.xml`, and core's master changelogs already
`<include>` them. The overlay build unzips that core jar, overwrites those two entries with the files
above, and re-jars into `WEB-INF/lib`.

Rename or relocate either file and **every migration is silently dropped** — the build still succeeds
and the war still deploys.

## The current/rebuild contract — REPLACES core's rebuild section

`current/` holds incremental changes applied to existing databases. `rebuild/` holds the full schema
for a fresh build. The two are tied by five rules, all machine-enforced by `LiquibaseFileTest`:

1. Every changeset in `current` must exist in `rebuild` with the same `id` + `author` (+ `dbms`).
2. In `rebuild`, that twin must be **empty**: `<changeSet id="…" author="…"/>`.
3. Every **empty** changeset in `rebuild` must exist in `current`.
4. No duplicate `id` + `author` + `dbms` within either file.
5. `current` must contain **no** empty changesets.

Structure creation (`createTable`, `createSequence`, foreign keys) lives **only** in `rebuild`,
non-empty, with no counterpart in `current`.

### Run the enforcement test

```bash
cd <overlay-module> && mvn test -Dtest=LiquibaseFileTest
```

It resolves `src/main/resources/...` **relative to the working directory**, so it must be run from the
module directory, not the repo root. It is JUnit 4 — leave it that way.

## Changeset id — REPLACES core

`#TICKET_yyyymmdd` with an **underscore** before the date (`#INTRD-43322_20260625`), where core uses a
hyphen. Legacy free-form ids in `rebuild` (`point_of_delivery_init`) are grandfathered — leave them.

## Column types, indexes, multitenancy

Core's sections apply unchanged. The `${type.*}` substitutions come from core's master changelog —
confirm a property is actually defined there before using it.

## Ad-hoc SQL is not a migration

Loose `.sql` files in a database-config module are **never executed by the build** and often use two
different naming conventions. They are operational scripts. A schema change the application depends on
must go through the `overlay.xml` pair — never there.
