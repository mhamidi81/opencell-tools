---
description: Orchestrate the full implementation of a Jira ticket in an Opencell OVERLAY repository across entities, Liquibase, services, apiv0 API, scripts/jobs, tests and Postman — with core-repo and branch-target gates, and the LiquibaseFileTest check.
argument-hint: "[TICKET-NUMBER]"
---

# Implement an overlay ticket

Orchestrates a complete backend implementation in an Opencell **overlay** repository
(e.g. `MACRD-1905`).

> **Critical rules**: read `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_CRITICAL_RULES.md` and the core
> `CRITICAL_RULES.md` it layers over, resolved via `_CORE_BASE.md`. They are deliberately **not**
> restated here — an inlined copy of core's rules would reimpose the AGPL-header and registration
> rules that the overlay deltas exist to override.

---

## Phase 0 — Branch setup (blocking)

1. Confirm the repo is an overlay: read its `CLAUDE.md` `## Overlay profile` block. If there is none,
   fall back to the module-prefix heuristic in `OVERLAY_PROFILES.md`, and ask if that is inconclusive.
2. **Ask which target branch(es)** with `AskUserQuestion` — `dev` (default), `18.1.X`, `18.X`,
   `16.5.X`, `15.X`, or several. This is not optional: the target decides the branch-name suffix, and
   **several targets means one branch and one pull request per target**.
3. Create the branch as `[<type>/]<KEY>-<number>-<slug>-<targetSuffix>` per
   `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_WORKFLOW.md`. Suggest `/rename <TICKET> <summary>` for
   the session title.
4. Create the AI-stats run directory `.claude/cache/ai-stats/<TICKET>-<yyyymmdd-HHMMSS>/` and keep the
   `RUN_ID`; every builder gets a manifest path inside it.

## Phase 0.5 — Core repository preflight (blocking on user confirmation)

Overlay code is written against core classes, so core must be present and consistent.

1. Locate core: the repo `CLAUDE.md` `## Core project` block → `../opencell-core` → a remembered path
   → **ask the user**, and remember the answer for future sessions.
2. Compare core's pom version with the overlay's `opencell.version`.
3. Determine each side's **base** branch (not the current branch name — either side may be on a feature
   branch). Report both and **ask the user to confirm they correspond**.
4. Warn and continue on mismatch; do not hard-block. Record what was confirmed, because a wrong core
   version silently produces overrides against the wrong API.

## Phase 1 — Fetch the ticket

Read the Jira issue with `fields: ["*all"]`. Story content lives in custom fields, not `description` —
see core `CRITICAL_RULES.md` rule 8. Read sub-tasks and comments too.

## Phase 2 — Plan (blocking approval)

Produce an implementation plan covering, with an explicit "none" where it does not apply:

- Entities and enums, with the module and base class
- **Liquibase**: the `current` change and its `rebuild` twin
- Services: new, or **`@Specializes`** on a core service (state the blast radius)
- apiv0 API: Rs interface, RsImpl, Api bean, DTO, and the exact `/ve/…` path
- Scripts and Jobs, and whether a `JobInstance` must be created
- Jasper reports
- **Core overrides introduced** — an explicit "none" line, so an override is always a conscious choice
- Unit tests and Postman collections

Get approval, then write `<RUN_ID>/_planning.json` so analysis effort that produces no code is credited.

## Phase 3 — Build, in order, with a blocking checkpoint after each

| Step | Agent | Manifest phase |
|---|---|---|
| 1. Entities + the `overlay.xml` pair | `oc-ov-tools:oc-ov-entity-builder` | `entity` |
| 2a. New services | `oc-be-tools:oc-be-service-builder` + overlay context block | `service` |
| 2b. Core-service changes | `oc-ov-tools:oc-ov-service-builder` (`@Specializes`) | `service` |
| 3. apiv0 API + DTOs | `oc-ov-tools:oc-ov-api-builder` | `api` |
| 4. Scripts / Jobs *(skip if the plan has none)* | `oc-ov-tools:oc-ov-script-builder` | `script` |

**Overlay context block** — include verbatim when dispatching a reused `oc-be-*` agent:

> This is an Opencell **overlay** repository, not core. Use the module paths in the repo `CLAUDE.md`
> `## Overlay profile` block, never core's `opencell-model` / `opencell-admin/ejbs` layout.
> **Do not add an AGPL license header.** Read
> `${CLAUDE_PLUGIN_ROOT}/guidelines/OVERLAY_CRITICAL_RULES.md` and the delta for your layer before
> writing anything.

After each agent, verify its manifest and `snapshots/<phase>.diff` exist; write them yourself if the
agent did not.

### Step 5 — Compile

```bash
mvn clean package -DskipTests
```

From the **repo root, full reactor** — not `-pl`. The war overlay needs every module's jar. Core must
already be installed at the matching version (Phase 0.5).

### Step 6 — Liquibase gate (blocking when Liquibase changed)

```bash
cd <overlay-war-module> && mvn test -Dtest=LiquibaseFileTest
```

From the module directory. Fix any pairing failure before continuing.

## Phase 4 — Tests and Postman

1. Unit tests via `oc-be-tools:oc-be-test-generator` with the overlay context block, plus: JUnit 5 +
   Mockito; add deps to the *module* pom; **never** place tests in the script module. Manifest phase
   `tests`.
2. Run them, then Postman via `oc-be-tools:oc-be-postman-generator` with the overlay context block,
   plus: write to the overlay postman folder as `<KEY>_<Feature>.postman_collection.json`; read apiv0
   `*Rs` interfaces for URLs; TNR is additive only; never touch the generated scripts collection.
   Manifest phase `postman`.
3. If a `.jrxml` changed, remind that the regenerated `.jasper` must be committed.

## Phase 5 — Wrap-up

Report files grouped by module, a suggested commit message `<KEY>-<number> <description>` (no
`Co-Authored-By` trailer), and a **Deployment actions still required** list:

- `cd <script-module> && mvn opencell:deploy-scripts@deploy-scripts -P deploy-script` — writes to a
  **live** server; confirm the target URL
- `JobInstance` creation for any new job, via the environment-setup Postman collections
- Jasper file copy, if reports changed
- Any override-register entry added to the repo `CLAUDE.md`

Finally, remind the user to record AI usage — see `/oc-ov-calculate-ai-use`.
