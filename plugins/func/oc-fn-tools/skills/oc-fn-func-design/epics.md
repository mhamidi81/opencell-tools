# Jira INTRD — Epics

Reference rules for Epic issues on the INTRD project.
Read together with the main `SKILL.md`.

## What is an Epic

An Epic is a portfolio-level container that groups a coherent body of work — multiple User Stories and Enablers — delivering a single strategic outcome. It is **not** a sprint-sized work item: it spans weeks to quarters and is owned at PO / product-management level, not at dev-team level.

| Compare with…       | Key distinction                                                                                                                                                |
|---------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Initiative**      | An Initiative is the bounded, multi-Epic programme above Epic on the altitude axis. An Epic sits below an Initiative only when it is part of that programme; standing product-area Epics have no Initiative parent and are tagged by Module instead. |
| **User Story**      | A User Story is a sprint-sized increment of user value. An Epic groups many such increments around a shared strategic outcome.                                 |
| **Enabler**         | An Enabler is sprint-sized technical work. An Epic groups Enablers and Stories whose combined delivery realises the Epic outcome.                              |

## Template

The Epic template is **INTRD-1949**. It uses the standard `description` field with the shared ADF vocabulary documented in [`SKILL.md` § Templates index](SKILL.md#templates-index) — including the read-side `description`-field gotcha and the `expand: "renderedFields"` verification trick. Edits to the Epic template (or any Epic-derived issue that should keep the formatting) must be written as ADF.

Although the `description` field also accepts Markdown, new Epics authored from the template must be written as ADF reproducing the template's dark-red (`#bf2600`) `strong` headings, each followed by a `rule` node. A first pass with plain ADF headings (no colour, no rule) will be rejected by reviewers even when the prose content is correct — visual fidelity to the template is expected.

## Fields

Epics use the standard **`description`** field — not the custom fields used by User Stories.

Field preset for full read:

```
["summary", "status", "issuetype", "priority", "assignee", "parent", "labels", "components", "description"]
```

For hierarchy inspection (Stories and Enablers under the Epic):

```
["summary", "status", "issuetype", "subtasks", "issuelinks"]
```

## Child Story naming

Every Story that belongs to an Epic **must** follow this naming pattern:

```
[<epic-suffix>] (<n>) <story name>
```

- **`<epic-suffix>`** — a short, lowercase, hyphenated token that identifies the Epic, chosen when the Epic is created and used consistently across all its children (e.g. `e-reporting`, `payment-v2`, `usage-rating`).
- **`(<n>)`** — an integer indicating the intended **order of delivery** within the Epic (starting at 1). It is a **delivery-order label, not a stable identifier**: it is renumbered — sometimes **retroactively** — to match the actual development order (lower `(<n>)` = further along / done first), and a Story can **move to another Epic** and be renumbered under that Epic's suffix / scheme (e.g. a step-4 story moving to a step-5 `5NN` range). **Always identify a Story by its Jira key (`INTRD-#####`)** — the `(<n>)` reflects current state only; never rely on it as an identifier in docs, links, or cross-references. Renumber in Jira as the order changes (and refresh any dated snapshot table in a design doc); key-anchored references stay valid.
- **`<story name>`** — the story's own title, written as a short imperative phrase.

**Example:** `[e-reporting] (1) Generate e-reporting XML`

The suffix must be identical across all Stories of the same Epic — any variation (casing, spelling, spacing) breaks the visual grouping in the Jira backlog. When creating a batch of Stories, define the suffix on the Epic first and copy it verbatim to each child.

**Every child Story must be functional *and* demonstrable.** When decomposing an Epic, each Story
must pass the functional litmus (`SKILL.md` § *Authoring boundary — User Stories are functional,
never technical*) — describe user-facing value, not implementation work. It must also be
**independently demonstrable**: slice the Epic **vertically** (thin end-to-end increments of
observable value), never by technical pipeline stage — see `stories.md` § *Story scope —
demonstrable, not just functional*. Technical needs surfaced while decomposing become
architect-created **Enablers**, not Stories: list them separately for the architect lane rather
than emitting them as child Stories.

## Domain model & decided design inputs

Cross-cutting principle and the bounded-exception framing: see `SKILL.md` § *Decided model bindings
— name the conceptual home in the functional design*. The Epic is where the **consolidated**
conceptual model lives, so child Stories reference it instead of each re-deriving (and drifting) it.

**Placement.** A dedicated *Domain model & decided design inputs* section in the Epic `description`,
after the strategic outcome / scope and before the breakdown of child work (it sits alongside the
*Limits & volumes (envelope)* section as the other shared, inherited envelope). The Epic template
**INTRD-1949** carries the scaffold.

**What it contains** — the conceptual data dictionary, at the conceptual level only:

- **New entities** introduced by the Epic + their key attributes.
- **Attributes added to existing entities** (name the entity and the attribute).
- **Read-only sources** the work consumes but does not own.
- **Decided inputs** the architect must respect, **each with its rationale / ADR** so the decision
  is not re-litigated downstream.

**Stay conceptual.** Physical realization — tables, JPA mappings, indexes, DDL — is out of lane here;
it belongs to the architect in each Story's *Technical design* (`customfield_10137`). Close the
section with a boundary note: *the architect lane owns the physical design in each Story's Technical
design; decided inputs are not to be re-litigated; to change a constraint, update this Epic first.*

**Inheritance.** Child Stories **inherit** this section the same way they inherit the *Limits &
volumes (envelope)* — each Story names only its slice (its *Held on (conceptual model)* rows, see
`stories.md` § *Information requirements — naming decided model bindings*) and **references** the
Epic. The shared model is defined **once** on the Epic; children narrow or reference it, never
duplicate it (duplication drifts).

**Render gotcha (Epic `description`).** In an Epic `description`, a bare `{ENUM}` in curly braces gets
macro-parsed by Jira and isolated onto its own line, and an inline-code mark there renders as a
literal `{{..}}`. Prefer plain prose ("values: A, B, C") over "{A, B, C}" in Epic descriptions.
(Inside Story custom fields `10134`–`10137`, inline-code chips render fine.)

## Limits & volumes (envelope)

Cross-cutting rule and strict-answering policy: see `SKILL.md` § *Limits & volumes — mandatory reflection*. The Epic carries the **envelope** that child Stories and Enablers inherit and refine.

**Placement.** The limits-and-volumes content lives in a dedicated *Limits & volumes (envelope)* section of the Epic `description`, placed after the strategic outcome / scope and before the breakdown of child work.

**Tone.** Epic-level figures are program-level, not implementation-level. They describe the scale the *whole* outcome must support, not the per-endpoint detail (that belongs in the child Enabler) nor the per-flow detail (that belongs in the child Story).

**Checklist.** Answer each point, or write `N/A — <one-line reason>`:

1. **Target adoption horizon** — projected number of tenants, end users, and active users at GA, at 6 months post-GA, and at 12 months post-GA. State the assumption source (PM forecast, contract commitment, comparable feature uptake).
2. **Business-volume drivers** — the domain entities whose growth drives load (invoices, subscriptions, events, jobs, …): expected count per tenant per month, peak month vs steady state, and the long-tail vs whale distribution if relevant.
3. **Traffic envelope** — sustained and peak requests/sec aggregated across all child Stories/Enablers, with the burst-window length. Distinguish read-heavy vs write-heavy components of the envelope.
4. **Concurrency envelope** — concurrent end-user sessions on the Epic's flows at peak. Call out any flow with structural contention (single-writer, queue-ordered, locked resource).
5. **SLA budget** — p95 / p99 latency target for the Epic's main user actions, and the availability target (uptime / error-rate budget) the Epic commits to. This is the envelope child Stories carve up.
6. **Storage & data-volume horizon** — total storage footprint of the Epic's new or modified entities at GA, at 6 months, and at 12 months post-GA. State the retention / archival assumption.
7. **Hard limits inherited from outside** — non-negotiable caps imposed by compliance, contractual SLAs, infrastructure quotas, third-party APIs, or licensing. Each child must respect these even if no other limit is set.
8. **Cost envelope** — order-of-magnitude infrastructure cost the Epic commits to (per-tenant, per-month, or per-event), where the design must stay within a stated budget. `N/A` is acceptable but should not be reflexive.
9. **Degradation strategy at the envelope level** — what the *product* does when the envelope is exceeded: rate-limit, queue, shed, scale out, fail closed. Children inherit this strategy unless they override it explicitly.
10. **Telemetry & SLO ownership** — which dashboards / SLOs cover the Epic's envelope, and who is on-call for breaches. Children plug their per-flow metrics into these.

**Reviewer expectation.** An Epic with a blank or hand-waved envelope blocks its child Stories and Enablers from being reviewed in isolation. Fill it before opening children for design review — or, if the Epic is already in flight, retrofit the envelope and circulate it to the team before continuing.

**Updating the envelope.** When a child needs to exceed an envelope number, update the Epic first: change the figure, leave a comment explaining what triggered the change (forecast revision, new contract, discovered constraint), and link the child issue. Do not silently let a child exceed the envelope.

## Workflow

The Epic workflow is documented separately in Jira; until captured here, run `getTransitionsForJiraIssue` on a sample Epic to discover the available transitions for the current issue.
