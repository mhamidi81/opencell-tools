---
name: oc-ov-postman-guide
description: >
  TRIGGER when creating or editing Postman collections in an OVERLAY repository: the ordered
  NEW_VE_ENV_SETUP setup chain, per-ticket collections, the TNR non-regression suite, release
  collections, the environment file, or the generated Opencell_Scripts collection.
  Loads the core oc-be-tools Postman guidelines first, then the overlay delta.
---

# Overlay Postman guidelines

## 1. Resolve and load the core baseline first

Read `${CLAUDE_PLUGIN_ROOT}/guidelines/_CORE_BASE.md` and follow its resolver to locate the
`oc-be-tools` guidelines directory as `$CORE`. Then read:

- `$CORE/POSTMAN_TESTING.md`
- `$CORE/CRITICAL_RULES.md`

If the resolver finds nothing, **stop** and emit the hard-stop message from `_CORE_BASE.md`.

## 2. Load the overlay deltas

1. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_PROFILES.md`
2. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_POSTMAN_DELTA.md`
3. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_API_DELTA.md` — for verifying endpoint URLs against the code

## 3. Apply

Core's endpoint-map and DTO-field-map verification steps are mandatory, but read the **apiv0**
interfaces. Never hand-edit the generated scripts collection, and only ever add to TNR.
