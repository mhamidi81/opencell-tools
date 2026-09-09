---
name: oc-ov-test-guide
description: >
  TRIGGER when writing or fixing JUnit tests in an OVERLAY repository, when deciding which overlay
  module a test belongs in, or when adding test dependencies to an overlay module pom.
  Loads the core oc-be-tools unit-testing guidelines first, then the overlay delta.
---

# Overlay unit-testing guidelines

## 1. Resolve and load the core baseline first

Read `${CLAUDE_PLUGIN_ROOT}/guidelines/_CORE_BASE.md` and follow its resolver to locate the
`oc-be-tools` guidelines directory as `$CORE`. Then read, in order:

- `$CORE/UNIT_TESTING.md`
- `$CORE/CODE_QUALITY.md`
- `$CORE/CRITICAL_RULES.md`

If the resolver finds nothing, **stop** and emit the hard-stop message from `_CORE_BASE.md`.

## 2. Load the overlay deltas

1. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_PROFILES.md`
2. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_UNIT_TESTING_DELTA.md`

## 3. Check the module before writing

The script module's `src/test/java` **never runs** — test compilation is skipped there. Put the test in
the api, job or war-overlay module, and add test dependencies to that module's own pom, matching the
versions its siblings use.
