<!-- TEMPLATE — copy to CLAUDE.md at the repo root. These are PROJECT-specific agent rules; they
     complement your global ~/.claude/CLAUDE.md (if present) and the `oc-fn-project-management` skill.
     Replace <placeholders>; delete guidance comments. Where this file speaks it is more specific and wins. -->

# CLAUDE.md — <Project Name> (<ACRONYM>)

Project-specific agent rules. These **complement** your global `~/.claude/CLAUDE.md` (if present) and
the **`oc-fn-project-management`** skill (which defines the phased methodology, gates, ADR discipline,
repo conventions, and engagement model). **Load `oc-fn-project-management` on kickoff/resume.** Where
this file is silent, the methodology applies; where it speaks, it is more specific and wins.

## What <ACRONYM> is

<2–3 sentences. **Read [`PLAN.md`](./PLAN.md) first on every resume** — source of truth for vision,
requirements, candidate architecture, and the Decision Register.>

## The non-negotiables

### 1. Design-first & phased — respect the gates
- Eight phases with hard gates (`PLAN.md §7`, `docs/process/ways-of-working.md`).
- **Phases 0–3 produce ONLY `.md` artifacts + ADRs** (Phase 2 also a pitch deck). No application
  code before Phase 6.
- **🚫 Jira opens ONLY at Phase 4** (after functional design is approved). Do not create Jira issues
  before the 3→4 gate — capture early items in the relevant `.md` instead. Stories open with their
  functional sections; the Technical design section and Enablers follow in Phase 5.
- A phase exits only when its deliverables are merged **and** its decisions are `Accepted` ADRs.
- **Track the current phase** at the top of `docs/process/ways-of-working.md`.

### 2. Every decision is an ADR
- Significant decisions → MADR ADRs in `docs/decisions/`, never ad-hoc prose. Update `DECISIONS.md`.
- Open decisions live in the `PLAN.md §9` Decision Register; graduate them to ADRs by phase.
- Superseded ADRs are never deleted — re-head with `Superseded by ADR-MMMM` + forward link.

### 3. Domain invariants (domain law, not preferences)
<!-- The correctness laws specific to THIS project. State them as facts to be enforced. -->
- **<Invariant 1>** — <statement>.
- **<Invariant 2>** — <statement>.

### 4. Stable seams
- <Name the swappable boundaries> are clean ports/adapters; keep them swappable, no leakage into the
  core.

## Repo, branching, CI/CD

- **Single mono-repo** (backend + GUI + `docs/`); carve out cross-product code to live with its own
  product.
- **Trunk-based on protected `main`**, short-lived branches, **squash-merge**, releases via annotated
  tags `X.Y.Z` (no `v` prefix). **Phase tags** `phase-N` at each gate.
- **From Phase 4:** branch `{author}/{type}/{base}/{KEY-NN}-{desc}` (base = `main`); commit subject
  `KEY-NN: <desc>`. Pre-Phase-4 commits use a plain imperative subject. (Full convention + common-flow
  interop: `oc-fn-project-management` `repo-and-ci.md`.)
- **CI/CD = Jenkins**; Bitbucket = source + PRs only; Jira = planning.
- **Tier-2 human sign-off is non-waivable** for PRs touching <this project's sensitive seams>.

## Documentation

- **`.md` in the repo is the single source of truth; Confluence is a one-way mirror.** Never
  hand-edit synced Confluence pages.
- Update `README.md` in the **same commit** as any change to what it documents.

## People & engagement

Sponsor/lead: **<you>**. Approvers: **<…>**. Architecture: **<…>**. Infra: **<…>**. Domain PO:
**<…>**. Engagement is staged (`PLAN.md §2`); the sponsor controls who is brought in when.

## Tooling note

This repo is **Bitbucket/Jira-hosted** → use Opencell/Jira conventions (the `oc-fn-func-design` /
`oc-fn-documentation` skills) and `KEY-NN:` commit subjects once Jira keys exist. Confirm via
`git remote -v` if ever unsure.
