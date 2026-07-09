# The official-template PPTX lane

How to render a deck's `.md` source into an **editable PowerPoint file on the official Opencell
template** — the deliverable mandated for SteerCo and external audiences. The Marp HTML lane
(SKILL.md) and this lane consume the **same `.md` source**; this file carries only what is
specific to the PPTX side.

## When this lane is mandatory

The official template must be used for **every presentation, internal or external** (all-hands
mandate, 2024-10-31; the CEO actively checks). In practice:

- **SteerCo, customers, partners, anything leaving the product team** → deliver the
  official-template **PPTX** (this lane). The Marp HTML remains a fine *presentation aid*.
- **Working sessions / internal product-team decks** → Marp HTML alone is acceptable.
- **Template owner: Soraya Bamba** (marketing) — contact her for template needs or new layouts.

## Assets

Master copies live in this skill's `pptx/`; repos producing official decks get a working copy at
**`<repo-root>/assets/pptx/`** (same in-repo reproducibility rule as the Marp theme —
see SKILL.md § *Where the theme lives*).

| File | Role |
|------|------|
| `opencell-slides-ref.pptx` | Curated pandoc reference: the official template + 7 layouts renamed to pandoc's English names, cover placeholders rewired, brand fonts embedded |
| `deck2pptx.py` | One-command render: Marp-dialect bridge → pandoc → red closing bookend |
| `close_deck.py` | Finishing pass: red closing bookend ("Thank you" / "Merci" slides → cover layout, backups may follow) + dynamic caption/table spacing on text-then-table slides (standalone-usable) |
| `curate_ref.py` | Regenerates the reference from marketing's template (see *Re-curation*) |

Provenance: curated from **`Opencell_2024 V3 - EN.pptx`** (SharePoint → *2 - Marketing / 01_Brand /
01_Visual assets / 05_Templates*), 16:9, 44 layouts. Beware: **`Opencell_2025 (A4).potx` in the
same folder is the A4-portrait *document* template, not slideware.**

## Rendering

From the repo root (so `assets/pptx/` and relative image paths resolve):

```bash
python3 assets/pptx/deck2pptx.py <path>/<deck>.md          # writes <deck>.pptx
```

That is: bridge the Marp dialect (drop the explicit title slide, `<!-- note: … -->` →
`::: notes`), run `pandoc --reference-doc=… --slide-level=2`, then `close_deck.py` for the red
closing. Requires `pandoc` ≥ 2.15 and `python3`; **no network, no PowerPoint, no LibreOffice**.

## Authoring for both lanes — the deltas

The SKILL.md conventions apply unchanged. On top of them, a dual-lane deck needs:

- **Front-matter metadata**: `title:`, `subtitle:`, `author:` (e.g.
  `'Stéphane Chambrin — VP Product, Opencell'`) — pandoc builds the cover from these; Marp
  ignores them. The explicit lead title slide stays (Marp needs it) and **must mirror the
  metadata**; the bridge drops it for PPTX. **Fold the date into `subtitle:`** (the cover layout
  has no date placeholder).
- **Speaker notes**: `<!-- note: … -->` after the slide content. Marp shows it in presenter view;
  the bridge turns it into a real PowerPoint speaker note. Never write raw `::: notes` — Marp
  renders fenced divs as visible text.
- **Section slides** (`<!-- _class: lead -->` + bare `#` H1) map to the template's photo section
  divider. Keep them **H1-only**: extra content under an H1 spills onto an untitled extra slide
  in pandoc.
- **Closing**: recap on a final `## The ask` content slide, then the bare `# Thank you` lead
  slide — `close_deck.py` moves it onto the red cover layout, matching the Marp bookend.
- **Table (or image) last on its slide.** A PPTX body placeholder cannot contain a table — it is
  a separate shape — so pandoc pushes anything *after* a table/image onto an **untitled
  continuation slide**. Put commentary above the table; if a slide grows two tables plus prose,
  split it yourself instead of letting pandoc do it blindly.
