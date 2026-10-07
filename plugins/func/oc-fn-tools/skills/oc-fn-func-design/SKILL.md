---
name: oc-fn-func-design
version: 1.38.0
updated: 2026-10-07T10:46:16+02:00
author: Stéphane Chambrin
description: >
  Rules and data for Jira issues in the Opencell INTRD project and the CR (Change Requests)
  project. Use whenever the user mentions Jira, INTRD, User Story, Epic, Bug, Backport, Feature,
  Initiative or a Change Request / CR — creating, reading, updating or writing any issue type
  — or asks about custom fields, acceptance criteria, functional design, requirements,
  Components (modules), issue templates, or triaging / responding to Change Requests (Product
  response field, To Study / In Study). Technical Design (customfield_10137):
  scaffold/read/review only; authoring is the architect lane — defer to oc-ar-tech-design.
  Also the PO review lane: reviewing, validating or rejecting a delivered Story (To Review /
  Validated / Rejected by PO, PO can't test yet), INTRD workflow transitions, the Sub-bug
  type, and retesting a Bug fix ("test this ticket for me", In Test, Test failed) with its
  Case / Expected / Actual report. Always load before any Atlassian Rovo Jira tool call or
  direct Jira REST call on INTRD or CR.
---

# Jira — INTRD & CR projects

## Instance

- **URL:** https://opencellsoft.atlassian.net
- **Cloud ID:** `648ef912-b483-4da2-91af-73ea1e3fdad8`
- **Main project:** INTRD — delivery (Initiative → Epic → Story / Enabler, plus Bug).
- **Change-request project:** CR ("Change Requests") — customer/stakeholder change requests the
  Product team triages and rules on (the *Product response* decision field); feeds INTRD delivery.
  See `change-requests.md`.

## Requirements

This skill reads and writes Jira/Confluence through the **Atlassian (Rovo) MCP connector** — the
claude.ai Atlassian connector, which surfaces tools such as `getJiraIssue`, `editJiraIssue`,
`searchJiraIssuesUsingJql`, `createConfluencePage`, `updateConfluencePage`. This connector is **not**
bundled in the Opencell marketplace; enable it in claude.ai. It is the same connector the marketplace's
`oc-ar-tech-design` and `oc-cache-jira` plugins assume. Tool names below are written as bare verbs and
resolve against whatever Atlassian MCP your environment registers (the claude.ai connector exposes them
as `mcp__…Atlassian_Rovo__<verb>`; a self-hosted Atlassian MCP may use a different prefix).

Check at session start: call `atlassianUserInfo` (or `getVisibleJiraProjects`); if it errors, the
connector is not enabled. That is not blocking: the optional `jira`/curl helper covers reads, search, transitions, plain edits **and** ADF writes — including the Story custom fields (10134–10137) and template clones — by posting an ADF document object from a file. Only edits guarded by the inline-media safety rule need the connector.

## Transport — Rovo MCP (baseline) vs the optional `jira` helper

The Atlassian **Rovo MCP** is the **baseline transport that always works** — it covers every operation below (reads, search, metadata, transitions, plain writes, and rich ADF writes). The optional `jira` helper (a thin curl/jq Jira REST wrapper on `~/.local/bin/jira`; install it per `rest-api.md`) — or raw `curl` — is a **token-saving accelerator**, not a dependency: the MCP injects every tool response into context in full, whereas direct calls filter with `jq` in the shell so only the projection costs tokens. Run `command -v jira` once: if absent, use the Rovo MCP equivalent for every row below.

| Operation | Use |
|---|---|
| Read an issue, JQL search, approximate count | `jira`/curl if the helper is installed, else `getJiraIssue` / `searchJiraIssuesUsingJql` (Rovo MCP) |
| **Count-complete read** — a full roster, a rollup, "every issue matching X" | **`jira jql … --all --fields=… --json`**, which drains every page itself. Strongly prefer it: the MCP returns 50–100 per call with a `nextPageToken` to carry by hand, and injects every page into context in full. Scope with `jira count` first |
| Field & custom-field metadata (createmeta) | `jira`/curl if the helper is installed, else `getJiraIssueTypeMetaWithFields` / `getJiraProjectIssueTypesMetadata` (Rovo MCP) |
| List or apply a transition | `jira`/curl if the helper is installed, else `getTransitionsForJiraIssue` / `transitionJiraIssue` (Rovo MCP) |
| Plain-text comment | `jira`/curl if the helper is installed, else `addCommentToJiraIssue` (Rovo MCP) |
| Simple plain-field edit (summary, labels, plain description) | `jira`/curl if the helper is installed, else `editJiraIssue` (Rovo MCP) |
| Story rich-text fields `customfield_10134`–`10137` (ADF-only) | Rovo MCP (`createJiraIssue`) **or** direct REST with an ADF document object (`jira raw POST /issue @payload.json`) — **prefer REST for bulk**; the four fields must be set **inside the create call**, see `stories.md` § *Template-seeding automation* |
| Create / rewrite from a template (panels, dark-red headings, rules) | **Rovo MCP**, or `jira raw` with an `@file` ADF payload |
| ADF `description` at creation, or a rich ADF comment | **Rovo MCP**, or `jira raw` with an `@file` ADF payload |
| Edits guarded by the inline-media safety rule (below) | **Rovo MCP** |

**Default to the `jira` helper when it is installed; otherwise use the Rovo MCP for every row.**

**Atlassian's own `twg` CLI is a third transport, but only for two operations** — reading the
*edit-only* custom fields (`twg jira workitem field update-metadata --id KEY`, the only way to list
`customfield_10134`–`10137`, which `jira meta` cannot show because it reads the create screen) and
posting a **rich Markdown comment** (`twg jira workitem comment create … --body-format markdown`,
which converts to ADF client-side where `jira comment` is plain-text only). Everything else stays on
the two transports above: `twg` is 7–12× more verbose on reads, and **`twg jira workitem create`
silently drops fields absent from `createmeta` while returning `{"success": true}`** — never use it
for a create. Measurements, scopes and the full trap: `rest-api.md` § *The `twg` CLI*.

**A rich ADF body does not force you onto the MCP.** `jira raw` posts one from a file, so the blob never enters the context at all — recipe in `rest-api.md`. This holds for `customfield_10134`–`10137` too: direct REST writes ADF to all four correctly (verified across nine Stories plus a template rewrite, with formatting confirmed via `expand=renderedFields`). Because these payloads are large — ~330 KB of ADF across seven Stories — **REST is the preferred transport for bulk Story creation**: the MCP injects whole responses into context, while a generated `@file` payload never enters it. Only **edits guarded by the inline-media safety rule** stay on the MCP.

When the helper is installed, common reads have shortcuts: `jira mine`, `jira open`, `jira recent`, `jira unassigned`, `jira new`, and `jira children KEY` (an Epic's Stories / an issue's subtasks) — run `jira aliases` to list them.

In a marketplace-equipped repo, the `oc-cache-jira` plugin maintains a separate lightweight `.claude/cache/jira-tickets.json` (summary/type/status only) for the commit-workflow commands; this skill's reads are authoring-grade (full ADF fields the cache doesn't store) and always go live — the two don't share a fetch path and don't need to.

