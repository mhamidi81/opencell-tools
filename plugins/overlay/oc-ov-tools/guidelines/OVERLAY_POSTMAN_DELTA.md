# Overlay Postman collections

> LAYERS OVER: oc-be-tools/guidelines/POSTMAN_TESTING.md
> CORE BASELINE: oc-be-tools 1.17.0
> PRECEDENCE: core's endpoint-map / DTO-field-map verification process and its assertion rules apply
> in full. Only location, taxonomy and the async pattern differ.

## Location — REPLACES core's `opencell-tests/US-Tests/`

The overlay's own postman folder, with subfolders for the environment, per-domain setup and releases.
Note the environment folder may use French spelling (`environnement/`).

## Collection taxonomy

| Kind | Naming | Notes |
|---|---|---|
| Environment bootstrap | `NEW_VE_ENV_SETUP_<NN>_<Topic>` | The `NN` is **execution order**, not decoration — run them in sequence |
| Per-ticket | `<KEY>_<Feature>.postman_collection.json` | e.g. `INTRD-44783_HomeInfo_AutoFill` |
| Non-regression | `TNR.postman_collection.json` | **Additive only** — never weaken or delete an existing case |
| Release delta | `release/<version>.postman_collection.json` | New-release deltas appended as a new file |
| Job setup | the jobs/workflow and MACO job collections | Where `JobInstance`s get created |
| Scripts | `Opencell_Scripts.postman_collection.json` | **Generated** by `mvn opencell:create-postman` — never hand-edit |

## Environment variables

New variables go in the environment file, never inlined into a request.

## Verify URLs against the code, not from memory

Core's mandatory endpoint-map and DTO-field-map steps apply — but read the **apiv0** interfaces
(`org.meveo.apiv0.rest.*Rs`, paths under `/ve/`), not apiv2 resources. Cross-check against an existing
request in the collections, since the deployed prefix comes from core's JAX-RS application.

## Most overlay features are asynchronous

The assertion shape is usually *launch a job → poll its execution result → assert the outcome*, not a
single synchronous call. Core's status-code and business-assertion rules still apply; the difference is
that a `200` on the launch call proves nothing on its own.
