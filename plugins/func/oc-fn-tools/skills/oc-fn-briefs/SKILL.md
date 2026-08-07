---
name: oc-fn-briefs
version: 1.3.0
updated: 2026-08-07T23:20:00+02:00
author: Stéphane Chambrin
description: >
  Author and render branded Opencell DOCUMENTS — one-pagers, analysis notes,
  briefs, memos, short reports — styled with the Charte Graphique 2023 and
  rendered to a print-ready A4 HTML/PDF via headless Chromium. Two authoring
  tiers: markdown-first (a `.md` source rendered through Pandoc — the default,
  the "Marp for documents" workflow) and hand-authored self-contained HTML (the
  escape hatch for bespoke layouts). Load this skill whenever the user wants a
  branded one-pager, note, brief, memo, fact-sheet, summary sheet, or short
  standalone document (not slides), or asks to render Markdown/HTML content to a
  branded PDF. Carries the document brand theme (`theme/brand.css` + shared
  logos + `theme/oc-brief.lua`), a markdown source template
  (`templates/one-pager.md`) with its Pandoc HTML template, a ready-to-fill
  hand-authored `templates/one-pager.html`, the `YYYYMMDD_` dated-filename
  rule, the render commands, and the screenshot verification step. NOT for
  slide decks (that is `oc-fn-decks`), NOT for Confluence pages (that is
  `oc-fn-documentation`), and NOT for Jira functional designs / requirement
  briefs (that is `oc-fn-func-design`).
---

# Opencell documents — branded one-pagers, notes & briefs (Markdown/HTML → PDF)

This skill covers **how to build a branded Opencell *document*** — a one-pager, analysis note,
brief, memo, or short report. It is the non-slide sibling of `oc-fn-decks`: same Charte Graphique
brand, different medium (a flowing A4 page, not slides).

Reach for it when the user says "one-pager", "note", "brief", "memo", "fact-sheet", "summary sheet",
or "make this a branded PDF" — and it's **not** a slide deck, a Confluence page, or a Jira field.

## Two authoring tiers — pick the lowest one that fits

A document has **arbitrary, content-specific layout**, so — unlike a Marp deck, where markdown just
fills a fixed slide box — no single "markdown → branded page" tool can express every layout. This
skill resolves that with **two tiers that share one brand, one renderer, and one verify step:**

