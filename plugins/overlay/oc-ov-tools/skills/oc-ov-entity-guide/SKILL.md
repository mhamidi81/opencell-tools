---
name: oc-ov-entity-guide
description: >
  TRIGGER when creating, modifying or refactoring JPA entities, enums or @Embeddable classes in an
  OVERLAY repository (modules named opencell-elec-* or opencell-ext-*), including entities extending
  BusinessCFEntity, @CustomFieldEntity / @ObservableEntity annotations, or the overlay persistence.xml.
  Also trigger on review feedback about overlay entity code.
  Loads the core oc-be-tools entity and database guidelines first, then the overlay deltas.
---

# Overlay entity guidelines

## 1. Resolve and load the core baseline first

Read `${CLAUDE_PLUGIN_ROOT}/guidelines/_CORE_BASE.md` and follow its resolver to locate the
`oc-be-tools` guidelines directory as `$CORE`. Then read, in order:

- `$CORE/ENTITY_GUIDELINES.md`
- `$CORE/DATABASE_GUIDELINES.md`
- `$CORE/CODE_QUALITY.md`
- `$CORE/CRITICAL_RULES.md`

If the resolver finds nothing, **stop** and emit the hard-stop message from `_CORE_BASE.md`.

## 2. Load the overlay deltas

1. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_PROFILES.md` — establish the repo profile
2. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_CRITICAL_RULES.md`
3. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_ENTITY_DELTA.md`
4. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_DATABASE_DELTA.md` — an entity is not done without its changeset pair
5. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_ARCHITECTURE.md` — persistence.xml registration

## 3. Apply

Core rules hold unless an overlay section is marked `REPLACES`. Match the neighbouring entities in the
same module rather than the core guideline's defaults.
