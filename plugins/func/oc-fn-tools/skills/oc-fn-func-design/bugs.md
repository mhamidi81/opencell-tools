# Jira INTRD — Bugs

Reference rules for Bug issues on the INTRD project.
Read together with the main `SKILL.md`. **Minimal by design** — a Bug is a single
`description`-field issue fully driven by its template; this file adds only the
Bug-specific framing the template alone doesn't teach.

## What is a Bug

A Bug reports a defect in existing, shipped behaviour — something that does not work as
specified. It is a *fix*, not new scope: if the work introduces or changes intended
behaviour, it is a User Story or an Enabler, not a Bug.

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
["summary", "status", "issuetype", "priority", "assignee", "parent", "labels", "components", "description"]
```

## Authoring notes

Follow the template's sections. A well-formed Bug makes the defect reproducible and scoped:

- **Reproduction** — exact, numbered steps; **expected vs. actual** result; frequency
  (always / intermittent).
- **Environment** — tenant/instance, build or version, and browser/OS where relevant.
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
