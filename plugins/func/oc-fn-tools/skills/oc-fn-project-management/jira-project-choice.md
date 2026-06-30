# Where the Jira backlog lives — existing vs dedicated vs hybrid

> Load this at Phase 4 (when the backlog opens) or in Phase 0 when *recording the criteria* for the
> deferred decision. Jira opens **only at Phase 4** (spine non-negotiable #4) — but the *criteria*
> are recorded early so the call is fast and grounded when the time comes.

## The decision

Should the project's Jira work live in an **existing project** (e.g. Opencell's `INTRD`), in a
**new dedicated project**, or in a **hybrid** split? Record the criteria in Phase 0
(`docs/process/jira-project-criteria.md`); **take** the decision in Phase 4 and graduate it to an ADR.

## Criteria to settle before the first Epic

1. **Product vs feature framing.** Is it staffed and reported as **its own product**, or as feature
   work inside an existing one? Own-product framing favours a dedicated project.
2. **Isolated reporting.** Do you need **separate velocity, burndown, and roadmap reporting**? If
   yes → dedicated project.
3. **Context-switching pattern.** Will the team **switch constantly** between the existing product
   and this work within a sprint (favours a *single* project, less overhead), or work **largely
   separately** (favours a *split*)?
4. **Jira-admin overhead tolerance.** A new project means new workflows, screens, permissions,
   boards, and automations to set up and maintain. How much appetite is there for that?

## The hybrid option

The new work gets **its own Jira project** for the parts that are genuinely its own (e.g. its
backend, GUI, infra, policy engine, connectors), while work that belongs to **another product's
lifecycle** stays in that product's project (e.g. a module that imports into Opencell Core → that
product's Jira project). This **mirrors the source-layout split** (`repo-and-ci.md`: carve out
cross-product code) — keep the Jira home aligned with the repo home.

## Inputs that exist by Phase 4

- **The Phase-2 approval mandate** — is it funded/staffed as a product? → answers criteria 1 & 2.
- **The Phase-3 functional capability map** — Epics map 1:1 to functional capabilities, so it sizes the
  backlog and frames the functional scope the Stories will cover.
- **The candidate architecture (`PLAN.md §6`)** — shows which work plausibly belongs to **another
  product's lifecycle** (e.g. a module that imports into Core), informing the hybrid call. The
  *definitive* component split is frozen later, in Phase 5; if it shifts the carve-out, adjust **Enabler**
  placement then — but the project-location decision is taken now, at Phase 4, because you cannot create
  issues without knowing where they live.

## Recording the decision

When taken in Phase 4: graduate the register entry to an ADR (`decisions-adr.md`), update
`DECISIONS.md`, and set up the chosen project(s) following Opencell/Bitbucket/Jira conventions. Issue
authoring from that point is **`oc-fn-func-design`**'s job.
