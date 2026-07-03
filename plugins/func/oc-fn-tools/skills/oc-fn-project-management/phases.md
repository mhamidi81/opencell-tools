# Phases — deliverables, gates, and who's involved

> Load this when planning, entering, or exiting a phase. The spine (`SKILL.md` §4) has the
> summary table; this file is the detail. OPH (Opencell Payment Hub) is an internal Opencell
> reference project used here as an illustrative worked example — it is not bundled with this plugin.

## The gate rule (applies to every phase)

A phase **exits only when both hold**:

1. **Deliverables merged to trunk** — the phase's `.md`/ADRs (or, from Phase 6, working software)
   are on `main`, not sitting in a branch. *(Phases 4–5 also deliver Jira items — Stories with their
   sections, then Enablers; "done" for those means the issues exist and are approved, not a trunk merge.)*
2. **Decisions resolved as `Accepted` ADRs** — every open design question the phase was meant to
   settle is an `Accepted` ADR (`decisions-adr.md`), not a half-finished register entry.

No half-open phases: you do not start Phase N+1's deliverables while Phase N's gate is unmet.
When the gate is met, **tag the merge commit `phase-N`** (annotated, pushed) — see `repo-and-ci.md`.
**Track the current phase** at the top of `docs/process/ways-of-working.md`.

**Phases 0–3 produce only `.md` + ADRs** (Phase 2 also a pitch deck). The **3 → 4 gate is the
single hard line where Jira items first appear** — Stories open with their functional sections; the
technical design enriches them in Phase 5. See non-negotiable #4 in the spine.

## The co-authoring fast track (Phases 3–5)

When the design is **co-authored with Claude** — the sponsor/PO/architect steer and decide, Claude
drafts — and the **Phase 4 functional backlog is generated directly from the Phase 3 specs** (with the
Phase 5 Technical design sections + Enablers generated from the Phase 5 technical design), the
document-authoring phases compress from weeks to days. Plan Phases 3–5 in **days, not weeks**.

**This does not waive design-first.** The gates are unchanged: specs with acceptance criteria, state
machines `Accepted`, the component list frozen, every backlog item traceable to an ADR/spec. What
shrinks is *authoring time*, not *rigour* — Claude drafts, humans ratify, and the ADRs are identical
either way.

Because only the writing compresses, the critical path moves onto what authoring speed cannot touch.
Estimate and de-risk **these**, not the drafting:

1. **Stakeholder availability.** The architect (gates the Phase 2 feasibility read *and* the Phase 5
   technical-design review) and the domain PO (Phases 3–4: functional design + functional backlog) must
   be engaged; their review/ratify time is the new bottleneck.
2. **External inputs.** Specs, schemas/XSDs, reference data, regulatory dictionaries — acquiring and
   validating them is calendar-bound regardless of how fast the docs are written.
3. **The build's human floor (Phase 6).** Review, integration, QA/UAT, and correctness verification do
   **not** compress because code is AI-authored — and an AI-speed build estimate already assumes the
   coding speed-up, so don't double-count it by also shrinking the floor.

**Precondition:** the steering humans are available to co-author in tight loops. If they can only engage
part-time or asynchronously, the phases stretch back toward traditional durations — the bottleneck
becomes *their* availability, not Claude's drafting. *(Worked example — OER, 2026-06: design→backlog
replanned from ~6 weeks to ~3 once co-authoring + backlog-from-design was assumed; the residual schedule
risk sat entirely on the three items above.)*

## Phase 0 — Setup & Process

- **Purpose:** stand up the project's skeleton and the rules it will run by, before any thinking
  about the product itself can get lost.
- **Deliverables:** repo scaffold; `PLAN.md` (vision + Decision Register); `README.md` skeleton;
  project `CLAUDE.md` (agent rules); the `docs/` tree (`decisions/ functional/ technical/ process/
  research/`); `docs/process/ways-of-working.md`; **bootstrap ADRs** — adopt MADR, repo layout,
  branching/commit convention, doc-sync (Confluence), CI/CD platform; the Jira-project **criteria**
  recorded (decision itself deferred — `jira-project-choice.md`).
