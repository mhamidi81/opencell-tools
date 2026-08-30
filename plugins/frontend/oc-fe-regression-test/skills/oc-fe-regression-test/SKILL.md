---
name: oc-fe-regression-test
description: Create and run Playwright regression tests for the OpenCell Portal screens changed by the current diff. Runs directly after the Vitest step, stays on the current branch so the specs land in the pull request, and blocks the workflow when a screen has genuinely regressed.
argument-hint: "[BASE-BRANCH] [--files <path> ...] (e.g. dev)"
---

## Purpose

Protect the **screens** a change touches. `/oc-fe-write-tests` covers units; this covers the
rendered page in a real browser, with every API mocked.

This is **not** `/oc-fe-create-e2e-test`. That skill is driven by Jira acceptance criteria and
cuts its own `test/[TICKET]` branch. This one is driven by the **diff**, stays on the
**current** branch, and therefore ships inside the pull request.

**Repository gate.** This skill only applies to **opencell-portal**. If
`git remote get-url origin` does not name that repository, report "not opencell-portal —
skipping Playwright regression step" and exit 0.

**Prerequisite.** The portal must have `playwright.config.ts`, a `test:e2e` script and
`tests/support/app-boot.ts`. If any is missing, report that the Playwright harness is not
bootstrapped on this branch and exit 0 — do not attempt to create it here.

## Context

Parse `$ARGUMENTS`:

- **[BASE-BRANCH]** — first positional argument, default `dev`. Used to compute the diff.
- **`--files <path> ...`** — optional explicit file list. When given, use exactly those paths:
  do not expand to the diff, and **do not re-apply the Step 1 extension/exclusion filter** —
  the caller named these files deliberately, so an excluded extension is an instruction, not
  an oversight. Skip straight to Step 2 with them as `[CHANGED-FILES]`.

## Tasks

### Step 1: Resolve the changed source files

```bash
git diff --name-only [BASE-BRANCH]...HEAD
git diff --name-only HEAD          # unstaged, so the skill also works pre-commit
git ls-files --others --exclude-standard
```

Union the three lists, then apply the filter below. **The filter applies to the diff only —
`--files` bypasses it entirely** (see Context above).

**Keep** a path when it starts with `src/` **and** matches any one of:

| Extension | Where |
|-----------|-------|
| `.ts`, `.tsx` | anywhere under `src/` |
| `.js`, `.jsx` | under `src/srcProject/**` |
| `.json` | under `src/srcProject/layout/**` |

**Then drop** — whatever the extension — every path that is:

- under an `i18n/` directory (translations only);
- `*.test.*`, or under `__tests__/`;
- under `src/test-utils/` or `tests/`;
- a config file (`*.config.*`, `vite.config.js`, `playwright.config.ts`, …).

That is the whole rule: JSON **is** in scope, but only page-descriptor/module JSON under
`src/srcProject/layout/**`, and never `i18n/` JSON.

**Do not narrow this back to `.ts`/`.tsx`.** In this repo the screens are defined
overwhelmingly in JavaScript and JSON — `src/srcProject/layout/**` holds 1884 `.js` and 1032
`.json` files against 29 `.ts` and 9 `.tsx`, and roughly half of recent `src/` churn is
`.js`/`.jsx`/`.json`. A ticket that changes a list's column set
(`.../billing-accounts/list/list.js`), a page descriptor `.json` (the `"type"` that selects
the widget) or a module `index.js` (`resource`, `pages`, `inMenu.path`) is precisely the
change class most likely to break a screen. Under a `.ts`-only filter every one of those
resolves to **zero** files, and the step exits 0 reporting "no screen-level change" — a
silent no-op dressed up as success.

Store as `[CHANGED-FILES]`. If it is empty, report "no screen-level change — Vitest coverage
is sufficient" and exit 0. This is a normal outcome, not a failure.

### Step 2: Map each changed file to a screen URL

There is **no route table**. Routes are derived at runtime by
`src/components/App/Resource/Resource.tsx:87-166` from module configs, following

```
/<layout modulePath>/<inMenu.path?>/<module resource>/<pages key>
```

built at `src/configuration/layout/utils/buildModules.js:6-20`. Only the literal keys
`list` / `show` / `edit` / `create` become React-Admin pages with the suffixes in
`src/utils/routing.js:167-172`; every other `pages` key is mounted verbatim at
`` `${match.url}/${key}` `` (`Resource.tsx:93`). All ten layouts use `PATH_CREATE = 'new'`
and `PATH_EDIT = ':id/modify'` from their `url-helper.js`.

