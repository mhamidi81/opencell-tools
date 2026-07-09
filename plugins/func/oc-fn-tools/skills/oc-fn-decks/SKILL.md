---
name: oc-fn-decks
version: 1.3.1
updated: 2026-07-09T19:05:00+02:00
author: Stéphane Chambrin
description: >
  Author and render branded slide decks with the Opencell Marp theme (Charte
  Graphique 2023) and/or as editable PowerPoint files on the OFFICIAL Opencell
  PPT template. Load this skill whenever the user mentions a slide deck, a
  presentation, slides, a pitch deck, a SteerCo deck, Marp, `.pptx` /
  PowerPoint, the official template, or rendering a Markdown deck to
  HTML/PDF/PPTX — or asks to build, style, or render an Opencell-branded deck.
  Carries the theme master (`theme/`), the official-template PPTX lane
  (`pptx/` + `pptx.md`: curated pandoc reference, embedded fonts, deck2pptx
  pipeline), the authoring conventions (lead slides, front-matter, one-way
  mirror), the `marp-cli` render command, the overflow check, and the
  24h-time / ISO-date locale non-negotiable. Used for the **Phase-2 approval
  deck** in `oc-fn-project-management` and for standalone strategy / SteerCo
  decks.
---

# Opencell slide decks — authoring & rendering with the Marp theme

This skill covers **how to build an Opencell-branded slide deck**: establishing the audience,
the theme, the authoring conventions, the render command, and the checks. Decks are authored as
**Marp Markdown** and rendered **one-way** to HTML/PDF/PPTX against the shared **Opencell Marp
theme**. Load it whenever you're producing a deck — the Phase-2 framing/approval deck in
`oc-fn-project-management` (see that skill's `phase2-estimate.md` for *what a Phase-2 deck
must quantify*), or a standalone strategy / SteerCo deck.

## Audience first — establish it before authoring

**Before writing any slide, establish who the deck is for and what it must land.** These set the
**tone, depth, and emphasis** of every slide, so settle them *before* authoring — not after.

- **Not clear from context? Ask.** Ask the user who will see or receive the deck — e.g. SteerCo,
  sponsor/lead, engineering, sales, a named customer, an internal all-hands — and what they most
  need from it.
- **Think it's clear? Still confirm.** State your read and get the user's OK before authoring —
  never assume it silently.
- **Record it as metadata** — in the deck's heading comment block (the `<!-- … -->` block right
  after the front-matter), add two keys: `audience:` (who — e.g. SteerCo, sponsor/lead,
  engineering, a named customer) and `focus:` (what they care about / what the deck must land).
  It travels with the `.md` source, so later edits keep the same target.
- **Let them drive the slides:** `focus` fixes *what to emphasize* (business outcomes vs.
  technical design vs. product value); `audience` fixes *tone* (formal SteerCo vs. informal team)
  and *depth* (headline-level for execs; detailed for practitioners).

## Two deliverables — the audience also picks the lane

One `.md` source, two renders:

- **Marp HTML** (this file) — the presentation aid: self-contained, presenter view, 24h clock.
  Sufficient on its own for working sessions and internal product-team decks.
- **Official-template PPTX** (`pptx.md`) — an editable PowerPoint on the official Opencell
  template. **Mandatory deliverable for SteerCo, customers, partners — any deck leaving the
  product team** (company-wide template mandate; the CEO checks). Rendered from the *same*
  `.md` via `pptx/deck2pptx.py`.

The conventions below keep the source valid for both lanes; the PPTX-side deltas (front-matter
metadata, `<!-- note: … -->`, no fenced divs) live in `pptx.md` — read it before authoring a
deck that will ship as PPTX.

## Where the theme lives (and why it's in two places)

- **Canonical master:** `theme/` in this skill — `opencell.css` + `opencell-logo-red.svg`
  + `opencell-logo-white.svg`. This is the source of truth for the brand theme; update it here.
- **Working copy:** every project repo that produces decks gets a copy at
  **`<repo-root>/assets/marp/`**. For an Opencell project this is dropped in at Phase-0
  scaffolding (`oc-fn-project-management` → `templates/index.md`). Decks reference *that* copy,
  not the skill.

