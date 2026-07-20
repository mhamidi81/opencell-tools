---
name: oc-fn-gui-design
version: 1.2.1
updated: 2026-07-16T14:33:14+02:00
author: Stéphane Chambrin
description: >
  Design GUI-impacting Opencell User Stories against the real Opencell Design System in Figma —
  so a Story ships with an actual, design-system-grounded screen design instead of vague prose
  (the team has no UX designer; developers should not be inventing UX). Load this skill whenever
  the user mentions Figma, a mockup, a wireframe, a screen/page/UI/GUI design, "design the screen",
  the design system or design tokens, MUI components for the Portal, or shares a `figma.com` URL —
  and before any Figma MCP tool call (`get_design_context`, `get_screenshot`, `search_design_system`,
  `get_variable_defs`, `use_figma`, …) in the Opencell context. Produces the design that feeds the
  Story's *Functional design → GUI* section; issue authoring itself stays in `oc-fn-func-design`.
---

# Opencell GUI design — design the screen, grounded in the Design System

When an Opencell User Story has GUI impact, this skill produces the **actual screen design** —
real MUI-v6 components, real Opencell tokens, concrete layout, states, and bilingual labels — so a
developer can build it without inventing UX. It exists because the team has **no UX designer**, and
a Story that only *describes* a screen in prose leaves the design to whoever picks up the ticket.

The design is grounded in the **Opencell Design System** (a published Figma team library, built on
**MUI v6 + ApexCharts**) and in the existing page designs. Reading the design system is fully
automated; the output feeds the Story's *Functional design → GUI* section.

## When this skill applies

Load whenever any of the following is true:

- The user asks to **design / mock up / wireframe** a screen, page, view, dialog, or component for
  Opencell — even if Figma isn't named ("design the screen for this story", "what should this page
  look like").
- The user mentions **Figma**, the **design system**, **design tokens**, **MUI** components for the
  Portal, or shares a **`figma.com` URL**.
- A Story with **GUI impact** is being authored or reviewed and its screen needs a concrete design
  (the counterpart to `oc-fn-func-design`'s *GUI* section, which this skill fills with substance).
- Any **Figma MCP tool** is about to run in the Opencell context (`get_design_context`,
  `get_screenshot`, `search_design_system`, `get_variable_defs`, `use_figma`, …).

## Scope & boundaries — lane discipline

This skill designs the **screen**. It does not write Jira, and it does not implement the design.

- **`oc-fn-func-design` owns the Story.** It writes the *Functional design → GUI* section (ADF
  format, the bilingual-labels rule, the inline-media safety rule). This skill hands it the
  artifacts (Figma link + screenshot + grounded spec); func-design writes them into the issue. See
  § *Output contract*.
- **`oc-fn-portal` screenshots the *existing* Portal.** When a Story changes an existing screen,
  use `oc-fn-portal` (Playwright) to capture the current state as the *before*, then design the
  *after* here. The two are complementary: portal = what exists, this skill = what should be.
- **Implementation is the developer's.** The grounded spec tells the dev *what* to build with which
  DS components and tokens; the React/MUI code is theirs (backend/frontend split — see global
  `CLAUDE.md`).
- **Phase placement.** This is **Phase 2 (Functional Design)** work in the INTRD Story workflow —
  the PO lane, before Technical Design. See `oc-fn-func-design/stories.md` § *Workflow*.

## Access — in brief

Figma is reached through the **claude.ai Figma connector** (the official Figma remote MCP server,
OAuth). It is **enabled in claude.ai** (`/mcp` → "claude.ai Figma"), **not** bundled in the
marketplace — the same pattern as the Atlassian Rovo connector. Confirm it at session start with
`whoami`; if it errors, the connector is not authorized.

**Two surfaces, split by job.** The MCP does search, tokens, screenshots, styling context, and
authoring — but it **cannot list a file's pages** (`get_metadata` returns only the *Cover* page).
The **Figma REST API** fills that gap: the `figma` helper (`figma pages` / `find` / `screens`)
enumerates pages and screens. So:

- **Design system** — library-scoped `search_design_system` / `get_variable_defs` (MCP), page-independent.
- **Screen discovery** — `figma pages` / `find` / `screens` (REST); enumerate screens yourself, then
  hand a node id to the MCP for the picture and styling. Don't send the user hunting for node-URLs.
- **Authoring** — `use_figma` (Mode B), MCP only.

File keys, the library key, seats/scopes, the REST discovery commands, and the node-URL recipe live
in **`access.md`** and **`figma-rest.md`** — load them when connecting, discovering, or on an access error.

## The staged workflow — two modes (A default, B opt-in)

Two modes. **Default to A**; do B only on explicit request.

- **Mode A — read → grounded spec / mockup** (default, fully mature). Read the design system and any
  analogous existing screens, then produce a design-system-grounded **GUI spec** (+ an optional
  HTML/artifact mockup) that lands in the Story's GUI section. No writes to Figma. Full recipe:
  **`workflow-read.md`**.
- **Mode B — author editable Figma frames** (opt-in, sandboxed). Additionally build real, editable
  frames in Figma via `use_figma`, in a **duplicate/sandbox file**, human-reviewed, linked from the
  Story. Beta-quality; gated. Full recipe + safety gate: **`workflow-author.md`**.

**Never enter Mode B implicitly.** "Design this screen" means Mode A. Author in Figma only when the
user asks for it, and only under the safety gate below.

## Grounding mandate — never invent, always resolve

The value of this skill is that its designs are **real**, not plausible-looking inventions.

- **Every component maps to a real DS component.** Resolve names via `search_design_system` (scoped
  to the Opencell library key) before you name a component. Use the real name (`select`,
  `ToggleButtonGroup`, `iconButton`, `buttons`, …) — the DS naming is inconsistent (camelCase /
  spaced / PascalCase), so quote what search returns, don't normalise it.
- **Every colour and text style maps to a real token.** Colours come from the `Colors_Tokens`
  collection, type from `Font_Tokens`; read live values with `get_variable_defs` on a real frame.
  Do **not** hardcode hex or invent token names. Spacing/radius are **not** tokenised — follow MUI's
  8px system and component defaults. Full catalogue + method: **`design-system.md`**.
- **Reuse existing patterns.** Before designing new, look for an analogous existing screen (ask the
  user for its node-URL) and mirror its structure. Consistency beats novelty.
- **Flag gaps, don't fabricate.** When a Story needs something the DS lacks (no suitable component,
  no token for a needed state), **say so** and propose either the closest DS primitive or a net-new
  component for the design system — never silently invent one and present it as existing.

