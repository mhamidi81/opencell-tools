---
name: oc-ar-tech-design
description: >
  Generates complete, production-ready technical designs for Opencell Jira user stories,
  written directly into the Jira Technical Design field (customfield_10137) in ADF format.
  Use this skill whenever the user asks to "design a US", "write the technical design",
  "do the tech design for INTRD-XXXXX or MACRD-XXXXX", or wants to generate or update
  a technical design for a Jira story in the Opencell platform (opencellsoft.atlassian.net).
  Also triggers for requests like "design the selected US", "generate tech design from functional",
  or any mention of billing/invoicing/API design + Jira in the Opencell context.
  Always use this skill when the user references Opencell story keys (INTRD-*, MACRD-*).
---

# Opencell Technical Design Skill

Generates structured, accurate technical designs for Opencell Jira user stories and writes
them directly into `customfield_10137` (Technical Design field) using the Atlassian MCP.

---

## Context & Setup

**Jira instance**: `opencellsoft.atlassian.net`
**Cloud ID**: `648ef912-b483-4da2-91af-73ea1e3fdad8`
**Assignee (Rachid)**: `accountId: 5f2032a7f78bea0016478dab`
**Technical Design field**: `customfield_10137`
**Functional Design field**: `customfield_10135`
**Requirement field**: `customfield_10134`
**Acceptance field**: `customfield_10136`

---

## Workflow

### Step 1 — Gather context

Before writing anything, read:

1. **The target US** — fetch via `searchJiraIssuesUsingJql` with fields:
   `["summary", "status", "fixVersions", "customfield_10134", "customfield_10135", "customfield_10136", "customfield_10137"]`
   and `responseContentFormat: "markdown"`

2. **Sibling/related stories** — if the US is part of a series (e.g. story 3 of a VAT recognition series),
   always fetch the sibling stories first and read their existing technical designs.
   Search by epic link, parent, or issue links. Consistency across a series is critical.

3. **Source code** — if the user provides Java source files (uploaded or pasted), read them fully
   before writing any design. Extract exact class names, method signatures, field names, and call chains.
   Never invent method names — use only what is confirmed in the code or existing technical designs.

4. **Comments on the story** — read them. They often contain architect corrections, PO clarifications,
   or decisions that override the functional design text (e.g. "no backend restriction on due date < today").

### Step 2 — Identify the design type

| Type | Signals | Approach |
|---|---|---|
| New feature / API | "new endpoint", "create API", functional design describes new behaviour | Full API + model + service + GUI sections |
| Enhancement | "extend", "also support", sibling story exists | Read existing tech design, extend it, flag unchanged methods explicitly |
| Bug fix | story has bug icon, "fix", "prevent", "double billing" | Minimal targeted fix; prefer prevention at source over compensation after the fact |
| Config / model only | "add field", "new column", "migration" | Focus on model + migration; API/GUI sections may be NO IMPACT |

### Step 3 — Apply the critical design rules

These rules were established through architect corrections and must always be respected:

**Rule 1 — Reuse, don't introduce**
Never introduce a new service method when an existing one can be enhanced.
If `createVatTransferEntries` exists, enhance it. Don't create `buildVatTransferJournalEntries`.

**Rule 2 — Virtual flag**
`createRatedTransaction(wo, isVirtual)`: `true` = simulation, RT NOT persisted. `false` = RT persisted, WO → TREATED.
Never use `isVirtual=true` in production paths. Bug fix designs must use `false`.

**Rule 3 — Partial matching guard**
The `isValidAo` guard in `assignMatchingCodeToJournalEntries` only supports full matching (matchingStatus = L).
For partial matching (matchingStatus = P), extend the condition explicitly: `isValidAo.get() || MatchingStatusEnum.P.equals(...)`
Do NOT modify the `isValidAo` block itself — it controls matching code stamping, not VAT transfer.

**Rule 4 — Persistence mode**
`createRatedTransaction(wo, false)` is required for production. `true` is simulation-only.

**Rule 5 — Bug fix approach**
Prefer prevention at the source (e.g. `isVirtual=true` for INVOICING_PLAN charges at instantiation)
over compensation after the fact (e.g. converting WOs to RTs post-hoc).

**Rule 6 — Consistency across sibling stories**
Always read related stories' existing technical designs before drafting a new one in the same series.
Class names, method names, and field names must be identical across the series.

### Step 4 — Write the technical design

Use the exact ADF structure in `references/adf-template.md`.

Each section must be filled, even if with a "NO IMPACT" panel. Never leave the template placeholder text.

**API section**: For each endpoint, provide:
- HTTP verb + full path
- New/Existing label
- Summary description
- Request body (JSON code block)
- Business logic (bullet list)
- Response description

**Error dictionary**: Always bilingual (EN + FR). No hardcoded strings in Java — use message keys.
Format: `entity.context.rule` e.g. `invoice.creditNote.dueDate.beforeInvoiceDate`

**Implementation / Services section**: Provide exact Java code blocks with:
- Full method signature
- Class name and package comment
- Inline comments explaining the fix or logic
- Side-by-side CURRENT vs FIXED when modifying existing code

**Model section**: List new/modified entity fields with Java type and DB column name.

**Migration section**: Include Liquibase changeset snippet if columns are added.

**GUI section**: Reference functional design screen names. State NO IMPACT explicitly if none.

**Non-regression checks**: At least 3-5 specific, testable scenarios. Each must name the exact
method, status, or condition being checked.

### Step 5 — Write to Jira

Call `editJiraIssue` with:
- `cloudId: "648ef912-b483-4da2-91af-73ea1e3fdad8"`
- `contentFormat: "adf"`
- `fields: { "customfield_10137": { ...ADF doc... } }`
- `issueIdOrKey: "INTRD-XXXXX"`

If the payload is too large (Jira returns INVALID_INPUT), split into sections and write the most
critical parts first (Overview + API + Implementation), then add remaining sections via a comment.

---

## Listing and selecting US

When the user asks to see their US queue, fetch with:
```
JQL: issuetype = Story AND assignee = "5f2032a7f78bea0016478dab" AND status = "To Design - Tech"
ORDER BY fixVersion ASC, created ASC
Fields: ["summary", "status", "fixVersions", "project"]
maxResults: 100
```

Group results by `fixVersions[0].name` (descending numeric order, "No version" last).
Present as an interactive widget using `show_widget` so the user can select stories to design.

---

## Quality checklist before writing to Jira

Before calling `editJiraIssue`, verify:

- [ ] No invented method names — all class/method names confirmed from source code or existing tech designs
- [ ] Error codes are bilingual (EN + FR)
- [ ] `isVirtual` parameter is correct for the context (never `true` in production paths)
- [ ] Sibling stories were read first if this is part of a series
- [ ] Existing methods are enhanced, not duplicated
- [ ] Non-regression checks are specific (method names, status values, not generic statements)
- [ ] All sections filled — no template placeholder text remaining
- [ ] Comments on the story were read (may contain overrides to functional design)

---

## Reference files

- `references/adf-template.md` — Complete ADF JSON structure for `customfield_10137`
- `references/error-patterns.md` — Error code conventions and bilingual message examples
- `references/design-examples.md` — Excerpts from validated technical designs for reference
