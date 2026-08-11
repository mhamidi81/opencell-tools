# Jira INTRD — Bugs

Reference rules for **Bug** and **`Sub-bug`** issues on the INTRD project.
Read together with the main `SKILL.md`. Both are single `description`-field issues fully driven
by the same template; this file adds only what the template alone doesn't teach — which of the
two types applies, what to check before filing either, and the create-time fields that differ
between them.

## What is a Bug

A Bug reports a defect in existing, shipped behaviour — something that does not work as
specified. It is a *fix*, not new scope: if the work introduces or changes intended
behaviour, it is a User Story or an Enabler, not a Bug.

## Sub-bug — defects found while reviewing a Story

`Sub-bug` is INTRD's sub-task defect type: canonical `issuetype.name` **`Sub-bug`** (lower-case
*b*), **id `10071`**, `subtask: true`. JQL tolerates `"Sub-Bug"`, so a search that works is **no**
proof of the spelling — `Sub-bug` is the name the API takes on create.

**Routing — which of the two types:**

| The defect… | File it as | Parent |
|---|---|---|
| breaks something the Story under review is meant to deliver | **`Sub-bug`** | the reviewed **Story**, set via the `parent` field **at creation** |
| sits outside that Story's scope — e.g. a generic framework-level problem the Story merely exposed | standalone **`Bug`** | none; link it to the Story/Epic whose behaviour it concerns |

A Sub-bug carries `fixVersions` and `priority`; `components` are typically left empty in practice
and read from the parent.

Set **`customfield_10228` (*Regression*)** when the defect is a regression — a single-**option**
field whose only allowed value is `Regression`, i.e. a flag. Establish that it *is* one with the
archaeology below before setting it.

> **There is no Sub-bug template.** Verified on Jira: `jira jql 'project = INTRD AND summary ~
> "TEMPLATE" AND (summary ~ "COPY" OR summary ~ "CLONE")'` returns INTRD's seven template issues
> (Story ×3, Epic, Initiative, Enabler, Bug) — no Sub-bug among them. A Sub-bug follows the
> **Bug template INTRD-5340** — same eight sections (listed in § *Template* below, with the
> three-block structure they form) and the same heading rule: plain `strong`, **no `#bf2600`**.

**A Story is not rejected on its own** — the defects go under it as Sub-bugs first. The PO
review / rejection lane is `po-review.md`.

## Before filing — regression archaeology

Two checks before a defect becomes an issue. Both are cheap, and both were skipped in the review
that produced this section. `po-review.md` is the lane that reaches them most often.

- **Search closed issues for the same symptom first.** The blocking defect in the INTRD-26660
  review was a regression of a Bug already closed as *Done* — **INTRD-36420**, *"[Reg][Seller]
  can't update seller : Server communication error"* — whose title would have matched on the
  symptom wording alone. Search the symptom as the reporter phrased it, across **all** statuses,
  not just open ones. A hit turns a fresh Bug into a regression (flag `customfield_10228`) and
  hands you the original fix to diff against.
- **When the code went through a revert and a later re-apply, diff the re-applied patch against
  the *pre-revert* state, not against the original commit.** A re-apply silently drops every
  bugfix that landed in between. Here the *guarded* version of the code was removed by a revert of
  the Story's own commit, and the re-apply restored the *unguarded* original; half of it had been
  independently re-fixed months later on a sibling field, with nobody noticing the twin.

Tooling:

- `git log -L <start>,<end>:<file>` attributes a specific block instead of the whole file.
- **Sort and read by committer date, not author date** — plain `git log` prints the *author* date,
  so ask for `%cd` explicitly. The re-apply here was authored 2025-12-31 but committed 2026-05-01;
  author-date ordering hides the sequence entirely.

**Ship the verdict, not the transcript.** The archaeology is a *pre-filing* obligation — it is how you
establish the regression and earn the `customfield_10228` flag, and it stays mandatory. What belongs
in the `description` is the **conclusion in one line** — *"Regression of INTRD-36420; the guards were
lost in `e310f06e574`"* — not the commit table you built to reach it. INTRD-45541 shipped a five-row
archaeology table (with a parenthetical warning that author dates mislead) for a defect whose fix is
two null guards: ~140 words that change nothing about the patch, while inviting the reader toward a
revert or a wholesale cherry-pick of a Story-sized commit.

## Template

