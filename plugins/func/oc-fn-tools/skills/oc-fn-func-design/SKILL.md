---
name: oc-fn-func-design
version: 1.19.0
updated: 2026-06-30T22:37:23+02:00
author: Stéphane Chambrin
description: >
  Rules and reference data for working with Jira issues in the Opencell INTRD project
  (opencellsoft.atlassian.net). Use this skill whenever the user mentions Jira, INTRD,
  User Story, Epic, Bug, Feature, or Initiative — including creating, reading, updating, or writing
  content for any issue type. Also trigger when the user asks about custom fields,
  acceptance criteria, functional design, requirements, or issue templates for Opencell —
  and for the scaffold/read/review side of a Story's Technical Design (creating the empty
  customfield_10137 template, or reviewing it). Authoring/filling the Technical Design field
  is the architect lane — defer to oc-ar-tech-design for "write the technical design for INTRD-*".
  Always load this skill before any Atlassian Rovo Jira tool call — or direct Jira
  REST API calls — on the INTRD project.
---

# Jira — INTRD Project

## Instance

- **URL:** https://opencellsoft.atlassian.net
- **Cloud ID:** `648ef912-b483-4da2-91af-73ea1e3fdad8`
- **Main project:** INTRD

## Requirements

This skill reads and writes Jira/Confluence through the **Atlassian (Rovo) MCP connector** — the
claude.ai Atlassian connector, which surfaces tools such as `getJiraIssue`, `editJiraIssue`,
`searchJiraIssuesUsingJql`, `createConfluencePage`, `updateConfluencePage`. This connector is **not**
bundled in the Opencell marketplace; enable it in claude.ai. It is the same connector the marketplace's
`oc-ar-tech-design` and `oc-cache-jira` plugins assume. Tool names below are written as bare verbs and
resolve against whatever Atlassian MCP your environment registers (the claude.ai connector exposes them
as `mcp__…Atlassian_Rovo__<verb>`; a self-hosted Atlassian MCP may use a different prefix).

Check at session start: call `atlassianUserInfo` (or `getVisibleJiraProjects`); if it errors, the
connector is not enabled. Without it, reads/search/transitions/plain edits still work via the optional `jira`/curl helper, but ADF-only Story custom fields (10134–10137) and template clones cannot be written.

## Transport — Rovo MCP (baseline) vs the optional `jira` helper

The Atlassian **Rovo MCP** is the **baseline transport that always works** — it covers every operation below (reads, search, metadata, transitions, plain writes, and rich ADF writes). The optional `jira` helper (a thin curl/jq Jira REST wrapper on `~/.local/bin/jira`; install it per `rest-api.md`) — or raw `curl` — is a **token-saving accelerator**, not a dependency: the MCP injects every tool response into context in full, whereas direct calls filter with `jq` in the shell so only the projection costs tokens. Run `command -v jira` once: if absent, use the Rovo MCP equivalent for every row below.

| Operation | Use |
|---|---|
| Read an issue, JQL search, approximate count | `jira`/curl if the helper is installed, else `getJiraIssue` / `searchJiraIssuesUsingJql` (Rovo MCP) |
| Field & custom-field metadata (createmeta) | `jira`/curl if the helper is installed, else `getJiraIssueTypeMetaWithFields` / `getJiraProjectIssueTypesMetadata` (Rovo MCP) |
| List or apply a transition | `jira`/curl if the helper is installed, else `getTransitionsForJiraIssue` / `transitionJiraIssue` (Rovo MCP) |
| Plain-text comment | `jira`/curl if the helper is installed, else `addCommentToJiraIssue` (Rovo MCP) |
| Simple plain-field edit (summary, labels, plain description) | `jira`/curl if the helper is installed, else `editJiraIssue` (Rovo MCP) |
| Story rich-text fields `customfield_10134`–`10137` (ADF-only) | **Rovo MCP** (`editJiraIssue`) |
| Create / rewrite from a template (panels, dark-red headings, rules) | **Rovo MCP** |
| Edits guarded by the inline-media safety rule (below) | **Rovo MCP** |

**Default to the `jira` helper when it is installed; otherwise use the Rovo MCP for every row.**

When the helper is installed, common reads have shortcuts: `jira mine`, `jira open`, `jira recent`, `jira unassigned`, `jira new`, and `jira children KEY` (an Epic's Stories / an issue's subtasks) — run `jira aliases` to list them.

In a marketplace-equipped repo, the `oc-cache-jira` plugin maintains a separate lightweight `.claude/cache/jira-tickets.json` (summary/type/status only) for the commit-workflow commands; this skill's reads are authoring-grade (full ADF fields the cache doesn't store) and always go live — the two don't share a fetch path and don't need to.

One-time auth setup and the full recipe + endpoint catalog — including the JQL aliases and the critical `POST /search/jql` migration (the classic `/search` is removed and returns `410`) — live in **`rest-api.md`. Load `rest-api.md` before any direct REST call.** The field-selection and ADF rules below apply to both transports.

## Issue-type-specific rules — read on demand

The rules below cover **all issue types**. For type-specific conventions (custom fields, workflows, templates, creation quirks), also read the matching reference file:

| Working on…   | Also read                              |
|---------------|----------------------------------------|
| User Story    | `stories.md`                           |
| Enabler       | `enablers.md`                          |
| Epic          | `epics.md`                             |
| Bug           | `bugs.md`                              |
| Initiative    | `initiatives.md`                       |

Load only the file relevant to the current task — do not pre-read all of them.

## General Rules

