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

**Who decides** (CPO, 2026-11-04; `oc-roadmap` § 3). There are two bodies:
- **The Roadmap Committee** schedules a CR into a version, as it decides every small roadmap subject.
  Its members are the CPO (chair), the VP Engineering, the CCO and the CRO. The Factory's release
  manager is invited to its checkpoints during the build.
- **The CODIR**, also called the SteerCo, is consulted on big subjects and informed otherwise.

There is **no standing Discovery Committee**: triage and study are Product's.

- **Project:** key **`CR`** ("Change Requests", project id `10054`). Single issue type **Change
  Request** (id `10077`, not a subtask).
- **Not a bug.** A **bug fix is not a CR** (though a client may report a bug that gets *requalified*
  into a CR). A CR changes intended behaviour; a Bug restores specified behaviour.
- **Lifecycle position:** **SUPS** (support ticket) → **CR** (Product decision) → **INTRD**
  (Initiative / Epic / Story / Enabler delivery). A CR does not itself ship — it authorises and
  scopes; delivery lives in INTRD (author those per the rest of this skill).
- **Not an INTRD issue type.** Do not set INTRD module Components on a CR, do not treat it in the
  Initiative→Epic→Story hierarchy, and do not look for the Story custom fields on it.

## From a support ticket to a CR — Product takes no SUPS

**Product works on CRs, not on support tickets: a SUPS ticket is not assigned to Product.** When a
SUPS asks to change the product, **Support** turns it into a CR. Ruled by the CPO on 2026-10-08 and
written into the Confluence page (v13, section *From a support ticket to a change request*).

| Step | Who | What |
|---|---|---|
| Qualify | Support | A SUPS that asks to change, extend or add a feature becomes a CR. **When in doubt, create the CR**: if it turns out to be a bug, already in the product, or covered by a workaround, Product rejects it with the matching *Change rejection reason*. |
| Create | Support | Create the CR (§ *Template — CR-3*), link it to the SUPS, *Send to Product*. The SUPS stays with Support. |
| Study and decide | Product | Product answers **on the CR**. It may read the linked SUPS for context (customer files, attachments) but does not take it over. |
| Relay | Support | When the CR changes status, Support relays the *Product response* to the customer on the SUPS, then closes it or keeps it open as agreed with the customer. |
| Bug after all | Support | A CR rejected as *This is a bug* → Support handles the SUPS through the bug process. |

**Ready for Product — the minimum bar** before *Send to Product*:
- the description says what is asked and why (the CR-3 template sections);
- ***Expected by*** names the customer(s), reusing existing labels;
- the originating SUPS is linked.

A CR that misses one goes back to its reporter as *Need Information*. **Product does not pick up
Draft CRs** — a Draft stays with its reporter until it is sent; if the reporter is no longer
available, Support takes the CR over.

**How a session applies this:**
- **A SUPS assigned to the CPO is not triaged as his.** Point to the rule: Support creates the CR,
  links the SUPS, sends it. Don't analyse the SUPS in its place.
- **Reading a SUPS linked from a CR is fine** — that is context for the CR, not ownership of the SUPS.
- **Don't author the CR for Support**, and don't relay the answer on the SUPS — both are Support's
  steps. Product's output is the *Product response* on the CR.

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
| **Draft** | new | Reporter | Logged but not ready — reporter is still filling it in. **Product does not pick it up.** |
| **To Study** | new | Product | Submitted (*Send to Product*); queued for Product triage. |
| **In Study** | indeterminate | Product | Product is actively studying it. |
| **Need Information** | indeterminate | Reporter | Product has asked the reporter for more information. |
| **Rejected** | done | — | Declined — a **Change rejection reason** is always set (+ detailed *Product response*). |
| **Accepted** | indeterminate | Product / Factory | Has value for Product — but **NOT scheduled yet**; schedule-vs-backlog still under discussion. A roadmap-round CR without the label `roadmap-public` stays here even once its Epic is versioned (step 5). |
| **Backlog** | done | Product | Interesting, but will stay unscheduled for the foreseeable future. |
| **Scheduled** | indeterminate | Product / Factory | The **Roadmap Committee** picked a candidate version — *Fix versions* set, and the INTRD Epics/Stories are **created and linked** to the CR. A roadmap-round CR comes here only with the label `roadmap-public` on it or its Epic (step 5). |
| **Released** | done | — | Delivered — actual version set. |

