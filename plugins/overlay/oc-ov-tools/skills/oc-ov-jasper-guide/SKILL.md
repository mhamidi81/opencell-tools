---
name: oc-ov-jasper-guide
description: >
  TRIGGER when editing a .jrxml or .jasper invoice report in an OVERLAY repository, or when discussing
  overlay report templates, report fields, or the invoice XML those reports read from.
---

# Overlay Jasper report guidelines

## 1. Resolve and load the core baseline first

Read `${CLAUDE_PLUGIN_ROOT}/guidelines/_CORE_BASE.md` and follow its resolver to locate the
`oc-be-tools` guidelines directory as `$CORE`. Then read:

- `$CORE/CODE_QUALITY.md`

If the resolver finds nothing, **stop** and emit the hard-stop message from `_CORE_BASE.md`.

## 2. Load the overlay guideline

1. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_JASPER.md`

## 3. The rule that ships a stale report

The Maven build does **not** compile `.jrxml`. Every `.jrxml` change must ship a regenerated `.jasper`
of the same basename in the same commit, or the deployed report silently stays on the old version.
