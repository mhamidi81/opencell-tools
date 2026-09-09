---
name: oc-ov-api-guide
description: >
  TRIGGER when working on REST APIs in an OVERLAY repository: apiv0 resources in org.meveo.apiv0.rest,
  *Rs interfaces extending IBaseRs, *RsImpl classes extending BaseRs, endpoints under /ve/, *Api beans
  extending BaseApi, or plain-POJO DTOs in an overlay dto module.
  Also trigger on review feedback about overlay API or DTO code.
  Loads the core oc-be-tools API guidelines first, then the overlay delta, which REPLACES most of them.
---

# Overlay API guidelines (apiv0)

## 1. Resolve and load the core baseline first

Read `${CLAUDE_PLUGIN_ROOT}/guidelines/_CORE_BASE.md` and follow its resolver to locate the
`oc-be-tools` guidelines directory as `$CORE`. Then read, in order:

- `$CORE/API_GUIDELINES.md`
- `$CORE/CODE_QUALITY.md`
- `$CORE/CRITICAL_RULES.md`

If the resolver finds nothing, **stop** and emit the hard-stop message from `_CORE_BASE.md`.

## 2. Load the overlay deltas

1. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_PROFILES.md`
2. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_CRITICAL_RULES.md`
3. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_API_DELTA.md`
4. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_ARCHITECTURE.md`

## 3. Apply

On the `vertical-energy` profile the overlay delta **replaces** most of core's API model — there is no
`BaseCrudApi`, no Immutables DTO, and no activator to register in.

Before finishing, re-check the one rule whose failure is silent: the resource impl must live under
`org.meveo.apiv0.rest.*` **and** extend `BaseRs`, or the endpoint will not exist.
