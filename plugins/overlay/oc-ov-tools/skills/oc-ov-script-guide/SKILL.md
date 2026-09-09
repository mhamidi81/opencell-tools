---
name: oc-ov-script-guide
description: >
  TRIGGER when authoring or modifying Opencell ScriptInstances in an OVERLAY repository (classes
  extending Script or a vertical script base, under com.oc.* or an overlay script module), when
  deploying scripts with mvn opencell:deploy-scripts, and when writing background Jobs (classes
  extending Job with a paired JobBean). Also trigger on review feedback about overlay scripts or jobs.
  Loads the applicable core oc-be-tools guidelines first, then the overlay script and job rules.
---

# Overlay script and job guidelines

## 1. Resolve and load the core baseline first

Read `${CLAUDE_PLUGIN_ROOT}/guidelines/_CORE_BASE.md` and follow its resolver to locate the
`oc-be-tools` guidelines directory as `$CORE`. Then read:

- `$CORE/SERVICE_GUIDELINES.md` — Exception Handling, Logging Standards and Performance sections
- `$CORE/CODE_QUALITY.md`
- `$CORE/CRITICAL_RULES.md`

If the resolver finds nothing, **stop** and emit the hard-stop message from `_CORE_BASE.md`.

## 2. Load the overlay deltas

1. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_PROFILES.md`
2. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_CRITICAL_RULES.md`
3. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_SCRIPTS.md`
4. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_JOBS.md` — when the work involves a Job

## 3. The rule that breaks production

Scripts are **not** CDI beans. `@Inject` compiles cleanly and is never processed, giving a null field
and an NPE at runtime. Always use `getServiceInterface("XxxService")`.

Jobs are the opposite — they *are* EJBs, and `@Inject` is correct there.