One-time auth setup and the full recipe + endpoint catalog — including the JQL aliases and the critical `POST /search/jql` migration (the classic `/search` is removed and returns `410`) — live in **`rest-api.md`. Load `rest-api.md` before any direct REST call.** The field-selection and ADF rules below apply to both transports.

## Issue-type-specific rules — read on demand

The rules below cover **all issue types**. For type-specific conventions (custom fields, workflows, templates, creation quirks) — and for the PO-review lane, a task rather than a type — also read the matching reference file:

| Working on…   | Also read                              |
|---------------|----------------------------------------|
| User Story    | `stories.md`                           |
| Enabler       | `enablers.md`                          |
| Epic          | `epics.md`                             |
| Bug           | `bugs.md`                              |
| Sub-bug       | `bugs.md`                              |
| Initiative    | `initiatives.md`                       |
| Change Request | `change-requests.md`                  |
| Backport      | `backports.md`                         |
| Reviewing a delivered Story (PO verdict) | `po-review.md`      |
| Retesting a delivered Bug fix (`In Test`) | `po-review.md` + `bugs.md` |

Load only the file relevant to the current task — do not pre-read all of them.

> **Change Request** issues live in the **separate `CR` project** (not INTRD). `change-requests.md`
> covers the CR workflow (To Study / In Study → Accepted / Rejected), the **Product response**
> decision field, its custom fields (e.g. *Expected by* = the customer), and the **SUPS → CR →
> INTRD** lifecycle. The INTRD module-Component and altitude-hierarchy rules do **not** apply to CRs.

## General Rules