- **Exit gate:** repo initialized; bootstrap ADRs `Accepted`; Jira-project criteria recorded.
- **Who:** sponsor/lead + Claude (solo).
- **Scaling (feature/Epic):** no repo *per feature* — the design lives as a self-contained folder in a
  shared design repo (a repo dedicated to design-only artifacts), or a `docs/<feature>/` subtree of the
  product repo when that repo is a suitable design home (`repo-and-ci.md` § *Where the design artifacts live*).
  Reuse the shared ways-of-working; ADRs are folder-scoped and gate tags are namespaced
  `<initiative>/phase-N`. Bootstrap ADRs already exist; you only add feature-scoped ones.

## Phase 1 — Functional Scoping & Vision

- **Purpose:** make the MVP boundary unambiguous and the vocabulary shared, so the pitch is credible
  and design can't drift.
- **Deliverables:** `scope.md` (MVP in/out), personas, **glossary** (frozen), use-cases, quantified
  **NFRs**, and the project's **domain invariants** (non-negotiable #7 — name them here).
- **Exit gate:** scope clear enough to pitch; glossary frozen; MVP boundary unambiguous.
- **Who:** sponsor/lead + Claude; optional informal read from a domain PO.
- **Scaling:** a short scope/brief note rather than a document set — but the MVP boundary and any
  new domain invariants are still written down.

## Phase 2 — Framing & Approval

- **Purpose:** get a formal mandate and resources *before* sinking heavy design effort — and *after*
  enough scoping to be credible. This is the single phase that also yields a non-`.md` artifact (a
  slide deck), authored as `deck.md` and rendered one-way with the **Opencell Marp theme** — authoring
  conventions, the render command, and the overflow check live in the **`oc-fn-decks`** skill.
- **Deliverables:** **business case** (problem, qualitative value, **effort in man-days + delay**,
  risks, the "ask"); high-level architecture sketch (reuse the candidate architecture from `PLAN.md`); a
  light **feasibility read** from the architect + infra owner; **slideware** for the approvers.
  **For a Claude-authored build, the figures that matter at this gate are effort (man-days) and delay —
  not euros/ROI/P&L**, which Finance builds later; quantify with the authoring + human-floor model in
  `phase2-estimate.md`.
- **Exit gate:** **go/no-go** — SteerCo for a full product, sponsor/lead sign-off for a big feature
  (`engagement.md`). A "go" means: mandate, budget/resourcing, and stakeholder time secured.
- **Who:** sponsor/lead presents; approvers decide; architect + infra give the feasibility read.
- **Scaling:** for a feature, this collapses to a one-page brief + a sponsor decision — but the
  *intent* (someone with authority says "go", resourcing is real) still has to clear.

## Phase 3 — Functional Design

- **Purpose:** specify *what* the system does precisely enough to build, with behaviour pinned down.
- **Deliverables:** conceptual domain model; per-capability specs with acceptance criteria; API
  contract sketch; **state machines**; behavioural ADRs (e.g. retry/idempotency/callback guarantees).
- **Exit gate:** every MVP use case has a spec + acceptance criteria; state machines `Accepted`; API
  surface enumerated.
- **Who:** sponsor/lead + the **domain PO** (now formally engaged) + Claude.
- **Scaling:** proportionate — fewer specs, but **design-first is never waived**; the behaviour of a
  big feature still gets specified before its backlog is cut.

## Phase 4 — Backlog Creation, Functional (**Jira opens here**)

- **Purpose:** turn the *approved* functional design into trackable work. **This is the first phase
  where Jira issues exist.** Hand off issue authoring to **`oc-fn-func-design`**.
- **Deliverables:** Epics (one per **functional capability** from Phase 3); User Stories (vertical
  slices) created with their **functional** sections filled from the Phase-3 specs — **Requirement**,
  **Functional Design**, **Acceptance** criteria — each traceable to its Phase-3 spec/ADR. *(The
  Technical design section and Enablers are deferred to Phase 5 — they depend on the technical design.)*
- **Exit gate:** every MVP use case is a Story in Jira; each Story's functional sections are complete
  and **domain-PO-approved**; the functional backlog traces to Phase-3 specs. *(Build-readiness —
  Technical design sections, Enablers, sprint 1 — is the Phase 5 gate, not this one.)*
