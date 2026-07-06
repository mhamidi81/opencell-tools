# Mode B — author editable Figma frames (opt-in, sandboxed)

Read together with `SKILL.md`. This is the **opt-in** path: after grounding a design in Mode A,
build it as real, editable Figma content via the write tools. It is **beta**, gated, and never runs
implicitly.

## Precondition — the safety gate

Do **all** of these before the first write tool call (`use_figma` / `create_new_file` /
`generate_figma_design` / `upload_assets`):

1. **Explicit request.** The user asked to author in Figma. "Design this screen" alone is Mode A.
2. **`/figma-use` first.** The Figma MCP server ships a `/figma-use` skill (fallback
   `skill://figma/figma-use/SKILL.md`) that is **mandatory before `use_figma`**. Read it and follow
   it — it carries Figma's own current rules for the write path. If the user's environment has the
   Figma plugin skills, prefer those.
3. **Confirm the target file, and make it a sandbox.** Write to a **duplicate** of the relevant file
   or a **fresh drafts file** (`create_new_file`). **Never** write into the shared Design System file
   (`La67u40TTxeEy8HAcXMOeC`) or a live product file. State the target and get a go-ahead.
4. **Full seat confirmed.** Writing outside drafts needs a Full seat (present for this account —
   `access.md`). Drafts always work.
5. **Grounding done.** Mode A steps 1–3 have resolved the real components and tokens. Mode B builds
   from those, not from scratch.

If any item is unmet, stop and resolve it — do not "just try" a write.

## Build

Follow `/figma-use`; the shape of the work:

1. **Read the libraries first** (`get_libraries`, `search_design_system`) so `use_figma` builds with
   **real published components and variables**, not detached frames and hardcoded values. This is the
   single biggest quality lever — instances of DS components stay in sync; raw rectangles don't.
2. **Construct the frame** — pages/frames/auto-layout/components/variables via `use_figma` (it runs
   Plugin-API code server-side). Bind colours to `Colors_Tokens`, type to `Font_Tokens`; use MUI 8px
   spacing.
3. **Screenshot-and-iterate.** After a write, `get_screenshot` the result, compare against the intent,
   and refine in a self-healing loop. Show the screenshot to the user.

### Beta caveats (state them; don't paper over)

- **Review everything.** The write path is beta — treat every generated frame as a draft for human
  review, not a finished design.
- **Output/asset limits.** Writes are size-capped per call; images and custom fonts have early
  limits (fonts may need pre-uploading via `upload_assets`). Build incrementally.
- **Work on a duplicate, keep the original.** Per Figma's own guidance — never author directly on a
  file you can't afford to have modified.

## Hand off to the Story

Once the frame is reviewed and accepted:

1. Get its **node-specific URL** (*Copy link to selection*) — this becomes the Story's Figma link and
   the **source of truth**.
2. Produce the **dated screenshot** and hand the PNG path to `oc-fn-func-design` for attachment +
   embedding (see `workflow-read.md` § *Land the design in the Story* — same output contract).
3. Deliver the **grounded spec** alongside.

Mode B changes *where the canonical design lives* (an editable Figma frame instead of a referenced
existing one); it does **not** change the output contract or the lane boundary — issue authoring
still belongs to `oc-fn-func-design`.
