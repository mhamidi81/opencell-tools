# Opencell Portal — recurring UI patterns

The portal is **React + Material UI (MUI)**. The patterns below are the MUI conventions to
expect. **Read-only seed catalogue** — this file ships with the skill; do **not** edit it in
place. As you observe how a control actually behaves in this portal (exact labels, where the
save/cancel controls sit, how grids paginate, etc.), record the specifics in your *user
catalogue* at `~/.local/state/oc-fn-portal/catalog/ui-patterns.md` (create it on first use,
mirroring the table format below), and consult both. This file is for reasoning about how to
*drive* an unfamiliar control with the fewest snapshots.

| Pattern | Looks like | How to drive it | Confirmed in this portal? |
|---|---|---|---|
| **Left navigation** | Persistent side drawer with sections/sub-items | Click the section, then the sub-item; the route in the address bar is what to record in your user catalogue `~/.local/state/oc-fn-portal/catalog/pages.md` | _to confirm_ |
| **Data grid / table** | MUI table or DataGrid with column headers, row actions, pagination | Read the relevant rows from a single snapshot; paginate/sort via header or footer controls; row-level actions often behind a kebab (⋮) menu | _to confirm_ |
| **Dialog / modal** | Overlay with title, body, action buttons | Snapshot once when it opens; act on its buttons by ref; expect a backdrop that closes on outside-click or a Cancel/Close button | _to confirm_ |
| **Form layout** | Labelled fields, often grouped in cards/sections | `browser_type` into fields by their label/ref; required fields usually flagged; watch for inline validation before submit | _to confirm_ |
| **Tabs** | Horizontal tab strip switching panels within a page | Click the tab; content swaps without a route change — re-snapshot only if you need the new panel's structure | _to confirm_ |
| **Save / action bar** | Sticky bar (top or bottom) with Save / Cancel | Mutating — confirm with the user before clicking Save (see SKILL.md boundaries) | _to confirm_ |
| **Filters / search** | Filter chips, search box, advanced-filter panel | Set filters, then read the resulting grid from one snapshot | _to confirm_ |
| **Toast / snackbar** | Transient bottom notification after an action | Confirms success/failure of an action; capture quickly (it auto-dismisses) if it matters | _to confirm_ |

<!--
Record observations in your user catalogue `~/.local/state/oc-fn-portal/catalog/ui-patterns.md`
(not this read-only seed): replace "to confirm" with specifics there — exact control labels,
selector/ref patterns, quirks (lazy-loaded grids, debounced search, confirm-dialogs on
delete, etc.). Keep entries about *how to interact*, not page-specific content — page
specifics belong in the pages catalogue.
-->