- **Who:** sponsor/lead + **domain PO**; issue authoring per `oc-fn-func-design`.
- **Decision due here:** where the backlog lives — `jira-project-choice.md`.
- **Scaling:** one **Epic + functional Stories** in the existing project rather than a full program backlog.

## Phase 5 — Technical Design / Architecture

- **Purpose:** decide *how* it is built, freeze the component list, and enrich the backlog with the
  technical design.
- **Deliverables:** C4 architecture; **stack ADRs**; security design; any external **contract** (e.g. a
  gateway/integration module); OpenAPI draft; data model; **deployment/infra** (CI/CD, K8s, container
  topology); observability/audit design — all as `.md` in `docs/technical/` (the repo stays the source
  of truth). Then, in Jira: each Story's **Technical design** section (`customfield_10137`) populated
  from those `.md` artifacts, and **Enablers** created for the technical work the design surfaces, each
  linked to its ADR/spec. *(The Technical-design section is authored by the **architect lane** — the
  `oc-ar-tech-design` skill (marketplace `oc-ar-tools`), where available — from these Phase-5
  `docs/technical/` artifacts. `oc-fn-func-design` covers Enabler creation and the functional sections,
  and creates the empty Technical-design scaffold, but does **not** author `customfield_10137`. The
  architect lane needs the same Atlassian/Jira connector — gate the hand-off on it regardless of which
  lane owns the field.)*
- **Exit gate:** stack chosen + ADR'd; OpenAPI validates; deployment topology agreed with infra;
  **component list frozen**; every Story's Technical design section filled; Enablers created;
  **sprint 1 selected** (the backlog is now build-ready).
- **Who:** sponsor/lead + **architect** + **infra owner** + Claude; Enablers + functional sections per
  `oc-fn-func-design`; the Technical-design section per the architect lane (`oc-ar-tech-design`, where available).
- **Scaling:** the technical decisions a feature introduces still become ADRs; the "frozen component
  list" becomes the Enablers + the Stories' Technical design sections.

## Phase 6 — Iterative Implementation

- **Purpose:** build the software, with tests and docs in the *same* PR.
- **Deliverables:** working software per Story; tests; docs updated in the same PR; AI-authored code
  under human review (`repo-and-ci.md`, two-tier review).
- **Exit gate:** story criteria met; CI green; demoed. **MVP exit:** the end-to-end critical path is
  proven (for OPH: Core → Gateway → OPH → PSP payment).
- **Who:** Claude authors; humans review; non-waivable sign-off on sensitive seams.

> **Execution layer (Phase 6).** On an `oc-fn-tools` + common-plugins setup (if those plugins are
> installed), per-ticket implementation in this phase runs through the marketplace **common flow**:
> `/oc-cache-jira` → implement (`/oc-fe-fix-bug` or `/oc-fe-create-ui` for frontend; `oc-be-tools`
> `/oc-be-implement` for backend) → `/oc-commit` → `/oc-pull-request` → `/oc-review-pr` — subject to
> the reconciliations in `repo-and-ci.md` (branch base-segment, trunk default, ticket-cache
> dependency). **This skill is the PROCESS layer; the common flow is the EXECUTION layer; they meet at
> the Phase 5 → 6 gate** — implementation only begins once Phase 5's hard gate is cleared (no
> application code before the gate, non-negotiable #1).

## Phase 7 — Docs & Release

- **Purpose:** finalize documentation and ship a tagged release.
- **Deliverables:** finalized technical + **user manual**; Confluence sync (hand off to
  **`oc-fn-documentation`**); CHANGELOG; version tag; runbook.
- **Exit gate:** tagged release; Confluence live & matching the repo `.md`.
- **Who:** sponsor/lead + Claude; infra owner for the release/runbook.

## Why Phase 2 sits where it does

The approval gate comes **after** lightweight scoping (so the pitch is credible) but **before**
detailed functional/technical design (so heavy, unofficial effort isn't sunk before a mandate
exists). This ordering is deliberate — don't move design work earlier to "strengthen the pitch";
that's exactly the sunk-cost trap the gate prevents.