The Bug template is **INTRD-5340**. It uses the standard `description` field with the shared
ADF structure in [`SKILL.md` § Templates index](SKILL.md#templates-index) — including the
read-side `description` gotcha (it fetches as Markdown; verify structure with
`expand: "renderedFields"`). **Read the template first**, then reproduce its structure: new
Bugs written from it must be ADF with `strong` headings each followed by a `rule` node and the
note panels, not plain Markdown.

> **Bug headings carry *no* colour.** Unlike the Epic / Initiative / Enabler / Story / CR
> templates (dark-red `#bf2600` headings), the Bug template's headings are **plain `strong`
> with no `textColor`**. Do **not** add `#bf2600` to a Bug's headings — match the template
> exactly (plain `strong` + `rule` + note panel).

### The eight sections — three blocks

The heading levels are load-bearing: they sort the body into **what was observed**, **what it costs**,
and **what is inferred**. Keep a sentence in the block matching its epistemic status.

| | Section | Level | Block |
|---|---|---|---|
| 1 | *Description* | **H1** | **Observed.** One line — what breaks, for whom, and at which interface (see § *Authoring notes* → *Observed at*). |
| 2 | *Steps to reproduce* | H2 | ↳ black-box, numbered, with frequency |
| 3 | *Expected results* | H2 | ↳ |
| 4 | *Actual results* | H2 | ↳ verbatim error text, status, offending input |
| 5 | *Impact and criticality* | **H1** | **Cost.** Who is blocked, and whether a workaround exists. |
| 6 | *Analysis* | **H1** | **Inferred — optional.** Governed by § *Analysis — separate what you observed from what you inferred*. |
| 7 | *Evidence base* | H2 | ↳ fill only when the Analysis asserts a cause |
| 8 | *Suggested fix* | H2 | ↳ at most the minimal change for the *observed* symptom |

**Blocks 1 and 5 are the record; block 6 is not.** Everything under *Description* is something a
reporter saw, and it is what defines the fix as done. Everything under *Analysis* is reasoning that may
be wrong — which is why it carries its own status markers rather than inheriting the authority of the
sections above it.

> **Revised 2026-08-06** — *Impact and criticality* was promoted from an H2 under *Analysis* (it is
> user-POV content, misfiled under the diagnostic heading), *Evidence base* was added, *Description*
> gained the note panel it never had, and the *Analysis* / *Suggested fix* panels were rewritten.
> Verified after the edit via `expand: "renderedFields"`: 8 purple `#eae6ff` note panels, 3 `<h1>`,
> 5 `<h2>`, 8 `<hr>`, and **zero** `#bf2600`.

## Fields

Bugs use the standard **`description`** field (not the Story custom fields). Full-read preset:

```
["summary", "status", "issuetype", "priority", "assignee", "parent", "labels", "components", "description", "environment"]
```

## The `environment` field — environment URI + versions tested

**Fill `environment` on every Bug and Sub-bug.** It is what makes a defect reproducible on the right
build; without it QA cannot tell whether a failure is current, already fixed, or environment-specific.

**`environment` is an ADF rich-text field**, not a plain string — send a full
`{"type":"doc","version":1,…}` document object, same as `description`. Follow the Bug template's
styling rule: **plain `strong` labels, no `#bf2600` colour.**

Two parts, both expected:

1. **The environment URI** — a link to the exact page, endpoint or environment where the defect
   shows, with link text that identifies it. Real examples:
   - a deep Portal link — `https://energie-18.oc-nsb.eu/opencell/frontend/DEMO/portal/B2B/orders/31/modify`, labelled `ORD-26000030 - Orders - Customer Care - Opencell` (INTRD-45540)
   - a Jenkins job — `https://jenkins.opencell.eu/view/TNR/job/tnr-sandbox-18.X/` (INTRD-45519)
   - a DB-viewer target, when the defect is in stored data (INTRD-45537)
2. **The versions tested** — the build block for **Core and/or Portal**. Copy it verbatim from the
   Portal's version panel when you have it open; otherwise both builds are readable without a login —
   Core from `GET /opencell/api/rest/v2/version`, and the Portal's from the build constants in its
   shell bundle. Recipes and the mandatory sha-verification step are in the `oc-fn-portal` skill,
   `api-replay.md` § 3 *Confirm which build you are reasoning about*.

   ```
   Opencell Core
   Version: 18.2.0-SNAPSHOT
   Build: 00cf40eac534275fe0f1bc112c7c40e40f25252d
   Date: 2026-07-30T14:30:16Z

   Opencell Portal
   Version: 18.2.0-SNAPSHOT
   Build: a38d95489c0bb61f81ffa1c337d0e6ffa00b4d09
   Date: 2026-07-30T17:26:18+02:00
   ```

   **Give both layers whenever either could be implicated** — a Portal symptom often has a Core
   cause, and a mismatched pair of builds is itself a common root cause. At minimum, give the layer
   the Bug is filed against (its `components` `Backend` / `Frontend`). Examples: INTRD-45514 (both),
   INTRD-45521 (Core only), INTRD-45522 (Portal only). Keep the `Build` SHA — the `Version` alone is
   ambiguous across `-SNAPSHOT` rebuilds, which is precisely when "works for me" happens.

**Not redundant with the two required fields** — they answer different questions, and all three are
expected:

| Field | Carries | Used for |
|---|---|---|
| `customfield_10359` *Issue location (URL)* | one URL, **required**, URL-typed | the single canonical pointer to the defect |
| `versions` *Affects versions* | release picker values, **required** | triage, filtering, release reporting |
| `environment` | the env link **plus** the full build fingerprint (version + SHA + date) per layer | reproducing the defect on the exact build |

> **The automation seeds a hint panel here.** INTRD's *"Issue created (one automation to rule them
> all)"* rule writes a 234-char note into `environment` a few seconds after creation — *"Add a link to
> the environment/page where issue is located (if possible)"* / *"Paste version information copied
> from Portal"* / *"You can delete this note"*. Replace it wholesale with the real content and drop
> the note; a Bug still carrying that panel has an unfilled `environment`.
>
> **Set `environment` inside the create call**, for the snapshot reason in `stories.md`
> § *Template-seeding automation*. The rule is guarded on `environment is not empty`, so a value
> present in the create call is left alone. **Verified 2026-08-03** on a throwaway Bug *and* Sub-bug
> created with `environment` + `description` in `POST /issue`: both fields survived intact and the
> automation touched only `Account` and `timeestimate` — no hint panel written. (Before the guard, the
> same rule wrote `environment` unconditionally at `+4 s`.)
>
> `environment` is **not** on either create screen, yet `POST /issue` accepts it — same as
> `description`, see the note at the end of § *Required fields at creation*. Do not conclude from
> `createmeta` that it needs a follow-up edit.
>
> Spot-check past the window (`> 10 s`) if you want certainty on a batch:
> ```sh
> jira raw GET "/issue/$K?fields=environment" | jq -r '[.fields.environment|..|.text? // empty]|join(" ")'
> ```
> A result reading *"Add a link to the environment/page…"* means the hint panel is still there — the
> field was never filled, or the guard did not hold; re-`PUT` your value.

