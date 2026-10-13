---
name: oc-fn-documentation
version: 1.7.0
updated: 2026-10-09T22:40:00+02:00
author: Stéphane Chambrin
description: Rules and conventions for creating and updating Confluence documentation pages in the Opencell documentation space (opencellsoft.atlassian.net/wiki/spaces/docs). Use this skill whenever the user mentions Confluence, documentation, a "Concepts" page, a "User Manual" page, or asks to document anything for Opencell. Always load this skill before any Atlassian Rovo Confluence tool call targeting the docs space. Also covers linking each documented Story to its pages from Jira.
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
connector is not enabled.

The connector is the portable path, but it is **not the only one**: on a machine whose `~/.netrc`
carries the Atlassian host, the Confluence REST API answers `curl -n` directly (verified on
`sabretooth`, 2026-08-07) — see § *Page update workflow* for when to prefer it. Everything else in
this skill — the rules, the audience constraints, the HTML patterns — applies to both transports.

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
6. **Audience: this space is customer-facing — never reference an internal
   tracker.** No Jira keys (`INTRD-…`, `SUPS-…`, `CR-…`), no sprint or Epic
   names, no branch or commit identifiers, no internal ticket links — not in the
   body, not inside a panel, and **not in the `versionMessage`** (page history is
   readable by anyone with access to the page). This holds even when the ticket
   is the most precise way to say it, and even when the reference is labelled
   "internal ref." — labelling it does not make it publishable. State the change
   and the version instead: *"planned for a future version"*, *"corrected by the
   same future change"*, *"from 18.0.0 onwards"*. Traceability to the ticket
   belongs in Jira and in the design repo, both of which the docs owner can
   reach; the published page cannot. The Story points at the page, never the
   reverse: see § *Link each Story to the pages that document it*.

## Space Structure — Parent Pages

Always place new pages under the correct **non-versioned** parent.

| Section | Page ID | Audience |
|---|---|---|
| Concepts | `638877697` | Consultants |
| User manuals | `516718593` | Portal end-users |

