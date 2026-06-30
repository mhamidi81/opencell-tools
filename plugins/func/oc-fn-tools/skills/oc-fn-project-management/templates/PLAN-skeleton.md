<!-- TEMPLATE — copy to PLAN.md at the repo root. Replace every <placeholder>; delete these
     guidance comments. This is the source of truth for process until the Jira backlog opens
     (Phase 4). Keep §6 (architecture) explicitly provisional until Phase 5 ratifies it. -->

# PLAN.md — <Project Name> (<ACRONYM>)

> **Status:** Initialization / roadmap — _provisional_.
> **Purpose:** Bootstraps the project — vision, stakeholders, way of working, provisional target
> architecture, and the **open decisions** to resolve **before building**. Source of truth for
> process until the Jira backlog opens (Phase 4).
> **Founding brief:** [`PROMPT.md`](./PROMPT.md) <!-- the verbatim original request, if you have one -->
> **Last updated:** <YYYY-MM-DD>.

> ⚠️ Nothing in §6 (architecture) is locked. It is the _candidate_ design that the design phases
> confirm, amend, or reject. Every real decision becomes an ADR; genuinely open ones live in the
> **Decision Register** (§9).

---

## 1. Vision & product charter

<!-- 3–6 bullets: what it is, what makes it independent/distinct, the mandatory cross-cutting
     properties (e.g. multi-X by design), the deployment/tenancy stance, "platform not a script". -->

---

## 2. Stakeholders & governance

| Person | Role | Involvement |
|---|---|---|
| **<You>** | <e.g. VP Product> | Sponsor & lead; writes the pitch; drives design with Claude |
| … | … | … |

**Engagement sequence:** lightweight/solo through early phases → informal feasibility read from
architect + infra → approval gate (Phase 2) → on approval, engage domain PO (Phases 3–4) and
architect/infra (Phase 5). The sponsor controls who is brought in when. <!-- see engagement.md -->

---

## 3. Consolidated requirements

### 3.1 Functional
| # | Requirement |
|---|-------------|
| F1 | … |

### 3.2 Non-functional
| # | Requirement |
|---|-------------|
| N1 | … |

### 3.3 Infrastructure & delivery constraints *(org standards — given)*
| # | Constraint |
|---|-----------|
| C1 | … |

---

## 4. Guiding principles

<!-- Start from the methodology's non-negotiables (SKILL.md §3), then add THIS project's domain
     invariants (non-negotiable #7) as numbered, non-preference laws. -->
1. **Decide before building.** Functional → technical design precedes implementation.
2. **Every decision is written down with its rationale** — as an ADR.
3. **<Domain invariant 1>** — <the law, stated as fact not preference>.
4. **Stable seams.** <name the swappable boundaries>.

---

## 5. Integration points *(if this plugs into an existing system)*

<!-- Optional but high-value: the FACTUAL contract you must integrate with (interfaces, gaps,
     required changes on the other side). Keep it grounded in the other system's real code. -->

---

## 6. Provisional target architecture *(to be ratified in Phase 5)*

<!-- Candidate shape, modules, core domain, key state machines, security posture, deployment.
     Mark everything provisional; each real choice becomes an ADR via the Decision Register. -->

---

## 7. Delivery model — the phased plan

Eight phases with **hard gates**. **Phases 0–3 produce only `.md` + ADRs** (Phase 2 also a pitch
deck). The **3 → 4 gate is the single hard line** where Jira items first appear. A phase exits only
when (a) its deliverables are merged to trunk and (b) its design questions are `Accepted` ADRs.

| Phase | Name | Produces | Exit gate |
|---|---|---|---|
| 0 | Setup & Process | this plan, README/CLAUDE skeletons, `/docs` scaffold, bootstrap ADRs, ways-of-working | repo initialized; bootstrap ADRs Accepted; Jira criteria recorded |
| 1 | Functional Scoping & Vision | scope, personas, glossary, use-cases, NFRs, domain invariants | scope pitch-ready; glossary frozen; MVP boundary unambiguous |
| 2 | Framing & Approval | business case + slideware; feasibility read | **go/no-go** — mandate, budget, stakeholders engaged |
| 3 | Functional Design | domain model, specs, API sketch, state machines | every MVP use case spec'd; state machines Accepted; API enumerated |
| 4 | Backlog Creation — Functional (**Jira opens**) | Epics (per capability) + Stories with functional sections (Requirement, Functional Design, Acceptance) | every MVP Story exists; functional sections PO-approved |
| 5 | Technical Design | C4, stack ADRs, security, contracts, OpenAPI, data model, infra; Stories' Technical design filled; Enablers created | stack ADR'd; OpenAPI validates; infra agreed; component list frozen; Technical design filled; Enablers created; sprint 1 selected |
| 6 | Iterative Implementation | working software, tests, docs in the same PR | story criteria met; CI green; end-to-end path proven |
| 7 | Docs & Release | finalized docs, Confluence sync, CHANGELOG, tag, runbook | tagged release; Confluence live & matching repo `.md` |

---

## 8. Ways of working

Operational detail lives in [`docs/process/ways-of-working.md`](./docs/process/ways-of-working.md).
Summary: MADR ADRs in `docs/decisions/` + `DECISIONS.md` index; mono-repo with cross-product code
carved out; trunk-based protected `main`, squash-merge, annotated `X.Y.Z` + `phase-N` tags; two-tier
PR review (automated gauntlet + non-waivable human sign-off on sensitive seams); Jenkins CI/CD,
Bitbucket source+PRs, Jira planning; `.md` source of truth, Confluence one-way mirror.

---

## 9. Decision Register

Decisions owed; each becomes an ADR. **Status:** `Open` · `Narrowed` · `Resolved`.

| ID | Decision | Status | Direction & rationale | Target phase |
|---|---|---|---|---|
| DR-1 | <decision> | Open | <lean, if any> | <phase> |

---

## 10. Top risks & mitigations

| Risk | Mitigation |
|---|---|
| **No mandate / under-resourced** | Sharp business case + ROI before heavy investment; secure specialist time in the "ask" |
| **Phase-gate erosion** — coding before design ADRs Accepted | Jira opens only after functional design is approved (Phase 4); no application code until Phase 5 ADRs Accepted + the component list frozen |
| … | … |

---

## 11. Immediate next steps (Phase 0)

1. Discuss & adjust this PLAN.
2. Scaffold the `/docs` tree + `DECISIONS.md` + `adr-template.md`.
3. Write the bootstrap ADRs (MADR, repo layout, branching, doc-sync, CI/CD).
4. Draft `README.md` + project `CLAUDE.md`.
5. Record the Jira-project criteria (decision deferred to Phase 4).
6. First commit on the chosen trunk.

---

## Appendix — provenance

<!-- Where this plan's grounding came from: source systems read, docs/standards consulted. -->