- All Jira issues must be written in **English**.
- Minimise token usage on every call. First pick the cheapest transport (see [Transport](#transport--rovo-mcp-baseline-vs-the-optional-jira-helper) — default to the `jira` helper when it is installed; otherwise use the Rovo MCP for every operation). Then, on whichever transport, pass an explicit `fields` allowlist (see [Reading efficiency](#reading-efficiency--field-selection)) and prefer `markdown` over ADF on MCP calls whenever possible (see [Content format policy](#content-format-policy--adf-vs-markdown)).

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
  - **Story** → the *Information requirements* of *Functional design* (`customfield_10135`), via the
    optional *Held on (conceptual model)* column — see `stories.md` § *Information requirements —
    naming decided model bindings*.
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

**Reviewer expectation.** When a decided model element exists for a Story's data, **reject** an
*Information requirements* section that names the user-facing information but omits its conceptual
home. (The default still stands where no decision is fixed — listing information without a model
property is correct there, not a gap.)

## Reading efficiency — field selection

The Rovo MCP returns very large payloads by default (avatars, schemas, expansion stubs, ADF JSON, history). To control token usage, **never fetch all fields by default**. Pass an explicit `fields` allowlist on every `getJiraIssue` and `searchJiraIssuesUsingJql` call. The same presets feed the `jira` helper's `fields` / `--fields` arguments (see `rest-api.md`) — the discipline is transport-agnostic.

When the next operation is a destructive edit of an ADF field, also include attachment in the allowlist — see Destructive edits on fields containing inline media below.

### Field presets by use case

| Use case | Recommended `fields` |
|---|---|
| Triage / JQL list view | `["summary", "status", "issuetype", "priority", "assignee", "updated"]` |
| Epic / Initiative / Bug — full read | `["summary", "status", "issuetype", "priority", "assignee", "parent", "labels", "description"]` |
| Workflow / status inspection | `["summary", "status", "issuetype", "assignee"]` |
| Relations / hierarchy | `["summary", "issuetype", "parent", "subtasks", "issuelinks"]` |
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

Before any `editJiraIssue` that rewrites a field whose current ADF contains a
`mediaSingle` node, check whether the `media.id` (a Media Services UUID)
corresponds to a file present in the issue's `attachment[]` array.

- **If yes** → the image is a standard Jira attachment. Safe to proceed; the
  attachment will remain available even after the field is rewritten.
- **If no** → the image is an inline Media Services embed, orphaned from the
  Attachments panel. The ADF media node is the **only** reference to the file.
  Rewriting the field destroys that reference, and the Media Services token
  **cannot be re-inserted via the REST API** — the file effectively becomes
  unrecoverable through API means.

This applies to all issue types and all ADF-bearing fields (`description`,
`customfield_10134`–`10137` on Stories, comments, etc.).

In the second case:

1. Confirm explicitly with the user before proceeding.
2. If the user still wants the edit, recover the image first — typically by
   asking the user to download it from the current rendering and re-attach it
   to the issue as a regular attachment, then reference it from the new ADF.
3. As a fallback, an ADF `media` node of `type: "external"` pointing to
   `https://<site>.atlassian.net/rest/api/3/attachment/content/<attachmentId>`
   on a sibling issue can render the image inline for authenticated users, but
   this is fragile (cross-issue dependency, breaks if the source attachment is
   removed, may not render in mobile/export contexts).

### Detection helper

When fetching an issue prior to editing an ADF field, include `attachment` in
the `fields` allowlist and use `responseContentFormat: "adf"`, then for each
`mediaSingle` node found in the field being edited:

- extract `content[0].attrs.id` (the media UUID),
- check whether any element of `attachment[]` matches — typically by comparing
  `attachment[].filename` to the media node's `alt` attribute.

A media UUID with no matching attachment is the warning sign.

## Templates index

The INTRD project has a canonical template issue for each issue type. Use these to discover the structure (panels, layout, custom-field mapping) before authoring a new issue of the same type.

| Type                  | Template key | Rich-text field(s)          | Reference file |
|-----------------------|--------------|-----------------------------|----------------|
| Bug                   | INTRD-5340   | `description`               | `bugs.md`      |
| Initiative            | INTRD-42501  | `description`               | `initiatives.md` |
| Epic                  | INTRD-1949   | `description`               | `epics.md`     |
| User Story — generic  | INTRD-1486   | `customfield_10134`–`10137` | `stories.md`   |
| User Story — backend  | INTRD-42531  | `customfield_10134`–`10137` | `stories.md`   |
| User Story — frontend | INTRD-42554  | `customfield_10134`–`10137` | `stories.md`   |
| Enabler               | INTRD-42939  | `description`               | `enablers.md`  |

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

All INTRD templates share the following ADF vocabulary:

- **Coloured headings** — real ADF `heading` nodes (`attrs.level`: 1 for the field title, 2 for sections, 3–4 for subsections), their text marked `strong` + `textColor` `#bf2600` (dark red), each followed by a `rule` node. **Not** styled `paragraph` nodes — see the copy-pasteable recipe in `stories.md` § *ADF recipe*. `#bf2600` is the func/brand heading colour; other Opencell skills (e.g. `oc-ar-ai-tech-design`) may emit `#FF0000` — keep func-authored content on `#bf2600` and do not silently normalise to another value.
- **Note panels** (purple, `panelType: "note"`, `#eae6ff` background) — wrap author hints. Closing line: italic-grey "You can delete this note" (`em` + `textColor #97a0af`).
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

