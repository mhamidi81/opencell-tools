# Templates — index & usage

> Copy-paste scaffolding for kicking off an Opencell project (or a big feature subtree). Each file
> below is a **skeleton**: copy it to its target path, rename it, replace every `<placeholder>`, and
> **delete the `<!-- guidance -->` comments** before committing. They embody the methodology — don't
> invent structure ad hoc; start here and trim.

## What to copy where

| Skeleton | Copy to (new project) | Purpose |
|---|---|---|
| `PLAN-skeleton.md` | `PLAN.md` (repo root) | Source of truth until Jira opens: vision, requirements, candidate architecture, phased plan, Decision Register |
| `ways-of-working-skeleton.md` | `docs/process/ways-of-working.md` | Operational handbook; the `Current phase:` line is tracked here |
| `adr-template.md` | `docs/decisions/adr-template.md` | MADR template, copied per-decision |
| `DECISIONS-skeleton.md` | `DECISIONS.md` (repo root) | ADR index; mirrors to the Confluence "Decision Log" |
| `README-skeleton.md` | `README.md` (repo root) | What the project is, how to navigate docs, build/run |
| `CLAUDE-skeleton.md` | `CLAUDE.md` (repo root) | Project-specific agent rules; points back at this methodology |
| `oc-fn-decks` skill → `theme/` | `assets/marp/` (repo root) | Shared **Opencell Marp deck theme** (`opencell.css` + logos) for the Phase-2 deck. Copy the `oc-fn-decks` skill's `theme/` contents in — that skill holds the canonical master; the repo copy is what decks reference. See the **`oc-fn-decks`** skill. |

## The `docs/` tree to create (Phase 0)

```
<project>/
├── PLAN.md            # from PLAN-skeleton.md
├── README.md          # from README-skeleton.md
├── DECISIONS.md       # from DECISIONS-skeleton.md
├── CLAUDE.md          # from CLAUDE-skeleton.md
├── assets/marp/       # Opencell deck theme, from the oc-fn-decks skill's theme/ (Phase-2 deck)
└── docs/
    ├── decisions/     # ADR-NNNN-*.md + adr-template.md (+ a short README pointing at the convention)
    ├── functional/    # Phase 1+: scope, glossary, personas, use-cases, nfr, specs/, user-manual/
    ├── technical/     # Phase 5+: architecture, stack-decisions, security, data-model, api-spec/, deployment
    ├── process/       # ways-of-working.md (+ steerco-pitch/ in Phase 2)
    └── research/      # initialization snapshot / sources
```

**Order of operations** (matches `SKILL.md` §7): create the tree → drop in `PLAN.md` + `ways-of-
working.md` → set up decision machinery (`adr-template.md`, `DECISIONS.md`, write `ADR-0001` to
adopt MADR) → generate the project `CLAUDE.md` → plan engagement. For a **big feature** (not a new
product), don't spin up a repo per feature: create a self-contained folder in the shared design repo
(a repo dedicated to design-only artifacts) — or a `docs/<feature>/` subtree of the product repo if
it's a suitable design home (`repo-and-ci.md` § *Where the design artifacts live*). Reuse the shared ways-of-
working; ADRs are folder-scoped and gate tags namespaced `<initiative>/phase-N`.

For the deck theme in a **shared design repo**, `assets/marp/` lives **once at the shared repo root**
(shared by every initiative), not duplicated in each initiative folder; a per-initiative deck under
`<initiative>/docs/process/` references it via the relative path to the root (the **`oc-fn-decks`** skill).