- All Jira issues must be written in **English**.
- **Check the create screen before the first create of an issue type you have not created this session** — required fields differ per type and are not guessable. Run `jira meta <issuetypeId>` (or `getJiraIssueTypeMetaWithFields`). Notably a **`Bug`** requires *Issue location (URL)* (`customfield_10359`, a URL-typed string field — send a full URL) and *Affects versions* (`versions`) at creation, while a **`Sub-bug`** requires neither — see `bugs.md` § *Required fields at creation — Bug vs Sub-bug*.
- Minimise token usage on every call. First pick the cheapest transport (see [Transport](#transport--rovo-mcp-baseline-vs-the-optional-jira-helper) — default to the `jira` helper when it is installed; otherwise use the Rovo MCP for every operation). Then, on whichever transport, pass an explicit `fields` allowlist (see [Reading efficiency](#reading-efficiency--field-selection)) and prefer `markdown` over ADF on MCP calls whenever possible (see [Content format policy](#content-format-policy--adf-vs-markdown)).

## Product area — the module Component is mandatory

INTRD carries the **product-area axis as a Jira Component** (the "module") — orthogonal to both the issue *type* and the altitude hierarchy (Initiative → Epic → Story/Enabler). Its purpose is **cost attribution**: an issue's effort must land in exactly one **primary** product module. Argos, the financial steering project, values every logged hour by module to compute the cost and ROI of each module; an issue without one is cost nobody can attribute — and Bugs carry the maintenance half of it. **Of the items worked since 2026-04-01, 132 of 189 Epics, Stories and Enablers carried no module before the 2026-10-06 backfill (22 after it: 2 templates, 13 cross-cutting, 7 left for a human decision), and 644 of 662 Bugs carried none before their own backfill the same day (100 of 663 after it, left for a human decision). Backports were backfilled on 2026-10-07: 104 of the 108 created or worked in 2026 carry one.** Hence § *Enforcement* below.

- **Every Epic, Story, Enabler, Bug and Backport carries its primary module Component** — for a Bug, the module of the affected area; for a Backport, the original's (`backports.md`). Pick the single module that best owns the work. A **Sub-bug** reads it from its parent Story, Enabler or Backport and needs none of its own.
- **Cross-tag a second Component only when the work genuinely spans modules** — e.g. a business screen that also advances the shared front-end substrate → its **business module (primary) + `Portal platform`** (cross-tag). Never park business-screen work in `Portal platform`.
- **The 30 modules:**
  - **Quote-to-Cash (13):** Catalog · CPQ · Customer & contract management · Mediation · Rating · Billing · Invoicing · Accounts Receivable · Accounting · Dunning · Payments · Revenue recognition · Reporting
  - **Platform (3):** Core · Extensibility · Opencell AI
  - **Front-end (1):** Portal platform *(shared substrate only)*
  - **Connectors — CRM (2):** Salesforce · HubSpot
  - **Connectors — Payment (5):** Stripe · Ingenico · GoCardless · Slimpay · SIPS
  - **Channels (4):** Marketplace · Partner care · Selfcare · Marketing manager
  - **Energy (2):** Energy vertical · Energy market communications
- **`Backend` / `Frontend` are a *different* axis** (engineering layer, not product area) that coexists on the same field — an issue may carry `[Backend, Billing]`. Leave any existing `Backend`/`Frontend` in place; **add** the module Component, never replace the `components` field wholesale.
- **Not a module:** irreducible cross-cutting tech/functional debt has **no** Component (a non-module bucket, not a label) — don't invent a "debt" Component.
- The module is the *dimension* of work; **altitude** (Initiative/Epic/Story/Enabler) is the separate hierarchy (see `initiatives.md`). The old `Feature` type is **dissolved** — replaced by this Component axis plus the `Initiative` type.

### Enforcement — no Epic, Story, Enabler, Bug or Backport leaves this skill without a module

**The rule: any Epic, Story, Enabler, Bug or Backport this skill creates or edits ends the call with
a module Component.** It holds on every transport and every path — a create, an edit for another reason, a
Story conversion, an Epic decomposition, a Bug filed or retested.

1. **Create — the module is in the create call.** Put `components` in the same `POST /issue` /
   `createJiraIssue` call as everything else, with at least one module (plus `Backend` / `Frontend`
   where the layer applies). Never plan to add it afterwards.
   - REST: `"components": [{"name": "Billing"}, {"name": "Backend"}]` inside `fields`.
   - Rovo MCP: the same array under `additional_fields` (`{"components": [{"name": "Billing"}]}`).
2. **Choose it, don't leave it.**
   - **A Story or an Enabler** takes its parent Epic's primary module by default. Change it only
     when the work clearly belongs to another module.
   - **An Epic** takes the module that owns most of its scope.
   - **A Backport** takes the original's module (`backports.md`).
   - **A Bug** takes the module whose behaviour is wrong — not the module where the fix happens to
     land, nor the screen that merely displays it.
   - **When the module is not evident, ask the user** before creating. Never create without one,
     and never guess silently.
   - **Name the module you set** in the confirmation you give the user.
3. **Edit — fix a missing module in the same write.** Before any write to an existing Epic, Story,
   Enabler, Bug or Backport, include `components` in the read. If it carries no module, add one in
   that same edit, chosen as in step 2, and say so.
   - **REST adds without touching the rest:**
     ```sh
     jira raw PUT /issue/KEY '{"update":{"components":[{"add":{"name":"Billing"}}]}}'
     ```
   - **The Rovo MCP `editJiraIssue` has no `update` verb:** its `fields.components` *replaces* the
     list. Send the existing components plus the module. Sending the module alone wipes `Backend` /
     `Frontend`.
4. **Verify after creating.** The post-create re-read (`stories.md` § *Verify after creating*) also
   asserts a module is present:
   ```sh
   jira raw GET "/issue/$K?fields=components" | jq -e '[.fields.components[].name]
     | any(. != "Backend" and . != "Frontend")' >/dev/null || echo "NO MODULE: $K"
   ```
5. **Review — a missing module is a finding.** Report it whenever you read an Epic, Story, Enabler,
   Bug or Backport for a judgement: a PO review or a Bug retest (`po-review.md`), an Epic's validation or
   decomposition, a version's scope, a triage. Do not fix it silently inside a read-only task; propose the module.
6. **Sweep — list what lacks one.** Validated 2026-10-06 against a recount of the same set; `Backport`
   added 2026-10-07 (the query runs). Done Backports are swept separately (`backports.md`):
   ```
   project = INTRD AND issuetype in (Epic, Story, Enabler, Bug, Backport) AND statusCategory != Done
     AND (component is EMPTY OR component not in ("Accounting", "Accounts Receivable", "Billing",
     "Catalog", "Core", "CPQ", "Customer & contract management", "Dunning",
     "Energy market communications", "Energy vertical", "Extensibility", "GoCardless", "HubSpot",
     "Ingenico", "Invoicing", "Marketing manager", "Marketplace", "Mediation", "Opencell AI",
     "Partner care", "Payments", "Portal platform", "Rating", "Reporting", "Revenue recognition",
     "Salesforce", "Selfcare", "SIPS", "Slimpay", "Stripe"))
     AND key not in (INTRD-1486, INTRD-1949, INTRD-5340, INTRD-42501, INTRD-42939)
   ```
   The last line keeps the **template issues** (§ *Templates index*) out: they are not work, so they
   carry no module, and a sweep must never write one on them. Both component branches are needed:
   `component not in (…)` alone skips issues with **no** component at all. An issue carrying a module
   plus `Backend` / `Frontend` is correctly left out. Scope it (a
   version, an Epic, a period of work) before acting: **a backfill is a write; show the list and the
   proposed modules, and get the user's go-ahead first.**
7. **The one exception is explicit.** Irreducible cross-cutting debt (above) has no module, and
   that is a decision: state it to the user at creation. It then counts as unattributed cost, never
   as a forgotten field.

## Cost per version — the Fix version field

Argos, the financial steering project, costs every logged hour by version from **Fix versions**
(`fixVersions`), and the CPO block of the CODIR Obeya reads it. These rules were set by Stéphane on
2026-10-07.

**The counting rule.**

- An issue's hours go to the versions in its **Fix versions**. Several versions split the cost
  evenly between them.
- A **Sub-task** or **Sub-bug** follows the same rule on its own Fix versions. With none of its own,
  it counts under its parent's.
- A **Backport**'s hours go to its single version, whatever Epic it sits under (`backports.md`).

**Who may carry several versions.**

- **Bug, Sub-bug, Sub-task and Task** may carry several. On 2026-10-07, 153 of the 664 Bugs worked
  since April did.
- **A Story or an Enabler carries at most one: one once it is scheduled, never two.** Each older
  version it must also reach goes into its **Backport versions** field (`customfield_10260`) **and**
  gets its own Backport issue — `backports.md`.

**When it is set.**

- **An Epic, Story or Enabler gets its Fix version when it is scheduled into a version, not before.**
  Time logged is not a trigger, because study work is logged before an item is scheduled. Don't flag
  a worked item for a missing version on that ground alone.
- **A Bug is created with its Fix version(s),** which Jira requires (`bugs.md` § *Required fields at
  creation*).
- **A Sub-bug or Sub-task** takes one when scheduled, or counts under its parent's meanwhile.
- **A Task** takes one when scheduled. A Task is not a sub-item and inherits nothing; until it has a
  version, its hours have none.

**Read before you write.** Include `fixVersions` and, on a Story or Enabler, `customfield_10260` in
the read before any edit. The field presets in `stories.md`, `enablers.md`, `epics.md`, `bugs.md`
and `backports.md` carry them.

### Enforcement — a Story or Enabler never gains a second Fix version through this skill

1. **Create.** A Story or Enabler is created with at most one Fix version. A request for "this, and
   also in 18.3" becomes one Fix version, the older one in *Backport versions*, and a Backport issue
   (`backports.md` § *How to build one*).
2. **Edit.** A request to add a version to a Story or Enabler takes the same route; the Fix version
   stays single.
   - **REST:** `{"update": {"customfield_10260": [{"add": {"name": "18.3.0"}}]}}`.
   - **Rovo MCP `editJiraIssue`:** `fields.fixVersions` and `fields.customfield_10260` *replace* the
     list, so send the full list you mean to keep.
   - **An existing Story or Enabler that already carries several Fix versions keeps them** when it is
     edited for another reason. Report it; do not split it.
3. **Review.** Report these, as findings rather than verdicts (`backports.md` § *Review and sweep*):
   - an open Story or Enabler with several Fix versions
   - a Backport version with no linked Backport issue carrying it
   - a Backport whose version is missing from its original's *Backport versions*
   - a Backport with no Fix version, or with several
4. **History stays as it is, except missing Backport data.**
   - Never create Backport issues retroactively for work already done under several versions.
   - Never split an old multi-version Story or Enabler.
   - **Backfilled, with the user's go-ahead on the list:** a Backport missing its version or its
     module, and an original whose *Backport versions* lacks the version of a linked Backport. Neither
     moves cost already logged.
   - **Report only:** a Backport carrying several versions. Removing one would move cost already
     logged, and no decision covers that.

## Version scope — MoSCoW on Epics, Stories and change requests

**Business value (MoSCoW)** (`customfield_10103`) is set on Epics, Stories and change requests, not
on Enablers. It reads differently depending on where it is set:

- **On an Epic or a Story, `Must have` means the version cannot be delivered without it.** Set it
  with that meaning when scheduling, and read it that way when judging a version's scope.
- **On a change request, `Must have` is read as "the customer's go-live depends on it".** That is how
  the CPO Obeya's blocked-revenue register counts it, and Stéphane kept that use on 2026-10-07
  (`change-requests.md`).

## Authoring boundary — User Stories are functional, never technical

**Every User Story authored in the func/PO lane is a *functional* story:** it describes
user-facing value or behaviour a PO can validate. **Never author a *technical* story** — one
whose subject is implementation work (refactor, index, schema migration, query-engine change,
infrastructure, internal API) with no user-facing outcome. Technical work is the architect lane's
domain.

- **The litmus.** A Story must be expressible as *who* gets *what* observable value. If the only
  honest "so that…" is technical ("so the query is faster", "so the schema supports X"), it is
  **not** a Story — it is an **Enabler** (see `enablers.md` § *What is an Enabler*).
- **Enablers are architect-owned.** When a Story is too big or carries a technical prerequisite,
  the architect lane splits out an **Enabler** during Technical Design (Phase 3, see `stories.md`
  § *Workflow*). The func/PO lane does **not** create Enablers by default — it keeps the Story
  functional and **flags the technical need** for the architect lane. Author an Enabler here
  **only on explicit user request** (the same explicit-request exception as the Technical design
  field below).
- **When asked to "write a story" for clearly technical work:** do **not** author it as a User
  Story. State that it's technical and redirect it to an Enabler / the architect lane. A general
  "write the stories for this Epic/initiative" is **not** consent to emit technical stories —
  produce only the functional Stories and list the technical needs separately for the architects.
- **During Epic/initiative decomposition** (`epics.md` § *Child Story naming*): every child Story
  you emit must pass the functional litmus. Technical needs surfaced while decomposing go into a
  separate "technical needs for the architect lane" list, not into Stories.
- **Functional is necessary but not sufficient — a Story must also be *demonstrable*.** Do not
  even create technical-layer Stories sliced by pipeline stage; the demonstrability test, the
  horizontal-slicing anti-pattern, and the routing of non-demonstrable sub-steps into the
  demonstrable Story's acceptance (and to architect-owned Enablers) live in `stories.md` § *Story
  scope — demonstrable, not just functional*.

**See also** the Technical design *field* boundary below — the same lane discipline at field level.

## Authoring boundary — Technical design belongs to the architect lane

> **See also** § *Authoring boundary — User Stories are functional, never technical* above — the
> issue-level counterpart of this field-level rule.

**In the func/PO lane, leave the User Story *Technical design* field (`customfield_10137`) as the empty scaffold.** On the INTRD workflow, Technical Design is **Phase 3, owned by the Tech Lead** (see `stories.md` § *Workflow*); authoring it is the **architect lane's job**, done with the marketplace `oc-ar-tech-design` skill (oc-ar-tools) — or, by explicit user request, here via the `stories.md` § *ADF recipe*. **When the user asks to write or fill the technical design, defer to `oc-ar-tech-design` (where available) rather than refusing.**

- **What the func/PO lane fills on a Story:** *Requirement* (`10134`), *Functional design* (`10135`), *Acceptance* (`10136`) — the PO-owned fields.
- **What the func/PO lane leaves as the scaffold:** *Technical design* (`10137`), in full. This includes the *Limits & volumes* sub-section that lives inside it (see § *Limits & volumes — mandatory reflection*): leave the whole field as the untouched template scaffold for the architect lane / Tech Lead.
- **At Story creation,** reproduce the Technical design template scaffold (its empty dark-red headings, author-hint panels, and the *Limits & volumes* placeholder) but do **not** fill in any technical-solution content. Filling the three PO fields and leaving this one as the empty scaffold is the correct, complete result — not an unfinished one.
- **Reading is fine.** Claude may read *Technical design* — e.g. to derive acceptance tests from its *Limits & volumes* / *Error dictionary* sections. The boundary is on **authoring**, not reading.

**Only exception — explicit request in this lane.** When the user explicitly asks *this* lane to author (or draft, or revise) the Technical design, the cleaner hand-off is to defer to the architect lane's `oc-ar-tech-design` skill (oc-ar-tools), if installed. A general instruction such as "write this story" or "fill in the story" is **not** explicit consent — it covers the three PO fields only. If you do author it here on explicit request, follow the ADF recipe in `stories.md` and, where available, defer the filled section set, NO-IMPACT-panel policy, and fill-completeness rule to the architects' technical-design skill (`oc-ar-tech-design`, `references/adf-template.md`), which is the canonical authority for the FILLED 10137 body; this skill's recipe only supplies the shared ADF heading/rule/panel vocabulary. Note that this content normally originates from the Tech Lead, so they can review it.

**See also: `oc-ar-tech-design` (oc-ar-tools)** — the architect lane's technical-design authoring skill.

**Complement.** This boundary has a counterpart that runs the other way: when a Story depends on an **already-decided** conceptual model element, the func/PO lane **must name the conceptual binding** in the functional fields — it does not get to leave it implicit. Naming the *conceptual* home (entity.attribute) is functional and in-lane; the *physical* design (tables, JPA mappings, indexes, DDL) it maps to still belongs to *Technical design* (`customfield_10137`), the architect lane. See § *Decided model bindings — name the conceptual home in the functional design*.

This boundary is scoped to the User Story Technical design field; it does not change how Claude authors other issue types.

## Decided model bindings — name the conceptual home in the functional design

> **See also** § *Authoring boundary — Technical design belongs to the architect lane* above — this
> rule is its complement (name the conceptual binding in the functional fields; the physical design
> still belongs to *Technical design*).

**Driving principle — architects work from the Jira issue, not the design ADRs.** The architects
build a Story from its Jira fields **alone**; they do **not** read the design repo's ADRs or `.md`
files. So **any decided conceptual model element a Story depends on MUST be named in the Story's —
or its Epic's — functional design.** Never leave a settled model decision implicit in an ADR the
architects can't see: if it isn't in the issue, for them it doesn't exist, and they will re-invent
or re-litigate it.

**This is a bounded exception, not a reversal.** The functional-first default still holds — most
Stories simply *list the information* they need in business terms and never name a database or model
property (see `stories.md`). The exception fires only for an **already-decided** element the
architect must respect: then, and only then, name its conceptual home.

- **Stay conceptual.** Name the conceptual entity/attribute (e.g. `EreportingSetting.vatRegime`) and
  the decided input behind it, with its source (ADR / spec). The **physical** realization — tables,
  JPA mappings, indexes, DDL — is out of lane; it belongs to the architect in *Technical design*
  (`customfield_10137`).
- **Per-type placement.**
  - **Story** → the *Data* section of *Functional design* (`customfield_10135`), in the item's
    *held on* part — see `stories.md` § *Data — naming decided model bindings*.
  - **Epic** → a consolidated *Domain model & decided design inputs* section in the `description`,
    **inherited** by child Stories (each names only its slice and references the Epic) — see
    `epics.md` § *Domain model & decided design inputs*.

**Worked example (INTRD e-reporting / OER).** The Phase-4 Stories named user-facing information
("VAT regime", "VAT status") but not the conceptual entities holding it — `EreportingSetting`
(layered Provider default + per-Seller override), the `EreportingVatRegime` reference table,
`taxablePersonStatus` (default on `CustomerCategory`, override on `BillingAccount` — **not**
`AccountEntity.vatStatus`), `EreportingPeriod`. Those lived only in the design repo's ADRs/`.md`, so
the architects would have re-invented or re-litigated them. Fix: name each conceptual home in the
functional fields, leaving physical realization to the architect lane.

**Reviewer expectation.** When a decided model element exists for a Story's data, **reject** a
*Data* section that names the user-facing information but omits its conceptual home. (The default still stands where no decision is fixed — listing information without a model
property is correct there, not a gap.)

## Reading efficiency — field selection

The Rovo MCP returns very large payloads by default (avatars, schemas, expansion stubs, ADF JSON, history). To control token usage, **never fetch all fields by default**. Pass an explicit `fields` allowlist on every `getJiraIssue` and `searchJiraIssuesUsingJql` call. The same presets feed the `jira` helper's `fields` / `--fields` arguments (see `rest-api.md`) — the discipline is transport-agnostic.

When the next operation is a destructive edit of an ADF field, also include attachment in the allowlist — see Destructive edits on fields containing inline media below.

### Field presets by use case

| Use case | Recommended `fields` |
|---|---|
| Triage / JQL list view | `["summary", "status", "issuetype", "priority", "assignee", "updated"]` |
| Epic / Initiative / Bug — full read | `["summary", "status", "issuetype", "priority", "assignee", "parent", "labels", "components", "fixVersions", "description"]` — the per-type files add their own fields |
| Workflow / status inspection | `["summary", "status", "issuetype", "assignee"]` |
| Relations / hierarchy | `["summary", "issuetype", "parent", "subtasks", "issuelinks"]` — `subtasks` lists only sub-task types; an Epic's or Initiative's children come from `jira children KEY` (JQL `parent = KEY`) |
| Comments review | base preset + `["comment"]` |

For issue-type-specific presets (e.g. User Story custom fields), see the corresponding reference file.

Add fields case by case when needed (`attachment`, `worklog`, sprint or story-point custom fields, etc.). When unsure of a field ID, run `getJiraIssueTypeMetaWithFields` **once** at the start of the session and reuse the IDs without re-fetching.

Use the implicit "all fields" mode (no `fields` parameter, or `["*all"]`) **only** when:
- the user explicitly asks for an exhaustive dump of an issue, or
- discovering the schema of an issue type for the first time.

Always set a tight `maxResults` on JQL searches (default to `10`, raise only if necessary).

## Content format policy — ADF vs Markdown

The MCP supports two formats for Jira content: `adf` (verbose JSON, preserves all rich formatting) and `markdown` (compact text, lossy on rich elements). ADF inflates token usage significantly. **Default to Markdown** and switch to ADF only in the cases listed below.

### Reading — `responseContentFormat`

| Situation | Format |
|---|---|
| Default — any read | **`markdown`** |
| Reading a **template** issue (see Templates index below) to replicate its structure | **`adf`** — but `description` always returns Markdown regardless; see [Templates index § Reading templates](#reading-templates) |
| Reading content that must be copied verbatim into another issue with rich formatting preserved | **`adf`** |

### Writing — `contentFormat`

| Situation | Format |
|---|---|
| Plain prose with headings, lists, bold/italic, inline code, code blocks, links, simple tables | **`markdown`** |
| Quick comments, worklog text, simple status updates | **`markdown`** |
| Editing a template issue, or any issue **derived from a template** (Epic description, Story custom fields 10134–10137) | **`adf`** mandatory — must reproduce dark-red (`#bf2600`) `heading` nodes, each followed by a `rule` node; see [Templates index § Writing templates](#writing-templates) |
| Reusing an ADF block read verbatim from a template | **`adf`** |

**Story custom fields always require ADF.** `customfield_10134`–`10137` reject `contentFormat: "markdown"` at the API level — the Jira API returns `"Operation value must be an Atlassian Document (see the Atlassian Document Format)"`. Always pass them as ADF document objects with `contentFormat: "adf"`.

ADF is **not** mandatory for all writes — only in the cases above.

When mixing formats inside a single issue creation/edit, set `contentFormat` to whatever matches the **richest** field being written — Markdown content also parses correctly under `contentFormat: "adf"` if needed, but the reverse is not true.

## Destructive edits on fields containing inline media

**The rule: an edit keeps every pasted image in the field it is in, copied verbatim — or moves it
the safe way first.** An image pasted into a field belongs to that field. Once the field stops
referencing it, Jira deletes the attachment, and nothing reports it: the `PUT` succeeds, and
`renderedFields` still shows an `<img>` for an `external` node whose attachment no longer exists.

*Why this is a hard rule:* on 2026-10-05, moving six legacy Stories' content out of `description`
deleted all ten of their image attachments — including when the image node had been put into
*Functional design* first — and three could not be brought back. An earlier version of this section
called an image listed in `attachment[]` "safe to proceed"; it is not.

This applies to all issue types and all ADF-bearing fields (`description`,
`customfield_10134`–`10137` on Stories, comments, etc.). Before any edit that rewrites one:

1. **Read the field as ADF, with `attachment` in the `fields` allowlist**, and list its `media` nodes
   (`type: "file"` carries a Media Services UUID; `type: "external"` a URL) and the attachment ids.
2. **Keep every `file` node in the same field, verbatim** — same `id`, `collection`, `alt`, sizes.
   Rewriting the text around it is safe: 57 Stories were rewritten that way on 2026-10-05 and every
   attachment survived (ids compared before and after).
3. **An image that must leave its field** — moved to another field, or dropped from it while kept on
   the issue — goes through § *Moving an image safely* **before** the source field is edited.
4. **After the edit, compare `fields=attachment` with the list from step 1.** A missing id is data
   loss: stop, and restore the field's previous ADF (§ *Recovery is partial*).

If an edit would lose an image anyway, confirm explicitly with the user before proceeding.

Two kinds of pasted image, same consequence:

- **Listed in `attachment[]`** (the usual case): Jira deletes the attachment when its field stops
  referencing it, even when another field of the same issue still references the same media node.
- **Not listed** — an inline Media Services embed orphaned from the Attachments panel: the ADF node is
  the **only** reference, and the Media Services token **cannot be re-inserted via the REST API**.

### Moving an image safely

Download it, upload it again as a plain attachment, embed it from there with an `external` media node
(the § *Inline images* recipe in `stories.md`), and only then edit the source field. A plain
attachment is owned by no field and survives later edits.

As a fallback, an `external` node pointing to
`https://<site>.atlassian.net/rest/api/3/attachment/content/<attachmentId>` on a **sibling** issue can
render the image for authenticated users, but this is fragile (cross-issue dependency, breaks if the
source attachment is removed, may not render in mobile/export contexts).

### Recovery is partial

Writing the field's previous ADF back can re-create a deleted attachment (with a new id). On
2026-10-05 it worked for all 7 images **the editing user had uploaded**, and failed with
`ATTACHMENT_VALIDATION_ERROR` for all 3 uploaded by other people, the editing user being a Jira
admin. That points to the uploader as the only one who can re-link an image (an observation, not a
controlled test). Otherwise an image comes back only from a site backup taken before the deletion, or
through Atlassian Support. Jira Cloud has
no recycle bin for attachments. So before any edit that could remove images, **back up the field's
ADF and the attachment list, and know who uploaded each image.**

### Detection helper

For each `mediaSingle` node in the field being edited, extract `content[0].attrs.id` (the media UUID)
and match it to `attachment[]` — typically by comparing `attachment[].filename` to the node's `alt`
attribute. Older nodes often have no `alt`; then match by the order images render in
`expand=renderedFields`, whose `<img>` URLs carry the attachment ids. A media UUID with no matching
attachment is an orphaned embed (the second kind above).

**Embedding an image inline in the first place** — the positive recipe (upload it as a real
attachment, then a `mediaSingle` → `media` node of `type: "external"` pointing at *that same issue's*
attachment content URL; and why `type: "file"` with the attachment id fails
`ATTACHMENT_VALIDATION_ERROR`) — is in `stories.md` § *ADF recipe → Inline images*. Because the file
stays a real attachment, that is the **standard, non-fragile** inline-embed path (unlike the
sibling-issue fallback in § *Moving an image safely*).

## Templates index

The INTRD project has a canonical template issue for each issue type. Use these to discover the structure (panels, layout, custom-field mapping) before authoring a new issue of the same type.

| Type                  | Template key | Rich-text field(s)          | Reference file |
|-----------------------|--------------|-----------------------------|----------------|
| Bug                   | INTRD-5340   | `description`               | `bugs.md`      |
| Sub-bug               | INTRD-5340 *(the Bug template — there is no separate Sub-bug template)* | `description` | `bugs.md` |
| Initiative            | INTRD-42501  | `description`               | `initiatives.md` |
| Epic                  | INTRD-1949   | `description`               | `epics.md`     |
| User Story            | INTRD-1486   | `customfield_10134`–`10137` | `stories.md`   |
| Enabler               | INTRD-42939  | `description`               | `enablers.md`  |
| Change Request        | CR-3 *(CR project)* | `description`        | `change-requests.md` |

Cache the template structure in the conversation context — do not re-fetch the same template multiple times in a single session.

### Reading templates

Templates use rich ADF that Markdown cannot encode without loss. Fetch with `responseContentFormat: "adf"` and an explicit `fields` allowlist matching the template's issue type (see issue-type reference files).

**Gotcha: `responseContentFormat: "adf"` is not honoured for the `description` field.** It is honoured for the User Story custom fields (`customfield_10134`–`10137`), so Story templates fetch cleanly as ADF. For every other template type (Bug, Initiative, Epic, Enabler), `description` always returns as plain Markdown on fetch — panels and heading colours are invisible in that output, but the underlying ADF storage is intact.

To verify whether panels and colours survived an edit (or to inspect the actual rendered structure of a `description`-field template), fetch with `expand: "renderedFields"` and look for:

- `<div class="panel" style="background-color: #eae6ff..."` — purple note panel.
- `<div class="panel" style="background-color: #fffae6..."` — yellow warning panel.
- `<font color="#bf2600">` — dark-red heading.

If those markers are missing in `renderedFields`, the description has been flattened to plain Markdown and the rich elements were lost.

### Writing templates

When writing or rewriting a template (or any issue cloned from one that should keep its formatting), pass an ADF `description` object with `contentFormat: "adf"`. Markdown round-trip silently collapses the elements below — and because reading the same template back fetches as Markdown (see *Reading templates* gotcha above), the regression is invisible without the `renderedFields` check.

This recipe supplies the shared ADF heading/rule/panel vocabulary and the EMPTY `customfield_10137` scaffold; the FILLED structure of `customfield_10137` is owned by the architects' `oc-ar-tech-design` (`references/adf-template.md`), where available.

Most Opencell issue templates — Epic, Initiative, Enabler, the Story custom fields, and the CR
template (CR-3) — share the following ADF vocabulary. **Exception: the Bug template (INTRD-5340),
which `Sub-bug` also follows, uses plain `strong` headings with *no* colour** (still `strong` +
`rule` + note panels) — do not add `#bf2600` to a Bug or a Sub-bug; see `bugs.md`.

- **Coloured headings** — real ADF `heading` nodes (`attrs.level`: 1 for the field title, 2 for sections, 3–4 for subsections), their text marked `strong` + `textColor` `#bf2600` (dark red), each followed by a `rule` node. **Not** styled `paragraph` nodes — see the copy-pasteable recipe in `stories.md` § *ADF recipe*. `#bf2600` is the func/brand heading colour; other Opencell skills (e.g. `oc-ar-ai-tech-design`) may emit `#FF0000` — keep func-authored content on `#bf2600` and do not silently normalise to another value. **The Bug template is the exception** — its headings are plain `strong`, no colour.
- **Note panels** (purple, `panelType: "note"`, `#eae6ff` background) — wrap author hints. Closing line: italic-grey "You can delete this note" (`em` + `textColor #97a0af`). **Not in the Story PO fields:** since 2026-10-05 the Story template's *Requirement*, *Functional design* and *Acceptance* (INTRD-1486) carry no panels; their hints are grey placeholder text in the spot the content goes (same `em` + `#97a0af` marks) — see `stories.md` § *Story structure — light format*. *Technical design* keeps its panels.
- **Warning panels** (yellow, `panelType: "warning"`, `#fffae6` background) — wrap rules that govern the content being filled in (REST v2 guideline, error-dictionary rules, etc.).
- **Multi-line table cells** — built with `hardBreak` nodes. Markdown cannot encode line breaks inside table cells and breaks the table on round-trip.

## Limits & volumes — mandatory reflection

Every issue that introduces or modifies behaviour with non-trivial data, traffic, or rendering must explicitly address limits and volumes. The intent is to force the author to think about scale at authoring time, not discover it in production.

**Strict rule.** The applicable checklist below must be answered point by point inside the field designated for the issue type. An item that genuinely does not apply must be marked `N/A — <one-line reason>`. A silently omitted item is treated as a missed reflection, not as N/A. Reviewers must reject issues whose limits-and-volumes section is blank, hand-waved ("should scale fine"), or missing explicit N/A justifications.

### Per-type placement

| Type        | Where it lives in the issue                                       | Checklist source                                |
|-------------|-------------------------------------------------------------------|-------------------------------------------------|
| Epic        | Dedicated *Limits & volumes (envelope)* section in `description`  | `epics.md` § Limits & volumes (envelope)        |
| User Story  | Inside *Technical design* (`customfield_10137`)                   | `stories.md` § Limits & volumes (story-level)   |
| Enabler — Backend  | Inside *Technical acceptance criteria*                     | `enablers.md` § Limits & volumes — Backend      |
| Enabler — Frontend | Inside *Technical acceptance criteria*                     | `enablers.md` § Limits & volumes — Frontend     |
| Bug         | Inside `description` — only if the defect is scale/perf-related; else N/A | `bugs.md` § Limits & volumes            |
| Initiative  | *Limits & volumes (envelope)* in `description`, if set at Initiative level | `initiatives.md` § Limits & volumes      |

> **User Story note.** The placement field for Stories — *Technical design* (`customfield_10137`) — is **not authored in the func/PO lane** (see § *Authoring boundary — Technical design belongs to the architect lane*); authoring it is the architect lane's job (the `oc-ar-tech-design` skill, where available). On Stories, this lane leaves the section as the template placeholder, reminds the Tech Lead that it is mandatory, and verifies it is present and answered point-by-point **when reviewing** — but does not fill it (unless the user explicitly asks, in which case prefer deferring to `oc-ar-tech-design`). For Epics and Enablers, Claude authors the section as normal.

### Inheritance

The envelope figures set by the parent Epic are inherited by its child Stories and Enablers. Children may **narrow** the envelope further (a single endpoint is naturally tighter than the program-wide target) but must not silently **exceed** it. When a child needs to exceed the envelope, update the Epic first and link the child to the revised number.

When authoring or reviewing a Story or Enabler, locate the parent Epic's *Limits & volumes (envelope)* section and quote the relevant figures verbatim in the child's section before refining them. If the parent Epic has no envelope yet, flag it — the child cannot be reviewed in isolation.

