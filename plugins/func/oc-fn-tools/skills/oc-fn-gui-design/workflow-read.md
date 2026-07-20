# Mode A — read → grounded spec / mockup (the default)

Read together with `SKILL.md`. This is the default workflow: read the design system and any
analogous existing screens, produce a design-system-grounded GUI design, and land it in the Story.
No writes to Figma.

## 0. Prerequisites

- Connector authorized (`whoami` — see `access.md`).
- The Story's functional intent is understood: what the user is trying to do on this screen, the
  information involved, the actions, and the states (empty / loading / error / success). If the
  Story's *Requirement* and *Functional design* are thin, resolve that with `oc-fn-func-design`
  first — you cannot design a screen for an undefined behaviour.

## 1. Anchor on what exists

Design consistency comes from reuse, so start by looking, not drawing.

1. **Existing Portal screen?** If the Story changes a screen that already exists, capture the
   current state with `oc-fn-portal` (Playwright) as the *before*. That is the ground truth for what
   users see today.
2. **Analogous Figma design?** Find it yourself — don't make the user hunt for a node-URL. Use REST
   discovery (`figma-rest.md`): `figma find <fileKey> "<feature>"` locates the page (the NewUI /
   To-come files are organised by feature, each with *Already dev* / *To come* / *Maquettes finales*
   pages), then `figma screens <fileKey> <pageId>` lists the frames on it. Pick the closest screen's
   node id, then use the MCP for the detail:
   - `get_screenshot(fileKey, nodeId)` — see it (URL + curl; `Read` the PNG only if you must).
   - `get_design_context(fileKey, nodeId)` — styling + which DS components/tokens it uses.
   - `get_metadata(fileKey, nodeId)` — cheap structure, if you only need the frame layout.
   Mirror its layout, spacing rhythm, and component choices. Consistency beats novelty. (If the user
   already pasted a node-URL, skip discovery and go straight to the MCP calls.)

## 2. Resolve the building blocks

For each element the screen needs, resolve it to a **real** DS asset (see `design-system.md`):

- **Components** — `search_design_system(query, fileKey, includeLibraryKeys=[DS])`. Use the returned
  names verbatim; note the MUI v6 component each wraps.
- **Colours / type** — `Colors_Tokens` / `Font_Tokens`; read live values via `get_variable_defs` on
  a real frame. Spacing/radius → MUI 8px + defaults.
- **Gaps** — if the Story needs a component or token the DS doesn't have, **flag it** (propose the
  closest primitive, or a net-new DS component). Do not fabricate.

## 3. Design the screen

Compose the resolved blocks into a concrete layout:

- **Structure** — page shell, regions, the primary content pattern (form / list+detail / table /
  wizard / dashboard). Reuse the analogous screen's skeleton where there is one.
- **States** — specify default, loading, empty, error, and success. A screen designed only in its
  happy state is not finished.
