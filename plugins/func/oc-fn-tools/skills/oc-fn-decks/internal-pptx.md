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

**It refuses a deck with a bare Jira key** (`SKILL.md` § *Authoring conventions*): the linker,
`oc-fn-briefs/jira_links.py`, must sit beside this skill, as it does in `oc-fn-tools`.

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
   - embeds Montserrat and Playfair Display (Playfair Display for list discs too)
   - keeps one `<a:pPr>` per paragraph (pptxgenjs writes one per run, which is invalid and loses
     bullets), and gives each list marker its face and a valid size (see *Not reproduced*,
     markers)
   - removes the alt text pptxgenjs gives an image that has none: its temporary file path
   - sets the theme's hyperlink colour to the deck's link colour

What lands where:

| In the deck | In the PPTX |
|---|---|
| Section background, logo (`section::before`), inset stripes, footer, header, page number, title position and rule | **Slide layouts**, one per distinct combination, and typically 2–8 per deck. Titles go in a real title placeholder. |
| Paragraphs, headings, labels | Text boxes, breaking lines **at the words Chromium broke them**, and inside a long word (a URL, a path) at every place Chromium cut it. Chromium's lines are told apart by the baselines of their glyphs, so a word in a larger font stays on its line with the words after it (until 2026-10-13 they were told apart by glyph tops, and « Grande ligne » broke after a 1.8 em word: edge decks v1, v2). An empty line made by forced breaks (`a<br><br>b`, a blank line in a code block) stays in the text, as a line holding a zero-width space, in a text box, a list item and a table cell alike; until 2026-10-13 consecutive breaks collapsed into one: the empty line was lost in a table cell (edge deck v1) and in a code block, and a paragraph got it back only by being cut there into two text boxes (edge deck e22). Text transforms are Chromium's own: `capitalize` capitalizes where Chromium does — after a space, a `/`, a `.` or a `-`, not after an apostrophe or an underscore — and a word broken across lines keeps one capital (edge deck e12: every piece of a broken URL got one until 2026-10-13). |
| Lists | Bulleted or numbered paragraphs, with nesting: each nested item starts its text where Chromium does. Numbers keep their list's style — `lower-roman`, `upper-roman`, `lower-alpha`, `upper-alpha` (Marp's default theme, which `opencell` imports, numbers a nested `<ol>` in lower-roman and the level below in lower-alpha) — and the hang is measured on the marker drawn (`iv.`, not `4.`). The marker hangs about one em of the item's font, and never less than the list's widest marker plus a quarter em. An item whose first run is not in its own font (a tag, bold or italic text) opens on a zero-width space in its own font, so its marker keeps the item's size, weight and colour. A list is one text box. A list with shapes drawn over its text (an empty inline box such as a size bar, a pseudo-element bar, an image — not a tag or an inline `code`, which are highlighted text), with an item whose line pitch is uneven (a line in a larger font, a loose item's paragraphs), with a centred or right-aligned item, or with an item that opens directly on its nested list, is **one text box per item** instead, each placed at the y Chromium gave the item (see *Text under shapes is anchored* below): same markers and hang, a numbered item keeps its number (`startAt`), a nested item is placed by its box at level 0, an item with no marker starts at its own text position, and a centred or right-aligned item is laid out over its own content box (the slack split evenly, or on the left), its marker a small box of its own at the list's marker position, where Chromium hangs an outside marker whatever the alignment; an inside marker (`list-style-position: inside`) is the box's own, drawn next to its centred or aligned text, as Chromium draws it. An item's `::before` string (an arrow in a `list-style: none` list) opens its text. An item with no marker starts at its own text position, kept whole or not. Text that follows an item's nested list (`<li>a <ul>…</ul> b</li>`) comes after the nested items, as in Chromium: a paragraph of its own with no marker, starting at the item's text position, in either form, and in document order when an item holds several nested lists (`a <ul>…</ul> b <ul>…</ul> c`). Around a nested list, the space between paragraphs is Chromium's gap, so the nested list's own margins count. An empty item keeps its marker. An item that opens directly on its nested list (`<li><ul>…</ul> b</li>`) has its marker on the first nested item's line, as in Chromium. A right-to-left list (`dir="rtl"`) is right-to-left paragraphs — markers right of the text, items right-aligned, nested items indented from the right — always in one text box, with no shapes over it, and it does not wrap again (see *Not reproduced*). |
| Tables | Native PowerPoint tables: cell fills, borders, padding, alignment, `colspan`/`rowspan`. Rows keep Chromium's heights. **A cell's lines sit on Chromium's baselines, line by line:** each takes exact line spacing, measured from the line before, so a cell is laid out like Marp's without being cut (it is one text body). A line that needs more than its line-height — after a paragraph or list-item margin, after an empty line (`<br><br>`) — keeps it and gets the rest as space before; a line holding a larger font gets a line spacing of its own, so the cell's paragraph is split there. Unevenness under 2 px (an inline `code` that makes its line 1.5 px taller) keeps the line-height, as for text with no shapes over it. The top and bottom margins are not the CSS padding: they place the text block where Chromium centres or aligns it. A cell with no glyph recorded on any line (a `::before` icon alone, a `<sup>` alone) keeps its CSS padding as margins and is aligned by the renderer instead; in a cell whose first lines alone have none (an icon, a `<sup>` or an image over a caption), those lines are placed above the first line that has glyphs — by that line's own box (a KPI figure's is taller than a line-height), then a line-height each — so the block keeps Chromium's alignment; a top-aligned cell keeps its content box's top instead, which also keeps a paragraph margin between the two, unless its glyph-less line holds a larger run (a 40 px icon). A glyph-less line after a paragraph margin loses the margin. A line with no glyph of the cell's font (an inline `code` alone, a tag alone) opens on a zero-width space in that font, the CSS strut: LibreOffice lays out Courier New with a smaller descent than Chromium — by the font's tables, its OS/2 typo descent, 0.19 em, where Chromium takes the hhea one, 0.30 em, which fits the offset measured — and such a cell sat 2–3 px low (the `ocskills` deck, slide 2). **A list in a cell** is bulleted or numbered paragraphs: each item starts where Chromium starts its text, moved left with the rest of the cell's text by the trimmed side padding, and its marker hangs the list's hang, or near it — pptxgenjs ties an item's hang to its left margin (a whole fraction of it, one per indent level), so the item takes the level whose hang comes nearest without being narrower than the list's widest marker plus a quarter em: 15 px for a 15.75 px hang in edge deck v2, but the whole 30 px for a numbered list whose « 2. » needs 17 px, its numbers then at the cell's text edge (a test table, 2026-10-13). Until 2026-10-13 a cell had one line spacing: paragraph margins were lost, a list's markers were not drawn, and a cell holding a larger font fell back to single spacing, its lines about 16 % of a line-height closer than in Marp and its row 5 px taller (edge deck v2: 104 px for 99). Measured in LibreOffice (2026-10-13, against Chromium laid out at device scale 2, as the lane measures), over the 27 slides with tables in the 49 regression decks, top, middle and bottom aligned: a cell's line tops are 0.8 px from Chromium's on average, at most 1.3 px on a slide (1.1 px and 2.8 px before); 16 slides came closer, and none moved away by more than a pixel. A line in a larger font (v2), a cell holding only an inline `code` (`ocskills`, slide 2) and Marp's `default` theme (e31) are within 2 px. |
| Boxes (`background`, `border`, `border-radius`, inset `box-shadow`) | Rectangles or rounded rectangles; a box holding only text (and inline boxes) becomes one shape with its text. Left-aligned text starts where Chromium starts it, border and padding included (a rounded rectangle's own text inset, 0.29 × its radius, is taken back); the slack against PowerPoint's own wrapping comes off the right inset (the left one for right-aligned text), and off both for centred text. When there is too little padding and border to give any (a fit-content note with a left border and no right padding, a centred label with no padding), the text stops wrapping instead: a line drawn a little wider than in Chromium runs a few pixels past the edge (both edges, when centred) rather than wrapping onto an extra line. Justified text, and text with a break the lane cannot record (`white-space: pre-wrap`, a `::before` / `::after` string with spaces), keeps wrapping and starts up to about 2 px + 1 % of its width nearer its edge to get that slack — in a rounded rectangle, plus the corner's own inset (0.29 × the radius: 7 px more for a 24 px radius) — but never over that edge's border. Justified text, whose lines are stretched across whatever slack they get, gets only the slack they need: that floor, less the room Chromium's lines leave before it stretches them; and its text area never reaches under the far border, which hid the last glyphs of each line (edge deck e12, slide 3: an 8 px right border). Centred text with such a break keeps wrapping as it is. |
| Inline boxes: an `inline-block` with a fill, a border or side margins (no background image), holding one line of plain text or nothing (a source tag, a pill, a size bar); a plain inline element with a fill, a gradient or a border (an inline `code`, a `<mark>`, a `<kbd>`, a span underlined by a border), on one line or broken across several | **Highlighted text in the line**, everywhere — paragraphs, lists, boxes, table cells, titles (see *Deliberate differences*): the text keeps its own colour, weight and size, highlighted in the box's fill, and a box with no fill (a dashed tag) is plain text in its colour. The box's side padding is highlighted too, as spaces in the label's own run (one run: a highlight split over two runs shows a seam; a decorated box — an `<ins>`, a filled `<u>` or `<del>` — is three, its padding apart, with no seam seen in LibreOffice); its border and side margins are plain spacing, so the text after it starts where Chromium put it. A box broken across lines is highlighted on each of its lines, its padding at its two ends. A translucent fill is composited over the backgrounds behind it, since a highlight has no transparency; over a background image (a Marp `_backgroundImage` gradient), over that image's mean colour under the box, sampled from its raster (edge decks n1 and v1, 2026-10-13: the highlights came out pale over a dark gradient, their white text unreadable). A plain inline element filled with a gradient is highlighted the same way, in the gradient's mean colour, sampled from a raster of its own background: the gradient itself is lost, but its text stays readable (edge deck n1, 2026-10-13: such a span was plain text, and white text on it vanished). A gradient that covers its box only by its colour stops (a marker sweep, `transparent 60%, #ffd23f 60%`) is a covering one: its mean colour tints the whole box. Such a span stays plain text, as before, when its gradient does not cover it (a gradient sized to a stripe: a gradient underline, a marker sweep) or is translucent over a background image (two layers that one colour cannot stand for: over a dark `_backgroundImage`, a near-white highlight made light text unreadable), and so does a background image with a `url()`. A box drawn by **its bottom border alone** is underlined instead, padding included, in the border's colour: a heavy line from 1.5 px, dashed or dotted as the border (edge deck e25, 2026-10-13: the line was lost). An underline runs just under the baseline, where CSS draws the border below the descenders, under the padding box: in LibreOffice, a 3 px line about 2.5 px higher than the 2 px border for the edge deck's 25 px text (not checked in PowerPoint). Linked text in an `inline-block` (a tag in a link, a link in a tag) keeps its link, but is underlined only where its own CSS says so (*Links are underlined*). A box with no text of its own but a `::before`/`::after` string carries that string. **An empty one** (a size bar, a swatch) is still a shape at its measured position, the text keeping a gap of its width: behind a text box, or over a table cell and over a box that carries its own text; a box whose own text has to be cut for it (*Text under shapes is anchored*) is drawn bare, its text over it in pieces. |
| Side margins and padding of a plain inline element that draws no box (an `<i>` with a `margin-left`, a padded `<span>`) | Plain spacing in the line, before and after its text, so the text after it starts where Chromium put it (the italic note closing the Obeya legend, 4 px). Negative margins are not reproduced. |
| Superscripts and subscripts: `<sup>`, `<sub>`, and any text an inline element raises or lowers (`vertical-align: super`, `sub`, a length or a percentage; a relative `top` or `bottom`) | Runs with a **baseline offset** (`baseline` in the run properties), set to Chromium's shift: Marp's default theme raises a `<sup>` by half its em and lowers a `<sub>` by a quarter, by relative positioning. A renderer draws an offset run smaller on its own — LibreOffice at 58 % of its size — so the run's size is written that much larger, for its glyphs to keep Chromium's size: a 10 px `<sup>` shows as 13 pt in PowerPoint's font size box. Measured in LibreOffice (edge decks e14, e16, e20, 2026-10-13): each `<sup>` and `<sub>` sits at Chromium's offset from its line, to the pixel, where they sat on the baseline, 3 to 5 px off; the line holding one moves up by 1 or 2 px (*Not reproduced*). An offset of more than 0.6 of the run's own size (a word moved by `position: relative`) is drawn on the baseline instead, as before 2026-10-13: LibreOffice lifts a line holding an offset run by its extra descent, and a word lowered by 0.85 em pulled its line onto the one above; its moved baseline is still read to find the lines. An inline box's own `vertical-align` (a tag) is not read. |
| Code: inline `code`, `kbd`, `samp`, fenced code blocks | In **Courier New** (see *Deliberate differences*). A code block keeps its indentation, and one that Marp shrinks to fit its box (auto-scaling) keeps that size. |
| Images in running text: in a list item, a table cell, a title | Placed at their measured position; the text keeps a gap of their width, as in Chromium. |
| Pseudo-elements | Inline string content joins the text. Block, absolute or inline-block ones (a title pill, a size bar) become shapes. |
| Inline SVG of lines, rects, circles, polylines, polygons and text | Native shapes and text. |
| Other SVG, `<img>`, CSS background images | PNG at 2×, with the element's CSS `filter` and `opacity` applied. Its alt text is the `<img>`'s `alt`, or the SVG's `aria-label` or `<title>`; a background image (a logo, a `![bg]`) has none, as in the HTML. |
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
  back on. So has a right-to-left list (*Not reproduced*). **Wide centred boxes have wrapping
  turned off, so they do not re-wrap when their text is edited in PowerPoint:** centred text gets its slack from a quarter of its side padding plus
  its borders, and the floor is 2 px + 1 % of its width, so with 14 px of padding each side and no
  border, any centred box wider than about 530 px stops wrapping when its text has two lines or
  more, whatever their width. LibreOffice starts such a
  line at its inset and lets it run past the far edge (the left one when right-aligned; both when
  centred); whether PowerPoint does the same has not been checked.
- **Leading.** CSS splits a line's extra leading above and below the text; PowerPoint puts it
  above, so every box is lifted by half of it. This was calibrated in LibreOffice to within 1 px
  at line-heights of 1.2 to 2. PowerPoint for the web rendered the Obeya deck as LibreOffice did
  (checked 2026-10-05), but a PowerPoint slide show draws exact line spacing tighter (*Text
  under shapes is anchored*, below);
  whether that slide show was desktop PowerPoint or PowerPoint for the web was not recorded.
  **A line-height at or below the font size** (a tight paragraph at 1, a title at 0.85) leaves a
  deficit under the text's natural height (about 1.22 em in Montserrat, 1.33 em in Playfair
  Display), which LibreOffice also puts above the glyphs, where CSS puts half: its fixed spacing sets a line's baseline one line-height less
  about 0.21 em below the line's top, whatever the line-height (Montserrat and Playfair
  Display, 13.5 to 40 px, measured 2026-10-13). Such text is moved down by half the deficit, in
  text boxes, lists, and top-aligned shapes (table cells are placed on Chromium's baselines
  instead, *Tables*). Until 2026-10-13 it was lifted by
  that half, and came out nearly a whole deficit above Chromium's in LibreOffice: on a scratch
  deck, 2 px for 13.5 px text at a line-height of 1, 6 px at 0.8 and 18 px, 10 px for a 30 px
  title at 0.85. It now lands 0 to 2 px low, and the paragraph at a line-height of 1 on edge
  deck e16 within 2 px instead of 3 to 4 px. That residue is not the deficit's: with 0.21 em
  under the baseline where both brand fonts have a 0.25 em descent, LibreOffice's baselines
  come out about 0.04 em below Chromium's in any text (derived from those measurements): under
  1 px at body sizes, about 2 px in a 52 px `h1`. **A smaller deficit keeps the lift**, which
  leaves its text high by the deficit less those 0.04 em: Marp's `h1` (Playfair Display at 1.25)
  2 to 3 px high (edge decks e26, ocskills), an inline-block at 1.1 about 1 px (edge deck d4).
  Moved down instead, such an `h1` came out as far below, and one holding a tag 5.5 px low
  instead of 0.5 (edge deck n1). **Centred text in a shape** is neither lifted nor moved for a
  deficit, only for extra leading: moved down, it came out no closer (boxes 1 to 2 px high became
  1 px low). None of this was checked in PowerPoint.
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
  its colour. A border on the bottom side alone is the exception, drawn as an underline; and a
  gradient fill on a plain inline element comes out as one colour, its mean. The highlight is as
  tall as the label's font (about 1.2 em of it), not as the CSS box (its line-height plus its
  borders): about 3 px shorter for the Obeya's tags. Its width is
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
  piece on its own glyphs. When that font is taller than the line-height, the piece is moved
  down by half the deficit, like any text whose line-height is at or below its font size
  (*Leading* above): lifted by that half instead, such a line (1.6 em at line-height 1.32) sat
  8 px above Chromium's; not checked in PowerPoint. Measured in
  LibreOffice (2026-10-09, edge decks e15, e16, e19, when tags were still shapes): a list item
  opening on a 1.6 em word was 12.7 px high on every line, and came within 1.5 px on its first
  line and exact below it; the second paragraph of a loose item was 6 px high, and came exact; a
  line set in 1.6 em between two plain lines, 10 px high and over the line above, came within
  2 px. Justified text and text with unrecorded breaks (`pre-wrap`, a pseudo-element string with
  spaces) are not cut, but they are anchored on their first line: when a larger font made it
  taller, the whole text starts where that line's glyphs need it to, so the lines below are
  right too when the rest of the pitch is even.
  **Uneven text with no shapes over it is anchored too** (since 2026-10-13). It is cut only where
  its pitch drifts: where a line lands more than 2 px from where an even pitch from the piece's
  first line would put it — a line in a larger font, a loose item's paragraph margin, a line
  beside a tall inline-block — and at a line set in a larger font; a first line made taller by
  a larger font is anchored on its glyphs as above. Smaller unevenness adds up to 2 px before
  it cuts, so a line that an inline `code` makes about 1.5 px taller does not split a paragraph
  on its own; steps under a pixel that keep adding up past 2 px cut too. A list holding such an
  item is drawn one box per item, and a box whose own text is so anchored (a card opening on a
  large figure) is drawn bare, its text in a text box over it, as under shapes. Measured
  in LibreOffice (2026-10-13), the 13 slides of the 49 regression decks that this touches all
  came closer to Chromium's layout; on edge deck n2, lines that sat 10 to 15 px high, over the
  line above, came within 1–2 px. Right-to-left lists are still not cut.
  **The cost is editability:** such a list is one text box per item, so editing one item in
  PowerPoint does not move the next, and a cut paragraph continues in another text box. **Table
  cells are not cut:** each is its own text body, its lines placed one by one by their exact
  line spacing and space before (*Tables* above), which LibreOffice lays out exactly. A shape
  over a cell (an image, an empty inline box) sits at Chromium's y, so in a PowerPoint slide
  show the words beside it would climb about 4 % of a line-height for every line above it (by
  the Obeya slide-3 figure; not checked in a table). In LibreOffice a cell's words land within
  about 1 px of Chromium's lines, 2 px at most (*Tables* above).