- **Tier 1 — markdown-first (the default).** Author a `.md` source; render it through **Pandoc**
  (with this skill's HTML template + Lua filter + `brand.css`) to a self-contained branded HTML,
  then to A4 PDF with the same Chromium step as Tier 2. This is the "Marp for documents" workflow:
  `.md → branded .html + .pdf`, one-way. **Use it for the common brief** — prose, tables, one KPI
  row, framing cards, a caveats note. The `.md` is greppable/diffable and *is the source of truth*.
- **Tier 2 — hand-authored HTML (the escape hatch).** Copy `templates/one-pager.html`, fill the
  layout by hand, render to PDF with Chromium. **Use it only when Tier 1's vocabulary can't express
  the layout** — bespoke multi-column dashboards, mixed card/figure grids, a table total row
  (`tfoot`), precise page-break control. Here the HTML carries the *layout*.

**Default to Tier 1.** Drop to Tier 2 only when you hit a wall — and when you do, it's a lower-level
entry into the *same* renderer and the *same* `brand.css`, not a fork. Keep the Tier-1 vocabulary
**deliberately tiny** (the components below and nothing more): the failure mode of this whole
approach is vocabulary creep that reinvents HTML in colons. Anything more elaborate → Tier 2.

## The `.md` is a source, never a hand-maintained mirror

A recurring instinct is "every branded doc should also have an unbranded `.md`." Right in spirit,
but the naive form — a `.md` twin you keep in sync with the HTML **by hand** — is a liability: edit
one, forget the other, and the "source" silently lies. So:

- **Tier 1:** the `.md` *generates* the HTML. It is the single source; there is nothing to drift.
- **Tier 2:** the **HTML is the layout source.** A `.md` alongside it, if kept, is a *content-of-record*
  (the wording, greppable) — **not** a full layout mirror. Do **not** try to hand-maintain an
  unbranded `.md` twin of a bespoke HTML page. Keep the words if useful; don't pretend the `.md`
  reproduces the page.

## Audience first — establish it before authoring

**Before writing, settle who the document is for and what it must land** — these set the tone, depth,
and which numbers lead.

- **Not clear? Ask.** Who receives it — sponsor/lead, SteerCo, a customer, engineering, internal? And
  what they most need from a single page.
- **Think it's clear? Confirm.** State your read and get an OK before authoring.
- **Record it** in the source header (the `.md` front matter, or the Tier-2 HTML header) so later
  edits keep the target.
- A document is **denser than a slide** but still **not an essay**: it must be skimmable in one pass —
  headline KPIs, a table or two, short framing cards, a caveats footnote.

## Why the HTML is self-contained (and decks are not)

`oc-fn-decks` keeps its Marp theme in the skill **and** as an in-repo working copy, because a
committed deck must re-render from the repo alone and skills are not guaranteed to ship inside a repo.

**Documents sidestep that: the rendered HTML inlines the brand** (CSS tokens **and** the logo SVG),
so a committed `.html` is fully self-contained — it re-renders from the repo alone, needs no external
theme, works offline, and is CSP-safe. In Tier 1 this happens at render time (`--embed-resources`
folds `brand.css` into the output; the logo lives in the Pandoc template); in Tier 2 the template
already carries an inlined copy of `brand.css`. Either way the shareable artifact is standalone.
`theme/brand.css` is the maintained source; the Tier-2 template carries an inlined copy of it (keep
them in sync — re-inline on change).

## The brand (Opencell Charte Graphique 2023 — document variant)

Defined in `theme/brand.css` (the document counterpart to `oc-fn-decks/theme/opencell.css`):

- **Palette (shared with the decks theme — Charte Graphique is the source of truth):** `#CE1428` red ·
  `#FA5757` coral · `#121011` black · `#EDE4E9`/tints · greys. Exposed as CSS custom properties
  (`--oc-red`, …) — never hard-code hexes in a document; use the tokens.
- **Logo:** the **white** logo sits in a full-red header band, inlined as SVG. Same SVGs as the decks
  theme (symlinked in `theme/`).
- **Type:** Montserrat-family intent, but the default stack is **system sans** so local rendering is
  **offline-safe** (no network at print time). For exact brand fonts, embed `@font-face` data URIs in
  `brand.css` — prefer that over a remote `@import` (a self-contained doc should not fetch at render;
  `--embed-resources` only inlines fonts that a stylesheet already pulls in via `url()`).
- **Components** (classes in `brand.css`): `.band` header + `.tag` classification · `h1`/`.sub` title ·
  `.meta` line · `.kpis`/`.kpi` tiles · `h2`/`.hint` section heads · `table` with `.num`, `.del`/`.why`,
  `.solo`/`.track`/`.val` magnitude bars, `.x` pill badge, `tfoot` total · `.cards`/`.card` framings ·
  `.note` caveats footnote. All tuned for A4 print (`@page`, `break-inside`, repeating table headers).
- **Links** are branded by an element rule, not a class: a plain `a` is `--oc-red-ink`, no underline
  (underline on hover). A link **inside a `.x` pill** inherits the pill's colour, so
  `[[INTRD-1234](url)]{.x}` reads white-on-red like any other pill. Never hand-roll a `<style>` block
  for this — the theme carries it, in both tiers.

## File naming — `YYYYMMDD_` prefix, always

Every document this skill produces is named **`YYYYMMDD_<slug>.<ext>`** — an all-numeric date, no
separators, then an **underscore** (not a hyphen), then a kebab-case slug:

```
20260807_ubl-conformance-brief.md      ← source
20260807_ubl-conformance-brief.html    ← render
20260807_ubl-conformance-brief.pdf     ← render
```

- **The date is the document's own date, fixed at creation** — the same date the front matter shows,
  not the date of the latest edit and not the date it was last rendered. **A revision does not rename
  the file:** renaming breaks every link already shared and detaches the file's history. Only a
  genuinely new document gets a new date.
- **The renders inherit it.** `.html` and `.pdf` share the source's basename, so the prefix
  propagates for free — never date a render differently from its source.
- **The underscore is the point.** It separates the date from the slug's own hyphens, so the boundary
  stays readable (`20260807_e-invoicing-brief`, not `20260807-e-invoicing-brief`). Compact
  `YYYYMMDD` sorts chronologically in any file listing. Don't "correct" it to ISO `YYYY-MM-DD` —
  that convention governs dates a *reader* sees, not the file on disk.
- **Existing documents keep their names.** This applies to new ones; do not sweep-rename a repo.
- Throughout this skill, **`<slug>` in a path or a render command means the full dated basename.**

## Tier 1 — authoring in markdown

Start from **`templates/one-pager.md`** (copy it to where the document lives, e.g.
`<initiative>/notes/<slug>.md`). The fixed chrome — header band, logo, title block, CSS — comes from
the Pandoc HTML template; you fill the front matter and the body. Every brand component is reachable
from plain markdown, Pandoc **fenced divs** / **bracketed spans** (both surface as `class="…"` that
`brand.css` styles), or the tiny **`theme/oc-brief.lua`** filter for the two things markdown can't
express cleanly (KPI tiles, magnitude bars):

| Component | Markdown source | Renders as |
|---|---|---|
| Title + red accent | front matter `title:` + `accent:` | `h1` + `.sub` |
| Classification pill | front matter `tag:` | `.band .tag` |
| Meta line | front matter `meta:` (inline `**bold**` OK) | `.meta` |
| Lead sentence | front matter `lead:` | `.lead` |
| Section head + hint | `## Heading [— hint]{.hint}` | `h2` + `.hint` |
| KPI row | `::: kpis` wrapping `::: {.kpi n="87" unit="%" l="label"}` blocks | `.kpis` / `.kpi` |
| Table | a plain pipe table (`:---`, `--:` set column alignment) | brand `table` |
| Row label + detail | `[label]{.del}[grey detail]{.why}` inside a cell | `.del` / `.why` |
| Magnitude bar | `[value]{.bar pct="0-100" sub="range"}` inside a cell | `.solo`/`.track`/`.val` |
| Pill badge | `[n]{.x}` or `[n]{.x .ink}` | `.x` |
| Link | `[text](url)` — including inside a pill, `[[INTRD-1234](url)]{.x}` | branded `a` |
| Framing cards | `::: cards` → `::: card` → `### label` + `::: big` + prose | `.cards` / `.card` |
| Caveats footnote | `::: note` (with `**bold**`, `[term]{.k}`) | `.note` |

**Tier-1 limits — these route to Tier 2:** a table **total row** (markdown tables have no `tfoot`, so a
totals row renders as an ordinary row); bespoke multi-column / mixed grids; anything needing precise
page-break control. Don't invent new fenced-div classes for these — hand-author the page in Tier 2.

## Rendering

### Tier 1 — Markdown → branded HTML (Pandoc) → PDF (Chromium)

```bash
SKILL=~/.claude/skills/oc-fn-briefs
pandoc "<abs>/<slug>.md" \
  --template "$SKILL/templates/one-pager.pandoc.html" \
  --lua-filter "$SKILL/theme/oc-brief.lua" \
  --css "$SKILL/theme/brand.css" --embed-resources --standalone \
  -o "<abs>/<slug>.html"
```

- `--embed-resources` inlines `brand.css` (and any local image) into a single self-contained HTML.
- `--standalone` is implied by `--template`; the template supplies the header band + inlined logo.
- Pass `brand.css` by **absolute path** so it resolves from any working directory.

Then render that HTML to PDF exactly as Tier 2:

### Tier 2 — hand-authored HTML → PDF (Chromium)

Copy `templates/one-pager.html`, fill between the `content start/end` markers, keep the `<style>`.
Then (both tiers use this step):

```bash
chromium --headless=new --no-sandbox --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="<abs>/<slug>.pdf" "file://<abs>/<slug>.html"
```

- `--no-pdf-header-footer` drops Chromium's default date/URL header & page-number footer.
- Paths must be **absolute** with the `file://` scheme.
- The document's own `@page { size:A4; margin:13mm }` controls the page; Chromium honours it.

## Verify before sharing — always

The document analog of the deck overflow check: **render a screenshot and actually look at it** — bar
labels, table wrapping, page breaks, and the header band all need eyeballing.

```bash
chromium --headless=new --no-sandbox --disable-gpu --hide-scrollbars \
  --window-size=860,1400 --screenshot="<abs>/preview.png" "file://<abs>/<slug>.html"
# open/inspect preview.png (scratch — not committed); confirm the PDF page count is what you expect
```

Fix by tightening copy or adjusting a component, not by shrinking the brand type. A 2-page PDF is fine
for a dense note; force one page only if it stays readable.

## Committing (Opencell design repos)

The shareable render (`.pdf`) and its **source** must be tracked, never treated as a throwaway.

In `opencell-features-design` the root `.gitignore` blanket-ignores `*.html`/`*.pdf`/`*.pptx` (deck
render-mirrors). **Do not fight that per-file with `git add -f`** — that silently drops the source the
moment anyone forgets the flag. Instead the repo **carves `notes/` out of the ignore** so branded
documents there track with a plain `git add`:

```gitignore
!**/notes/*.html
!**/notes/*.pdf
!**/notes/*.md
```

So: **keep documents under a `notes/` folder** (or add the equivalent negation for wherever they live),
then commit normally. What is the *source* depends on the tier:

- **Tier 1:** commit the **`.md` (source of truth)** and the **`.pdf` (shareable render)**. The `.html`
  is a self-contained intermediate — commit it too for an openable offline copy, or leave it to
  regenerate from the `.md` + this skill.
- **Tier 2:** commit the **`.html` (layout source)** and the **`.pdf`**. A `.md` content companion, if
  kept, is tracked too — but as words, not a layout mirror (see *The `.md` is a source…* above).

Deck renders under `docs/process/` stay ignored — they really are regenerated from a `.md`.

## Where this skill is used

- **Analysis notes & one-pagers** — e.g. `e-reporting/notes/design-effort-and-ai-leverage.*` (the first
  document built with this skill): a value/effort summary for the sponsor.
- **Briefs & memos** — any short, branded, standalone document that isn't a deck, a Confluence page, or
  a Jira field. Same brand as the decks so every Opencell artifact looks consistent.