> **Separate the version lines with `hardBreak` nodes.** A block pasted into the UI loses its line
> breaks and renders run-together — real example, INTRD-45514: `Version: 15.14.6-SNAPSHOTBuild:
> 3ed6ec35…Date: 2026-07-29T22:19:14+00:00`, with no separator between the three values. Authoring via
> the API, put a `hardBreak` between them (and mark the layer name `strong`); it renders as a proper
> `<br>` per line, so API-authored blocks read better than pasted ones. Don't imitate the mangled
> spacing of existing Bugs.

## Required fields at creation — Bug vs Sub-bug

The two required sets differ, and the difference bites: a **`Bug`** create that omits them fails
with a `400` a **`Sub-bug`** create never hits. The recognisable body:

```json
{"errorMessages":["Issue location (URL): Issue location (URL) is required.",
                  "Affects versions: Affects versions is required."],
 "errors":{"versions":"Affects versions is required.",
           "customfield_10359":"Issue location (URL) is required."}}
```

| | **`Bug`** (id `10004`) | **`Sub-bug`** (id `10071`) |
|---|---|---|
| **Required** | `project` · `issuetype` · `summary` · `priority` · `fixVersions` (*Fix versions*) · `versions` (*Affects versions*) · `customfield_10359` (*Issue location (URL)*) | `project` · `issuetype` · `summary` · `parent` — and nothing else |
| **Optional** | `parent` · `assignee` · `components` · `issuelinks` · `customfield_10095` (*Expected by*) · `customfield_10228` (*Regression*) | the same **minus `parent`** (required here), plus `priority` · `fixVersions` · `versions` · `customfield_10359` |