- **Figures are proportional, tables are laid out with Marp's.** DrawingML has no OpenType
  features, so tabular figures (Marp's default theme sets them on every table) come out
  proportional, which is narrower in Montserrat. The lane measures tables with the deck's own
  tabular figures, so column widths, line breaks and row heights are Marp's (checked on the 20
  edge decks with tables, 2026-10-13: every cell breaks at Marp's words and every column is
  within 0.2 px of Marp's width); a line holding figures then ends a little short of Marp's in
  the PPTX, and never wraps again since its breaks are fixed. A shape placed after a number in a
  cell (an image, an empty inline box) sits at Chromium's x, so the text before it ends that much
  short of it. Until 2026-10-13 tables were measured with proportional figures: the narrower
  numbers changed the automatic column widths, and cells broke at other words than the Marp HTML
  (the Obeya A3's row 6 lost a line, a number split from its unit on slide 4).
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
  **A named family that is not installed is skipped the same way** (since 2026-10-13): Chromium
  passes over it to the next family it has, while the PPTX would name the missing one and each
  renderer would substitute its own (a test deck, 2026-10-13: in LibreOffice, a `"Gill Sans",
  serif` paragraph took a third line and ran into the next paragraph). Such a stack falls back
  to the first family later in it that every renderer resolves alike: a face the deck loads, or a
  generic or platform-only family, replaced as above (`Lato, "Avenir Next", Avenir, "Trebuchet
  MS", "Segoe UI", sans-serif` becomes Arial). Other named families are skipped, installed or
  not: one installed where the deck is measured (Trebuchet MS here) need not be where the PPTX is
  opened. A generic family PowerPoint has no face for (`cursive`, `fantasy`, `emoji`, `math`)
  becomes Times New Roman too when Chromium resolves it; one it does not resolve is skipped, as
  Chromium skips it (`math, Montserrat` stays Montserrat). A stack with neither becomes Times New Roman, Chromium's
  default face. Whether a family is installed is read from Chromium itself, by measuring a sample
  in it in front of two different generic families: `document.fonts.check()` answers true for
  any family with no `@font-face`.
- **Font weights:** bold or regular only. Semibold (600) becomes Bold, and Playfair Display Black
  (900) becomes Bold. Measurement uses the same substitution, so widths still match.
- **Links are underlined only where CSS underlines them,** as in Marp, where the `opencell` theme
  underlines none (Stéphane, 2026-10-13). pptxgenjs underlines every text hyperlink it is given no
  underline for, so every other linked run is written with no underline (`u="none"`). That
  includes linked text in an inline box (a tag, a pill): a tag in a link, a link in a tag, since CSS
  does not carry a link's underline into an inline-block. Until 2026-10-13 a link was underlined
  whatever its CSS said, and before that day's earlier fix a tag in a link had its highlighted
  padding underlined too (edge decks n1 and v1). LibreOffice draws `u="none"` so; whether
  PowerPoint honours it on a hyperlink has not been checked. A plain inline box in a link (a
  `<mark>`, an inline `code`) is underlined with the link when CSS underlines it, its highlighted
  padding included; outside a link, a highlighted padding is underlined only by a bottom border,
  and never struck through. An inline-block placed on its own (a gradient block, one holding an
  image or several lines) follows the same rule. An
  underline or a line-through reaches the text of an element's descendants, as CSS draws it (a
  `<b>` in an underlined link) and to its `::before`/`::after` strings, up to an inline-block, a
  float or a positioned box. A header or footer keeps an underline or a line-through only when it
  covers all its text (`~~Brouillon~~`); otherwise it is one run in its first run's format. **Colour:** each linked run
  carries its own colour and the Office 2019 hyperlink-colour extension (`ahyp:hlinkClr
  val="tx"`, written by pptxgenjs), which asks PowerPoint to draw that colour, so a tag in a link
  keeps its own. A PowerPoint that predates the extension draws every link in the theme's
  hyperlink colour instead, which `finish.py` sets to the deck's most frequent link colour,
  leaving out highlighted runs (tags in links), unless they are the only links: there, a tag in
  a link takes the link's colour.
  Neither checked in PowerPoint; LibreOffice draws each run's own colour.
- **Inline shapes are placed, not anchored.** An empty inline box (a size bar, a swatch), a
  pseudo-element shape such as a size bar after a label, and an image in running text are drawn
  at their measured position; in a table, over the table. If someone edits the text or the
  table, they no longer follow it. Inline boxes holding text are highlighted text, so they move
  with their words.
  Empty inline boxes stay shapes by decision (Stéphane, 2026-10-13): drawing them as
  highlighted spaces would widen the 2026-10-09 rule for tags to boxes with no text, and no
  current deck uses them. Their drift is described under *Running text drifts* below.

## Not reproduced

- Drop shadows (non-inset or blurred `box-shadow`), CSS transforms and rotations, gradients drawn
  in CSS: a gradient survives only as a background image, which becomes a PNG, or, on a plain
  inline element, as a highlight in its mean colour.
- Marp's `![bg]` image backgrounds: their layers become PNGs, but split backgrounds and filters
  are untested.
- Playfair Display is the Latin subset from fontsource: a glyph outside it falls back to another
  font. Montserrat is complete.
- Any text in a font other than Montserrat or Playfair Display is not embedded. It renders only
  where that font is installed. Courier New, Arial and Times New Roman, which replace generic
  families (*Deliberate differences*), ship with Windows and macOS.
- Characters missing from Montserrat, such as arrows (→) and check marks, fall back to a system
  font in Chromium and in PowerPoint alike, and may come out at a different size.
- **Markers are glyphs at the text's size**, close to CSS's markers but not identical. Chromium
  draws a disc, a circle or a square as a shape about a third of the font's ascent across (4 px
  at 13.5 px, 8 px at 24 px); the lane draws a disc as Playfair Display's bullet, 0.285 em across
  and about as high above the baseline as Chromium's (embedded with the deck), and a circle or
  a square as Arial's, about 0.24 em (the brand fonts lack them; a renderer's own fallback can be
  an emoji font about twice as wide, which pushed level-3 text 20 px right in LibreOffice).
  Measured in LibreOffice 26.2 against Chromium (a test deck, 2026-10-13), a disc beside
  Montserrat text is within about 1 px of Chromium's width and centre from 11 to 24 px (it was
  Montserrat's bullet at 125 %, half to two thirds of Chromium's width); beside Playfair Display
  text, whose taller ascent makes Chromium's disc larger, it is about 2 px narrower and 2 px
  lower at 24 px. Circles and squares are about three quarters of Chromium's width, a little
  smaller than at the former 125 %. **No marker is scaled:** the size is written `<a:buSzTx/>`. The
  transitional schema of ISO/IEC 29500-4:2016 types `<a:buSzPct val>` as a percentage string
  (`"125%"`), which fails on the thousandths PowerPoint itself writes (`"125000"`, the form of
  ECMA-376's first edition; known, not checked here), while LibreOffice draws only the
  thousandths at their size —
  `"125%"` and `<a:buSzPts>` come out at the text's size — so no scaled size is both valid and
  drawn alike. Not checked in PowerPoint: whether it draws a bold first run's marker in Playfair
  Display Bold (LibreOffice draws it regular). Numbers start at the left of the hang, where CSS
  aligns them on the right: `9.` and `10.` start
  at the same x, and so do `i.` and `ii.`.
- An inline-block that holds an image, a block or more than one line is placed on its own, as a
  box, image or text box. The text after it keeps its position; when the inline-block makes its
  line more than 2 px taller, that line starts a piece of its own, on Chromium's baseline
  (*Uneven pitch starts a piece too*, and *Uneven text with no shapes over it is anchored too*);
  under that, it sits up to 2 px off its neighbours.
- An inline-block's own `vertical-align` (a tag) is not reproduced: its text sits on the line's
  baseline — about 0.8 px for the Obeya deck's tags (`vertical-align: .08em`). A plain inline
  element's is (*Superscripts and subscripts*), its highlight then written at the enlarged size
  of an offset run, so taller.
- **A web font the deck or its theme loads is measured in it, but not embedded.** Marp's `gaia`
  theme imports `Lato` and `Roboto Mono` from fonts.bunny.net: the measure uses them and the PPTX
  names them, so they render only where they are installed (see *Any text in a font other than
  Montserrat or Playfair Display* above); elsewhere each renderer substitutes its own and the
  lines no longer fit. Likewise a family installed where the deck is measured but not where it
  is shown (`Noto Sans Mono` on a Linux box, absent from Windows). A named family that is not
  installed at all is skipped (*Deliberate differences*).
- **Running text drifts against the shapes left in it** — an empty inline box (a size bar), an
  image. A shape is drawn at Chromium's position, but the text before it is laid out by the
  renderer, and LibreOffice's line widths differ from Chromium's by about ±0.5 % or more, with a
  sign and size that depend on the font size, not steadily. Measured 2026-10-08 on lines of plain
  Montserrat: −0.1 % at 20 px (narrower), −0.5 % at 18 px, +0.5 % at 13.5 px, +0.1 % at 11 px.
  Letter-spaced text drifts more: +0.4 % at 11 px with .06em. On edge deck h1's size bar
  (LibreOffice, 2026-10-13), the 257 px of 18 px text before the bar on its line came out 2 px
  (0.8 %) narrower, so the word after it sat 3 px from the bar instead of 5 px; the bar itself was
  at Chromium's x, and in a table cell of the same deck the gap was right. Measuring unkerned
  does not help: LibreOffice kerns as Chromium does. PowerPoint draws running text slightly wider
  still: on Stéphane's PowerPoint screenshots of the Obeya deck (slide 4, 2026-10-08), a word
  before a tag box ended 1 to 4 px before it, where LibreOffice left 3 to 5 px. The lane makes no
  horizontal compensation. **Tags no longer drift:** they are highlighted text and move with
  their words. The decision of 2026-10-08 (Stéphane, issue #9: a tag touching the word before it
  « accepted for the Obeya of 2026-10-14; no compensation ») no longer applies — the alternative
  proposed then, tags as highlighted text, was taken on 2026-10-09 (*Deliberate differences*).
- **A right-aligned or centred line that ends on an inline box** sits up to the box's border and
  right margin right of Chromium's (half that when centred) in LibreOffice, which leaves out the
  letter-spacing of a line's last character — here the plain spacing that stands for them: about
  1 px for the Obeya deck's tags (read from the code; it was 3.5 px when the whole right pad was
  that spacing). Not checked in PowerPoint.
