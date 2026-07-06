---
name: oc-fn-briefs
version: 1.0.1
updated: 2026-07-06T14:20:38+02:00
author: Stéphane Chambrin
description: >
  Author and render branded Opencell DOCUMENTS — one-pagers, analysis notes,
  briefs, memos, short reports — styled with the Charte Graphique 2023 and
  rendered to a print-ready A4 HTML/PDF via headless Chromium. Load this skill
  whenever the user wants a branded one-pager, note, brief, memo, fact-sheet,
  summary sheet, or short standalone document (not slides), or asks to render
  Markdown/HTML content to a branded PDF. Carries the document brand theme
  (`theme/brand.css` + shared logos), a ready-to-fill `templates/one-pager.html`,
  the Chromium render command, and the screenshot verification step. NOT for
  slide decks (that is `oc-fn-decks`), NOT for Confluence pages (that is
  `oc-fn-documentation`), and NOT for Jira functional designs / requirement
  briefs (that is `oc-fn-func-design`).
---

# Opencell documents — branded one-pagers, notes & briefs (HTML → PDF)

This skill covers **how to build a branded Opencell *document*** — a one-pager, analysis note,
brief, memo, or short report. Documents are authored as **self-contained HTML** (brand inlined) and
rendered **one-way** to PDF with **headless Chromium**. It is the non-slide sibling of
`oc-fn-decks`: same Charte Graphique brand, different medium (a flowing A4 page, not slides).

Reach for it when the user says "one-pager", "note", "brief", "memo", "fact-sheet", "summary sheet",
or "make this a branded PDF" — and it's **not** a slide deck, a Confluence page, or a Jira field.

## Audience first — establish it before authoring

**Before writing, settle who the document is for and what it must land** — these set the tone, depth,
and which numbers lead.

- **Not clear? Ask.** Who receives it — sponsor/lead, SteerCo, a customer, engineering, internal? And
  what they most need from a single page.
- **Think it's clear? Confirm.** State your read and get an OK before authoring.
- **Record it** in the `.md` source-of-truth header (see conventions) so later edits keep the target.
- A document is **denser than a slide** but still **not an essay**: it must be skimmable in one pass —
  headline KPIs, a table or two, short framing cards, a caveats footnote.

## Why documents are self-contained (and decks are not)

`oc-fn-decks` keeps its Marp theme in the skill **and** as an in-repo working copy, because a
committed deck must re-render from the repo alone and skills are not guaranteed to ship inside a repo.

**Documents sidestep that entirely: the template inlines the brand** (CSS tokens **and** the logo SVG),
so a committed `.html` is fully self-contained — it re-renders from the repo alone, needs no external
theme, works offline, and is CSP-safe. There is **no in-repo working-copy to scaffold**. `theme/brand.css`
here is the maintained source; the template carries an inlined copy of it.

## The brand (Opencell Charte Graphique 2023 — document variant)

Defined in `theme/brand.css` (the document counterpart to `oc-fn-decks/theme/opencell.css`):

- **Palette (shared with the decks theme — Charte Graphique is the source of truth):** `#CE1428` red ·
  `#FA5757` coral · `#121011` black · `#EDE4E9`/tints · greys. Exposed as CSS custom properties
  (`--oc-red`, …) — never hard-code hexes in a document; use the tokens.
- **Logo:** the **white** logo sits in a full-red header band, inlined as SVG. Same SVGs as the decks
  theme (symlinked in `theme/`).
- **Type:** Montserrat-family intent, but the default stack is **system sans** so local rendering is
  **offline-safe** (no network at print time). For exact brand fonts, embed `@font-face` data URIs in
  the document — prefer that over a remote `@import` (a self-contained doc should not fetch at render).
- **Components** (classes in `brand.css`): `.band` header + `.tag` classification · `h1`/`.sub` title ·
  `.meta` line · `.kpis`/`.kpi` tiles · `h2`/`.hint` section heads · `table` with `.num`, `.del`/`.why`,
  `.solo`/`.track`/`.val` magnitude bars, `.x` pill badge, `tfoot` total · `.cards`/`.card` framings ·
  `.note` caveats footnote. All tuned for A4 print (`@page`, `break-inside`, repeating table headers).