**A file already under `src/srcProject/layout/**` is its own descriptor** — it needs no
widget lookup. Walk up to the nearest directory holding an `index.js` with a `resource` key
and go straight to sub-step 5.

For every other file in `[CHANGED-FILES]`:

1. Walk up to `src/srcProject/widgets/<DOMAIN>/<FEATURE>/index.ts` and read the exported
   component names.
2. Grep each name in `src/components/GenericRenderer/Widgets/defaultWidgets.ts` for its
   registry entry — anchor on `]: <ExportName>,` (or grep `-w`), not a bare substring: e.g.
   `CreateTax` also matches `CreateTaxCategories` and `CreateTaxationCategory`. Confirm a
   single unambiguous entry before proceeding; if more than one matches, read the
   surrounding entries to pick the right one rather than taking the first hit.
3. Resolve that constant in `src/constants/generic.js` to its string literal. **The literal
   is not necessarily the export name** — e.g. the exported `CreateTax` component is
   registered under a constant whose literal is `'CreateAdminTax'`
   (vs. `B2B_DUNNING_POLICY_CREATE = 'CreateDunningPolicy'`, where they do match).
4. Grep **the literal resolved in sub-step 3** — never the sub-step 1 export name — across
   `src/srcProject/layout/**`: `"type": "<literal>"` in the page descriptor JSON, or
   `type: '<literal>'` in `create.js` / `list.js`.
5. Read the descriptor directory's `index.js` for `resource`, the `pages` keys and
   `inMenu.path`, and its import statements for any page-key constants it uses (e.g.
   `PATH_CREATE`/`PATH_EDIT`); read the layout root
   (`src/srcProject/layout/<X>/constant/paths.js`) for `modulePath`. **Follow the actual
   import**, not the descriptor's own layout by assumption — e.g. `settings/modules/taxes`
   imports `PATH_CREATE`/`PATH_EDIT` from `finance/url-helper.js`, not `settings/`.
6. Compose the URL with `screenUrl()` from `tests/support/routes.ts`.

The composition itself is implemented in
`src/configuration/layout/utils/buildModules.js:6-20` — read that if the formula above is
ever in doubt.

Worked example, resolved end to end. The descriptor that actually mounts for this resource
is `src/srcProject/layout/B2B/modules/apollo2/dunning-policies/index.js` — see the
mounted-descriptor rule in Step 4; its legacy sibling
`src/srcProject/layout/B2B/modules/dunning-policies/index.js` declares the same values but is
filtered out and never mounted. It declares `resource: 'dunning-policies'` and
`inMenu: { path: 'dunning' }`, and `src/srcProject/layout/B2B/constant/paths.js` exports
`modulePath = 'B2B'`. So the `list` page is:

```
modulePath   inMenu.path   resource            pageKey
B2B     /    dunning   /   dunning-policies /  list      →  /B2B/dunning/dunning-policies/list
```

which is `screenUrl('B2B', 'dunning-policies', 'list', { menuPath: 'dunning' })`. Note the
`inMenu.path` segment sits **between** the layout and the resource, and is absent for a
module whose `inMenu` has no `path` (e.g. billing-accounts → `/B2B/billing-accounts/list`).

Store the result as `[SCREENS]` — a list of `{ url, domain, feature, changedFiles }`.

**A file that resolves to no screen** (a shared hook, a mapper, a util) is reported as
"covered by Vitest only" and skipped. Never invent a URL.

If `[SCREENS]` is empty, report that and exit 0.

### Step 3: Resolve the AI-stats run directory

The sub-agent's `Write`/`Edit` calls never appear in this session's transcript and are lost
when it finishes, so `/oc-fe-calculate-ai-use` needs a manifest.

- Reuse the run directory for this ticket if one exists: the **`[TICKET-NUMBER]-*` prefix**
  match under `.claude/cache/ai-stats/`, not "most recent directory".
- Otherwise `[RUN_ID]` = `{TICKET-NUMBER or "regression"}-{yyyymmdd-HHMMSS}`
  (`date -u +%Y%m%d-%H%M%S`) and create `.claude/cache/ai-stats/[RUN_ID]/` (git-ignored).
- Cheap and non-blocking: if any of this fails, dispatch the agent anyway.