- **Left-aligned lists with inside markers** (`list-style-position: inside`) draw the marker
  outside the text, hung as an outside one: their text sits about one em left of Chromium's,
  marker included (a test deck, 2026-10-13). Centred and right-aligned ones are right.
- **Justified text stretches into whatever wrap slack it has.** A justified line fills its text
  box, so any slack the box has beyond Chromium's lines moves its words, up to the slack at the
  end of a line. Since 2026-10-13 justified text gets only the slack its lines need: the floor of
  2 px + 1 % of the width that keeps a renderer drawing them a little wider from wrapping them
  again, less the room Chromium's lines leave before it stretches them (each line but the last,
  measured set flush left) — none when every such line ends that far short of the edge. It was
  8 % (at least 8 px). Measured in LibreOffice 26.2: the lines of edge deck e15's 330 px
  paragraph end within 2 px of Chromium's, where they ended up to 26 px right; e12 slide 3's
  18 px box, which started 6 px early, lands on Chromium's. A box with no padding on the far side
  whose lines need slack takes it on the near side: e12 slide 3's 11 px box, with an 8 px right
  border and a first line that nearly fills it, starts 5 px early, just inside its 2 px left
  border (before, its lines ran 8 px on under the right border, which hid their last glyphs).
  A justified list takes the slack its items need, each item's room measured on its own text
  (a one-line item's is what its line leaves to the edge), when drawn one box per item or when every item is justified; a list kept whole that mixes
  justified and other items keeps the 8 %, and so does a justified table cell (its quarter of the
  side padding). A line's room counts an inline box, an image or a right padding, border or
  margin as part of the line, not as room. Not checked in PowerPoint, which draws text slightly
  wider than LibreOffice: a line it draws more than its slack wider would wrap again.
- **Other numbering styles.** A numbered list in a style other than decimal, roman or alphabetic
  (`decimal-leading-zero`, a language's own numerals such as `armenian` or `hebrew`) is numbered in
  arabic numerals. Past `z`, an alphabetic list follows DrawingML, taken to repeat the letter
  (`aa`, `bb`), where CSS goes on with `ab`, `ac`; not checked in PowerPoint.
- **Wide nested numbers widen every level's hang.** A list's hang is the widest marker of any of
  its levels plus a quarter em, given to every level (finish.py): a nested list numbered `viii.`
  moves the top level's markers left of Chromium's, about 3–4 px with `iii.` or `iv.` and about
  20 px with seven or eight nested items (a test deck, 2026-10-13).
- **Numbering from 0, reversed lists, `<li value>`.** A list starting at 0 or below (a Markdown
  `0.` list, `<ol start="-1">`) is numbered from 1, a reversed list (`<ol reversed>`) counts up,
  and an item's own `value` is ignored: DrawingML numbers from 1 upwards, one paragraph after
  another.
- **Centred text in a box with uneven side padding or borders** is centred over the whole box,
  where Chromium centres it over the box's content: about 4 px left on edge deck e12, slide 1
  (24 px of left padding, or a 6 px left border), seen in one LibreOffice render on 2026-10-13
  and not investigated further (`addBox`'s centred branch).
- **A title holding a `<sup>`** sits about 5 px low in LibreOffice (10 px with a `<sub>`): the
  title placeholder has no exact line spacing, and the offset run, written at 1 / 0.58 of its
  size, deepens its line.
- **List items' pseudo-elements, partly.** An item's `::before` string is drawn, but its own
  right margin or padding is not (the text sits that much nearer it, about 15 px at 0.6 em), and
  an item's `::after` string is dropped. A wrapped centred item with an inside marker centres its
  later lines about half a hang right of Chromium's (13 px), its marker's hanging indent
  narrowing them.
- **A right-to-left list nested in a left-to-right one** hangs its markers on the left, where
  Chromium hangs them on the right.
- **Two nested numbered lists in one item, with text between them** (`<li>a <ol>…</ol> b
  <ol>…</ol></li>`), each start again at their first number, as in Chromium, in LibreOffice (edge
  deck e17 and a test deck of 2026-10-13, lists kept whole): each nested item carries its own
  start (`startAt`), and the text between is a paragraph at the item's level with no marker.
  Whether PowerPoint numbers the second list on from the first instead (« ii. ») has not been
  checked. A list drawn one box per item restarts in any renderer.
- **A right-to-left list** (`dir="rtl"`) is drawn right to left — markers right of the text,
  items right-aligned, nested items indented from the right, which LibreOffice places where
  Chromium does with Latin text (a test deck, 2026-10-13) — but always in one text box. So none
  of what a list drawn one box per item does applies to it: its empty inline boxes and images are
  not drawn (its inline boxes holding text are highlighted text as anywhere else), an item that
  opens on its nested list loses its marker, a centred item sits half the wrap slack left of
  Chromium's, and its pitch is never anchored. Its script is in a fallback font, since the brand
  fonts have no Arabic or Hebrew, and that font is each renderer's own: LibreOffice drew edge deck
  e14's Arabic about a quarter wider than Chromium. Such a list therefore does not wrap again: its
  lines break at Chromium's words, and a line drawn wider runs past the list's left edge (about
  45 px on e14's first line, LibreOffice) where a wrap added a line and pushed the list onto the
  one below. Until 2026-10-13 it was drawn left to right, marker on the left. Not checked in
  PowerPoint, whose fallback font for these scripts is its own.
- **A text that opens on a forced break and holds one line after it** (`<p><br>x</p>`) loses the
  empty first line Chromium draws: a leading break is dropped, so the text starts a line higher.
  With two lines or more after the break, the text is anchored on its glyphs and lands where
  Chromium put it, and a table cell places it on Chromium's baseline (a test deck, 2026-10-13),
  except preformatted text (`white-space: pre-line` or `pre-wrap`) that opens on a newline,
  which sits a line high whatever its length (its lines record no glyph to anchor on). A list
  item that opens on a forced break lands at Chromium's text position, but its marker moves down
  onto that text line, where Chromium draws it on the empty first line. An empty line anywhere
  after the first text is kept (see *Paragraphs* above).
- **A line holding a `<sup>` or a `<sub>` sits 1 to 2 px higher in LibreOffice.** The offset run
  is written at 1 / 0.58 of its size (*Superscripts and subscripts* above), and LibreOffice takes
  the line's descent from that enlarged size, plus the lowering of a `<sub>`: with exact spacing,
  a deeper descent lifts the line — 1 px with a `<sup>`, 2 px with a `<sub>`, at 13.5 px (edge
  decks e14, e16), and more at larger sizes (3 px with a `<sub>` at 25 px) — which is why larger offsets are drawn on the baseline (*Superscripts and
  subscripts* above). In Chromium Marp's `<sup>` and `<sub>` (`line-height: 0`) leave their line
  alone. **Not checked in PowerPoint**, which also decides the glyphs' size: written for
  LibreOffice's 58 %, they come out larger or smaller if PowerPoint draws an offset run at
  another ratio. Their offset holds whatever the ratio, since it is a percentage of the size
  written. Edited in PowerPoint, such a run shows its enlarged size.
- **Drift under 2 px.** Text with no shapes over it, table cells included, keeps a drift of up
  to 2 px from Chromium's lines before it is cut (or, in a cell, before a line gets a spacing of
  its own): a line that an inline `code` makes 1.5 px taller (edge deck e27) is not followed. A
  right-to-left list, which is never cut, keeps all of its drift. Justified text is not cut but
  is anchored on its first line, which covers a taller first line; a justified text made uneven
  further down (a larger font on its third line) still drifts from that line on (by
  construction; not measured).
- **Lists in table cells, partly.** Their markers are drawn, in their list's numbering style,
  and their items start at Chromium's text position, but a marker hangs the nearest indent
  level's hang rather than the list's own (*Tables*). Text after an item's nested list
  (`<li>a <ul>…</ul> b</li>`) is a paragraph of its own after the nested items, as in Chromium.
  An item that opens on its nested list loses its marker, which Chromium draws on the first
  nested item's line. A list is found only as a cell's own child (`td > ul`, not `td > div >
  ul`, whose items are plain lines); an inside marker (`list-style-position: inside`) in a cell
  with no left padding hangs nothing, so it sits against its text, which starts about 1 em left
  of Chromium's; and a list in a centred or right-aligned cell is not laid out as a list kept
  whole is (read from the code; not rendered).
- **Table cells in PowerPoint.** In LibreOffice a cell's line in a larger font sits up to 2 px
  below Chromium's (edge deck v2: a 1.8 em word, a 2 em KPI figure). PowerPoint not checked: a
  cell's line spacing now changes from line to line, with space before after a margin, and a
  PowerPoint slide show draws exact spacing about 4 % tighter, its first line higher (*Text
  under shapes is anchored*).

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
in a run's `<a:rPr>`), which LibreOffice 25.2 and 26.2 draw. PowerPoint for the web matched LibreOffice on the
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
| `internal-pptx/finish.py` | Paragraph properties, list-marker faces and sizes, raster paths out of alt texts, font embedding, hyperlink colour |