**Never create or edit anything under versioned `(vXX) ...` sections.** Those are
the snapshots K15t Scroll Content Manager saves for a major (e.g. "(v18) Customer
Care", "(v17) User manuals"), and they are **never updated** — not even for a
change that only concerns a released 18.x line. Every change, whatever version it
describes, goes into the **working version**: the non-versioned pages listed above.
(In June 2026, 13 User manual pages were written only into a `(v18)` copy; that
content never reached the working version and had to be rebuilt.)

### The working version and when it is published

Stated by the CPO on 2026-10-09:

- **The working version is the up-to-date documentation.** Customers read it on
  the knowledge center (`knowledgecenter.opencellsoft.com`, K15t Scroll Sites),
  where every link opens it by default; saved versions are one click away in the
  version picker. `docs.opencellsoft.com` is only a small public subset.
- **A change is published when the version it describes is released**, minor or
  major. So a draft may sit until its release: when you save one, tell the user
  which version it waits for, so the docs owner publishes it at the right time.
- **A published page holds a single unpublished draft.** Before drafting a change
  for a later version on a page whose draft already carries a change for an
  earlier version, stop and tell the user: the docs owner could no longer
  publish the earlier change on its own. The later change can still be written
  and reviewed, built on that draft, but keep it out of Confluence (a local file)
  and save it only once the earlier draft is published. Tell the user which pages
  hold such a prepared part.

**A draft whose body equals the published body is not a pending change.**
Confluence leaves such a draft behind a publish (on *Orders - newUI*, saved
0.5 s after published version 7), and old ones linger, some by deactivated
authors (*Quotes - newUI*, an empty draft from 2024). Compare the two bodies
before treating a draft as someone's pending work: when they are equal, base the
update on the published body and do not hold it behind that draft. Compare the
**text**, not the bytes: such a draft often differs only in `ac:macro-id` or
`local-id` attributes. Observed on 2026-10-09.

**A draft older than the published version can be stale.** When its body is
byte-identical to an earlier published version
(`GET /wiki/rest/api/content/{id}?status=historical&version=N&expand=body.storage`),
it is an editor draft left behind before that publish, not pending work: build on
the published body, and tell the user that saving replaces the stale draft with
nothing lost. On 2026-10-09, *Collection plans listing* and *Dunning actions* held
2025 drafts identical to their published v12 and v20 (live v13 and v22).

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

**Read around each Story before writing from it** (learned on the 19.0.0
quote and order pages, 2026-10-09):

- **Its children.** A Done Sub-task or Sub-bug can change what shipped after the
  Story was written: on the quote page, a Sub-task replaced the Story's editable
  *Validity period (in days)* with a read-only *Validity* date. List them with
  `jira children KEY` and read the Done ones.
- **Its comments, and the rulings in its Sub-bugs.** A ruling recorded there
  overrides the functional design: on the chart of accounts, a ruling made in a
  Sub-bug on 2026-06-22 turned the account code read-only on update, while the
  Story still says it can be typed in. Comments also record reverts ("the backend
  dev has been reverted"): check the current source before trusting either way.
- **The later Stories of the same Epic.** A later Story can redefine a mechanic
  an earlier one describes: a page-level Save made an earlier Story's "saved on
  blur" mean "kept until the page is saved".
- **When Stories conflict, or one contradicts itself, read the Portal source**
  (`git fetch` first: local checkouts lag) to decide which statement shipped.
  Use the source only to choose between statements the Stories make, never to
  add behaviour no Story describes. Record each call as *read from source, not
  observed* in the work notes and the report, never on the page.
- **Take UI labels from the Portal's English i18n** (`src/i18n/common-resources.en.json`
  and the module's `i18n/en.json`), not from the Story's EN/FR label pairs,
  which drift: the Stories say *Calculate*, the button reads *Re-calculate quote*.

## Link each Story to the pages that document it

Asked by the CPO on 2026-10-09. **Every time you save a draft, link each Story
whose behaviour the page documents to that page**, from Jira: a *Confluence page*
link on the Story. It is a Jira remote link to the Confluence application link,
relationship `Wiki Page`. It is not an issue-link type, and it shows on the Story
among its Confluence pages. It is the only trace allowed between the two, since
Rule 6 keeps keys off the page. Confluence's automatic *mentioned in* links
appear only when a page mentions the issue, which Rule 6 forbids.

- **One link per Story per page that documents it.** Several pages documenting a
  Story get one link each.
- **Not linked:**
  - Backports: the original Story carries the link.
  - Bugs and Sub-tasks.
  - Stories read only for context or corroboration.
  - A Story whose behaviour the page does not describe yet, such as an
    unreleased version that the page mentions only as a current limitation.
- **Link right after saving the draft.** The page ID does not change at
  publication, so the link stays valid. A link to a new page that was never
  published opens only for its author until the page is published.
- **There is no MCP tool for it.** `createIssueLink` links two issues, and
  `getJiraIssueRemoteIssueLinks` only reads. Use Jira REST, with
  `jira raw POST /issue/KEY/remotelink @link.json` or `curl -n`:

  ```json
  POST /rest/api/3/issue/{KEY}/remotelink
  {"globalId": "appId=<app link id>&pageId=<page id>",
   "application": {"type": "com.atlassian.confluence", "name": "Confluence"},
   "relationship": "Wiki Page",
   "object": {"url": "https://<site>/wiki/pages/viewpage.action?pageId=<page id>",
              "title": "<page title>"}}
  ```

- **The app link ID is tenant-specific: resolve it at use-time** from
  `GET https://<site>/rest/applinks/1.0/listApplicationlinks` (header
  `Accept: application/json`), the entry whose `typeId` is `confluence`. On the
  reference tenant it is `aeefea1b-e599-3bce-9d06-8b1a80d1bd04`, which Confluence's
  own *mentioned in* links also carry.
- **Idempotent by `globalId`.** Posting the same `globalId` again updates the
  existing link (same `id`) instead of adding one, so a re-run is safe. Read it
  back with `GET /rest/api/3/issue/{KEY}/remotelink`.
- **Reverse lookup.** To find the Stories a page documents, use JQL
  `issue in issuesWithRemoteLinksByGlobalId("appId=<app link id>&pageId=<page id>")`.
- **Report the count** of links created to the user, with any Story left
  unlinked and why.

Verified on 2026-10-09 by API read-back and that JQL, not by looking at the Jira
issue view. Before that date the practice did not exist: a sample of 100 delivered
Stories and Epics carried one Confluence link, an automatic *mentioned in*.

## HTML — Required Patterns

### Colored heading (H2–H6)

```html
<h2><span style="color: #bf2600">Section Title</span></h2>
```

Replace `h2` with the appropriate level (h2–h6).

In **storage format** (`body.storage` over REST, the form the *Documentation
page* template itself uses, verified 2026-10-09) the same colour is written as
`rgb(191,38,0)`:

```html
<h2><span style="color: rgb(191,38,0);">Section Title</span></h2>
```

Use that form in a storage body. It is `#bf2600` spelled differently, so it does not
break Rule 5's "do not normalise".

### Status lozenge

```html
<span data-type="status" data-color="green|yellow|blue|red|neutral|purple">LABEL</span>
```

### Panels

```html
<div data-type="panel-info|warning|note|success|error"><p>text</p></div>
```

In **storage format** (`body.storage` over REST), a panel is a macro:

```html
<ac:structured-macro ac:name="info|note|warning|tip"><ac:rich-text-body><p>text</p></ac:rich-text-body></ac:structured-macro>
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

**Check the title first, archived pages included.** A title stays taken by an
archived page, and CQL title search misses archived pages. Query
`GET /wiki/rest/api/content?spaceKey=docs&title=<title>&status=current`, then again
with `status=archived`. On 2026-10-09, *Creating a subscription* was held by an
archived 2022 page and *Invoicing minimum* by archived page 248381573.

### Page update workflow

1. Fetch the current page with `getConfluencePage`, `contentFormat: "html"`.
2. Reconstruct the **full** body — existing content verbatim (preserving all
   media nodes) plus new or modified sections integrated in the right place.
3. Call `updateConfluencePage` with `contentFormat: "html"`, `status: "draft"`,
   and the full reconstructed body.

The tool replaces the entire body; sending a partial body silently drops
existing content and orphans any media nodes it contained.

4. **Verify both revisions afterwards** — that the draft carries the change and
   still has every media node, *and* that the published page has not moved
   (same version number, none of the new text). Rule 3 is only honoured if the
   second check passes.

**Two draft gotchas that cost a failed call each.**

- **A draft revision is always version `1`.** A `PUT` carrying an incremented
  number is rejected with `DRAFT pages do not support multiple versions.
  Expected version: [1]` — including on the *second* and later edits of the same
  draft. Send `version: {number: 1}` every time; the live page keeps its own
  numbering untouched.
- **Reading a draft back needs the v1 API.** `GET /wiki/api/v2/pages/{id}?status=draft`
  answers `404 NOT_FOUND … with any status of [draft]`. Use
  `GET /wiki/rest/api/content/{id}?status=draft&expand=version,body.atlas_doc_format`.

**Large pages: prefer direct REST over the MCP.** On a machine whose `~/.netrc`
carries the Atlassian host, `curl -n https://<site>/wiki/api/v2/pages/{id}?body-format=atlas_doc_format`
works — the same pattern `bin/jira` uses for Jira. That matters because Rule 3's
full-body reconstruction means a whole page must round-trip: through the MCP it
lands in context twice (fetch, then re-send), while over REST it can be edited
**surgically in a file** — locate the node, change it, `PUT` the result — which
also guarantees media nodes are preserved byte-for-byte rather than re-typed.
`~/.netrc` is machine-local, so check before relying on it; the MCP remains the
portable path.
