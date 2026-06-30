---
name: oc-fn-documentation
version: 1.3.0
updated: 2026-06-27T12:00:00+02:00
author: Stéphane Chambrin
description: Rules and conventions for creating and updating Confluence documentation pages in the Opencell documentation space (opencellsoft.atlassian.net/wiki/spaces/docs). Use this skill whenever the user mentions Confluence, documentation, a "Concepts" page, a "User Manual" page, or asks to document anything for Opencell. Always load this skill before any Atlassian Rovo Confluence tool call targeting the docs space.
---

# Confluence — Opencell Documentation Space

## Requirements

This skill reads and writes Jira/Confluence through the **Atlassian (Rovo) MCP connector** — the
claude.ai Atlassian connector, which surfaces tools such as `getJiraIssue`, `editJiraIssue`,
`searchJiraIssuesUsingJql`, `createConfluencePage`, `updateConfluencePage`. This connector is **not**
bundled in the Opencell marketplace; enable it in claude.ai. It is the same connector the marketplace's
`oc-ar-tech-design` and `oc-cache-jira` plugins assume. Tool names below are written as bare verbs and
resolve against whatever Atlassian MCP your environment registers (the claude.ai connector exposes them
as `mcp__…Atlassian_Rovo__<verb>`; a self-hosted Atlassian MCP may use a different prefix).

Check at session start: call `atlassianUserInfo` (or `getVisibleJiraProjects`); if it errors, the
connector is not enabled. There is no fallback: without this connector the skill cannot function.

## Instance

- **URL:** https://opencellsoft.atlassian.net/wiki/spaces/docs
- **Cloud ID:** `648ef912-b483-4da2-91af-73ea1e3fdad8`
- **Space key:** `docs`

### Resolving IDs at use-time

Treat every literal numeric ID in this skill — the cloud ID above, the parent
page IDs in **§ Space Structure**, the template ID in **Rule 4**, and the
`parentId`/`templateId` arguments to the **page-creation call** — as
**defaults-for-one-instance that must be re-verified per tenant**, not as
constants. Before relying on them:

- **Cloud ID:** read it from `getAccessibleAtlassianResources` for the
  *current* connector — do not trust the hardcoded value above on another tenant.
- **Parent pages (Concepts / User manuals):** resolve them **by title** via
  `getPagesInConfluenceSpace` (space key `docs`) rather than trusting the literal
  IDs; confirm the space itself via `getConfluenceSpaces` if the key is uncertain.
- **Documentation template:** resolve the "Documentation page" template **by
  title** rather than trusting the literal template ID.

The numbers listed throughout are correct for the reference tenant only; verify
them against the live instance before each create/update.

## Non-Negotiable Rules (apply to every page)

1. **Language:** All pages must be written in **English**.
2. **Format:** Always create/update pages in **HTML format** — never Markdown.
   Markdown strips heading colors and rich formatting. HTML is round-trip safe
   and supports all required Confluence elements (see patterns below).
3. **Status:** Always save as **DRAFT**. Never publish directly.
   The docs owner reviews and publishes manually. On updates to already-published
   pages, `status: "draft"` creates an unpublished revision while the live
   version remains visible to readers.
4. **Template:** Use global template ID `913080328` ("Documentation page") on
   **`createConfluencePage` only**. The templateId parameter does not apply to
   `updateConfluencePage`.
5. **Heading color:** All body headings (H2–H6) must use color `#bf2600` via an
   inline `<span style="color: #bf2600">` (see patterns below). The page title
   (H1) is rendered by Confluence outside the body and is not styled.
   `#bf2600` is the func/brand heading colour; other Opencell skills (e.g.
   `oc-ar-ai-tech-design`) may emit `#FF0000` — keep func-authored content on
   `#bf2600` and do not silently normalise to another value.

## Space Structure — Parent Pages

Always place new pages under the correct **non-versioned** parent.

| Section | Page ID | Audience |
|---|---|---|
| Concepts | `638877697` | Consultants |
| User manuals | `516718593` | Portal end-users |

**Never place pages under versioned `(vXX) ...` sections.** Those exist for
archiving only (e.g. "(v18) Customer Care", "(v17) User manuals"). Always target
the non-versioned parent pages listed above.

## Audience Guidelines

### Concepts pages (→ Consultants)
- Technical tone, precise terminology
- May reference configuration, APIs, data model
- Assumes familiarity with Opencell concepts

### User Manual pages (→ Portal end-users)
- Step-by-step guidance, plain language
- Focus on UI interactions, not internals
- No references to code, APIs, or configuration

## Source of Truth for Content

**Use only User Stories** (fields: Requirement, Functional design, Acceptance)
as the basis for documentation content.

**Never use** the "High level functional design" section of an Epic.
That section is a preliminary draft, superseded by the finalized stories.
Documenting from it risks describing features that were never implemented as specified.

## HTML — Required Patterns

### Colored heading (H2–H6)

```html
<h2><span style="color: #bf2600">Section Title</span></h2>
```

Replace `h2` with the appropriate level (h2–h6).

### Status lozenge

```html
<span data-type="status" data-color="green|yellow|blue|red|neutral|purple">LABEL</span>
```

### Panels

```html
<div data-type="panel-info|warning|note|success|error"><p>text</p></div>
```

### Existing media node — copy verbatim from fetched body

```html
<figure data-type="media-single" data-layout="center" data-width="760" data-width-type="pixel">
  <div data-type="media" data-media-type="file" data-id="UUID"
       data-collection="contentId-PAGEID" data-width="W" data-height="H"></div>
  <figcaption>optional caption</figcaption>
</figure>
```

Never reconstruct a media node from scratch — only copy it verbatim from a prior
`getConfluencePage` call with `contentFormat: "html"`. The `data-id` UUID is the
sole reference to the file; reconstructing it incorrectly makes the image unrecoverable.

### Smart link (inline card)

```html
<a href="URL" data-card-appearance="inline">URL</a>
```

### Page creation call

Use `createConfluencePage` with:
- `contentFormat: "html"`
- `status: "draft"`
- `templateId: "913080328"`
- `parentId`: one of the page IDs from the table above

### Page update workflow

1. Fetch the current page with `getConfluencePage`, `contentFormat: "html"`.
2. Reconstruct the **full** body — existing content verbatim (preserving all
   media nodes) plus new or modified sections integrated in the right place.
3. Call `updateConfluencePage` with `contentFormat: "html"`, `status: "draft"`,
   and the full reconstructed body.

The tool replaces the entire body; sending a partial body silently drops
existing content and orphans any media nodes it contained.
