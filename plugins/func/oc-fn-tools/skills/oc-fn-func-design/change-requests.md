# Jira CR — Change Requests

Reference rules for the **CR ("Change Requests") project** — the Product-team triage & decision
lane that sits between customer/support demand and INTRD delivery. Read together with the main
`SKILL.md`. **The INTRD module-Component rule, altitude hierarchy, and Story custom fields
(`10134`–`10137`) do NOT apply here** — CR is its own project with its own workflow and fields.

## What a Change Request is

A **Change Request (CR)** is any request to **change / extend / add / (rarely) remove a feature**,
raised by a customer, Support, or another Openceller, that the **Product team** triages, studies, and
rules on. It gives Opencell a **single channel** to raise change requests and **one place to check
the official Product decision**. The CR is the **decision record**, not the build: the ruling —
accept / reject / defer — is written into the **Product response** field, and once scheduled the
actual work is authored as INTRD issues and linked back.

> **Source of truth:** the [Change request process](https://opencellsoft.atlassian.net/wiki/spaces/docs/pages/2368569345/Change+request+process)
> page (docs space, Product-authored). This file mirrors it — if they diverge, that page wins; keep
> this file in step.

- **Project:** key **`CR`** ("Change Requests", project id `10054`). Single issue type **Change
  Request** (id `10077`, not a subtask).
- **Not a bug.** A **bug fix is not a CR** (though a client may report a bug that gets *requalified*
  into a CR). A CR changes intended behaviour; a Bug restores specified behaviour.
- **Lifecycle position:** **SUPS** (support ticket) → **CR** (Product decision) → **INTRD**
  (Initiative / Epic / Story / Enabler delivery). A CR does not itself ship — it authorises and
  scopes; delivery lives in INTRD (author those per the rest of this skill).
- **Not an INTRD issue type.** Do not set INTRD module Components on a CR, do not treat it in the
  Initiative→Epic→Story hierarchy, and do not look for the Story custom fields on it.

## Querying the CR project

The `jira` helper defaults to `JIRA_PROJECT=INTRD`, so target CR with **raw JQL** (or
`JIRA_PROJECT=CR jira …`). The built-in aliases (`mine`, `open`, …) are INTRD-scoped — don't use
them for CR.

- **My triage queue** (the recurring "what's on my plate" read):
  ```
  jira jql 'project = CR AND assignee = currentUser() AND status IN ("To Study","In Study") ORDER BY updated DESC'
  ```
- **CR triage read preset** (the fields that actually carry signal — most others are empty JSM
  fields):
  ```
  ["summary","status","assignee","priority","updated","description",
   "customfield_10095","customfield_10103","customfield_10153","issuelinks","fixVersions"]
  ```
  = *Expected by*, *Business value (MoSCoW)*, *Product response*, links, fix versions.

## Workflow — statuses & transitions

Each status has an **actor** — *Reporter* (raises / answers), **Product** (triage & decision), or
*Factory* (delivery):

| Status | Category | Actor | Meaning |
|---|---|---|---|
| **Draft** | new | Reporter | Logged but not ready — reporter is still filling it in. |
| **To Study** | new | Product | Submitted (*Send to Product*); queued for the **Discovery Committee** / Product triage. |
| **In Study** | indeterminate | Product | Product is actively studying it. |
| **Need Information** | indeterminate | Reporter | Product has asked the reporter for more information. |
| **Rejected** | done | — | Declined — a **Change rejection reason** is always set (+ detailed *Product response*). |
| **Accepted** | indeterminate | Product / Factory | Has value for Product — but **NOT scheduled yet**; schedule-vs-backlog still under discussion. |
| **Backlog** | done | Product | Interesting, but will stay unscheduled for the foreseeable future. |
| **Scheduled** | indeterminate | Product / Factory | **Roadmap committee** picked a candidate version — *Fix versions* set, and the INTRD Epics/Stories are **created and linked** to the CR. |
| **Released** | done | — | Delivered — actual version set. |

Happy path: **Draft →(*Send to Product*)→ To Study → In Study → Accepted → Scheduled → Released**,
with **Need Information** as an In-Study side-loop and **Rejected** / **Backlog** as exits.

**Assignee convention:** in **Draft** and **Need Information** the assignee is usually the
**reporter**; in every other status it is someone from **Product**.

**Transition IDs/paths are instance-specific — list them live before applying**
(`jira transitions CR-NNN`, or `getTransitionsForJiraIssue`). Observed: *Request is being studied*
(To Study→In Study) = 11, *More information is needed* = 21, *Accept change* = 71,
*Reject request* = 81, *To Study* = 141.

## The **Product response** field — the official decision

**`customfield_10153` "Product response"** is where the Product team records its **official
response**. It is an **ADF rich-text field** — write it like a `description` (via the Rovo MCP
`editJiraIssue` with `contentFormat: "adf"`, or raw REST with an ADF document value; **never** a
plain string for structured content).

- **Structure:** the Product response ADF **MUST begin with the template's field-title heading as
  its first two nodes** — an H1 `Product response` (marks: `strong` + `textColor #bf2600`) followed
  by a `rule` node, the same scaffold the empty `customfield_10153` and the CR-3 template both ship
  with. **Do NOT start the ADF at the `DRAFT`/Decision paragraph** — that silently drops the template
  heading. After the title heading come the (optional) bold **`DRAFT`** marker while the response is
  not yet final, then the ruling and its rationale — scope summary, what will/won't be done, and
  links (design-repo folder, the delivery INTRD Epic/Initiative). Remove the `DRAFT` marker when the
  decision is committed. Any **further** section headings (Analysis, What will be done, Delivery &
  links, …) are optional and, when used, follow the same shared func dark-red `#bf2600`
  `strong`+`rule` vocabulary (`SKILL.md` § *Templates index*) — the CR template (CR-3) uses it.
  *(Note: the existing CR-281 response used a `#b22222` firebrick variant — a one-off; keep new func
  content on `#bf2600`.)*

  Mandatory opening — copy-pasteable ADF (matches CR-3), the first two nodes of the field value:

  ```json
  {"type":"heading","attrs":{"level":1},"content":[{"type":"text","text":"Product response",
    "marks":[{"type":"strong"},{"type":"textColor","attrs":{"color":"#bf2600"}}]}]}
  {"type":"rule"}
  ```

  General rule: when overwriting **any** templated ADF field from scratch, reproduce the template's
  own field-title heading scaffold rather than starting at the body.
- **Keep it in English** (per `SKILL.md` § *General Rules*) and factual: it is the answer the
  customer/Support will be given, not internal design.
- **Finalise the response as part of the decision transition** — write/clean up Product response,
  then transition *Accept change* / *Reject request* / *More information is needed*.

## Key custom fields (CR project)

| Field | ID | Type | Meaning / use |
|---|---|---|---|
| **Product response** | `customfield_10153` | ADF text | Official Product ruling (see above). |
| **Expected by** | `customfield_10095` | labels (array) | **The customer/driver(s)** behind the CR (e.g. `Fnac-Darty`, `Docaposte`, `Vialis`). *This* is the customer field — **not** `labels`. Can hold several. |
| **Business value (MoSCoW)** | `customfield_10103` | select | `Must have` · `Should have` · `Could have` · `Won't have`. |
| **Change rejection reason** | `customfield_10139` | select | Set when rejecting. One of: `Not in product scope` · `Not in product strategy` · `Too specific` · `Workaround exists` · `Already in Product` · `Duplicate` · `This is a bug`. |
| **Epic Link** | `customfield_10014` | epic link | Links a scheduled CR to its delivery Epic. |
| **Delivery status** | `customfield_10401` | select | Delivery-side progress once scheduled. |
| `fixVersions`, `priority`, `assignee` | — | standard | Target version, priority, owner. |

> **Triage reality check.** In practice most CRs carry only *Expected by* (and sometimes
> *Business value*); *PO estimate*, *Release version*, *Prime Customer*, *Target dates*,
> *Urgency/Severity* are usually **empty**. So prioritisation rests on **customer + regulatory
> urgency + readiness + effort**, not on field data — flag the gap rather than inventing signal.

## Linking CR ↔ SUPS ↔ INTRD

CRs link **cross-project** via ordinary issue links (same Jira Cloud instance, so links span
projects freely). Typical shape:

- **SUPS → CR** — the originating support ticket *Relates* to the CR.
- **CR → CR** — related change requests *Relate* to each other (e.g. a shared theme or a superseding
  CR).
- **CR → INTRD** — at **scheduling**, the CR is linked to the **Initiative / Epic** that delivers it
  (via an issue link and, where applicable, the **Epic Link** field). Name that delivery item in the
  Product response too.

When a CR is **scheduled**, create or locate the INTRD delivery issue(s) (authored per the rest of
this skill) and link them back so the decision → delivery trail is explicit.

## Template — CR-3

The canonical CR template is **`CR-3` "CHANGE REQUEST TEMPLATE"** (in the CR project). It drives the
**`description`** field with the shared dark-red (`#bf2600`) ADF heading vocabulary
(`SKILL.md` § *Templates index* — including the read-side `description`-fetches-as-Markdown gotcha).
Read it before authoring a new CR, then reproduce its sections as ADF:

1. **Change request** — what is being asked.
2. **Target use cases** — the concrete scenarios (a table).
3. **Customer value** — why it matters to the customer.
4. **Criticality for client** — how important/urgent it is for them.
5. **Possible workaround** — any interim workaround that exists.
6. **Business impacts** — positive/negative impacts of doing (or not doing) it.

**Creation quirk:** at creation only the **Summary** is required — there is no description field on
the create form. A Jira automation then prefills the template a few seconds later (refresh if it's
not visible), the reporter fills *Description / Use cases / Customer value* (saving each section), and
uses the **Send to Product** transition to move Draft → To Study.

Note: authoring new CRs is usually the requester's/Support's job — the Product-team lane's day-to-day
is **triage → study → respond** on existing CRs, not creation.

## The Product-team job on a CR

1. **Triage** (*To Study*): read it; identify the customer (*Expected by*), the ask, MoSCoW value;
   spot bundled/duplicate concerns, missing info, and links (SUPS origin, related CRs/INTRD work).
2. **Study** (→ *In Study* via *Request is being studied*): assess scope, feasibility, layer
   (backend/frontend — the teams are strictly separated), effort, and dependencies. A shallow first
   pass sizes and clarifies; a deep pass produces the decision.
3. **Blocked on input** → *More information is needed* (*Need Information*), with a clear ask.
4. **Decide:** write/finalise the **Product response** (filled when Accepting/Rejecting), then
   transition — **Accept change**, or **Reject request** (always set a *Change rejection reason* —
   the *basic* reason; the *Product response* carries the detailed one).
5. **Accepted ≠ scheduled.** *Accepted* means "has value"; scheduling is a separate decision. When
   the **Roadmap committee** picks a candidate version, move to **Scheduled**, set **Fix versions**,
   and **create the INTRD Epics/Stories** (authored per the rest of this skill) **linked back** to
   the CR — reference them from the Product response. (Or park it in **Backlog** if it's valuable but
   unschedulable for now.)

## Limits & volumes

The cross-cutting *Limits & volumes* reflection (`SKILL.md`) targets the **delivery** issue. On a
CR — a decision record — it is normally **`N/A — decision record; scale envelope authored on the
resulting INTRD Epic/Story`**. The exception: when the request *itself* is a scale/performance ask,
capture the envelope in the CR `description` so it carries into the INTRD work.