### Step 4: Dispatch the oc-fe-e2e-expert agent

Use the Task tool with `subagent_type: oc-fe-create-e2e-test:oc-fe-e2e-expert`. The prompt
must carry:

- `[SCREENS]` with the resolved URLs, and `[CHANGED-FILES]` per screen.
- "These are **regression** specs for changed screens, not feature specs from a ticket.
  Write `tests/e2e/[DOMAIN]/[FEATURE].spec.ts` and a page object under `tests/pages/` when
  one does not exist. Stay on the current branch."
- "Import the boot fixture: `import { expect, test, mockApi } from '../../support/app-boot';`
  and take **`appPage`**, never `page`, as your test argument — `installAppBoot` runs inside
  the `appPage` fixture, so a spec written as `async ({ page })` gets no stubs and never
  boots. It already stubs `keycloak-js`, replaces `app-properties.js` and installs a
  permissive API catch-all. Override individual endpoints with
  **`mockApi(appPage, pattern, body)`** — the same page object the fixture set up; Playwright
  matches route handlers in reverse registration order, so a handler you register inside the
  test wins over the fixture's."
- "**Do not modify** `playwright.config.ts`, `vite.config.js`, `package.json` or
  `bitbucket-pipelines.yml`. The harness is already bootstrapped and its settings are
  deliberate; if a spec appears to need a config change, that is a defect in the spec."
- "**Do not create or use any Keycloak login helper, `global-setup`, or `storageState`.** The
  `appPage` boot fixture is the *only* auth path here — it stubs the `keycloak-js` module
  itself, so there is no login to perform and no live Keycloak to reach. Any
  `loginViaKeycloak` / `global-setup.ts` / `storageState` recipe in your own agent
  instructions does not apply to this skill."
- "**Confirm the changed descriptor is the one that actually mounts.** Exactly one
  descriptor mounts per resource, and `apollo2/` in a path implies nothing on its own — in
  both directions. Resolve it from the module tree, never from the path segment:

  **(a) Is the resource variant-switched?** Only the ten resources in
  `resourcesToAttributesAndRoles` (`src/components/App/SwitchUI/constants.ts:52-114`) are:
  `billing-accounts`, `quotes`, `orders`, `subscriptions`, `invoices`, `collection-plans`,
  `products`, `offers`, `contacts`, `reminders`. For those ten the boot fixture renders the
  **legacy** variant — the fixture's `/rest/user` payload carries no
  `attributes.selectedPageVersion_*`, so the old-UI filter sees `'1'`
  (`SwitchUI/utils.ts:58-60`) while **both** newUI branches require `'2'` (`:80-83`). So if
  the diff touches only the **apollo2** descriptor of one of these ten, write **no** spec
  for that screen and say why: the URL renders the legacy variant and a passing spec is
  false coverage.

  **(b) Otherwise, check the descriptor is not dead code.** For a resource *not* among the
  ten, `resourcesToAttributesAndRoles.get(resource)` is `undefined`, so the old-UI filter
  evaluates `attributes[undefined] || '1'` → `'1'` → **true** and the newUI filter is false.
  Net effect (`SwitchUI/utils.ts:47-61`): every resource named in `modulesNewUI` is stripped
  from the layout's base `modules` array, then its `modulesOldUI` entry is re-added — and
  that entry is frequently the **apollo2** module (`B2B/modules/index.js:190-206` re-adds
  eight of them). So open `src/srcProject/layout/<LAYOUT>/modules/index.js` and confirm the
  changed file lives under the module `modulesOldUI` actually imports for that resource
  (falling back to the base array when the resource appears in neither list). If it does
  not, the descriptor is never mounted — write **no** spec and say so.

  Worked example of (b): `B2B/modules/dunning-policies/` is legacy and has no `apollo2/` in
  its path, yet its resource `dunning-policies` is stripped at `:47-51` and re-added as
  `dunningPoliciesApollo2`, so `/B2B/dunning/dunning-policies/list` renders
  `B2B/modules/apollo2/dunning-policies/`. A diff confined to the legacy directory is dead
  code, and a spec at that URL would be exactly the false green this rule exists to
  prevent."
- "Build URLs with `screenUrl()` from `tests/support/routes.ts`. Do not hard-code paths."
- "**Locators:** hand-written `data-testid` is almost absent from widget source. Every
  generic-renderer input gets an auto-generated one from
  `src/components/GenericRenderer/Form/InputRenderer/withTest.tsx:12-16` in the form
  `<resource>-<source>-<type>`. Prefer that, then `getByRole` / `getByLabel` / `getByText`.
  **Do not edit widget source to add test ids.**"
