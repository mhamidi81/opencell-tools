---
name: oc-ov-db-guide
description: >
  TRIGGER when editing Liquibase changesets in an OVERLAY repository, specifically
  db_resources/current/overlay.xml or db_resources/rebuild/overlay.xml, when LiquibaseFileTest is
  mentioned or failing, or when writing ad-hoc SQL in an overlay database-config module.
  Also trigger on review feedback about overlay migrations.
  Loads the core oc-be-tools database guidelines first, then the overlay delta.
---

# Overlay database guidelines

## 1. Resolve and load the core baseline first

Read `${CLAUDE_PLUGIN_ROOT}/guidelines/_CORE_BASE.md` and follow its resolver to locate the
`oc-be-tools` guidelines directory as `$CORE`. Then read, in order:

- `$CORE/DATABASE_GUIDELINES.md`
- `$CORE/CODE_QUALITY.md`
- `$CORE/CRITICAL_RULES.md`

If the resolver finds nothing, **stop** and emit the hard-stop message from `_CORE_BASE.md`.

## 2. Load the overlay deltas

1. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_PROFILES.md`
2. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_CRITICAL_RULES.md`
3. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_DATABASE_DELTA.md` — **the five-rule current/rebuild contract**
4. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_ARCHITECTURE.md` — how these files reach the database

## 3. Always finish by running the enforcement test

```bash
cd <overlay-war-module> && mvn test -Dtest=LiquibaseFileTest
```

It must be run **from the module directory** — it resolves its paths relative to the working
directory. The pairing rules are not advisory; this test is what enforces them.
