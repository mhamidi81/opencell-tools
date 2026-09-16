# Technical bug taxonomy — core (Backend)

The vocabulary `/oc-bug-clusters --axis technical` classifies **core** bugs onto. One
subject per bug, chosen by the **source of the defect** — the mechanism that produced it —
not the product area it surfaced in. A wrong invoice total caused by a broken copy
constructor is `dto-mapping`, not `invoicing`.

This is the counterpart of `functional-subjects.md`, which groups the same bugs by
product area instead. Both views are useful and neither replaces the other.

Names here must not collide with `technical-portal.md` — a shared name would make a
cluster ambiguous about which area it came from.

Editing this file changes future runs. Adding a subject is safe; **renaming one breaks
month-over-month comparison**, so prefer adding an alias line to renaming.

## api-contract
The REST surface behaving differently from its contract: wrong HTTP status for a
condition, v1 and v2 answering the same request differently, endpoints rejecting valid
payloads, generic API filtering and search semantics.

## dto-mapping
Conversion between DTOs and entities: fields silently dropped, custom-field values lost or
deleted on update, copy constructors omitting attributes, request fields never reaching
the backend.

## jpa-persistence
The persistence layer and the shape of what lands in the database: duplicate rows for a
single logical item, corrupted relationships and version chains, cascade and orphan
behaviour, queries returning the wrong set.

## transactions
Transaction boundaries and their consequences: work committed in a transaction separate
from the one that should own it, decrements or side effects surviving a rollback, changes
applied twice.

## null-handling
Missing-value handling that surfaces as a failure: NullPointerExceptions from optional
configuration, absent settings rows, unguarded lookups before a null check.

## business-rules
Domain rules evaluated or applied wrongly, where nothing is technically broken but the
outcome is incorrect: conditions and ELs not honoured, state transitions firing when they
should not, amounts recomputed or rounded against the rule, values defaulted or left null
that the rule requires, guards missing on an entity's allowed states.

## liquibase-migration
Database change management and upgrades: changesets that fail on a clean install,
hard-coded values in a changeset, artefacts not updated by a version migration.

## file-storage
The storage layer and its backends: S3 and filesystem storage types, filenames the layer
mishandles, storage configuration changes that cannot be applied.

## document-generation
Producing documents from data: invoice PDF and XML generation, UBL and other schema
validation, generation that fails on first call or leaves metadata unset.

## job-scheduling
Jobs and the scheduler: jobs that hang with no timeout, job creation and update endpoints,
batch execution and its lifecycle.

## script-runtime
Custom ScriptInstances and their compilation or execution: compilation failures aborting
startup, scripts in the database diverging from compiled versions, classloading errors.
