---
description: Evaluate Opencell OVERLAY code changes against the core guidelines plus the overlay deltas using oc-ov-pr-reviewer, with overlay mechanical gates (Liquibase pairing, apiv0 registration, script @Inject, Jasper pairing), a requirements-conformance check against the Jira ticket, and an optional SonarQube summary. Reviews uncommitted changes or a Bitbucket pull request.
argument-hint: "[PR-number | list] [light]"
---

# Review overlay changes

Reviews backend changes in an Opencell **overlay** repository. Use this instead of `/oc-be-review`
here — the core reviewer's AGPL, Immutables-DTO, `BaseCrudApi` and `structure.xml` checks are false
positives on an overlay and drown the real findings.

## Modes

- **LOCAL** (no argument) — review uncommitted changes plus the branch diff against its target branch.
- **PR** (`<number>`) — review that Bitbucket pull request.
- **LIST** (`list`) — show open pull requests and let the user pick.
- `light` — single-pass conformance instead of the default deeper multi-agent pass.

Bitbucket access uses Basic auth, and the diff endpoints answer 302:

```bash
curl -sL -u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}" \
  "https://api.bitbucket.org/2.0/repositories/<owner>/<repo>/pullrequests/<id>/diff"
```

Without `-L` the body is empty and the reviewer silently reviews nothing.

---

## Axis 0 — Overlay mechanical gates (run first, before any agent)

Cheap deterministic checks. Each failure is a **blocking** finding; report them all rather than
stopping at the first.

1. **Liquibase pairing** — if `db_resources/**/overlay.xml` changed:
   ```bash
   cd <overlay-war-module> && mvn test -Dtest=LiquibaseFileTest
   ```
   from the module directory.
2. **apiv0 registration** — any changed class extending `BaseRs` must be under `org.meveo.apiv0.rest.*`,
   and any changed resource-looking class under that package must extend `BaseRs`. Either miss and the
   endpoint does not exist, with no build error.
3. **`@Inject` in a script** — grep changed files under the script module for `@Inject` / `@Stateless`.
4. **Generated collection** — `Opencell_Scripts.postman_collection.json` must not be hand-edited.
5. **Entity jar registration** — a new module with `@Entity` classes must appear as a `<jar-file>` in
   the overlay `persistence.xml`.
6. **Jasper pairing** — a changed `.jrxml` with no regenerated `.jasper` of the same basename.
7. **Branch suffix** — the branch must end in a target suffix; accept either separator
   (`-dev`, `_dev`, `-181x`, `-18x`, `-165x`, `-15x`).
8. **Unregistered core override** — a new file shadowing a core resource path or colliding with a core
   FQN, with no entry in the repo `CLAUDE.md` override register.
9. **Test placement** — no tests added under the script module's `src/test/java`.

## Axis 1 — Guideline conformance

Dispatch `oc-ov-tools:oc-ov-pr-reviewer` with the diff. It resolves the core guidelines itself and
applies them as amended by the overlay deltas. Parse its `**Status**:` line.

## Axis 2 — Requirements conformance

Dispatch `oc-be-tools:oc-be-conformance-reviewer` — it is repo-agnostic and needs no overlay changes.
Inject the ticket key, acceptance criteria and test scenarios read live from Jira (do not use the
ticket cache for this).

## Axis 3 — SonarQube (opt-in)

Read the project key from the repo `CLAUDE.md` `## Overlay profile` block. **If no key is configured,
skip this axis with a one-line note** — do not guess a key and do not fall back to core's.

## Core-baseline drift check

Read the installed `oc-be-tools` version and compare it with the `CORE BASELINE` header in the overlay
deltas. If the installed version is newer, **warn** that a delta may reference a renamed core heading.
Never block on this.

## Verdict

Approve only when all axes pass and Axis 0 is clean. Fold the three axes into one verdict with a single
score, using the rubric in `oc-ov-pr-reviewer` — do not restate or re-weight it here.

For a pull request, post the report as a comment and set the PR action from the verdict.

## Jira tagging

Append **`ai_code_review_back`** to the ticket's AI tag field (`customfield_10613`). Overlay work is
backend work — Java and xhtml — so it uses the ordinary backend tag, not a separate one.

The field is multi-value and free-text, so it must never be overwritten: read the current array,
append, and write back the whole array. If the read fails, skip the write rather than clobbering it.

Overlay tickets live in **`INTRD`** (alongside core tickets) and **`MACRD`**, so the ticket key does
not tell you which codebase the change landed in. The **repository** decides that — which is why this
command exists separately from `/oc-be-review`. See `oc-ov-calculate-ai-use.md`.
