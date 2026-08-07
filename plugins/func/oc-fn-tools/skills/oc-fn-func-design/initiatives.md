# Jira INTRD — Initiatives

Reference rules for Initiative issues on the INTRD project.
Read together with the main `SKILL.md`. **Minimal by design** — an Initiative is a single
`description`-field issue driven by its template; this file adds only the Initiative-specific
framing.

> **`Initiative` replaced `Feature` — migration complete 2026-07-09.** `Initiative` is the
> above-Epic container, and it is the **altitude** axis *only*: the product area is captured
> orthogonally by the **Module**, a Jira Component set on Epics/Stories/Enablers — never by the
> Initiative.
>
> **The `Feature` type no longer exists.** All 80 `Feature` issues were deleted and the work type
> was retired site-wide; the 86 functional areas they encoded became 30 module Components, with 370
> Epics backfilled. So there are no legacy `Feature` issues left to handle, and a `Feature` cannot
> be created. If someone asks for one, they mean either an **Initiative** (altitude) or a **Module**
> Component (product area) — establish which. Note the Component field also carries a pre-existing
> dev-layer taxonomy (`Backend`, `Frontend`); module and layer tags coexist on it.

## What is an Initiative

An Initiative is the **strategic, multi-Epic programme** above Epic in the INTRD hierarchy
(Initiative → Epic → Story | Enabler → Sub-task). It is a **bounded programme** — typically
**phased** (`step 1 → step N`) and converging on a **named end-state** — that **closes when
shipped**. It is owned at product-management level.

Use an Initiative only for a *bounded programme*, never for a standing product area:

- **Initiative (altitude)** — a finite, phased programme with a terminus: e.g. *Multi-currency*,
  *Dunning build-out (step 1→4)*, *French e-invoicing reform compliance*, *Mass rerating*.
- **Module (area — NOT an Initiative)** — a perpetual product area that never "finishes":
  e.g. *Catalog*, *Billing*, *Payments*. A Module is a **Jira Component** set on the Epics — it
  is not an issue type. A heterogeneous bag of unrelated Epics is a Module, not an Initiative.

The discriminator: if the work has **no end-state** and just accumulates capability forever, it
is a Module (Component), not an Initiative.

## Template

The Initiative template is **INTRD-42501** (repurposed from the former Feature template). It
uses the standard `description` field with the shared ADF vocabulary in
[`SKILL.md` § Templates index](SKILL.md#templates-index) — same read-side `description` gotcha
and `expand: "renderedFields"` verification as Epics. **Read the template first**; new
Initiatives written from it must be ADF with the dark-red (`#bf2600`) `strong` headings each
followed by a `rule` node. It is typed `Initiative` and follows the **Epic workflow** lifecycle
(`To Study … Released … Rejected`) — same as Epics.

## Fields

Initiatives use the standard **`description`** field. Full-read preset:

```
["summary", "status", "issuetype", "priority", "assignee", "labels", "components", "description"]
```

For hierarchy inspection (child Epics under the Initiative):

```
["summary", "issuetype", "subtasks", "issuelinks"]
```

## Authoring notes

Follow the template's sections. An Initiative description is **strategic, not implementation**:

- **Charter** — one sentence, "give Opencell the ability to …": the bounded outcome the
  Initiative delivers and the strategic/regulatory bet behind it, above any single Epic.
- **Phases & breakdown** — the Epics that compose it, ideally as the `step 1 → step N`
  sequence; what is in scope and explicitly out; the end-state that closes the Initiative.
- **Linkage** — parent or link the child Epics so the hierarchy is navigable. Each child Epic
  carries its own **Module** (the orthogonal area axis), independent of the Initiative.

Per-Epic and per-Story detail belongs in those children, not here.

## Limits & volumes

See `SKILL.md` § *Limits & volumes — mandatory reflection*. The **envelope normally lives on
the child Epics** (`epics.md` § *Limits & volumes (envelope)*). Carry an Initiative-level
envelope in the `description` only when the Initiative sets **cross-Epic, programme-wide** scale
targets the Epics must inherit — use the Epic checklist at a coarser grain. Otherwise mark it
**`N/A — envelope set per child Epic`**.
