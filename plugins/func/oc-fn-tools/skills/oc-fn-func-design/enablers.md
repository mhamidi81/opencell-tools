# Jira INTRD — Enablers

Reference rules for Enabler issues on the INTRD project.
Read together with the main `SKILL.md`.

## What is an Enabler

An Enabler covers technical work that does not directly deliver user-facing value. Use it when the work is a prerequisite, infrastructure improvement, or architectural foundation rather than a feature a user would describe.

An Enabler is either **Backend** (API, job, data model, infrastructure) or **Frontend** (UI component, route, store, theming) — never both. Horizontal slicing is the whole point: a single Enabler delivers one technical slice on one side of the stack.

| Compare with… | Key distinction |
|---|---|
| **User Story** | A User Story delivers value a user or PO can validate; an Enabler delivers technical capability that other stories depend on. Horizontal slicing (back-only or front-only work) is an Enabler's legitimate justification, not a User Story variant. |
| **Bug** | A Bug fixes a defect in existing behaviour; an Enabler introduces new technical capability or makes a deliberate improvement. |
| **Epic / Initiative** | Epics and Initiatives are portfolio/product-level containers; an Enabler is sprint-sized, dev-team owned, and implements one concrete technical outcome. |

## Ownership — architect-initiated

**Enablers are architect-owned.** They are typically split out by the architect lane during
Phase-3 Technical Design, when a Story is too big or carries a technical prerequisite. The
func/PO lane does **not** create Enablers by default: it keeps Stories functional and **flags
the technical need** for the architects. Author an Enabler from this lane **only on explicit user
request** — the same explicit-request exception used for the Story *Technical design* field. See
`SKILL.md` § *Authoring boundary — User Stories are functional, never technical*. The authoring
guidance below applies once that explicit request is given (or when reviewing/linking an
architect-authored Enabler).

## Template