Both create screens expose the same thirteen fields — only the required/optional split differs.

The error body above names only two of the Bug's four extra requirements, because `priority` and
`fixVersions` happened to be set on that call. Read the table, not the error.

The two Bug-only fields worth naming:

- **`versions` — *Affects versions*.** The version(s) where the defect is observed. **Distinct from
  `fixVersions`** (*Fix versions* — where it will be fixed); a Bug requires both, and they are not
  interchangeable.
- **`customfield_10359` — *Issue location (URL)***. The page or endpoint where the defect shows — a
  **URL-typed** string field (`schema.custom` …`customfieldtypes:url`), so **send a full URL**; a
  bare page name is rejected.

**General rule: run `jira meta <issuetypeId>` — or `getJiraIssueTypeMetaWithFields` — before the
first create of an issue type you have not created before in this session.** Required sets vary per
type, the check is one cheap call, and a `400` on create costs more.

> **`description` does not appear in `createmeta` for either type** — it is not on their create
> screen — **yet `POST /issue` accepts a `description` at creation anyway.** Verified: INTRD-45541
> was created with a 33-node ADF description and its changelog carries no `description` entry. Do
> **not** conclude from `createmeta` that a Bug must be created empty and then edited.

## Authoring notes

Follow the template's sections. A well-formed Bug makes the defect reproducible and scoped:

- **Observed at** — name the interface where the defect surfaces, on the *Description* line:
  **Portal GUI**, **REST API**, **batch or file processing**, or a **generated document** (invoice
  PDF, SEPA `pain` file, e-reporting submission). It routes the fix — with no full-stack developers,
  a GUI defect and an API defect go to different teams and different repos — and it exposes the case
  where one defect needs **two** issues (a Core fix plus an additive Portal fix). It is *not* a
  duplicate of `customfield_10359` (*Issue location (URL)* — one pointer to one page) or of
  `components` (`Backend`/`Frontend` — the engineering layer, set at triage).
- **Reproduction** — exact, numbered steps a reader can follow **without reading code**; **expected
  vs. actual** result; frequency (always / intermittent). A screenshot may *illustrate* a step; it may
  never *be* the step. INTRD-45655 is the counter-example — twelve words and three PNGs, with no page,
  no steps and no expected result: the cheapest body to write and among the most expensive to act on.
- **Verbatim over paraphrase** — quote the exact error text, HTTP status and offending input literal.
  This is the cheapest content a Bug can carry: `NumberFormatException: For input string: "*invoice*"`
  (INTRD-45622, a 73-word Bug with no diagnosis at all) is a greppable entry point that needs none.
  Attach stack traces past ~15 lines and full request/response bodies rather than pasting them inline.
- **Never paste credentials.** No bearer tokens, cookies, passwords or `Authorization` headers —
  INTRD-45597 carries ~700 characters of a live bearer token plus fifteen browser headers in its
  `description`. A Bug body is readable by everyone with tracker access; this is a security defect
  independent of any formatting question. Redact to `Authorization: Bearer <redacted>` and keep the
  rest of the call, which is the part with signal.
- **Environment** — tenant/instance and browser/OS where relevant. The environment URI and the
  Core/Portal build fingerprints go in the **`environment` field**, not here — see § *The
  `environment` field*; don't duplicate them in the `description`.
- **Severity & priority** — set per the project's triage scale; justify if non-obvious.
- **Linkage** — link the Bug to the Story/Epic whose behaviour it concerns (and to the
  offending change if known) so the fix lands in the right scope.

Keep prose factual — a Bug records what is broken, not how to redesign it. Substantial
solution design belongs in a linked Story or Enabler.

**This binds the *Suggested fix* section specifically.** It may name **at most the minimal change that
removes the *observed* symptom** — the file(s) and the change itself. Out of lane, and to be routed to
a linked Story or Enabler instead: ranked alternatives, refactors, relocating logic into a shared
service, and revert or cherry-pick proposals. INTRD-45633 is the anti-pattern — a defect its own
*Analysis* says was *"not reproduced on a live instance"*, whose *Suggested fix* nonetheless recommends,
as the option labelled *"better, since it closes every current and future path at once"*, moving number
allocation into `CommercialOrderService.create()` and accepting a change to sequence-consumption
semantics. A reader following the section as written mutates a shared service on an unobserved bug.

## Analysis — separate what you observed from what you inferred

