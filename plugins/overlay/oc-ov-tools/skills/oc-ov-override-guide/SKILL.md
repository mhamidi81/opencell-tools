---
name: oc-ov-override-guide
description: >
  TRIGGER when overriding anything belonging to CORE Opencell from an overlay repository: adding a file
  to the overlay war module src/main/webapp or src/main/resources, editing the overlay persistence.xml
  or log4j2.xml, introducing a class whose FQN matches a core class, or writing a startup bean that
  rewrites a core-shipped file at runtime. Also trigger when planning a core-version upgrade.
---

# Overlay core-override guidelines

## 1. Resolve and load the core baseline first

Read `${CLAUDE_PLUGIN_ROOT}/guidelines/_CORE_BASE.md` and follow its resolver to locate the
`oc-be-tools` guidelines directory as `$CORE`. Then read:

- `$CORE/CRITICAL_RULES.md`
- `$CORE/CODE_QUALITY.md`

If the resolver finds nothing, **stop** and emit the hard-stop message from `_CORE_BASE.md`.

## 2. Load the overlay deltas

1. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_CRITICAL_RULES.md`
2. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_ARCHITECTURE.md` — override precedence and the register
3. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_SERVICE_DELTA.md` — prefer @Specializes over replacement

## 3. Before overriding anything

Work down the ranked list in `OVERLAY_ARCHITECTURE.md`: add a new class, else `@Specializes`, else
replace a resource file, and only as a last resort shadow a class by FQN.

Whatever you choose, add it to the **override register** in the repo `CLAUDE.md`. An override that is
not written down is one nobody re-checks at the next core upgrade.
