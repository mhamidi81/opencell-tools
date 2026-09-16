# Technical bug taxonomy — portal (Frontend)

The vocabulary `/oc-bug-clusters --axis technical` classifies **portal** bugs onto. One
subject per bug, chosen by the **source of the defect** — the mechanism that produced it —
not the product area it surfaced in. A crash in the quote screen caused by a grid
component is `ag-grid`, not `quoting`.

This is the counterpart of `functional-subjects.md`, which groups the same bugs by
product area instead. Both views are useful and neither replaces the other.

Names here must not collide with `technical-core.md` — a shared name would make a cluster
ambiguous about which area it came from.

Editing this file changes future runs. Adding a subject is safe; **renaming one breaks
month-over-month comparison**, so prefer adding an alias line to renaming.

## ag-grid
Defects in the shared grid/table stack: GridList and AG Grid behaviour, row selection,
column sorting and filtering, pagination, and the bulk-action banner. Includes grids that
paginate or sort only the loaded page.

## apollo-graphql
Defects in the Apollo/GraphQL data layer and the "new design" pages built on it: queries
returning the wrong shape, cache staleness, mutations not persisting, cancel/rollback not
discarding local state, routing between old and new design.

## form-state
Form and field state: values silently dropped on save, falsy-coalescing bugs, dirty-state
tracking, fields editable that should be read-only, missing or wrong client-side
validation.

## i18n-locale
Translation keys, locale configuration and locale-dependent rendering — including a locale
property that breaks boot, and untranslated or object-rendered labels.

## number-format
Numeric presentation and precision in the UI: decimal limits, rounding, floating-point
values sent to the API, currency symbol resolution, and numeric range bounds rendered
wrongly.

## date-timezone
Date and time handling in the browser: UTC-offset errors, dates shifted by a day, date
pickers and validity periods.

## routing-menu
Navigation mechanics: menu and submenu rendering, routes, page shells, and boot sequences
that never complete.

## permissions-ui
How the front end reacts to roles and access rules: screens that fail when a role grants
read without edit, menus whose visibility disagrees with the access matrix, missing
permission handling on a section.

## export-download
Client-initiated exports and downloads: filters not applied to the export, silent row
truncation, malformed export requests.

## rendering-performance
Front-end performance and stability as the defect itself: infinite loading, excessive
memory or CPU, render loops.