## Authoring conventions

- **Start from the template:** copy `templates/one-pager.html` to where the document lives (e.g.
  `<initiative>/notes/<slug>.html`), fill between the `content start/end` markers, keep the `<style>`.
- **Keep a `.md` source of truth for the text.** Repo convention is markdown-first: commit a
  `<slug>.md` that carries the words (greppable, diffable); the `.html`/`.pdf` carry the *layout*. Put a
  pointer between them (the `.md` links the styled `.html`/`.pdf`; the template header notes the `.md`).
- **One-way mirror:** the `.pdf` is a render of the `.html` — never hand-edit the PDF; regenerate.
- **Locale:** any all-numeric date uses **ISO-8601 (`YYYY-MM-DD`)**; month-name dates (`6 July 2026`)
  are fine. No ambiguous `dd/mm/yyyy`.
- **Density check:** if a section is turning into paragraphs, cut it — a one-pager earns its name by
  what it leaves out.

## Rendering

Render the HTML to PDF with headless Chromium (`google-chrome` also works):

```bash
chromium --headless=new --no-sandbox --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="<abs-path>/<slug>.pdf" "file://<abs-path>/<slug>.html"
```

- `--no-pdf-header-footer` drops Chromium's default date/URL header & page-number footer.
- Paths must be **absolute** with the `file://` scheme.
- The document's own `@page { size:A4; margin:13mm }` controls the page; Chromium honours it.

## Verify before sharing — always

The document analog of the deck overflow check: **render a screenshot and actually look at it** — bar
labels, table wrapping, page breaks, and the header band all need eyeballing.

```bash
chromium --headless=new --no-sandbox --disable-gpu --hide-scrollbars \
  --window-size=860,1400 --screenshot="<abs-path>/preview.png" "file://<abs-path>/<slug>.html"
# open/inspect preview.png (scratch — not committed); confirm the PDF page count is what you expect
```

Fix by tightening copy or adjusting a component, not by shrinking the brand type. A 2-page PDF is fine
for a dense note; force one page only if it stays readable.

## Committing (Opencell design repos)

The document `.html` is a **hand-authored source** — it carries the *layout*, and there is **no
`.md → .html` build step**, so it must be **tracked**, never treated as a throwaway render.

In `opencell-features-design` the root `.gitignore` blanket-ignores `*.html`/`*.pdf`/`*.pptx` (deck
render-mirrors). **Do not fight that per-file with `git add -f`** — that silently drops the source the
moment anyone forgets the flag. Instead the repo **carves `notes/` out of the ignore** so branded
documents there track with a plain `git add`:

```gitignore
!**/notes/*.html
!**/notes/*.pdf
```

So: **keep documents under a `notes/` folder** (or add the equivalent negation for wherever they live),
then commit the `.html` (layout source) + `.pdf` (shareable render) normally. Deck renders under
`docs/process/` stay ignored — they really are regenerated from a `.md`.

**Source model:** the `.md` is the source of the *wording* (greppable, diffable — the repo's md-first
convention); the `.html` is the source of the *layout*; the `.pdf` is the render. Keep a `.md` beside the
document. For a **prose/table-only** note you can skip bespoke HTML and let the `.md` be the sole source
(then HTML/PDF are true renders and need not be tracked); the hand-authored HTML path is for **designed**
one-pagers whose layout markdown cannot express.

## Where this skill is used

- **Analysis notes & one-pagers** — e.g. `e-reporting/notes/design-effort-and-ai-leverage.*` (the first
  document built with this skill): a value/effort summary for the sponsor.
- **Briefs & memos** — any short, branded, standalone document that isn't a deck, a Confluence page, or
  a Jira field. Same brand as the decks so every Opencell artifact looks consistent.
