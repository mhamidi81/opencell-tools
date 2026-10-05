# Internal-look PPTX lane — a Marp deck as an editable PowerPoint, in its own look

How to turn a deck's `.md` into an **editable `.pptx` that looks like the Marp deck**: the
`opencell` theme, the deck's own `<style>`, custom HTML blocks and all. It is the sibling of the
official-template lane (`pptx.md`), which re-lays the content onto marketing's template instead.

## When to use it

- **An internal deck has to travel as a file.** A block of slides pasted into a colleague's
  PowerPoint (the CODIR Obeya, 2026-10-02, is the case that created this lane), a deck someone
  without Marp will edit, a `.pptx` attachment for an internal meeting.
- **Scope: internal, like the Marp HTML.** Anything leaving the product team — SteerCo, customers,
  partners — stays on the official template (`pptx.md`; the company-wide mandate, the CEO checks).
- **Not a substitute for the source.** The `.md` stays the source. The `.pptx` is a render:
  regenerate it, never hand-edit it. Polishing a copy in PowerPoint is legitimate for a final
  deliverable, but that copy is a fork. Keep it under another name.

## Render

```bash
SKILL=~/.claude/skills/oc-fn-decks
"$SKILL/render-internal-pptx.sh" <deck>.md                 # writes <deck>.pptx next to the deck
"$SKILL/render-internal-pptx.sh" <deck>.md -o out.pptx --qa <dir>   # plus PNGs for review
```

| Option | Effect |
|---|---|
| `-o <out.pptx>` | Output path. Default: next to the deck, same basename. |
| `--theme-set <css>` | Theme. Default: the nearest `assets/marp/opencell.css` walking up to the repo root, as in `render-artifact.sh`. |
| `--keep-centring` | Keep Marp's vertical centring on every slide (see *Deliberate differences*). |
| `--qa <dir>` | Also render the `.pptx` to `slide-N.png` through LibreOffice, with the brand fonts loaded. |

**Requirements:** `node` + `npx`, `python3`, Chromium or Chrome (on `PATH`, or `CHROME_PATH`);
LibreOffice + `pdftoppm` for `--qa`. The first run needs network:

- the pinned npm packages (pptxgenjs 3.12.0, puppeteer-core 24.43.1)
- the brand TTFs

They are cached in `~/.cache/oc-fn-decks/internal-pptx` (`OC_DECKS_CACHE` overrides it). The
theme's Google Fonts `@import` is fetched at every run. Expect about a minute for 25 slides on a
small machine.

## How it works

1. **marp-cli renders the deck** with the bare template, pinned like the Artifact lane
   (`MARP_CLI_VERSION`).
2. **`internal-pptx/measure.js` lays it out in headless Chromium** and records each slide in slide
   pixels: every box, text run, table cell, list paragraph, SVG primitive and image, with its
   computed style. It measures with the **same TTFs that end up embedded**, not the theme's
   webfont, so the widths it records are the ones PowerPoint will draw.
3. **`internal-pptx/build.js` writes native PowerPoint objects** at those positions (pptxgenjs).
4. **`internal-pptx/finish.py` finishes the file:**
   - embeds Montserrat and Playfair Display
   - keeps one `<a:pPr>` per paragraph (pptxgenjs writes one per run, which is invalid and loses
     bullets)
   - sets the theme's hyperlink colour to the deck's link colour

What lands where:

| In the deck | In the PPTX |
|---|---|
| Section background, logo (`section::before`), inset stripes, footer, header, page number, title position and rule | **Slide layouts**, one per distinct combination, and typically 2–8 per deck. Titles go in a real title placeholder. |
| Paragraphs, headings, labels | Text boxes, breaking lines **at the words Chromium broke them**. |
| Lists | Bulleted or numbered paragraphs, with nesting. |
| Tables | Native PowerPoint tables: cell fills, borders, padding, alignment, `colspan`/`rowspan`. |
| Boxes (`background`, `border`, `border-radius`, inset `box-shadow`) | Rectangles or rounded rectangles; a box holding only text becomes one shape with its text. |
| Pseudo-elements | Inline string content joins the text. Block, absolute or inline-block ones (a title pill, a size bar) become shapes. |
| Inline SVG of lines, rects, circles, polylines, polygons and text | Native shapes and text. |
| Other SVG, `<img>`, CSS background images | PNG at 2×, with the element's CSS `filter` and `opacity` applied. |
| `<!-- note: … -->` | Speaker notes. |

## Deliberate differences

- **Slides that open with a title are top-aligned.** Marp centres slide content vertically, so its
  titles move from slide to slide with the amount of content; a PowerPoint deck wants them at one
  position, in one layout. Slides that open with anything else, such as a custom board, keep
  Marp's centring. `--keep-centring` keeps it everywhere.
- **Line breaks are fixed.** The lines break where Chromium broke them (soft breaks), and boxes get
  extra width so PowerPoint never adds a wrap of its own. If you edit the text in PowerPoint,
  those breaks stay put.
- **Leading.** CSS splits a line's extra leading above and below the text; PowerPoint puts it
  above, so every box is lifted by half of it. This was calibrated in LibreOffice to within 1 px
  at line-heights of 1.2 to 2. PowerPoint for the web rendered the Obeya deck as LibreOffice did
  (checked 2026-10-05). Desktop PowerPoint has not been checked.
- **Font weights:** bold or regular only. Semibold (600) becomes Bold, and Playfair Display Black
  (900) becomes Bold. Measurement uses the same substitution, so widths still match.
- **Links are underlined.** PowerPoint always underlines a text hyperlink. Its colour comes from the
  theme, which takes the deck's link colour.
- **Inline-block shapes inside table cells,** such as a size bar after a label, are drawn over the
  table at their measured position. If someone edits the table, they no longer follow it.

## Not reproduced

- Drop shadows (non-inset or blurred `box-shadow`), CSS transforms and rotations, gradients drawn
  in CSS: a gradient survives only as a background image, which becomes a PNG.
- Marp's `![bg]` image backgrounds: their layers become PNGs, but split backgrounds and filters
  are untested.
- Playfair Display is the Latin subset from fontsource: a glyph outside it falls back to another
  font. Montserrat is complete.
- Any text in a font other than Montserrat or Playfair Display is not embedded. It renders only
  where that font is installed.
- Characters missing from Montserrat, such as arrows (→) and check marks, fall back to a system
  font in Chromium and in PowerPoint alike, and may come out at a different size.
- Bullets are drawn in the text's font at 125 %, so they are close to CSS's disc markers but not
  identical.

## Verify — render it, look at it

`--qa <dir>` writes `slide-N.png` from LibreOffice with the brand fonts. Compare them with Marp's own
PNGs (`SKILL.md` § *Overflow*) slide by slide:

- text running past a box, or white text off a dark pill
- missing decorations (stripes, rules, bars, logos)
- text visibly higher or lower than its neighbours
- table cells breaking a word

LibreOffice's verdict on layout is reliable, because the fonts are the real ones. PowerPoint for the
web matched it on the Obeya deck (2026-10-05). For a deck with unusual line-heights, open it in
PowerPoint once before it is shared widely.

## Files

| File | Role |
|---|---|
| `render-internal-pptx.sh` | Entry point: theme lookup, cache, marp-cli, the three steps, `--qa` |
| `internal-pptx/measure.js` | Chromium layout → `model.json` + raster PNGs |
| `internal-pptx/build.js` | `model.json` + the `.md` (speaker notes) → `.pptx` |
| `internal-pptx/finish.py` | Paragraph properties, font embedding, hyperlink colour |
