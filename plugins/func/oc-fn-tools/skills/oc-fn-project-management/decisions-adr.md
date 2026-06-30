# Decisions — ADRs and the Decision Register

> Load this whenever recording a decision, writing/superseding an ADR, or maintaining the index.
> The skill's non-negotiable #2: **every significant decision is an ADR, never prose buried in a
> doc or tribal knowledge.** The examples below are illustrative, not a resolvable reference.

## Two artifacts, one trail

| Artifact | What it is | Where |
|---|---|---|
| **Decision Register** | Holding area for decisions you owe yourself but haven't taken yet | `PLAN.md §9` (a table) |
| **ADR** | A *taken* decision, with full context and consequences | `docs/decisions/ADR-NNNN-*.md` |
| **`DECISIONS.md`** | Human-readable index of all ADRs; mirrors verbatim to Confluence | repo root |

The register is the *pre-decision* backlog; an ADR is the *post-decision* record. Each register
entry **graduates** to an ADR when taken, and the trail is **two-way**: the ADR header names the
`DR-NN` it graduates, and the register row notes the `ADR-NNNN` it became.

## The Decision Register (`PLAN.md §9`)

A table of decisions, each with a **status** and a one-line direction:

- **`Open`** — still to decide, no lean yet.
- **`Narrowed`** — options reduced, a likely direction noted, not yet committed.
- **`Resolved`** — decided; the rationale is in the row, and it has graduated (or is about to) to an ADR.

Each row also carries a **target phase** (when the decision is due). This lets you defer a decision
honestly — it's visible and scheduled, not forgotten. Recording the *criteria* for a deferred
decision (e.g. the Jira-project choice) is itself a deliverable even when the decision waits
(`jira-project-choice.md`).

> Keep `DECISIONS.md` showing the still-ungraduated register entries too, so the index is the one
> place to see the whole decision landscape (taken + pending).

## ADR format — MADR

Lightweight [MADR](https://adr.github.io/madr/). The template lives in `templates/adr-template.md`;
copy it into the project's `docs/decisions/`. Every ADR has these sections:

**Title** (`ADR-NNNN: <decision in the imperative>`) · **Status** · **Date** · **Deciders** ·
**Decision Register ref** (the `DR-NN` it graduates, or `—`) · **Context** · **Decision** (active
voice, "We will…") · **Consequences** (Positive / Negative / Neutral) · optional **Considered
Options** (pros/cons — include when the choice was non-obvious) · **Links**.

## Conventions (do not deviate)

- **One file per decision:** `ADR-NNNN-kebab-title.md`, zero-padded 4-digit, **sequential**.
- **Numbers are never reused** — even for a superseded or deprecated ADR.
- **Status lifecycle:** `Proposed → Accepted → Superseded by ADR-MMMM` | `Deprecated`.
- **Superseded ADRs are never deleted.** Re-head the status line with `Superseded by ADR-MMMM` and a
  forward link; the historical content stays intact. The superseding ADR links back.
- **A phase exits only when its decisions are `Accepted`** — `Proposed` ADRs do not clear a gate
  (`phases.md`).

## Keeping `DECISIONS.md` in sync

`DECISIONS.md` is **generated from the ADR headers** and is the page that mirrors to the Confluence
"Decision Log" (one-way — `repo-and-ci.md`). Whenever you add, accept, or supersede an ADR, update
`DECISIONS.md` **in the same commit**. It has three sections:

1. **Accepted / active ADRs** — table: ADR · Title · Status · Date · DR.
2. **Superseded / deprecated ADRs** — moved here when re-headed, never removed.
3. **Decisions not yet graduated to ADRs** — the live register entries, with target phase.

## What counts as "significant" (→ needs an ADR)

Anything that constrains the build and would otherwise be re-litigated: stack/framework/language
choices, repo layout, branching model, CI/CD platform, security posture, an external contract, the
tenancy model, a state-machine design, the MVP feature boundary. If a future reader would ask "why
is it this way?", it's an ADR. Routine, reversible implementation choices are not.

## Worked examples (illustrative pattern)

These show the shape, not a specific project's register — adapt the numbers to yours:

- **Bootstrap ADRs (Phase 0), e.g.:** ADR-0001 adopt MADR · ADR-0002 repo layout · ADR-0003 branching
  & commit convention · ADR-0004 Confluence sync · ADR-0005 CI/CD platform.
- **Graduation, e.g.:** a register entry (`DR-NN`) → `ADR-0006`; two related entries graduated
  *together* to one ADR (one ADR can resolve several related register entries).
- **Deferred-but-recorded, e.g.:** the Jira-project register entry stays `Open` with its criteria
  written in `docs/process/jira-project-criteria.md`, due Phase 4.
