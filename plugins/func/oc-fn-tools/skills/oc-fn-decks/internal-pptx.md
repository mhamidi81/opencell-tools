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
| Paragraphs, headings, labels | Text boxes, breaking lines **at the words Chromium broke them**, and inside a long word (a URL, a path) at every place Chromium cut it. |
| Lists | Bulleted or numbered paragraphs, with nesting: each nested item starts its text where Chromium does. The marker hangs about one em of the item's font, and never less than the list's widest marker plus a quarter em. An item whose first run is not in its own font (a tag, bold or italic text) opens on a zero-width space in its own font, so its marker keeps the item's size, weight and colour. A list is one text box. A list with shapes drawn over its text (an empty inline box such as a size bar, a pseudo-element bar, an image — not a tag or an inline `code`, which are highlighted text) is **one text box per item** instead, each placed at the y Chromium gave the item (see *Text under shapes is anchored* below): same markers and hang, a numbered item keeps its number (`startAt`), a nested item is placed by its box at level 0, an item with no marker starts at its own text position, and a centred or right-aligned item is laid out over its own content box (the slack split evenly, or on the left), its marker a small box of its own at the list's marker position, where Chromium hangs it whatever the alignment. A list kept whole whose items are all centred (or all right-aligned) takes its wrap slack on both sides (or on the left), so its text lands where Chromium puts it. Text that follows an item's nested list (`<li>a <ul>…</ul> b</li>`) comes after the nested items, as in Chromium: a paragraph of its own with no marker, starting at the item's text position, in either form, and in document order when an item holds several nested lists (`a <ul>…</ul> b <ul>…</ul> c`). Around a nested list, the space between paragraphs is Chromium's gap, so the nested list's own margins count. An empty item keeps its marker. An item that opens directly on its nested list (`<li><ul>…</ul> b</li>`) has its marker on the first nested item's line when drawn one box per item; in a list kept whole it loses its marker (see *Not reproduced*). A right-to-left list (`dir="rtl"`) is always kept whole, with no shapes over it (see *Not reproduced*). |
| Tables | Native PowerPoint tables: cell fills, borders, padding, alignment, `colspan`/`rowspan`. A cell is laid out at Chromium's line pitch (exact line spacing at its line-height), so its lines sit as far apart as in Marp; with the renderer's single spacing they sat about 16 % of a line-height closer under the `opencell` theme. A cell holding a run in a font more than 10 % larger than its own keeps single spacing instead, which makes room for that taller line — at the cell's exact pitch it was drawn over the line above — so its lines sit closer than in Marp (see *Not reproduced*); a cell holding an image keeps exact spacing all the same. Rows keep Chromium's heights. |
| Boxes (`background`, `border`, `border-radius`, inset `box-shadow`) | Rectangles or rounded rectangles; a box holding only text (and inline boxes) becomes one shape with its text. Left-aligned text starts where Chromium starts it, border and padding included (a rounded rectangle's own text inset, 0.29 × its radius, is taken back); the slack against PowerPoint's own wrapping comes off the right inset (the left one for right-aligned text), and off both for centred text. When there is too little padding and border to give any (a fit-content note with a left border and no right padding, a centred label with no padding), the text stops wrapping instead: a line drawn a little wider than in Chromium runs a few pixels past the edge (both edges, when centred) rather than wrapping onto an extra line. Justified text, and text with a break the lane cannot record (`white-space: pre-wrap`, a `::before` / `::after` string with spaces), keeps wrapping and starts up to about 2 px + 1 % of its width nearer its edge to get that slack — in a rounded rectangle, plus the corner's own inset (0.29 × the radius: 7 px more for a 24 px radius). Centred text with such a break keeps wrapping as it is. |
| Inline boxes: an `inline-block` with a fill, a border or side margins (no background image), holding one line of plain text or nothing (a source tag, a pill, a size bar); a plain inline element with a fill or a border (an inline `code`, a `<mark>`, a `<kbd>`), on one line or broken across several | **Highlighted text in the line**, everywhere — paragraphs, lists, boxes, table cells, titles (see *Deliberate differences*): the text keeps its own colour, weight and size, highlighted in the box's fill, and a box with no fill (a dashed tag) is plain text in its colour. The box's side padding is highlighted too, as spaces in the label's own run (one run: a highlight split over two runs shows a seam); its border and side margins are plain spacing, so the text after it starts where Chromium put it. A box broken across lines is highlighted on each of its lines, its padding at its two ends. A translucent fill is composited over the backgrounds behind it, since a highlight has no transparency. A box with no text of its own but a `::before`/`::after` string carries that string. **An empty one** (a size bar, a swatch) is still a shape at its measured position, the text keeping a gap of its width: behind a text box, or over a table cell and over a box that carries its own text; a box whose own text has to be cut for it (*Text under shapes is anchored*) is drawn bare, its text over it in pieces. |
| Code: inline `code`, `kbd`, `samp`, fenced code blocks | In **Courier New** (see *Deliberate differences*). A code block keeps its indentation, and one that Marp shrinks to fit its box (auto-scaling) keeps that size. |
| Images in running text: in a list item, a table cell, a title | Placed at their measured position; the text keeps a gap of their width, as in Chromium. |
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
  those breaks stay put. A box with no room for that extra width has wrapping turned off (see
  *Boxes* above): text typed into it in PowerPoint runs on until you turn *Wrap text in shape*
  back on. **Wide centred boxes have wrapping turned off, so they do not re-wrap when their text
  is edited in PowerPoint:** centred text gets its slack from a quarter of its side padding plus
  its borders, and the floor is 2 px + 1 % of its width, so with 14 px of padding each side and no
  border, any centred box text wider than about 530 px stops wrapping. LibreOffice starts such a
  line at its inset and lets it run past the far edge (the left one when right-aligned; both when
  centred); whether PowerPoint does the same has not been checked.
- **Leading.** CSS splits a line's extra leading above and below the text; PowerPoint puts it
  above, so every box is lifted by half of it. This was calibrated in LibreOffice to within 1 px
  at line-heights of 1.2 to 2. PowerPoint for the web rendered the Obeya deck as LibreOffice did
  (checked 2026-10-05), but a PowerPoint slide show draws exact line spacing tighter (*Text
  under shapes is anchored*, below);
  whether that slide show was desktop PowerPoint or PowerPoint for the web was not recorded.
- **Inline boxes are highlighted text.** Decided by Stéphane on 2026-10-09 (issue #9), for every
  deck the lane renders: an inline box that holds text — a source tag, a pill, an inline `code`,
  a `<mark>`, a `<kbd>` — is not drawn as a shape. Its text stays in the line as a run with a
  text highlight in the box's own colours: the highlight is its CSS fill, the text its CSS
  colour, bold where the CSS says so. That is the « tint » option, chosen so that the PPTX stays
  consistent with the Marp version, which is unchanged. **Why:** a shape drawn over flowing
  text never sat on its words in PowerPoint, which lays text out differently from Chromium and
  LibreOffice — about 96 % of the line pitch, and another first-line offset (next item). In the
  PowerPoint slide shows of the Obeya deck's slide 3 (screenshots at 1920 × 1080, 2026-10-08
  and 2026-10-09), the tag boxes ended up to about 9 px off their words down the list, and still
  about 5 px off within each item once every item was anchored at Chromium's y. LibreOffice lays
  exact spacing out exactly, so no overlay approach can be checked on this machine.
  **What is lost:** the border, the rounded corners and a dashed border, which a highlight cannot
  draw; a box with no fill (the Obeya's `Argos` tag: transparent, dashed) is plain bold text in
  its colour. The highlight is as tall as the label's font (about 1.2 em of it), not as the CSS
  box (its line-height plus its borders): about 3 px shorter for the Obeya's tags. Its width is
  the box's padding box: the padding is made of no-break, thin and hair spaces in the label's
  own run, the combination nearest the CSS padding — within 0.1 px a side for the Obeya's tags
  (0.45 em of padding against 0.443 em of spaces) — and the 1 px border outside it is plain
  spacing. Faces other than Montserrat and Playfair Display get no-break spaces only, so their
  padding is up to half a space off; an inline `code` gets none (a Courier New space, 0.6 em, is
  wider than its 0.4 em padding), so its highlight hugs the glyphs, 0.4 em narrower on each side
  than Marp's box. **Caveats, neither checked:** a PowerPoint version without text-highlight
  support shows the tags as plain coloured text — which versions those are has not been
  verified; and the thin and hair spaces allow a line break after them (the brand fonts lack a
  word joiner), so a renderer that wrapped a line on its own — the lines are broken where
  Chromium broke them, with slack, so it should not — could leave a few pixels of a box's left
  padding at the end of the line before it.
- **Text under shapes is anchored, paragraph by paragraph.** This now concerns the shapes that
  remain in running text — an empty inline box (a size bar), a pseudo-element bar, an image —
  since inline boxes holding text are highlighted text. Observed once, in a PowerPoint slide
  show (screenshot at 1920 × 1080, Obeya slide 3, 2026-10-08; whether desktop PowerPoint or
  PowerPoint for the web was not recorded): with exact line spacing (`spcPts`), PowerPoint's
  line pitch is about **96 %** of the value — 17.1 to 17.2 px for 17.83 px — and the paragraph
  gap about 3.2 px for 3.37; LibreOffice and Chromium give the value exactly. The first line
  also sat 1.3 to 1.8 px higher than in LibreOffice. Shapes are placed at Chromium's
  coordinates, so in a text box the text rose against them by about 0.7 px a line,
  cumulatively: in the « défauts constatés » list (one text box, six items, ten lines), whose
  tags were then shapes, the tag boxes sat right on the first line and the last one's border ran
  through « Jira ». The lane does not tune spacing to either renderer; it stops the drift from
  adding up. **A text with shapes drawn over it is anchored at Chromium's y:** a list becomes
  one text box per item, and a paragraph (or a box's own text) is cut into pieces wherever a
  shape sits two lines or more below the first line of the piece it would be in — shapes on
  lines 1, 3 and 5 make pieces starting at lines 1, 3 and 5. No shape is then more than one line
  below its anchor: at most about 0.7 px of drift at 13.5 px, plus the first-line offset. Even
  so, the 2026-10-09 slide show put tags about 5 px off within an item, which is why tags are no
  longer shapes. Cutting at every line instead was rejected: it would add a text box per line
  for under a pixel.
  **Uneven pitch starts a piece too.** A renderer with exact spacing draws every
  line one line-height below the last, but Chromium does not always: a line holding a larger
  inline font is taller, and a loose item's paragraphs are apart by their margin. Each line's top
  is therefore taken from Chromium's glyphs — as far below an earlier line as its glyphs of the
  same font and size are below that line's — and wherever it is more than 1 px off one
  line-height below the line before, a new piece starts there. A first line made taller by a
  larger font starts where a plain line would have to start for its glyphs to land on
  Chromium's (its larger glyphs then sit about 1.5 px higher than in Chromium in LibreOffice;
  not checked in PowerPoint), and the pieces of such uneven text are lifted as plain lines of
  the block's font. A line set entirely in a larger font (no glyph of the block's font on it) is
  a piece of its own, placed as a plain line of that font, and the line after it starts a new
  piece on its own glyphs. When that font is taller than the line-height, the piece is lifted by
  the signed half-leading — moved down by half the deficit — because LibreOffice's fixed spacing
  puts a deficit above the glyphs as it does extra leading: lifted the usual way, such a line
  (1.6 em at line-height 1.32) sat 8 px above Chromium's; not checked in PowerPoint. Measured in
  LibreOffice (2026-10-09, edge decks e15, e16, e19, when tags were still shapes): a list item
  opening on a 1.6 em word was 12.7 px high on every line, and came within 1.5 px on its first
  line and exact below it; the second paragraph of a loose item was 6 px high, and came exact; a
  line set in 1.6 em between two plain lines, 10 px high and over the line above, came within
  2 px. Justified text and text with unrecorded breaks (`pre-wrap`, a pseudo-element string with
  spaces) are not cut, but they are anchored on their first line: when a larger font made it
  taller, the whole text starts where that line's glyphs need it to, so the lines below are
  right too when the rest of the pitch is even. Text with no shapes over it is never cut.
  **The cost is editability:** such a list is one text box per item, so editing one item in
  PowerPoint does not move the next, and a cut paragraph continues in another text box. **Table
  cells are not cut:** each is its own text body, laid out at Chromium's line pitch unless it
  holds a larger font (*Tables* above). A shape over a cell (an image, an empty inline box) sits at
  Chromium's y, so in a PowerPoint slide show the words beside it would climb about 4 % of a
  line-height for every line above it (by the Obeya slide-3 figure; not checked in a table). In LibreOffice a cell's
  words land on Chromium's lines: within about 1 px under the `opencell` theme, top, middle and
  bottom aligned (edge decks e27, e28, 2026-10-09); about 1–2 px low with Marp's `default`
  theme (edge deck e31).
- **Figures are proportional.** DrawingML has no OpenType features, so tabular figures (Marp's
  default theme sets them on every table) come out proportional, which is narrower in Montserrat.
  The lane measures tables with proportional figures too (only tables: nothing else sets tabular
  figures), so the widths it records are PowerPoint's — but they are not Marp's: narrower
  numbers change the automatic column widths, so **any** cell of such a table, even one without
  a number, may break its lines at other words than the Marp HTML does. A line can then open on
  a `;` or a closing `»` that the source separates by a plain space (Obeya slide 5: `« Must
  have` / `»`), as the Marp HTML can elsewhere; a no-break space (`&nbsp;`) before it keeps them
  together in both. On a slide that
  keeps Marp's vertical centring, the table's new height moves everything: 6 px on the Obeya A3
  slide (2026-10-08).
- **Generic and platform-only fonts become Courier New, Arial or Times New Roman.** A run takes
  the first family of its CSS stack, and a stack that opens on a generic family (`monospace`,
  `sans-serif`, `system-ui`) or one that exists on one platform only (`ui-monospace`,
  `-apple-system`, `SFMono-Regular`, `Menlo`, `Consolas`, `Segoe UI`) names no face PowerPoint or
  LibreOffice can find: each fell back to a proportional font of its own while Chromium measured
  its own fallback, so the text before an inline box came out narrower or wider than measured and
  the box covered the next word. Such a stack is replaced, before measuring, by Courier New (code),
  Arial (sans-serif, system UI) or Times New Roman (serif) — names PowerPoint finds on Windows and
  macOS, and that fontconfig resolves on Linux to the metric-compatible Liberation fonts, so the
  widths agree on every renderer. A face the deck loads itself (`@font-face`) is left alone. With
  the `opencell` theme this touches code only — `code`, `pre`, `samp`, `tt` and `kbd`, whose
  stacks Marp's default theme opens on `ui-monospace` — and the Marp HTML shows the same
  metrics on Linux (Liberation Mono). On a Mac, Marp's HTML draws code in SF Mono, narrower. With
  Marp's own `default` theme every text is affected: its body stack opens on `-apple-system`,
  so the deck comes out in Arial.
- **Font weights:** bold or regular only. Semibold (600) becomes Bold, and Playfair Display Black
  (900) becomes Bold. Measurement uses the same substitution, so widths still match.
- **Links are underlined.** PowerPoint always underlines a text hyperlink. Its colour comes from the
  theme, which takes the deck's link colour.
- **Inline shapes are placed, not anchored.** An empty inline box (a size bar, a swatch), a
  pseudo-element shape such as a size bar after a label, and an image in running text are drawn
  at their measured position; in a table, over the table. If someone edits the text or the
  table, they no longer follow it. Inline boxes holding text are highlighted text, so they move
  with their words.

## Not reproduced

- Drop shadows (non-inset or blurred `box-shadow`), CSS transforms and rotations, gradients drawn
  in CSS: a gradient survives only as a background image, which becomes a PNG.
- Marp's `![bg]` image backgrounds: their layers become PNGs, but split backgrounds and filters
  are untested.
- Playfair Display is the Latin subset from fontsource: a glyph outside it falls back to another
  font. Montserrat is complete.
- Any text in a font other than Montserrat or Playfair Display is not embedded. It renders only
  where that font is installed. Courier New, Arial and Times New Roman, which replace generic
  families (*Deliberate differences*), ship with Windows and macOS.
- Characters missing from Montserrat, such as arrows (→) and check marks, fall back to a system
  font in Chromium and in PowerPoint alike, and may come out at a different size.
- Markers are glyphs at 125 %, close to CSS's markers but not identical: a disc in the text's
  font, a circle or a square in Arial (the brand fonts lack them; a renderer's own fallback can be
  an emoji font about twice as wide, which pushed level-3 text 20 px right in LibreOffice).
  Numbers start at the left of the hang, where CSS aligns them on the right: `9.` and `10.` start
  at the same x.
- An inline-block that holds an image, a block or more than one line is placed on its own, as a
  box, image or text box. The text after it keeps its position, but when the inline-block makes its
  line taller, that line may sit a few pixels off its neighbours — unless the text has shapes
  drawn over it: the taller line then starts a piece of its own, on Chromium's baseline (*Uneven
  pitch starts a piece too*).
