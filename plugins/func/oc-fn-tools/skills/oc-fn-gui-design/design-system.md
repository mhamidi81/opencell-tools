# The Opencell Design System — catalogue & method

Read together with `SKILL.md`. Load whenever resolving a component or token. This file records the
**shape** of the system and the **method** to query it live — it deliberately does **not** freeze
the full component list or token values, which change; resolve those at authoring time.

## What it is

- **File:** "Opencell — Design System", key `La67u40TTxeEy8HAcXMOeC`.
- **Published team library**, key `lk-63112bc6…` (full key in `access.md`) — this is what product
  files subscribe to.
- **Built on MUI v6 + ApexCharts.** The cover states "MUI v6" and "APEX CHARTS"; the Portal is
  React + Material UI (global `CLAUDE.md`). So **a design maps to MUI v6 primitives**, and charts to
  ApexCharts. When you name a component, you are naming the MUI component the DS wraps.

## Method — query it live, scoped to the library

Always scope searches to the DS library key so results are Opencell's, not community kits:

```
search_design_system(
  query: "<term>",
  fileKey: "La67u40TTxeEy8HAcXMOeC",
  includeLibraryKeys: ["lk-63112bc6…"],
  includeComponents: true,   // toggle off the facets you don't need
  includeVariables: false,
  includeStyles: false,
)
```

Results carry `name`, `assetType` (`component` / `component_set`), `componentKey`, `updatedAt`, and a
`filePath` like `design_systems/Opencell - Design System/components/<name>`. For token values, use
`get_variable_defs(fileKey, nodeId)` on a **real component or screen frame** — it returns
`name → value` (e.g. `text/colors_text_default → #…`). It returns `{}` on frames that bind no
variables (cover art, plain shapes), so target a node that actually uses the system.

## Components — the naming reality

Components map to MUI v6 names, but **DS naming is inconsistent** — camelCase, spaced, and
PascalCase all occur. **Quote what `search_design_system` returns; never normalise it.** Observed:

| DS component (verbatim) | `assetType` | Maps to (MUI v6) |
|---|---|---|
| `buttons` | component_set | `Button` (variants) |
| `iconButton` | component_set | `IconButton` |
| `buttonMenu` | component_set | `Button` + `Menu` |
| `toggle button ` (trailing space) | component_set | `ToggleButton` |
| `ToggleButtonGroup` | component | `ToggleButtonGroup` |
| `select` | component_set | `Select` |
| `chip` | component_set | `Chip` (semantic status colours) |
| `icon/x20/radiobuttoncheck`, `icon/x20/…` | component | icon set (20px grid) |

**Two components are NOT MUI** — the DS wraps third-party widgets, so don't map them to MUI:

- **Data tables/grids → `AG GRID`** (component_set) — the Portal uses **AG Grid**, not MUI's
  `DataGrid`. Every list/table (customer lists, invoices, subscriptions, …) is AG Grid.
- **Charts → ApexCharts** (per the DS cover) — not an MUI chart.

This is a **sample, not the full set** — run `search_design_system` for the components a given screen
needs (e.g. `input`, `table`, `dialog`, `checkbox`, `tabs`, `stepper`, `alert`, `card`, `nav`,
`snackbar`, `datepicker`). The cover art's "grid sheets" hints at the breadth: Text Field, Alert,
Table, Stepper, Radio, Button, Chip, Theme.

## Tokens (variables)

Two variable collections. **No spacing / radius collection exists** — spacing follows MUI's implicit
**8px system** and component defaults; state that explicitly rather than inventing spacing tokens.

### `Colors_Tokens` — semantic colours

Naming: `<category>/colors_<role>[_<scale>]`. Categories seen: `text/`, `icon/`, `border/`. Examples:

- `text/colors_text_default`, `text/colors_text_primary`, `text/colors_text_white`,
  `text/colors_text_grey_100`…`_800`, `text/colors_text_error_600`
- `icon/colors_icon_grey_50`…`_800`, `icon/colors_icon_white`, `icon/colors_icons_logo`
- `border/colors_border_50`, `border/colors_border_300`, `border/colors_border_white`

Scales run in steps (50 / 100 / 300 / 600 / 800…). `scopes` on each variable say where it's meant to
apply (`TEXT_FILL`, `STROKE`, `SHAPE_FILL`, `ALL_SCOPES`) — respect them (a `TEXT_FILL` token is for
text, not a background).

### `Font_Tokens` — type scale (FLOAT font sizes)

`font_size/text_h1`, `_h2`, `_h3`, `text_body1`, `text_body2`, `text_bodymedium1`, `text_bodymedium2`,
`text_caption`, `text_captionmedium`, `text_badge`. These are the type-scale steps; map headings/body
to these rather than inventing point sizes.

### FILL styles

Semantic text-colour styles also exist as Figma styles: `Text/Primary`, `Text/Secondary`,
`Text/Disabled`. Prefer the variable tokens above where both exist; use styles when a component wires
to a style.

## Grounding rules (recap of the SKILL mandate, applied here)

- Resolve **component names** via search before naming them; use them verbatim.
- Resolve **colours** to `Colors_Tokens`, **type** to `Font_Tokens`, reading live values with
  `get_variable_defs`. Never hardcode hex or invent token names.
- **Spacing/radius: not tokenised** → MUI 8px + component defaults.
- **Charts → ApexCharts.**
- When the DS lacks something the Story needs, **flag it** (closest primitive, or propose a net-new
  DS component) — do not fabricate.

## The Figma → MUI-v6 → Portal chain

Because the DS wraps MUI v6, the grounded spec can name all three layers, which is what makes it
directly buildable by a frontend dev:

1. **DS component** (verbatim Figma name, from search) — what the designer/PO points at.
2. **MUI v6 component** it wraps — what the dev instantiates.
3. **Token bindings** (`Colors_Tokens` / `Font_Tokens`) — the props/theme values, not raw literals.

Write the spec in those terms and a developer implements it without guessing UX or brand values.