Happy path: **Draft →(*Send to Product*)→ To Study → In Study → Accepted → Scheduled → Released**,
with **Need Information** as an In-Study side-loop and **Rejected** / **Backlog** as exits.
A roadmap-round CR held in **Accepted** (step 5) goes through **Scheduled** at its version's release,
or earlier when its code ships earlier (a backport): `101` *Feature has been scheduled* then `91`
*Feature has been released*, as there is no direct Accepted → Released transition.

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
| **Business value (MoSCoW)** | `customfield_10103` | select | `Must have` · `Should have` · `Could have` · `Won't have`. On a CR, `Must have` is read as "the customer's go-live depends on it" — the CPO Obeya's blocked-revenue register counts it that way. On the delivering Epic, `Must have` means the version cannot be released until it is done, and on its Stories that the Epic cannot be released without them (`SKILL.md` § *Version scope*). |
| **Due date** | `duedate` | date | The earliest date any of the CR's customers wishes for — a wish, set on Accept, revisable once *Scheduled*. On the edit screen since 2026-10-07, not on the create or transition screens: set it by an edit. |
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

- **SUPS → CR** — the originating support ticket is linked to the CR (*Relates*; Support also uses
  *Problem/Incident*). **Mandatory** when the CR comes from a SUPS — the reporter links it.
- **CR → CR** — related change requests *Relate* to each other (e.g. a shared theme or a superseding
  CR).
- **CR → INTRD** — at **scheduling**, the CR is linked to the **Initiative / Epic** that delivers it
  (via an issue link and, where applicable, the **Epic Link** field). Name that delivery item in the
  Product response too, once the CR is `Scheduled`.

When a CR is **scheduled**, create or locate the INTRD delivery issue(s) (authored per the rest of
this skill) and link them back so the decision → delivery trail is explicit. A roadmap-round CR held
in `Accepted` (step 5) gets its Epic, versioned and linked, at the Roadmap Committee's decision all
the same.

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

Note: authoring new CRs is the requester's/Support's job — for a customer ask raised in SUPS, always
Support's (§ *From a support ticket to a CR*). The Product-team lane's day-to-day is **triage →
study → respond** on existing CRs, not creation.

## The Product-team job on a CR

1. **Triage** (*To Study*): read it; identify the customer (*Expected by*), the ask, MoSCoW value;
   spot bundled/duplicate concerns, missing info, and links (SUPS origin, related CRs/INTRD work).
   A CR below the *Ready for Product* bar (no *Expected by*, no SUPS link when it came from one) goes
   back as *Need Information* rather than being completed by Product.
2. **Study** (→ *In Study* via *Request is being studied*): assess scope, feasibility, layer
   (backend/frontend — the teams are strictly separated), effort, and dependencies. A shallow first
   pass sizes and clarifies; a deep pass produces the decision.
3. **Blocked on input** → *More information is needed* (*Need Information*), with a clear ask.
4. **Decide:** write/finalise the **Product response** (filled when Accepting/Rejecting), then
   transition — **Accept change**, or **Reject request** (always set a *Change rejection reason* —
   the *basic* reason; the *Product response* carries the detailed one).
   **On Accept, the due date (`duedate`) is the earliest date any of its customers (*Expected by*)
   wishes for.** It is a wish, not a commitment, and may be revised once the CR is scheduled (step 5).
   **Set it by an edit.** *Due date* was added to the CR edit screen on 2026-10-07 (screen 10129, used
   by the CR project only). It is still on neither the create screen nor the *Accept change* /
   *Scheduled* transition screens, so write it with a plain edit, before or after the transition.