- "**Per screen assert:** the screen renders its key landmarks; then drive the specific
  interaction the diff touched and assert the resulting DOM state and the outgoing request.
  No `page.waitForTimeout()`, no CSS-structure selectors, no shared state between tests."
- "Run `yarn test:e2e <your spec paths>` and iterate on **your own** defects at most 3 times."
- The failure policy in Step 6 below, verbatim.
- Resolve `[PHASE]` **before dispatching**: `e2e` if `e2e.json` is free in
  `.claude/cache/ai-stats/[RUN_ID]/`, otherwise the first of `e2e-2`, `e2e-3`, … not already
  taken in that run directory (e.g. by a prior `oc-fe-create-e2e-test` run on the same
  ticket). Use this same `[PHASE]` for both the manifest and the snapshot below — a numbered
  manifest sitting beside a hardcoded `e2e.diff` is exactly the collision this exists to
  avoid.
- Manifest: "Write your file manifest to `.claude/cache/ai-stats/[RUN_ID]/[PHASE].json` per
  your manifest instructions, then snapshot your first pass to `snapshots/[PHASE].diff`."

### Step 5: Verify the snapshot before touching the agent's files

Use the same `[PHASE]` resolved in Step 4 (`e2e`, `e2e-2`, …) for the snapshot filename —
never hardcode `e2e.diff`, or a second run sharing this ticket-prefixed directory silently
overwrites the first run's snapshot and its retention becomes unmeasurable.

```bash
mkdir -p .claude/cache/ai-stats/[RUN_ID]/snapshots
git add -N -- <files from [PHASE].json>   # REQUIRED: git diff HEAD ignores untracked
                                      # files, so brand-new specs would otherwise diff to nothing
git diff HEAD -- <files from [PHASE].json> > .claude/cache/ai-stats/[RUN_ID]/snapshots/[PHASE].diff
```

Do this **before** any edit of your own, or retention reads a meaningless 100%. Best-effort
and non-blocking.

### Step 6: Apply the failure policy

- **All specs green** → report the specs written and the run result, and continue.
- **Still red and the cause is the spec** → report "could not produce a reliable spec for
  `<screen>`", leave that spec out rather than committing a broken one, and continue with
  the rest.
- **Still red and the cause is the application** → **stop the workflow**. Report the failing
  screen, the failing assertion, the expected-vs-actual, and the trace path
  (`test-results/**/trace.zip`). Do not commit, do not proceed to the PR.

**Prohibited, without exception:** deleting an assertion, replacing it with a weaker one, or
adding `test.skip` / `test.fixme` to reach green. Surfacing a real regression is this skill's
purpose — it is a success, not an error.

### Step 7: Tag the ticket

Append `ai_test_front_dev` to the JIRA **AI field** (`customfield_10613`).

**Never overwrite it** — it is a multi-value labels field shared with the other AI commands.
A bare string, a single-select `{ "value": … }` object, or a one-element array replaces the
whole field and destroys the other tags.

1. `getJiraIssue` with `fields: ["customfield_10613"]`; store the array as `[CURRENT-TAGS]`
   (`null`/missing → `[]`). If the read fails, **skip the write**.
2. If `ai_test_front_dev` is already present, skip and note "already tagged".
3. Otherwise `editJiraIssue` with `{ "customfield_10613": ["ai_test_front_dev", <...CURRENT-TAGS>] }`.

**Resolving the ticket:** match `XXX-NNNNN` in `git rev-parse --abbrev-ref HEAD`. If none
can be resolved, skip this step and say so. Skip it too when no spec was written.

## Report

```
PLAYWRIGHT REGRESSION
  Screens covered:   [N]
  Specs created:     [list]
  Specs updated:     [list]
  Run result:        [PASS | FAIL]
  Skipped files:     [files that resolved to no screen — covered by Vitest only]
  Blocking failure:  [screen + assertion, or "none"]
```

## Examples

```bash
# Diff against dev, the normal in-workflow call
/oc-fe-regression-test dev

# Diff against a release branch
/oc-fe-regression-test release/18.0

# Explicit files, outside the diff
/oc-fe-regression-test --files src/srcProject/widgets/B2B/DunningPolicy/Form.tsx
```
