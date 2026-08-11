<!-- TEMPLATE — copy to docs/process/ways-of-working.md. Replace <placeholders>; delete guidance
     comments. This is authoritative for PROCESS; PLAN.md remains authoritative for vision,
     requirements and open decisions. Keep the "Current phase" line (§2) up to date. -->

# Ways of Working — <Project Name> (<ACRONYM>)

> How we run this project: phased delivery, decision-recording, repo/branch/review conventions, and
> CI/CD. Authoritative for *process*; `PLAN.md` remains the source for *vision, requirements and open
> decisions*. **Last updated:** <YYYY-MM-DD>.

## 1. Guiding principles

1. **Decide before building.** Phases 0–3 produce only `.md`/ADRs (Phase 2 also a pitch deck); Jira
   opens at Phase 4 (after functional design is approved).
2. **Every decision is written down with its rationale** — as an ADR (§3).
3. **<Domain invariant>** — <the project's correctness law>.
4. **Stable seams.** <swappable boundaries> are clean ports/adapters.
5. **Start simple, keep the upgrade path.** No heavy infra on day one, structured so it can be
   adopted later behind an existing seam.

## 2. The phased delivery model

Eight phases with **hard gates**. A phase exits only when (a) its deliverables are merged to trunk
**and** (b) its design questions are `Accepted` ADRs. **Phases 0–3 produce only `.md` + ADRs**
(Phase 2 also a pitch deck). **The 3 → 4 gate is the single hard line where Jira items first appear.**

| Phase | Name | Produces | Exit gate |
|---|---|---|---|
| 0 | Setup & Process | repo scaffold, bootstrap ADRs, README/CLAUDE skeletons | repo initialized; bootstrap ADRs Accepted; Jira criteria recorded |
| 1 | Functional Scoping & Vision | scope, personas, glossary, use-cases, NFRs | scope pitch-ready; glossary frozen; MVP boundary unambiguous |
| 2 | Framing & Approval | business case + slideware; feasibility read | **go/no-go** — mandate, budget, stakeholders engaged |
| 3 | Functional Design | domain model, specs, API sketch, state machines | every MVP use case spec'd; state machines Accepted; API enumerated |
| 4 | Backlog Creation — Functional (**Jira opens**) | Epics (per capability) + Stories with functional sections (Requirement, Functional Design, Acceptance) | every MVP Story exists; functional sections PO-approved |
| 5 | Technical Design | C4, stack ADRs, security, contracts, OpenAPI, data model, infra; Stories' Technical design filled; Enablers created | stack ADR'd; OpenAPI validates; infra agreed; component list frozen; Technical design filled; Enablers created; sprint 1 selected |
| 6 | Iterative Implementation | working software, tests, docs in the same PR | story criteria met; CI green; end-to-end path proven |
| 7 | Docs & Release | finalized docs, Confluence sync, CHANGELOG, tag, runbook | tagged release; Confluence live & matching repo `.md` |

**Current phase: <N (Name)>.** <one line on what's done and what this phase produces>

## 3. Decision-recording (ADRs)

- Every significant decision → a MADR-based ADR in `docs/decisions/`.
- One file per decision, `ADR-NNNN-kebab-title.md`, sequential numbering never reused.
- Status: `Proposed → Accepted → Superseded by ADR-MMMM | Deprecated`. Superseded ADRs are never
  deleted, only re-headed with a forward link.
- `DECISIONS.md` is the index; keep it in sync with ADR headers.
- The **Decision Register** (`PLAN.md §9`) is the holding area; entries graduate to ADRs by phase.

## 4. Repository & documentation structure

- **Single mono-repo** (backend + GUI + `docs/`); **carve out code that belongs to another product's
  lifecycle** to live with that product.
- Doc tree: `docs/{decisions,functional,technical,process,research}/`.
- **`.md` in the repo is the single source of truth; Confluence is a one-way mirror.**

## 5. Branching, commits, review

- **Trunk-based on protected `main`**; short-lived feature branches; **squash-merge**; releases are
  **annotated tags** `X.Y.Z` (no `v` prefix); no long-lived `release/*` branches.
- **From Phase 4** (Jira keys exist): branch `{author}/{type}/{base}/{KEY-NN}-{desc}` (base = `main`);
  commit subject `KEY-NN: <desc>` (Smart Commits). Pre-Phase-4 commits use a plain imperative subject.
  (Full convention + marketplace common-flow interop: `oc-fn-project-management` `repo-and-ci.md`.)
- **PR review — two tiers:** (1) automated gauntlet (build, tests, lint, quality gate, SAST) — must
  be green; (2) **mandatory, non-waivable human sign-off** for PRs touching <this project's
  sensitive seams>. Doc-only PRs may use lighter approval.

## 6. CI/CD

- **Jenkins is the pipeline**; Bitbucket is source + PRs only; Jira is planning.
- Pipeline: build/test/quality gauntlet → build & publish Docker image → deploy to Kubernetes.
  Confluence sync runs as a trunk pipeline step.

## 7. Versioning

- Version source is the backend manifest (set in Phase 5 once the stack is chosen).
- **Major** only on explicit instruction; **Minor** on feature/core change; **Patch** on fixes. Every
  bump gets an **annotated tag** `X.Y.Z` with the `git log --oneline` range since the previous tag.
- **Phase tags (process milestones).** At each gate, tag the merge commit with an **annotated**
  `phase-N` tag and push it. Independent of the `X.Y.Z` version tags (which only begin once a manifest
  exists, Phase 5+).

## 8. Documentation discipline

- Update `README.md` in the **same commit** as any change that affects it.
- Technical **and** user documentation in `.md`, mirrored one-way to Confluence.
- **Deck-as-md:** any pitch deck is authored as **markdown** and rendered to PPTX one-way (never the
  master, never committed as a binary). Name the source `YYYYMMDD_<slug>.md` — the date it was cut,
  fixed at creation; the renders inherit the basename.

## 9. Who's involved when

<!-- One line summarizing the staged engagement for this project; full detail in engagement.md. -->
Lightweight/solo through early phases → feasibility read from <architect>/<infra> → approval gate
(Phase 2) → engage <domain PO> (Phases 3–4) and <architect>/<infra> (Phase 5).
