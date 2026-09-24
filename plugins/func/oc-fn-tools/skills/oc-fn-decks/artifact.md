# Artifact lane — a deck as a claude.ai Artifact

**Opencell shares internal reports as claude.ai Artifacts** (decided 2026-09-23; every Openceller has
a Claude account on the Team plan, so a link reaches any colleague). This lane renders the **same
Marp `.md`** — same theme, same slides, no second source — to an Artifact page, instead of or
alongside the Marp HTML and the PPTX. It is the deck sibling of `oc-fn-briefs`' Artifact lane and
follows the same rules.

- **Scope: internal.** Product talks, all-hands, team decks. For SteerCo, customers or partners the
  official-template PPTX stays mandatory (`pptx.md`); ask before publishing any deck addressed outside
  Opencell.
- **What the viewer gets:** Marp's own viewer — arrow keys / swipe, the on-screen controls
  (bottom-left, shown on mouse move or tap), fullscreen (`f`, desktop browsers), overview (`o`),
  presenter view (`p`, opens a window, which the Artifact frame allows only for some signed-in
  viewers in the organisation), and `#<n>` links to a slide. Slides stay fixed 16:9: on a phone,
  read it in landscape.
- **Speaker notes ship with the page.** `<!-- note: … -->` comments reach the presenter view, so
  anyone with the link can read them. Write them for the audience or leave them out.
- **No local images.** The page is one fragment; a relative image path does not resolve on
  claude.ai. Embed images as `data:` URIs (the theme's logos already are).

## Reproducible from git — enforced, not advised

An Artifact is a **render, never the source.** `render-artifact.sh` refuses to render when:

- the deck is **not in git**, has **uncommitted changes**, or its last commit is **not on the branch's
  upstream** (not pushed);
- the repo's **theme copy** (`assets/marp/opencell.css`) has uncommitted changes, or the theme lives
  outside the deck's repo;
- the **skill itself** has uncommitted changes, where it lives in a git work tree.

Every page carries its **provenance** in an HTML comment right after `<title>`: `remote · path @
commit · theme <path> @ commit · oc-fn-decks <version> · marp-cli <version>`. marp-cli is **pinned**
(`MARP_CLI_VERSION`, default in the script) so the same commit renders the same page. `--draft`
bypasses the guard **for a local preview only**; the stamp then says DRAFT. **Never publish a draft
render.** As with briefs: no Claude Docs, and no page that stores its content on claude.ai.

## Front matter it adds

Marp ignores both keys; the render reads them.

| Field | Purpose |
|---|---|
| `pagetitle:` | The Artifact's name in the gallery and the tab — **2–4 words, distinctive**. Falls back to `title:`. Keep it stable across republishes. |
| `artifact:` | The published URL. **Written back after the first publish and committed**, so a later session republishes to the same link. |

## What differs from the Marp HTML

- **A fragment, not a document.** marp-cli writes a full page; `artifact/fragment.py` keeps its
  stylesheets and body, drops the document shell and the `<meta>` tags, and puts `<title>` first (the
  Artifact tool scans only the first 8 KB for it and wraps the page in its own skeleton).
- **Light by default — a dark OS setting is ignored**, exactly as for briefs (most Opencellers dislike
  dark themes). Dark applies only on an explicit choice: the page's **light/dark switch** — a moon/sun
  button added to Marp's on-screen controls, remembered per viewer in `localStorage` — then claude.ai's
  theme setting (`[data-theme="dark"]`). Don't add a `prefers-color-scheme` block.
- **The dark slides are a variant of the theme, derived from the Charte palette only.** Brand black
  `#121011` is the ground, the `#EDE4E9` tint family the text, coral `#FA5757` the link red; the logo
  turns white; **lead slides stay brand red in both themes.** Marp scopes every slide rule to its own
  container, so a slide cannot see an attribute on the page root: `artifact/slides.css` is appended to
  a temporary copy of the deck and compiled by Marp with the theme, keyed on an `oc-dark` class that
  `artifact/tail.js` puts on each `<section>`.
- **A deck's own `<style>` needs a dark variant.** A colour a deck sets in its own `<style>` (a pill,
  a stripe, a status chip) must also get a `section.oc-dark …` rule, or it keeps its light colour on the
  dark ground. Only brand colours, as above.
- **The page around the slides** (`artifact/page.css`, not compiled by Marp): the letterbox takes the
  Charte's pale rose `#EDE4E9` in light, brand black deepened in dark, instead of Marp's black.
- **24-hour presenter clock** is injected by the lane (`artifact/head.js`), so the locale rule holds
  whatever the viewer's browser — a deck no longer needs its own override for this lane.

## Publishing — the procedure

1. **Commit and push the deck `.md`** (and the repo's theme copy, if it changed).
2. **Render into the session scratchpad**, never into the repo:
   ```bash
   SKILL=~/.claude/skills/oc-fn-decks
   "$SKILL/render-artifact.sh" "<abs>/<deck>.md" -o "<scratchpad>/<deck>.html"
   ```
   The script finds the theme by walking up from the deck to `assets/marp/opencell.css` (override with
   `--theme-set`) and says whether to republish (it found `artifact:`) or first-publish.
3. **Look once.** Run the overflow check (`SKILL.md` § *Overflow*) on the `.md` — it is the same Marp
   render — and fix in the `.md`, never in the render. For a visual pass of the page itself, wrap the
   fragment in a bare `<!doctype html><meta name="viewport" …>` page for Chromium (add
   `data-oc-theme="dark"` on `<html>` to see the dark variant).
4. **Publish with the Artifact tool:**
   - **no `artifact:`** → publish `file_path` with an `icon` and a one-sentence `description`, then
     write the returned URL into the front matter as `artifact:`, commit and push.
   - **`artifact:` present** → `read` that URL first (the tool refuses a publish to an artifact the
     session has not read), then publish with `url` set to it. Omit `icon`.
5. **Sharing is the user's act.** A published Artifact is private until they share it. In the Teams or
   email message that carries the link, the link plays the attachment's role.

The render is **never committed** — it lives in the scratchpad and is regenerated on every publish.
The `.md`, carrying its `artifact:` URL, is the whole record.

## Files

| File | Role |
|---|---|
| `render-artifact.sh` | Entry point: guard, theme lookup, pinned marp-cli render, provenance stamp |
| `artifact/fragment.py` | marp-cli document → Artifact fragment |
| `artifact/slides.css` | Dark variant of the theme, compiled by Marp (`section.oc-dark`) |
| `artifact/page.css` | The page around the slides: letterbox ground, the switch button |
| `artifact/switch.html` | The moon/sun button inserted into Marp's on-screen controls |
| `artifact/head.js` / `tail.js` | Theme switch (remembered choice first, then `oc-dark` on each slide) + the 24h clock |