5. **Accepted ≠ scheduled.** *Accepted* means "has value"; scheduling is a separate decision. When
   the **Roadmap Committee** picks a candidate version, move to **Scheduled**, set **Fix versions**,
   and **create the INTRD Epics/Stories** (authored per the rest of this skill) **linked back** to
   the CR — reference them from the Product response. (Or park it in **Backlog** if it's valuable but
   unschedulable for now.)
   **A roadmap-round CR goes `Scheduled` only with the label `roadmap-public`** on the CR or its
   delivering Epic (CPO, 2026-10-28). A roadmap-round CR is one whose version a roadmap round decided:
   today 20.0.0 and 21.0.0. Check the label before `101` *Feature has been scheduled*, and when it
   sits on only one of the two, add it to the other first. Without it:
   - the CR **stays `Accepted`** and carries **no Fix version**; its Epic is still created, versioned
     and linked back, and carries the version;
   - its **Product response names no version, no timing and no delivering Epic**;
   - it moves only when the label appears, or at its version's release (earlier if its code ships
     earlier, in a backport): `101` then `91` *Feature has been released*.
   - If you believe the CR was never part of the round (a maintenance or backport CR), ask the CPO
     rather than scheduling it.

   When scheduling:
   - **Each accepted CR is delivered by an Epic of its own, at least** (Stéphane, 2026-10-14).
     - **When it needs several Epics,** an Initiative carries them.
     - **Never a lone Story added to an existing Epic.** Who asked (*Prime Customer*), who paid
       (*Paid by*) and *Generic or specific* all sit on the Epic. A Story inside a catch-all Epic
       (« Miscellaneous Portal enhancements », « Discount plans (misc. enhancements) ») mixes several
       customers' requests, so its cost cannot be attributed. On 2026-10-14, 30 of the 54 accepted or
       scheduled CRs were linked to Stories only.
     - **Several CRs asking for the same feature may share one Epic.** That is resale: *Paid by* lists
       every customer that pays.
     - **History stays as it is.** Do not restructure delivered work.
   - **Set the Epic's decisions:**
     - *Generic or specific* (`customfield_10844`) from the acceptance decision;
     - *Paid by* when the CR is sold (`SKILL.md` § *Who asked, who paid*).
   - **The due date may be updated** to the date now committed.
   - **The delivering Epic carries the CR's customer in Prime Customer** (`customfield_10547`).
     Argos charges product cost to that customer's P&L from it. Write the generic-or-specific
     decision in the Product response.
     - **It is a single-select with a fixed option list,** so map the *Expected by* label to the
       exact option name. Since 2026-10-30 the options are spelled as the labels (`Fnac-Darty`,
       `Energied'ici`, `People&Baby`, `Mediaposte`, `Maileva`), except La Poste: label `LaPoste` →
       option `La Poste`, a label holding no space. La Poste's units (`BGPN` and the like) take
       `La Poste`.
     - **When the CR names several customers, or one with no option, ask the user.** Never invent
       or create an option. On 2026-10-30 OHM, RRF, IEC-Telecom, CanalPlus, Magellan and
       OuestFrance, among others, had none.
     - **Payload:** REST `{"fields": {"customfield_10547": {"value": "La Poste"}}}`, or the
       same object under Rovo `editJiraIssue` `fields`. The field is on the Epic create screen, so
       it can go in the create call.
   - **The delivering Epics and Stories get their own MoSCoW**, never copied from the CR. The Epic's
     comes from the Gate decision. A `Must have` Epic blocks its version's release, and a `Must have`
     Story blocks its Epic's (`SKILL.md` § *Version scope — MoSCoW on Epics, Stories and change
     requests*).
   - **Fix versions** follow `SKILL.md` § *Cost per version*: one per Story or Enabler, with
     backports in *Backport versions* and their own Backport issues.

## Limits & volumes

The cross-cutting *Limits & volumes* reflection (`SKILL.md`) targets the **delivery** issue. On a
CR — a decision record — it is normally **`N/A — decision record; scale envelope authored on the
resulting INTRD Epic/Story`**. The exception: when the request *itself* is a scale/performance ask,
capture the envelope in the CR `description` so it carries into the INTRD work.
