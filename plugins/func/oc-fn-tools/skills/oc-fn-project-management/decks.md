# Phase-2 slide deck — authoring & rendering with the Opencell Marp theme

> Load this when producing the **Phase-2 framing/approval deck** (the one non-`.md` artifact in the
> design phases — see `phases.md` Phase 2). Decks are authored as **Marp Markdown** and rendered
> **one-way** to HTML/PDF/PPTX. The brand theme is the shared **Opencell Marp theme**.

## Where the theme lives (and why it's in two places)

- **Canonical master:** `templates/marp/` in this skill — `opencell.css` + `opencell-logo-red.svg`
  + `opencell-logo-white.svg`. This is the source of truth for the brand theme; update it here.
- **Working copy:** every project repo gets a copy at **`<repo-root>/assets/marp/`**, dropped in at
  Phase-0 scaffolding (`templates/index.md`). Decks reference *that* copy, not the skill.

**Why both:** plugin/skill files are **not guaranteed to ship inside a project repo**. A committed deck
must be reproducible from the **repo alone** (a teammate, another machine, or CI must be able to
re-render). So the theme asset has to be **in-repo**; the skill holds the canonical master and the
scaffold step copies it in. Skill = source of truth + scaffolding; repo = the copy decks actually consume.

## The theme (Opencell Charte Graphique 2023)

Defined in `opencell.css` (`/* @theme opencell */`, extends Marp `default`):

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
  `'© <year> Opencell — Internal · <initiative> — Phase 2'`). Do **not** set a `header:` — the logo is
  the brand mark.
- **Title & closing slides:** `<!-- _class: lead -->` (red background, white text). On those add
  `<!-- _footer: '' -->` so the footer doesn't collide with the white logo, and on the title slide add
  `<!-- _paginate: false -->`.
- **Structure that fits the brand:** one `##` (H2) title per content slide; short bullet phrases;
  tables for inventories/asks (they render full-width with a black header + zebra rows). A red title +
  red closing slide make natural bookends.
- **One-way mirror:** the **`.md` is the source of truth** (commit it, alongside the in-repo
  `assets/marp/` theme). The rendered **HTML/PDF/PPTX are untracked mirrors — never hand-edit them**;
  regenerate from the `.md`. (Same rule as Confluence — `SKILL.md` §3 non-negotiable #5.)

## What a Phase-2 deck quantifies (Claude-authored builds)

When the build is **Claude-authored** (Claude Code writes the specs, code, tests, docs; humans review +
QA), the deck's quantified ask is **delay** and **effort in man-days** — **not euros**.

- **Why not euros.** Authoring runs on a flat-rate Claude subscription (~€0 marginal), so the € build cost
  ≈ the human-review/QA floor anyway — and **pricing / ROI / the P&L is Finance's job, built later**. A
  Phase-2 deck shows **effort + delay + the ask**, not a cost line. Don't put a € figure or a P&L on a
  slide; if asked, defer it explicitly to Finance.
- **Estimate model — authoring + human floor.** Size each work item as two terms:
  - **Authoring** (Claude, working days) — review-ready drafts incl. local build/test iteration. The term
    that compresses; ~€0, but carries a *fraction* of a man-day of human guidance per authoring-day.
  - **Human floor** (working days) — review, CI, integration/debug, migrations, QA. **Non-compressible**;
    scale by **novelty** (mechanical → low; new subsystem → high) and **review style** (AI-assisted light
    < normal < heavy). This is the binding term.
  - **External path** (not in the blocks) — stakeholder decisions, external inputs, release cadence.
    **Dominates calendar**; Claude can't compress it. (See the co-authoring fast-track in `phases.md`.)
- **How to combine — put the right number on each slide:**

  | Slide figure | Formula |
  |---|---|
  | **Delay** | external path + **max**(authoring, floor) + ~25% latency. **Don't sum** authoring + floor — they pipeline. |
  | **Effort (man-days)** | **combine**: (driver-fraction ≈ 0.3–0.5 × authoring) + floor; or authoring + floor as a conservative ceiling. Distinct labor, not pipelined. |
  | **Euros** | out of scope — Finance builds the P&L later. |

- **Relative comparison travels well.** Claude accelerates authoring across options proportionally, so an
  "Option A ≈ 1×, Option B ≈ 2×" framing is robust even when the absolute numbers are soft (±~50% at
  Phase 2). Lead the deck with the recommendation and the relative multiple.

*(Worked example: a Phase-2 deck paired with a macro-estimate note.)*

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

## Scaling note

For a **big feature / Epic**, Phase 2 can collapse to a one-page brief + a sponsor decision and a deck
may be optional (produce one only if presenting beyond the sponsor). When you do make one, use this
theme so every Opencell deck looks consistent.