## Output contract — how the design reaches the Story

The design lands in the Story's *Functional design → GUI* section (`customfield_10135`, owned by
`oc-fn-func-design`). Deliver **three** artifacts:

1. **Figma link — the source of truth, and ALWAYS present.** Every GUI section MUST carry a
   **node-specific** URL to the exact frame (via *Copy link to selection*), placed as a hyperlink
   (or a Jira smart-link card if the Figma-for-Jira integration is enabled) so a developer reaches
   the live design in **one click** — never make them hunt for it. It MUST be a real ADF `link` mark
   (a `text` node with `marks: [{type:"link", attrs:{href}}]`) — a raw URL pasted as plain text is
   **not** auto-linkified in Jira ADF custom fields and renders as unclickable plain text. The live
   link is canonical because designs keep evolving in Figma. A GUI section without a clickable Figma
   link is incomplete.
2. **Screenshot — a dated snapshot, ALWAYS inlined in the field body.** Produce a PNG
   (`get_screenshot` → download, or `download_assets`), **attach it to the Story as a regular
   attachment**, AND **embed it inline in the GUI-section ADF** — visible in the field body, not
   merely referenced by filename or left in the Attachments panel. Caption it `Snapshot — <frame
   name> — as of <YYYY-MM-DD>` so a stale mockup is never read as current. Both are mandatory: a GUI
   section whose design isn't visible inline is incomplete.
   - **Inline-embed recipe (REST-reliable).** A `media` node of `type: "file"` needs a Media Services
     fileId + collection, which the attachments REST API does **not** expose — PUTting the Jira
     attachment id returns `ATTACHMENT_VALIDATION_ERROR`. So embed via a `mediaSingle` → `media` node
     of **`type: "external"`** whose `url` is the attachment's content URL
     (`https://<site>.atlassian.net/rest/api/3/attachment/content/<attachmentId>`); pass the PNG's
     `width`/`height`. This passes validation and renders inline for authenticated Jira users
     (verified against INTRD-45279). The image MUST **also** remain a real attachment — the external
     node is a renderer, not the store, so the design survives even if the inline render is stripped
     (export/mobile). Because the file is a genuine attachment, this satisfies `oc-fn-func-design`'s
     *Destructive edits on fields containing inline media* rule (nothing is orphaned).
   - The Rovo MCP cannot upload attachments, so the PNG is uploaded via the `jira` helper /
     `curl` (`POST …/issue/<key>/attachments`, header `X-Atlassian-Token: no-check`) — or dragged in
     by the user. This skill produces the file + states the path; func-design does the upload **and**
     the inline embed.