**Why both:** skill/plugin files are **not guaranteed to ship inside a project repo**. A committed
deck must be reproducible from the **repo alone** (a teammate, another machine, or CI must be able to
re-render). So the theme asset has to be **in-repo**; this skill holds the canonical master and the
consuming repo keeps a working copy. Skill = source of truth; repo = the copy decks actually consume.

**Scaffolding a repo's working copy:** copy this skill's `theme/` contents into the repo's
`assets/marp/`. In a **shared design repo**, `assets/marp/` lives **once at the shared repo root**
(shared by every initiative), not duplicated per initiative; a per-initiative deck references it via
the relative path to the root.

The same master/working-copy rule applies to the PPTX lane: this skill's `pptx/` is the canonical
master; a repo producing official decks gets a copy at **`<repo-root>/assets/pptx/`**.

## The theme (Opencell Charte Graphique 2023)

Defined in `theme/opencell.css` (`/* @theme opencell */`, extends Marp `default`):

- **Type:** Heading 1 = Playfair Display Black; Heading 2 = Montserrat uppercase + red rule; body =
  Montserrat. Fonts are pulled from Google Fonts at render time via a remote `@import` in
  `opencell.css` → **rendering needs network**; it falls back to system sans otherwise. **Offline
  rendering** (air-gapped CI, no network) needs a self-hosted or inlined-font fallback — replace the
  remote `@import` with locally bundled font files / `@font-face` data URIs in your repo copy of the
  theme; the brand will otherwise degrade to system sans.
- **Palette:** `#CF1428` red · `#FA5757` coral · `#121011` black · `#EDE4E9` pale rose.
- **Logo:** red logo top-right on content slides; **white logo bottom-left on `lead` slides** (which get
  a full-red background, white text). Both embedded as data URIs → the rendered HTML is self-contained.
- Body font is **25px** — decks are for *headlines, not paragraphs*. Keep slides terse (see overflow).

## Authoring conventions

- **Front-matter:** `marp: true`, `theme: opencell`, `paginate: true`, and a `footer:` (e.g.
  `'© <year> Opencell — Internal · <initiative>'`). Do **not** set a `header:` — the logo is
  the brand mark. Add the deck metadata keys **`title:`**, **`subtitle:`** (fold the date in)
  and **`author:`** (`'Name — Role, Opencell'`): Marp ignores them, and the PPTX lane builds
  its cover from them — they must say the same thing as the title slide below.
