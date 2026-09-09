---
name: oc-ov-service-guide
description: >
  TRIGGER when creating or modifying service classes in an OVERLAY repository (opencell-elec-ejb,
  opencell-ext-ejb), when overriding or extending a CORE Opencell service, and whenever @Specializes,
  a startup @Singleton, or changing core service behaviour from an overlay comes up.
  Also trigger on review feedback about overlay service code.
  Loads the core oc-be-tools service guidelines first, then the overlay delta.
---

# Overlay service guidelines

## 1. Resolve and load the core baseline first

Read `${CLAUDE_PLUGIN_ROOT}/guidelines/_CORE_BASE.md` and follow its resolver to locate the
`oc-be-tools` guidelines directory as `$CORE`. Then read, in order:

- `$CORE/SERVICE_GUIDELINES.md`
- `$CORE/CODE_QUALITY.md`
- `$CORE/CRITICAL_RULES.md`

If the resolver finds nothing, **stop** and emit the hard-stop message from `_CORE_BASE.md`.

## 2. Load the overlay deltas

1. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_PROFILES.md`
2. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_CRITICAL_RULES.md`
3. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_SERVICE_DELTA.md` — **the three cases: new service, @Specializes, full replacement**
4. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_ARCHITECTURE.md` — only when overriding core

## 3. Decide which case you are in before writing code

- New overlay service → core guidelines apply unchanged.
- Changing a core service → **`@Specializes`**, overriding the minimum. Confirm the application-wide
  blast radius is intended, and remember it does not reach `getServiceInterface` callers in scripts.
- Full replacement by FQN → last resort only, and it must be registered in the repo `CLAUDE.md`.