The Enabler template is **INTRD-42939**. It uses the shared ADF vocabulary documented in [`SKILL.md` § Templates index](SKILL.md#templates-index) — including the read-side `description`-field gotcha and the `expand: "renderedFields"` verification trick. Edits to the Enabler template (or any Enabler-derived issue that should keep the formatting) must be written as ADF.

The template carries two parallel *Technical contract* sub-sections — **Backend** and **Frontend**. When authoring an Enabler, keep the one matching the scope and **delete the other entirely**, including its heading. The Backend variant covers API / Error dictionary / Model / Migration; the Frontend variant covers Components / Routes / State / API consumption / Styling & i18n.

## Fields

Enablers use the standard **`description`** field — not the custom fields `customfield_10134`–`10137` used by User Stories.

Field preset for full read:

```
["summary", "status", "issuetype", "priority", "assignee", "parent", "labels", "components", "description"]
```

## Creation pattern — mandatory two-step

> Applies only once the func/PO lane has explicit user consent to author an Enabler — otherwise
> flag the technical need for the architect lane (see § *Ownership — architect-initiated*).

A Jira automation on INTRD will overwrite fields at Enabler creation once a template is configured. Use the same two-step pattern as User Stories:

1. `createJiraIssue` — create the issue with summary and issue type only.
2. Immediately follow with `editJiraIssue` — set `description` (and any other fields) in this second call.

Never attempt to set `description` inside `createJiraIssue` — it will be lost once the automation is active.

## Content format

Follow the general skill policy: **Markdown by default**, ADF only when the content requires panels, multi-column layouts, status lozenges, or other rich elements that Markdown cannot express.

## Workflow

The Enabler workflow is simpler than the User Story workflow; it will be documented here once defined. Until then, run `getTransitionsForJiraIssue` on a sample Enabler to discover the available transitions for the current issue.

## Authoring guidance

> Applies when authoring an architect-initiated Enabler (or one the user explicitly asked this
> lane to write) — see § *Ownership — architect-initiated*.

An Enabler description should cover:

- **Scope** — state up front whether this is a *Backend* or *Frontend* Enabler. This drives which *Technical contract* sub-section is kept.
- **Technical context** — current state, motivation for the work, parent Epic or Initiative, and the User Stories that will consume this Enabler.
- **Technical contract** — fill in only the variant matching the scope:
  - *Backend*: API surface (REST v2), error dictionary, data-model changes, schema migrations, infrastructure configuration.
  - *Frontend*: components (props/events), routes & navigation, state management, backend endpoints consumed, styling/design-system tokens, i18n keys, accessibility.
- **Technical acceptance criteria** — measurable conditions: performance targets, backward-compatibility constraints, observability hooks, test coverage.
- **Non-goals** — the shared invariant is that an Enabler is not a standalone user-facing feature; value is realised by the consuming User Stories, and there are no functional acceptance criteria written from a user perspective. Add the scope-specific exclusion too: a Backend Enabler delivers no UI; a Frontend Enabler delivers no backend contract change.

## Limits & volumes

Cross-cutting rule and strict-answering policy: see `SKILL.md` § *Limits & volumes — mandatory reflection*. This section is the enabler-specific checklist, split per variant.

**Placement.** The limits-and-volumes content lives **inside *Technical acceptance criteria*** — it sets the measurable bar against which the enabler is validated, which is what that section is for. It is the final sub-section of *Technical acceptance criteria*, under a heading `Limits & volumes`.

**Inherit from the parent.** Before filling this section, open the parent Epic (and Initiative if any) and copy the relevant envelope figures verbatim into a short *Inherited envelope* paragraph. Then answer the checklist below in terms of this enabler's slice of that envelope. An enabler whose parent has no envelope blocks on the parent — flag it rather than invent numbers.

Pick exactly one of the two checklists below, matching the enabler's scope.

### Limits & volumes — Backend

For Backend enablers (API, job, data model, infrastructure). Answer each point, or write `N/A — <one-line reason>`:

1. **Throughput** — sustained and peak requests/sec (or jobs/min) the enabler must support, with the time window of the peak (burst length).
2. **Payload caps** — maximum request body size, maximum response body size, maximum batch size for any bulk endpoint. State what the server does beyond the cap (413 / 400 / chunked).
3. **Pagination & result-set caps** — default page size, maximum page size, total result-set cap on each new or modified listing/search endpoint, and the behaviour beyond the cap (truncate / paginate / error).
4. **Query limits** — for each new SQL/NoSQL query or aggregation: expected row count scanned, indexes relied on, worst-case complexity, and the timeout the layer above applies.
5. **Timeouts** — request timeout, per-dependency timeout, retry policy (count, backoff, idempotency assumption), and circuit-breaker behaviour where applicable.
6. **Concurrency model** — number of concurrent in-flight requests/jobs the design tolerates, locking strategy (pessimistic / optimistic / none), queue ordering guarantees, and behaviour under saturation (queue / shed / backpressure).
7. **Storage footprint & growth** — per-tenant and global row count / byte size at GA, growth assumption (per day / per active user), and retention or archival policy where applicable.
8. **Cardinality assumptions** — distinct values the design assumes are bounded (tenants, custom fields, error codes, enum values). State the bound and what breaks if it is exceeded.
9. **Migration & backfill volumes** — when the enabler ships a schema change or data migration: total rows touched, expected duration, online vs offline, lock footprint, rollback path.
10. **Degradation behaviour** — what callers observe when any limit above is hit: clear error code, soft truncation, graceful fallback, 429 + Retry-After. Silent failure is never acceptable.
11. **Telemetry hooks** — metrics, logs, traces, and dashboards that let operations observe each of the above in production. If observability is deferred, link to the follow-up issue.

### Limits & volumes — Frontend

For Frontend enablers (UI component, route, store, theming). Answer each point, or write `N/A — <one-line reason>`:

1. **List / grid sizes** — for any new list, table, or grid: typical and worst-case item count, virtualization or pagination strategy at the worst case, and behaviour beyond that (load-more / page / truncate with link).
2. **Render-cost-sensitive components** — components whose render cost scales non-trivially with input (charts, tree views, drag-and-drop boards, rich-text editors): the size threshold above which the component degrades, and the chosen mitigation (memoization, windowing, lazy mount).
3. **Bundle & asset weight** — gzipped JS/CSS added by this enabler, lazy-loaded vs eager. State the budget cap and whether the change is within it.
4. **Concurrent network calls** — number of in-flight API calls a page may issue (initial render, on-interaction). State debouncing / batching / request-deduplication strategy.
5. **Client-side data footprint** — size of in-memory state held by the new store / context / cache (rows, bytes), eviction strategy, and behaviour when the cap is reached.
6. **Latency target** — p50 / p95 for the user-perceived action (first contentful paint, time-to-interactive on the new route, response time of the new interaction). State the measurement device class (low-end / mid / high).
7. **Degradation behaviour** — what the user sees on slow network, large datasets, or partial backend failure: skeletons, empty states, retry affordances, offline messaging. Silent freeze is never acceptable.
8. **Accessibility under load** — keyboard navigation and screen-reader behaviour on the worst-case list / grid size remain functional (no focus loss, no announcement storms).
9. **Telemetry hooks** — RUM metrics, error tracking, and analytics events that observe each of the above in production. If observability is deferred, link to the follow-up issue.

**Reviewer expectation.** A backend enabler that answers fewer than ~6 of 11, or a frontend enabler that answers fewer than ~5 of 9, with substantive (non-`N/A`) content is almost certainly under-reflected. Push back rather than waving it through.