- **Title & closing slides:** `<!-- _class: lead -->` (red background, white text). On both, add
  `<!-- _footer: '' -->` (so the footer doesn't collide with the white logo) and
  `<!-- _paginate: false -->` (page numbers off on the bookends).
- **Title slide — required content, in this order:** an `#` **H1** (the deck title), an `##` **H2**
  (a one-line subtitle framing the topic or the ask), a **presenter** line (`Name — Role, Opencell`),
  and a **date** (month-name or ISO form per the locale rule). The full title slide:

  ```markdown
  <!-- _class: lead -->
  <!-- _paginate: false -->
  <!-- _footer: '' -->

  # <Deck title>
  ## <One-line subtitle — the topic or the ask>

  <Presenter Name> — <Role>, Opencell
  <Month YYYY>
  ```
- **Section slides:** a mid-deck slide holding **only** a bare `#` H1 (plus the `lead`
  directives) marks a section break — red lead slide in HTML, photo section divider in the
  PPTX lane. Keep them H1-only; any other content belongs on the following `##` slides.
- **Closing — two slides:** first a **`## The ask`** content slide carrying the recap — 2–3
  bullet phrases (for a Phase-2 / SteerCo deck: the recommendation, the ask, next step or
  contact) — then the bookend, a lead slide with **only** an `#` H1 `Thank you`:

  ```markdown
  ## The ask

  - <Key takeaway / the recommendation>
  - <The ask / decision needed>
  - <Next step or contact>

  ---

  <!-- _class: lead -->
  <!-- _paginate: false -->
  <!-- _footer: '' -->

  # Thank you
  ```

  (The recap does not sit on the Thank-you slide itself: content under an H1 breaks the PPTX
  render — see `pptx.md`.)
- **Speaker notes:** an HTML comment `<!-- note: <text> -->` after a slide's content — Marp
  presenter view shows it, and the PPTX lane converts it into a real PowerPoint speaker note.
- **Structure that fits the brand:** one `##` (H2) title per content slide; short bullet phrases;
  tables for inventories/asks (they render full-width with a black header + zebra rows). **A table
  (or image) goes LAST on its slide** — commentary above it, never below: in the PPTX lane, content
  after a table spills onto an untitled continuation slide (see `pptx.md`). A red title +
  red closing slide make natural bookends.
- **One-way mirror:** the **`.md` is the source of truth** (commit it, alongside the in-repo
  `assets/marp/` theme). The rendered **HTML/PDF/PPTX are untracked mirrors — never hand-edit them**;
  regenerate from the `.md`. (Same discipline as a Confluence sync.)

## Locale formatting — non-negotiable, every deck

Slideshows must display **24-hour time** (never AM/PM) regardless of the presenting machine's
browser/OS locale, and must **never** show a date in an ambiguous all-numeric form (`dd/mm/yyyy`,
`mm/dd/yyyy`, and the like). Any all-numeric date uses **ISO-8601 (`YYYY-MM-DD`)**; dates written with a
month name (`16 June 2026`, `Juin 2026`) are unambiguous and fine as-is.

The bespoke presenter-view clock calls `toLocaleTimeString()` with no locale (so it inherits the
browser locale and defaults to AM/PM on en-US), so **force it deck-side**: inject a `<script>` that
overrides no-argument `toLocaleTimeString()` to `fr-FR` 24h, and render with `--html` (the flag that
preserves the script).

## Rendering

Run **from the repo root**, with the **input file FIRST** and **`--theme-set` LAST** (it's an array
flag and will otherwise swallow the input path):

```bash
npx -y @marp-team/marp-cli <path>/<deck>.md \
  -o <path>/<deck>.html \
  --html --theme-set assets/marp/opencell.css
```

- `--html` — pass it always; required when the deck embeds raw HTML or a `<script>` (e.g. the 24h-clock
  override); harmless otherwise.
- Swap `-o ….pdf` or `--pptx` for other formats — **both need a local Chromium** (the HTML render does not).
  Marp's `--pptx` produces image-slides (not editable) and ignores the official template — for the
  **official editable PPTX deliverable**, use the pandoc lane instead: `python3
  assets/pptx/deck2pptx.py <deck>.md` (see `pptx.md`).
- `marp-cli` is invoked via `npx -y` (not usually installed globally).

## Overflow — always check before sharing

Marp does **not** auto-shrink; content past the slide bottom is silently clipped. Verify every slide:

```bash
npx -y @marp-team/marp-cli <path>/<deck>.md --images png --html --theme-set assets/marp/opencell.css
# → <deck>.001.png, .002.png, … — open/inspect each, then delete (scratch, not committed)
```

Keep `--html` here too — without it, an embedded `<script>` (e.g. the 24h-clock override) renders as
literal text on the slide and the PNG looks broken even when the real HTML output is fine. Input file
first, `--theme-set` last (array flag).

If a slide overflows, **tighten the copy** (shorter phrases, fewer words) rather than shrinking the
brand font — the 25px body is intentional. Reserve a deck-local `style:` font override for genuinely
unavoidable density.

## Where this skill is used

- **Phase-2 approval deck** — `oc-fn-project-management` produces one non-`.md` artifact per project
  (the framing/approval deck). This skill owns the *mechanics*; `oc-fn-project-management`'s
  `phase2-estimate.md` owns *what the deck must quantify* (effort in man-days + delay, not euros). For
  a big feature / Epic the deck may be optional — produce one only if presenting beyond the sponsor;
  when you do, use this theme so every Opencell deck looks consistent.
- **Standalone decks** — strategy, SteerCo, module-map, or any internal Opencell presentation. Same
  theme, same conventions; there is no Phase-2 estimate content to worry about.
