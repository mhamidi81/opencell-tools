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
> **Bug template INTRD-5340** — same seven
> sections (*Description · Steps to reproduce · Expected results · Actual results · Analysis ·
> Impact and criticality · Suggested fix*) and the same heading rule: plain `strong`, **no
> `#bf2600`**, per § *Template* below.

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

- **Reproduction** — exact, numbered steps; **expected vs. actual** result; frequency
  (always / intermittent).
- **Environment** — tenant/instance and browser/OS where relevant. The environment URI and the
  Core/Portal build fingerprints go in the **`environment` field**, not here — see § *The
  `environment` field*; don't duplicate them in the `description`.
- **Severity & priority** — set per the project's triage scale; justify if non-obvious.
- **Linkage** — link the Bug to the Story/Epic whose behaviour it concerns (and to the
  offending change if known) so the fix lands in the right scope.

Keep prose factual — a Bug records what is broken, not how to redesign it. Substantial
solution design belongs in a linked Story or Enabler.

## Limits & volumes

The cross-cutting rule (`SKILL.md` § *Limits & volumes — mandatory reflection*) targets
issues that **introduce or modify behaviour**. A Bug fix usually does neither, so the
point-by-point checklist is normally **`N/A — defect fix, no new scale envelope`**.

The exception: when the defect *is* a scale / performance / volume problem (e.g. a list that
times out past N rows, a job that fails at peak), address the relevant checklist points
inside the `description`, quoting the affected Story/Epic envelope figures.
