---
name: oc-mc-db-guide
description: >
  TRIGGER when user asks to create or modify a database migration, table, column, index or sequence
  in opencell-maco-project. Also trigger on any mention of Flyway, db/postgres, V__ or R__ scripts,
  or maco-db-sql-scripts. Loads the MACO Flyway migration guidelines.
---

# MACO Database Guidelines

Before any schema change in `opencell-maco-project`, read and follow:

1. **Migrations**: `${CLAUDE_PLUGIN_ROOT}/guidelines/DATABASE_GUIDELINES.md` — Flyway naming, versioning, the never-edit-an-applied-script rule
2. **Entity mapping**: `${CLAUDE_PLUGIN_ROOT}/guidelines/ENTITY_GUIDELINES.md` — the entity must match the column exactly
3. **Critical rules**: `${CLAUDE_PLUGIN_ROOT}/guidelines/CRITICAL_RULES.md`

MACO uses **Flyway**, not Liquibase. Scripts live in
`maco-db-sql-scripts/src/main/resources/db/postgres/` — the only location Flyway scans.