- An inline box's text sits on the line's baseline: a `vertical-align` offset on the box is not
  reproduced — about 0.8 px for the Obeya deck's tags (`vertical-align: .08em`).
- **Side margins and padding of a plain inline element with no fill or border** (an `<i>` with
  `margin-left`, a padded `<span>`) are not carried: the text after it sits that much left of
  Chromium's — 4 px for the italic note closing the Obeya legend (`.legend i`). Only inline
  elements that draw a box carry theirs.
- A first family that is named but not installed where the deck is measured or shown (Marp's
  `gaia` theme opens on `Lato`) is not replaced: each renderer falls back on its own.
- **Running text drifts against the shapes left in it** — an empty inline box (a size bar), an
  image. A shape is drawn at Chromium's position, but the text before it is laid out by the
  renderer, and LibreOffice's line widths differ from Chromium's by up to about ±0.5 %, with a
  sign and size that depend on the font size, not steadily. Measured 2026-10-08 on lines of plain
  Montserrat: −0.1 % at 20 px (narrower), −0.5 % at 18 px, +0.5 % at 13.5 px, +0.1 % at 11 px.
  Letter-spaced text drifts more: +0.4 % at 11 px with .06em. Measuring unkerned does not help:
  LibreOffice kerns as Chromium does. PowerPoint draws running text slightly wider still: on
  Stéphane's PowerPoint screenshots of the Obeya deck (slide 4, 2026-10-08), a word before a tag
  box ended 1 to 4 px before it, where LibreOffice left 3 to 5 px. The lane makes no horizontal
  compensation. **Tags no longer drift:** they are highlighted text and move with their words.
  The decision of 2026-10-08 (Stéphane, issue #9: a tag touching the word before it « accepted
  for the Obeya of 2026-10-14; no compensation ») no longer applies — the alternative proposed
  then, tags as highlighted text, was taken on 2026-10-09 (*Deliberate differences*).
