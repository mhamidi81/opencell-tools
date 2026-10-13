# Developer root-cause taxonomy

The vocabulary `/oc-bug-root-causes` classifies **"Development issue"** bugs onto. One
category per bug, chosen by **the mistake the fix corrects**: read the PR diff first and the
Jira prose second, and ask "what did the developer get wrong?", not "where did the user see
it?". The same list serves Frontend and Backend, so the two areas can be compared.

Whether a bug is a **regression** is recorded separately (`regression: true|false`) and is
never a category: a regression can be any of the mistakes below.

The first paragraph under each heading is the definition the report prints. Editing this
file changes future runs. Adding a category is safe; **renaming one breaks
period-over-period comparison**, so add a line to a definition rather than rename.

## incomplete-change-propagation
A change, fix or rename was applied to some code paths but not all of them: the create path fixed but not the update path, a setting applied to one entity type only, an enum renamed without migrating stored data, a previous fix that missed a sibling case.

Examples: INTRD-45634, INTRD-45671, INTRD-47270, INTRD-45624

## null-handling
A missing value was dereferenced without a guard: NullPointerException or "Cannot read properties of undefined" from optional configuration, an absent settings row, or an unguarded lookup.

Examples: INTRD-46331, INTRD-45167, INTRD-45541, INTRD-44718

## edge-case-boundary
A legitimate but unusual value was mishandled: zero, empty string, false, an empty list, a limit or boundary, a value with special characters, a case-sensitivity difference.

Examples: INTRD-45965, INTRD-44579, INTRD-46198, INTRD-45420

## dto-payload-mapping
Data lost or malformed crossing a boundary between UI, DTO and entity: a field dropped by a mapper or copy constructor, an object sent where a code was expected, an unknown or undeserialisable field, a field never reaching the backend.

Examples: INTRD-46196, INTRD-46854, INTRD-44595, INTRD-45543, INTRD-45461

## update-overwrites-state
An update replaced data it should have merged, or created a record it should have updated: omitted payload fields erase stored values, a partial object replaces the full one, a new line is added instead of editing the existing one, a user value is overwritten by the system.

Examples: INTRD-47176, INTRD-45282, INTRD-45590, INTRD-45620, INTRD-43559

## persistence-transaction
The persistence layer produced the wrong database state: duplicate or orphan rows, side effects surviving a rollback or applied twice, transient-entity and optimistic-lock errors, corrupted relationships or version chains, ID generator collisions.

Examples: INTRD-46292, INTRD-45439, INTRD-45168, INTRD-45292, INTRD-46781

## query-construction
A query was built wrong: invalid SQL/JPQL (GROUP BY, schema or table qualification), or server-side filtering, sorting, paging or export that covers the wrong set or the wrong field.

Examples: INTRD-43566, INTRD-44082, INTRD-47322, INTRD-46981, INTRD-46515, INTRD-45778

## api-contract
The REST surface disagrees with its contract: the wrong HTTP status for a condition, v1 and v2 answering the same request differently, a valid payload rejected, a response missing a documented part.

Examples: INTRD-46336, INTRD-44766, INTRD-46316, INTRD-45795

## frontend-state-effects
Client-side state or effect lifecycle is wrong: re-render or fetch loops, the same request fired repeatedly, stale data until refresh, unsaved changes discarded, UI preferences not persisted.

Examples: INTRD-47328, INTRD-45777, INTRD-46779, INTRD-43961, INTRD-45532

## missing-wiring
Something that had to be registered was forgotten: an app-roles or permission entry, an i18n key, a route, a request handler, a menu or configuration entry — the code exists but is not connected.

Examples: INTRD-45784, INTRD-46822, INTRD-45370, INTRD-45696, INTRD-45456

## business-rule-logic
A business rule was implemented wrongly: the wrong condition, the wrong data source, the wrong precedence or fallback, a rule applied when it should not be.

Examples: INTRD-47162, INTRD-45169, INTRD-44084, INTRD-43576

## numeric-date-precision
Numbers or dates computed or represented wrongly: rounding, floating-point totals, the number of decimals, timezone offsets, an off-by-one day.

Examples: INTRD-46710, INTRD-46784, INTRD-46778, INTRD-43377, INTRD-44021

## concurrency-lifecycle
Behaviour tied to time, nodes or process lifecycle: multi-node cluster races, deadlocks, startup and shutdown handling, timers and jobs relaunched or lost, caches that grow without bound.

Examples: INTRD-45412, INTRD-45289, INTRD-47287, INTRD-45028, INTRD-44507

## ui-cosmetic
Presentation only, with no data or behaviour wrong: wording, translation, casing, colours, layout, a label or icon.

Examples: INTRD-44765, INTRD-46824, INTRD-44707, INTRD-45417, INTRD-44058

## insufficient-evidence
Neither the Jira text nor the PR diff shows what the mistake was. Use it honestly: a bug that has a plausible best guess gets that guess with `low` confidence instead.

Examples: INTRD-45335, INTRD-47271