3. **Grounded spec.** The component-by-component breakdown: which DS components, which tokens, the
   layout, the states (default / hover / focus / error / empty / loading), responsive behaviour, and
   the **bilingual (EN + FR) label table** (func-design's mandatory rule — every user-facing label,
   enum value, button, tab, and action in both languages).

**Division of labour:** `oc-fn-gui-design` creates the frame / PNG / spec; `oc-fn-func-design` writes
them into the Story (ADF, attachment upload, **inline embed**, inline-media safety). Keep the boundary clean — do not
edit Jira from this skill. Details in `workflow-read.md` § *Land the design in the Story*.

## Token discipline — Figma MCP is verbose

Figma MCP responses are large (XML dumps, image payloads, full variable lists). Keep them cheap:

- **Scope every `search_design_system` to the Opencell library key** via `includeLibraryKeys`, and
  narrow with `includeComponents` / `includeVariables` / `includeStyles` — don't pull all three when
  you want one.
- **`get_screenshot` returns a short-lived URL + curl by default** — keep it that way; **do not** set
  `enableBase64Response` unless you genuinely cannot fetch URLs. `Read` a downloaded PNG only when
  *you* need to see it; for a doc capture, note the path and hand it on.
- **`get_metadata` before `get_design_context`.** Get the cheap structure first, drill into specific
  node IDs only where you need the styling/code detail.
- **Cache within the session.** File keys, the library key, and token collections don't change
  mid-session — resolve once, reuse.

## Mode B safety gate — authoring into Figma

Before any `use_figma` (or `create_new_file` / `generate_figma_design` / `upload_assets`) write:

1. **Explicit request only.** The user must have asked to author in Figma. Otherwise stay in Mode A.
2. **Sandbox, never production.** Write to a **duplicate or a fresh drafts file**, never a shared
   design-system or product file. Confirm the target with the user first.
3. **`/figma-use` is mandatory before `use_figma`.** The Figma MCP server ships a `/figma-use` skill
   (fallback `skill://figma/figma-use/SKILL.md`) that must be read first — follow it.
4. **Build from real components and variables**, not raw frames and hardcoded values — read the
   library first (Mode A grounding still applies).
5. **Human review.** The write path is **beta**: screenshot the result, show it, and treat every
   frame as reviewable. Note the output-size / asset limits.
6. **Full seat required** to write outside drafts (confirmed present for this account — see
   `access.md`).

Full step-by-step in `workflow-author.md`.

## Reference files

Load on demand — do not pre-read all of them.

- **`access.md`** — the Figma connector, auth check, the known file keys + library key, REST page/
  screen discovery, the node-URL recipe, seats / tiers / OAuth scopes. Load when connecting,
  discovering, adding a file, or on any access error.
- **`figma-rest.md`** — page & screen **discovery** over the Figma REST API (what the MCP can't do):
  the `figma` helper (`pages` / `find` / `screens` / `node` / `url`) and equivalent raw-`curl`
  recipes, plus the REST-discovers / MCP-does-content division. Load whenever you need to find pages
  or screens in a file.
- **`design-system.md`** — the Opencell Design System catalogue and method: file/library keys, the
  MUI-v6 + ApexCharts basis, the `Colors_Tokens` / `Font_Tokens` collections and naming conventions,
  FILL styles, the component-naming reality, and the Figma → MUI-v6 → Portal mapping. Load whenever
  resolving components or tokens.
- **`workflow-read.md`** — Mode A, step by step, through to landing the design in the Story
  (the output contract mechanics). The default workflow.
- **`workflow-author.md`** — Mode B, step by step, with the full safety gate. Load only when the
  user has asked to author in Figma.