- **A right-aligned or centred line that ends on an inline box** sits up to the box's border and
  right margin right of Chromium's (half that when centred) in LibreOffice, which leaves out the
  letter-spacing of a line's last character — here the plain spacing that stands for them: about
  1 px for the Obeya deck's tags (read from the code; it was 3.5 px when the whole right pad was
  that spacing). Not checked in PowerPoint.
- A list item with no marker (`list-style: none`) starts at the list's marker position, not at
  its text position — in a list kept whole; a list drawn one box per item places it right.
- **Justified text stretches into its wrap slack.** A text box is wider than Chromium's lines by
  the slack that keeps PowerPoint from wrapping again (8 % of the width, at least 8 px), and a
  justified line fills that width, so its words sit progressively right of Chromium's, up to the
  slack at the end of a line (edge deck e15, LibreOffice: about 25 px in a 330 px paragraph). Not
  checked in PowerPoint.
- **A centred or right-aligned list kept whole** (one with no shapes over it, which a list with
  tags now is) draws each marker next to its item's text, where Chromium hangs it at the list's
  left edge whatever the alignment. Its text lands where Chromium puts it when every item has
  the same alignment; when centred and left-aligned items are mixed, the text box carries the
  wrap slack on the right only, so a centred item sits half that slack right of Chromium's, a
  right-aligned one all of it (8 % of the list's width, at least 8 px; read from the code). A
  list drawn one box per item places both right.
- **An item that opens directly on its nested list** (`<li><ul>…</ul> b</li>`) loses its marker
  in a list kept whole, which cannot put two paragraphs on one line; Chromium draws it on the
  first nested item's line. A list drawn one box per item draws it there.
- **Numbered nested lists:** their `list-style-type` (lower-roman, lower-alpha) is not
  reproduced; every number is arabic (`1.`). In a list kept whole, when one item holds two nested
  numbered lists with text between them, LibreOffice continues the second list's numbering from
  the first (« 2. » where Chromium starts again); PowerPoint not checked. Drawn one box per item,
  each list restarts.
- **A right-to-left list** (`dir="rtl"`) is drawn left to right, in one text box; its inline
  boxes are highlighted text as anywhere else, but its empty inline boxes and images are not
  drawn: drawn one box per item, they would sit at Chromium's x, far from their place in the
  text.
- **`<sup>` and `<sub>` sit on the baseline.** Marp's default theme (which `opencell` imports)
  moves them by relative positioning (`position: relative; vertical-align: baseline`, then
  `top: -.5em` for `<sup>`, `bottom: -.25em` for `<sub>`), which the lane does not read: they
  keep their 75 % size but not their offset (`x²` reads `x2`).
- **Images carry the render's temporary file path as their alt text** (`descr`, pptxgenjs's
  default), for instance `/tmp/tmp.XXXX/model/raster-3.png`. Harmless on screen; a screen reader
  reads it out.