- **No pandoc-only syntax in shared decks**: fenced divs (`::::` columns, `::: notes`) show as
  junk text in Marp. A two-column official slide (`:::: columns`) is possible in a
  **PPTX-only** deck; prefer restructuring to stay dual-lane.

What lands where:

| `.md` construct | Official layout used |
|---|---|
| front-matter `title`/`subtitle`/`author` | *Introduction* (red cover; white title under the logo) |
| `<!-- _class: lead -->` + bare `# H1` | *1_image gauche mur* (photo section divider) |
| `## H2` + bullets / table / image | *Titre et contenu* (tables render as native PowerPoint tables) |
| bare `# Thank you` / `# Merci` | *Introduction* again (red closing bookend, via `close_deck.py`; backup slides may follow it) |
| (PPTX-only) `:::: columns` | *Deux contenus* |

All 44 official layouts (frises, process circles, chiffres clés, …) ride along in every
generated file — available in PowerPoint's layout picker for hand-extension. The template's
**slide 5 is an icon library**: generated decks don't include it, so copy icons from the
template file itself when hand-finishing.

## Editable output — the fork rule

The generated PPTX is fully editable *by design* (that's the point). The one-way mirror still
holds: the `.md` is the source, and re-rendering **overwrites** the file. Last-mile polish in
PowerPoint (layout swaps, icons, imagery) is legitimate for the final deliverable — but it is a
**fork**: do it last, keep the hand-finished copy under a distinct name, and never back-port
edits by hand-editing the generated file in place.

## Verification before sharing — render it, look at it

**Always run the local visual check** (LibreOffice + poppler) and inspect **every slide**,
exactly like the Marp overflow loop — structural checks (slide counts, layout names) do not
catch a title overprinting a caption or text clipped behind a table:

```bash
soffice --headless --convert-to pdf --outdir /tmp/vischeck <deck>.pptx
pdftoppm -png -r 60 /tmp/vischeck/<deck>.pdf /tmp/vischeck/slide
# → slide-01.png … — inspect each, then delete (scratch, not committed)
```

Look for: every slide on its intended layout, cover title white and under the logo, the red
closing, **no text overflow or overlap**. Mind the density: the template's body is **28 pt vs
Marp's 25 px — a slide that barely fits in the Marp lane overflows in PPTX**; tighten the copy
(or split the slide), don't shrink fonts. LibreOffice approximates fonts (Playfair may render as
sans) — layout/overflow verdicts are reliable, font fidelity is judged in real PowerPoint. Fonts
(Montserrat, Playfair Display) are **embedded** in every generated deck, so viewers need no font
install.

## Re-curation (when marketing revs the template)

The template is actively edited (layout names carry date suffixes) — the reference pins one
revision. When a new template ships:

```bash
# fonts (one-time; OFL-licensed, embedding is allowed) — 4 static TTF styles per family,
# renamed to <Family>-{Regular,Italic,Bold,BoldItalic}.ttf in a fonts/ dir:
curl -o m.zip "https://gwfh.mranftl.com/api/fonts/montserrat?download=zip&subsets=latin&variants=regular,italic,700,700italic&formats=ttf"
curl -o p.zip "https://gwfh.mranftl.com/api/fonts/playfair-display?download=zip&subsets=latin&variants=regular,italic,700,700italic&formats=ttf"

python3 curate_ref.py "Opencell_20XX ….pptx" opencell-slides-ref.pptx fonts/
```

`curate_ref.py` **fails hard when the expected layout names drift** — update its `RENAMES` table
against the new template's names (list them: `unzip -p file.pptx ppt/slideLayouts/slideLayoutN.xml
| grep -o 'cSld name="[^"]*"'`), re-run, and re-verify one deck in PowerPoint. pandoc's layout
matching is case-insensitive but **English-only** — unrenamed layouts silently fall back to
pandoc's default (unbranded) design, which is exactly what curation exists to prevent. A `.potx`
source needs its `[Content_Types].xml` presentation override switched from `…template.main+xml`
to `…presentation.main+xml` first (PowerPoint *Save As* `.pptx` does the same).