The *Analysis* block is where a Bug stops recording and starts reasoning, and a `description` gives it
no epistemic vocabulary of its own: **by default every sentence in it reads as the record.** That is
correct for *Description / Steps / Expected / Actual*, which are observations. It is wrong for a root
cause, which is a hypothesis until someone has read or replayed it — and a confidently-stated wrong
hypothesis costs more than none at all, because the reader (increasingly a coding agent working from
the issue alone) treats it as a constraint and prunes away the search space it rules out.

So keep the analysis. Mark its status.

- **Two voices, inline.** Prefix every causal or generalising claim with **`Established —`** (you read
  the code, replayed the call, or queried the data *yourself*) or **`Hypothesis —`** (you inferred it).
  A `Hypothesis —` claim should name what would settle it — *"one read of `X` confirms or kills this"*.
  An unmarked claim reads as established: do not leave inference unmarked.
- **Evidence base.** Whenever the *Analysis* asserts a cause, fill the *Evidence base* sub-section:
  one of **reproduced live** / **established from source only** / **not reproduced**, plus the tenant
  and the branch or ref actually read. INTRD-45633 already does this — *"Not reproduced on a live
  instance. The defect is established from source on `origin/18.X`"*, with its negative evidence named
  (tenant `energie-18`, 56 orders, 0 from a quote). Today that is the exception; it should be the norm.
- **Caveat locality.** A scope limit binds only where it is written — it must sit in the **same sentence
  or bullet** as the claim or suggestion it limits, because an upstream hedge does not license a
  downstream instruction. INTRD-45620 hedges *"not verified field by field… only the two name fields
  were tested"*, then ~200 words later states that the same treatment applies to five untested fields.
  Reject that shape on review.
- **Prefer exclusions to locations.** The cheapest analysis is subtractive: *"the API/data layer also
  correctly fetches `allowedValues` — this part is not the bug"* (INTRD-45664) is falsifiable in one
  read and removes a whole layer from the search. Contract statements do the same work — *"Core already
  treats an explicit `null` as 'clear', so no backend change is needed"* (INTRD-45620) saves a frontend
  developer from opening Java at all. Exclusions are what make a long *Analysis* cheap; archaeology is not.
- **Name the symbol, not the line.** `file:line` anchors go stale — the `opencell-core` and
  `opencell-portal` checkouts commonly lag their branch by weeks, so a quoted line number sends the
  reader to the wrong block while the surrounding confidence invites them to "confirm" whatever they
  find there. Name the function, method or component and quote the offending block (≤5 lines). Where
  the claim is about *deployed* behaviour, anchor it to the deployed artifact as INTRD-45543 does —
  *"the served lazy chunk `index-D5HSIrO6.js` carries exactly this logic"* — which is checkout-independent.
- **Re-read the *Description* against the *Analysis* before filing.** INTRD-45590 asserts *"The saved
  state does reach Keycloak — writing is not the problem"* up top, then prescribes a write-path fix a
  thousand words later. A reader who believed the first sentence will not look where the fix is.
- **One actionable statement, findable.** If the *Suggested fix* has a single load-bearing item, say so
  where it can be seen. INTRD-45590 buries *"This alone fixes the reported symptom"* as item 1 of nine,
  at roughly word 1,400.

**None of this applies to a Bug that asserts no cause.** A body of pure observation is **complete and
conformant** with no markers, no *Evidence base* and no *Suggested fix* — INTRD-45622 is 73 words with
zero diagnosis and the best signal-per-word in the sample. Diagnosis is optional in a Bug; what is not
optional is being clear about which kind of sentence you are writing.

**A retest comment is a different artifact under the same discipline.** When you report the *result* of
testing a delivered fix, the shape is a *Case / Expected / Actual* table — not a second *Analysis*, and
not a fix proposal. See `po-review.md` § *The verdict comment — what you did, expected, actual*, which
also carries the reassign-on-rejection and thank-you-on-pass rules.

## Limits & volumes

The cross-cutting rule (`SKILL.md` § *Limits & volumes — mandatory reflection*) targets
issues that **introduce or modify behaviour**. A Bug fix usually does neither, so the
point-by-point checklist is normally **`N/A — defect fix, no new scale envelope`**.

The exception: when the defect *is* a scale / performance / volume problem (e.g. a list that
times out past N rows, a job that fails at peak), address the relevant checklist points
inside the `description`, quoting the affected Story/Epic envelope figures.