- **Uneven line pitch is reproduced only under shapes.** Where Chromium makes a line taller (a
  larger inline font), or keeps the paragraphs of one loose item apart by their margin, a renderer
  with exact spacing does not, and text with no shapes over it is not anchored (*Text under shapes
  is anchored*): from that line down it sits higher than in Marp. Measured in LibreOffice
  (2026-10-09, edge deck e15): about 12 px for a paragraph whose first line holds a 1.6 em bold
  word at line-height 1.32, and 6 px for the second paragraph of a loose item in a list kept
  whole (6 px margin); 16 px at Marp's default 20 px text (edge deck e21). The items after such
  an item sit as high as its last paragraph: the gap between the items of a loose list
  (`<li><p>…</p></li>`) is Chromium's, paragraph margins included, so the offset does not add up
  from item to item (e21: 0, 0, 16 and 16.5 px high, where it was 11, 11, 27 and 38 px). **Tags
  and inline code are not shapes** (*Inline boxes are highlighted text*), so text that holds only
  those is not anchored either: an uneven list or paragraph with tags now sits as high as one
  without (e15, e16, e19, measured with tags as shapes, came within 1.5–2 px; they are back to
  the figures above). **A table cell holding a larger font** (a run more than 10 % larger than
  the cell's) is laid out with the renderer's single spacing instead (*Tables* above): its larger
  line gets its room, but its lines sit about 16 % of a line-height closer together than in Marp
  under the `opencell` theme (edge deck v2, 2026-10-09). Other uneven pitch in a cell is laid
  out evenly: a paragraph margin between two lines of a cell is lost, and a line that an inline
  `code` makes 1.5 px taller (edge deck e27) is not. Under shapes, justified text is not cut but is anchored on its first line,
  which covers a taller first line; a justified text made uneven further down (a larger font on
  its third line) still drifts from that line on (by construction; not measured).

## Verify — render it, look at it

`--qa <dir>` writes `slide-N.png` from LibreOffice with the brand fonts. Compare them with Marp's own
PNGs (`SKILL.md` § *Overflow*) slide by slide:

- text running past a box, or white text off a dark pill
- missing decorations (stripes, rules, bars, logos)
- text visibly higher or lower than its neighbours
- table cells breaking a word

LibreOffice's verdict on layout is reliable, because the fonts are the real ones, with one blind
spot: it lays out exact line spacing exactly, so it cannot show PowerPoint's tighter line pitch
(*Text under shapes is anchored*). For that, check the XML: each anchored text box's `<a:off y>`
is Chromium's line top less the leading lift. Inline boxes are text highlights (`<a:highlight>`
in a run's `<a:rPr>`), which LibreOffice 25.2 draws. PowerPoint for the web matched LibreOffice on the
Obeya deck (2026-10-05); a PowerPoint slide show did not (2026-10-08; whether desktop PowerPoint
or PowerPoint for the web was not recorded). For a deck with unusual
line-heights, long texts under shapes or many tags, open it in PowerPoint once before it is shared
widely.

## Files

| File | Role |
|---|---|
| `render-internal-pptx.sh` | Entry point: theme lookup, cache, marp-cli, the three steps, `--qa` |
| `internal-pptx/measure.js` | Chromium layout → `model.json` + raster PNGs |
| `internal-pptx/build.js` | `model.json` + the `.md` (speaker notes) → `.pptx` |
| `internal-pptx/finish.py` | Paragraph properties, font embedding, hyperlink colour |