- **Responsive** — note behaviour at the Portal's working widths; the DS is desktop-first.
- **Bilingual labels** — every user-facing label, enum value, button, tab, section title, and action
  in **EN + FR** (func-design's mandatory rule). Build the table now — it is part of the design, not
  an afterthought.

**Optional low-fi mockup.** When a picture helps the PO decide before any Figma authoring, render an
**HTML/artifact mockup** using the real token values (colours from `Colors_Tokens`, sizes from
`Font_Tokens`) and MUI-v6-shaped components. Label it clearly as a **non-authoritative sketch** — it
is a thinking aid, not the deliverable. The deliverable is the grounded spec (and, in Mode B, the
Figma frame).

## 4. Land the design in the Story

The design goes into the Story's *Functional design → GUI* section (`customfield_10135`), which
`oc-fn-func-design` owns and writes. This skill produces the artifacts; func-design writes them in.
Deliver all three (see `SKILL.md` § *Output contract*):

1. **Figma link (source of truth) — always present, always clickable.** The node-specific URL of the
   frame (Mode A: the analogous existing frame you referenced, or the new frame if Mode B ran), so the
   dev reaches the live design in **one click**. Embed it as a real ADF `link` mark (`text` node with
   `marks:[{type:"link",attrs:{href}}]`) — Jira does **not** auto-linkify raw URLs in ADF fields, so a
   pasted URL renders as plain unclickable text. Never ship the GUI section without a clickable link.
2. **Screenshot (dated snapshot) — attached AND inlined in the field body.**
   - Produce the PNG: `get_screenshot(fileKey, nodeId)` returns a short-lived URL + a curl command —
     run the curl to save the PNG to disk (or use `download_assets`). Do **not** base64 it into
     context. Note its pixel `width`/`height` (needed for the media node).
   - Hand the file path to `oc-fn-func-design`, which (a) **attaches it to the Story as a regular
     attachment** (Rovo MCP has no upload tool → `jira` helper / `curl`
     `POST …/issue/<key>/attachments`, header `X-Atlassian-Token: no-check`, or the user drags it in),
     and (b) **embeds it inline in the GUI-section ADF** so the design shows in the field body.
   - **Inline-embed recipe:** do NOT use a `media` node of `type: "file"` with the Jira attachment id
     — it fails validation (`ATTACHMENT_VALIDATION_ERROR`; the Media Services fileId isn't exposed by
     REST). Use a `mediaSingle` → `media` node of **`type: "external"`** with
     `url = https://<site>.atlassian.net/rest/api/3/attachment/content/<attachmentId>` (+ width/height).
     It validates and renders inline for authenticated users. The file must ALSO stay a real
     attachment (backup + satisfies the *Destructive edits on inline media* rule — nothing orphaned).
   - Caption: `Snapshot — <frame name> — as of <YYYY-MM-DD>`.
3. **Grounded spec** — the component-by-component breakdown (DS component → MUI v6 → token bindings),
   layout, states, responsive notes, and the EN+FR label table. This is what func-design writes as
   the substance of the GUI section, replacing vague prose.

**The live Figma link stays canonical; the screenshot is a point-in-time snapshot.** When the design
changes, update the Figma frame and refresh the snapshot — don't let the Story imply the screenshot
is current when the frame has moved on.

## Worked example — Customer 360° · General information (edit mode)

A real end-to-end pass against a *Maquettes finales* (validated-for-dev) screen in the NewUI file
(`DZ7EnuPmWBlkAsjHgEsoqI`). It shows the whole method; reproduce the shape for any GUI Story.

**1. Discover (REST — `figma-rest.md`).** No node-URL needed:

```
figma find DZ7EnuPmWBlkAsjHgEsoqI "Maquettes finales"     # → page 4:172 (Customers, 🎨 final)
figma node DZ7EnuPmWBlkAsjHgEsoqI 4:172 2                  # → SECTION 3756:18226 "17.03.2025 customer 360 new Design"
                                                           #    → FRAME 3756:20173 "Customers care > Customers > General information > Edit mode"
```

**2. See it (MCP).** `get_screenshot(DZ7EnuPmWBlkAsjHgEsoqI, 3756:20173)` → the customer view for
"Mairie de Clichy": breadcrumb + title with edit affordance and a status pill, a `Save modifications`
/ `Actions` button pair, two tabs, a read-only *Customer details* card, a *Billing information* form,
and *Subscriptions / Transactions / Quotes / Orders* each a data table with status pills.

**3. Resolve to real DS assets** (`search_design_system` scoped to the DS library — verbatim names):

| Screen element | DS component | Wraps / library |
|---|---|---|
| Billing cycle, Country, Language, Tax category, Currency, Favorite payment method | `select` | MUI `Select` (outlined, required `*`) |
| Email address | *(text field)* | MUI `TextField` (outlined) |
| `Save modifications` (outlined), `Actions` (contained), `Add payment method` (outlined + icon) | `buttons` | MUI `Button` |
| Row/section overflow (⋮) | `iconButton` | MUI `IconButton` |
| Invoices / Payments / Balance segmented control | `ToggleButtonGroup` | MUI `ToggleButtonGroup` |
| Subscriptions / Transactions / Quotes / Orders tables (column filters, pagination) | `AG GRID` | **AG Grid** (not MUI DataGrid) |
| Active / Activated / Unpaid / Partially-paid / Validated / Accepted pills | `chip` | MUI `Chip` (semantic colours) |
| Stripe payment brand | `logo/x40/Stripe` | brand asset |

Tokens: titles → `Font_Tokens/font_size/text_h2`·`h3`, body/fields → `body1`/`body2`; text →
`Colors_Tokens/text/colors_text_default`·`grey_*`; the status pills map to the semantic scales
(`error_600` for *Unpaid*, a success token for *Validated/Accepted*, a warning token for
*Partially-paid*). Read exact values with `get_variable_defs` on the frame. Spacing → MUI 8px.

**4. Bilingual labels** (EN + FR — mandatory; sample):

| EN | FR |
|---|---|
| General information / Advanced information | Informations générales / Informations avancées |
| Customer details | Détails du client |
| Billing cycle / Country / Language | Cycle de facturation / Pays / Langue |
| Favorite payment method / Add payment method | Moyen de paiement favori / Ajouter un moyen de paiement |
| Save modifications | Enregistrer les modifications |
| Active / Activated / Unpaid / Validated | Actif / Activé / Impayé / Validé |

**5. Land it in the Story** (§ *Land the design in the Story*): Figma link
`figma url DZ7EnuPmWBlkAsjHgEsoqI 3756:20173`
→ `https://www.figma.com/design/DZ7EnuPmWBlkAsjHgEsoqI/?node-id=3756-20173` (source of truth, always
present); the PNG attached **and inlined in the field body** (external-URL media node, § *Land the
design in the Story*) and captioned `Snapshot — Customer 360° · General information — as of <date>`;
and the component/token/label spec above as the GUI-section substance — a build-ready screen, not prose.
