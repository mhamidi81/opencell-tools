# Core guideline base — resolution contract

> This file is not a guideline. It is the contract every `oc-ov-*` skill and agent follows
> **before** reading any overlay delta.

## Precedence

The `oc-be-tools` guidelines are the **authoritative base**. Overlay files in this plugin are a
**delta**: they state only what differs. A core section applies unchanged unless an overlay section
is explicitly marked `REPLACES`.

Never read an overlay delta on its own. Each one says "REPLACES core §X" without restating X — read
in isolation they are incomplete and misleading.

## Resolve the core guidelines directory

`${CLAUDE_PLUGIN_ROOT}` resolves to *this* plugin's own root, and plugin installs are
**version-pinned and flat** (`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`), so it can
never address another plugin's files directly. Resolve `oc-be-tools` with this ordered candidate
list — no user configuration is required:

```bash
CORE=""
# 1. the marketplace checkout: a full clone of the marketplace repo, stable and version-agnostic
for d in ~/.claude/plugins/marketplaces/opencell-tools/plugins/backend/oc-be-tools/guidelines \
         ~/.claude/plugins/marketplaces/*/plugins/backend/oc-be-tools/guidelines; do
  [ -d "$d" ] && CORE="$d" && break
done
# 2. sibling plugin in the versioned cache, highest version wins
[ -z "$CORE" ] && CORE=$(ls -d "$CLAUDE_PLUGIN_ROOT"/../../oc-be-tools/*/guidelines 2>/dev/null | sort -V | tail -1)
# 3. a source checkout of the marketplace repo next to the project
[ -z "$CORE" ] && for d in ../ccode-marketplace/plugins/backend/oc-be-tools/guidelines \
                           ./ccode-marketplace/plugins/backend/oc-be-tools/guidelines; do
  [ -d "$d" ] && CORE="$d" && break
done
echo "$CORE"
```

Candidate 1 names `opencell-tools` before the `*` glob so two marketplaces both carrying an
`oc-be-tools` cannot race.

## Load order

1. The core files listed by the invoking skill/agent, read from `$CORE/`.
2. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_PROFILES.md` — establish which profile this repo follows.
3. `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_CRITICAL_RULES.md`.
4. The overlay delta(s) for the layer being worked on.

## Hard stop if unresolved

If `$CORE` is empty, **stop** and emit exactly:

> `oc-ov-tools` requires `oc-be-tools`, which supplies the base guidelines this plugin layers over.
> Run `/plugin install oc-be-tools@opencell-tools` and retry.
> (Fallback: invoke the matching `oc-be-tools:oc-be-*-guide` skill first, then re-run this one.)

Do not proceed on the overlay deltas alone. Failing is better than generating code against half a
rulebook.

## Core baseline and drift

Every `OVERLAY_*_DELTA.md` carries a `CORE BASELINE: oc-be-tools <version>` header. When the
installed `oc-be-tools` version exceeds that baseline, a delta may name a core heading that has since
been renamed. `/oc-ov-review` **warns** on this; it never blocks. When you change a core guideline
heading, bump the baseline line in the deltas that reference it.
