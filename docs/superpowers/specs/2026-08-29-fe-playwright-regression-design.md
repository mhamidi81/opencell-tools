# Frontend Playwright Regression Tests — Design

- **Date:** 2026-08-29
- **Repos touched:** `ccode-marketplace` (new plugin + wiring), `opencell-portal` (one-time bootstrap commit)
- **Status:** approved design, pending implementation plan

## 1. Problem

Frontend tickets currently gain Vitest coverage (`oc-fe-test-writer`) and then go
straight to commit and PR. Nothing exercises a **modified screen in a browser**, so a
change that passes unit tests can still break the rendered page — the regression class
this design targets.

Two facts constrain the solution:

1. **`opencell-portal` has no Playwright at all.** No `@playwright/test` dependency, no
   `playwright.config.*`, no `tests/` directory; `bitbucket-pipelines.yml` runs only
   `yarn test` (Vitest).
2. **The existing `/oc-fe-create-e2e-test` skill cannot serve this purpose.** It is
   driven by Jira acceptance criteria rather than by the diff, and it creates its own
   branch `test/[TICKET-NUMBER]` — so its output can never land in the fix branch's PR.
   It also instructs `npx playwright test`, which cannot work today (fact 1).

## 2. Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Specs run **mocked, against the Vite dev server**, with Keycloak stubbed | Deterministic, no backend or secrets, runnable in Bitbucket PR CI |
| D2 | Ship a **new plugin `oc-fe-regression-test`**; leave `/oc-fe-create-e2e-test` untouched | Diff-driven/same-branch vs. ticket-driven/own-branch are two different jobs; merging them would put two conflicting branch strategies in one skill |
| D3 | The step runs **directly after the Vitest step**, at every site where `oc-fe-test-writer` is dispatched | Uniform rule, and every one of those flows commits afterwards, so the specs land in the PR by construction |
| D4 | Playwright is **bootstrapped into `opencell-portal` now**, as its own commit | Chosen over a self-bootstrapping skill; the skill stays small and the setup is reviewable |
| D5 | On failure: **distinguish spec bug from app regression, block on the latter** | A generated spec must never be weakened to go green — that produces the coverage illusion this design exists to prevent |
| D6 | Specs assert **render + interaction**, no visual snapshots | Pixel baselines are font/OS-dependent between a dev machine and CI's docker image, and add PNG churn to every PR |

**Non-goals (explicitly out of scope):** visual/screenshot regression, live-environment
runs against real Keycloak, cross-browser matrices (chromium only), and any change to
`/oc-fe-calculate-ai-use` or `/oc-fe-create-e2e-test`.

## 3. Part A — `opencell-portal` bootstrap

A single commit on its own branch. **This part must be verified green before Part B is
written**, because everything in Part B assumes the harness boots.

### A1. Dependency and script

- devDependency `@playwright/test`, pinned to an exact version `X.Y.Z` (no caret). The CI
  docker image tag in A7 must be that same `X.Y.Z`, or the browser binaries and the runner
  disagree.
- `package.json` scripts: `"test:e2e": "playwright test"`, `"test:e2e:ui": "playwright test --ui"`.

### A2. `playwright.config.ts` (repo root)

- `testDir: './tests/e2e'`, `use.baseURL: 'http://localhost:3000'`.
- `webServer: { command: 'yarn start', url: 'http://localhost:3000', reuseExistingServer: !process.env.CI, timeout: 180_000 }`
  — `vite.config.js` already fixes the dev server to port 3000.
- Projects: chromium only.
- `retries: process.env.CI ? 2 : 0`, `trace: 'on-first-retry'`, `screenshot: 'only-on-failure'`,
  `reporter: [['html', { open: 'never' }], ['list']]`.
- `forbidOnly: !!process.env.CI`.

No conflict with Vitest: `vitest.config.ts` collects only `src/**/*.test.{ts,tsx,js,jsx}`,
so root-level `tests/e2e/**/*.spec.ts` is invisible to it. Playwright keeps `.spec.ts`
(its own convention), as the marketplace `CLAUDE.md` already documents.

### A3. `tests/support/app-boot.ts` — the boot fixture

The load-bearing piece. Exports an extended `test` whose `page` is already booted into an
authenticated, fully mocked SPA.

**Why the built-in flag is not enough.** `window.KEYCLOAK_BYPASS` exists
(`src/configuration/app/render.tsx:31`) but on its own the app **hangs on the loading
screen forever**: `src/user/hooks/usePermissionsKEYCLOAKAndSetProfile.tsx:29-31` returns
early when `preferredUsername` is absent, so `setUserProfile` never dispatches and
`src/configuration/layout/hoc/withConfigurationProvider.tsx:27-29` renders
`<GlobalLoadingScreen/>` indefinitely. The bypass branch inside that hook is unreachable
for the same reason and would throw at `jwt_decode(keycloak?.token)`.

The fixture therefore installs, in order:

1. **Runtime properties override** — `page.route('**/app-properties.js', …)` fulfilling a
   replacement script that sets `window._APP_PROPERTIES` with — and which must **not** set
   `PROJECT.LOCALE`, because `src/providers/i18nProvider.js:58-60` reads a bare,
   never-destructured `LOCALE` identifier, so any truthy value throws on boot (a real product
   bug, to be tracked separately rather than worked around in app code) —
   `SERVER_URL: 'http://localhost:3000'` and **`ASSETS_URL: '/'`**.
   `ASSETS_URL` is mandatory, not cosmetic: it becomes the browser-history `basename`
   (`src/providers/historyProvider.js:6`), and the shipped value
   `'/opencell/frontend/DEMO/portal/'` (`public/app-properties.js:35`) means no
   `http://localhost:3000/B2B/...` URL would route. The file is loaded at
   `index.html:36`, before `src/index.tsx` at `:81`, and it replaces the whole object —
   so an `addInitScript` that merely mutates `_APP_PROPERTIES` would be clobbered.
2. **`keycloak-js` module stub** — `page.route()` on the dep URL (glob tolerant of Vite's
   optimised path and hash, e.g. `**/keycloak-js*` and `**/deps/keycloak-js*`) fulfilled
   with a fake default-export class: `init()` resolves `true`; `token`, `tokenParsed`,
   `updateToken()`, `hasRealmRole()` are canned. This is the single choke point —
   `src/user/utils/keycloak.js:1` is the only import, `:37` the only `new Keycloak(...)`,
   and `getKeycloakInstance()` (`:77`) is what the rest of the app reads. No signature is verified
   client-side.

   **Correction, verified during implementation.** An earlier draft of this spec claimed the
   JWT shipped at `src/test-utils/mock/data/user/mockGetUser.js:78-80` was sufficient as-is.
   It is not. It carries 83 roles across `realm_access` and `resource_access`, but **neither
   `PORTAL_USER` nor `C_CARE`** — while `src/srcProject/layout/app-roles.json:165-166` gates
   the whole B2B layout on `oneOf:[PORTAL_USER], anyOf:[C_CARE,ADMIN,SALES]` and `:182` gates
   the `billing-accounts` read on `anyOf:[C_CARE,PORTAL_USER]`. `WithRoles` reads roles from
   `realm_access` only. The fixture therefore keeps the shipped token **byte-identical** as
   `BASE_JWT` and derives `MOCK_JWT` by re-encoding it with those two realm roles added.
   Without that, every B2B route renders `NotPermittedPage` and the smoke test is unreachable.
3. **`window.KEYCLOAK_BYPASS` must stay unset.** Setting it is actively harmful:
   `src/configuration/app/render.tsx:31-33` swaps `onAuthSuccess` for a stub when the flag
   is on, so `new Keycloak(...)` never runs, `getKeycloakInstance()` stays `null`,
   `getPreferredUsername()` (`src/user/utils/authentification.js:35-39`, which reads
   `jwtDecode(getKeycloakInstance()?.token)`) returns `undefined`, and the profile
   bootstrap deadlocks — the very hang described above. With the module stub of item 2 in
   place the **real** `onAuthSuccess` path runs end to end, which is what makes
   `preferredUsername` resolve. The 401 interceptor never fires because every API call is
   mocked.
4. **Default API mocks** — permissive catch-alls so nothing hangs, overridable per spec:
   - `page.route('**/opencell/api/**', …)` — covers 100% of business traffic. All of it
     funnels through `src/providers/dataProvider.js:125-131`
     (`${serverUrl}/opencell/api/rest/...`), plus the hand-built callers in
     `usePermissions.tsx:29`, `useLoadAppRolesConfiguration.tsx:42`,
     `useLoadAppVersionsConfiguration.tsx:22`, `useGlobalAppSettings.tsx:53,96`.
   - `page.route('**/maco/**', …)` — the `{maco}` provider prefix.
   - **Required for boot, not optional:** `GET **/opencell/api/rest/user?username=*` must
     return `{ actionStatus: { status: 'SUCCESS' }, user: { …, permission: […] } }`, and its
     `user.attributes` must be **non-empty** (`{ locale: 'en' }`). A literal `{}` survives
     lodash `get`'s default (`withConfigurationProvider.tsx:31-33` defaults only on `undefined`)
     and then trips `GlobalConfigProvider.tsx:19`'s `isEmpty` guard, which returns early and
     leaves `loaded` false — a permanently blank `#root` with no error.
     `usePermissionsKEYCLOAKAndSetProfile.tsx:52-75` awaits it before dispatching
     `setUserProfile`, and `withConfigurationProvider.tsx:27-29` holds the loading screen
     until that lands.
   - Blocked so the page settles: `https://chatbot.opencell.eu/**`
     (`public/app-properties.js:38`) and `https://unpkg.com/pdfjs-dist@**`
     (`index.html:85-86`).

Exported helper: `mockApi(page, pattern, body, status?)`, so a spec can override one
endpoint declaratively. Asserting on an outgoing request uses Playwright's own
`page.waitForRequest` — no wrapper of our own.

### A4. `tests/support/routes.ts` — URL construction

A helper encoding the URL formula (see §4.2) plus the page-suffix rules from
`src/utils/routing.js:167-172`, so specs read `screenUrl('B2B', 'billing-accounts', 'new')`
rather than hard-coded strings.

### A5. `tests/e2e/smoke/app-boot.spec.ts` — the verification gate

One spec that navigates to a real existing route (`/B2B/billing-accounts/list`), asserts
the global loading screen is gone and the datagrid renders. **This is the acceptance test
for the whole approach.** It must be green before any of Part B is written.

### A6. `.gitignore`

`test-results/`, `playwright-report/`, `blob-report/`, `tests/.auth/`.

### A7. CI — `bitbucket-pipelines.yml`

A second step alongside the existing Vitest step, on `mcr.microsoft.com/playwright:v<X.Y.Z>-jammy` (the exact `@playwright/test` version pinned in A1),
running `yarn install --frozen-lockfile && yarn test:e2e` with `HUSKY=0`. Added to the
`pull-requests: '**'` pipeline so a regression blocks the PR.

`eslint.config.mjs` may need `tests/**` added to its scope; if it flags the new files,
extend it in the same commit.

## 4. Part B — plugin `oc-fe-regression-test`

### 4.1 Layout

```
plugins/frontend/oc-fe-regression-test/
  .claude-plugin/plugin.json              # name, description, version 1.0.0
  skills/oc-fe-regression-test/SKILL.md
```

No new agent. `oc-fe-e2e-expert` (in `oc-fe-create-e2e-test`) is reused via
`subagent_type: oc-fe-create-e2e-test:oc-fe-e2e-expert` — it already carries the AI-stats
manifest and snapshot contract (its `.md`, lines 309-340) and already writes to
`tests/e2e/**`.

`argument-hint`: `[BASE-BRANCH] [--files <paths>]` (defaults `dev`).

### 4.2 Skill flow

**Step 1 — Resolve the changed source files.**
`git diff --name-only [BASE-BRANCH]...HEAD` (plus unstaged/untracked, so it also works
before a commit). Keep `src/**` `.ts`/`.tsx`; drop `*.test.*`, `__tests__/`, i18n JSON,
`tests/`, config. If `--files` is given, use exactly those. If nothing survives, report
"no screen-level change" and exit 0 — this is a normal outcome, not a failure.

**Step 2 — Map changed files to screens.** There is **no route table**; routes are derived
at runtime by `src/components/App/Resource/Resource.tsx:87-166` from module configs. The
URL is

```
/<layout modulePath>/<inMenu.path?>/<module resource>/<pages key>
```

built by `src/configuration/layout/utils/buildModules.js:6-20`. Only the literal keys
`list` / `show` / `edit` / `create` become React-Admin pages with the suffixes in
`src/utils/routing.js:167-172`; **every other `pages` key is mounted verbatim** at
`` `${match.url}/${key}` `` (`Resource.tsx:93`), and in practice all ten layouts use
`PATH_CREATE = 'new'` and `PATH_EDIT = ':id/modify'` from their `url-helper.js`.

Reverse lookup, changed file → URL:

1. Walk up to `src/srcProject/widgets/<DOMAIN>/<FEATURE>/index.ts`; read the exported
   component names.
2. Grep those names in `src/components/GenericRenderer/Widgets/defaultWidgets.ts`
   (~297 registered widgets) to get the registry constant.
3. Resolve that constant in `src/constants/generic.js` to its string literal
   (e.g. `B2B_DUNNING_POLICY_CREATE = 'CreateDunningPolicy'`).
4. Grep the literal in `src/srcProject/layout/**` page descriptors
   (`"type": "<name>"` in the `*.json` page files, or `type: '<name>'` in `create.js`/`list.js`).
5. The descriptor's directory `index.js` gives `resource`, the `pages` keys and
   `inMenu.path`; the layout root gives `modulePath`.
6. Compose the URL.

Worked example already in the repo:
`src/srcProject/layout/B2B/modules/apollo2/billing-accounts/__tests__/create-billing-account-route.test.ts:36-43`.
Nested resources produce composite keys such as `:billingAccountsID/subscriptions/list`
(`buildModules.js:22-56`).

If a changed file resolves to no screen (a shared hook, a mapper, a util), report it as
"covered by Vitest only" and skip it rather than inventing a route.

**Step 3 — AI-stats run directory.** Reuse the run's existing
`.claude/cache/ai-stats/[RUN_ID]/` (the orchestrator created it); otherwise derive
`[RUN_ID] = {TICKET or "regression"}-{yyyymmdd-HHMMSS}`. Non-blocking.

**Step 4 — Dispatch `oc-fe-e2e-expert`** with: the changed files, the resolved screens and
URLs, the boot-fixture contract from §3.A3, the locator strategy (§4.3), the failure
policy (§4.4), and the manifest line —
`"Write your file manifest to .claude/cache/ai-stats/[RUN_ID]/e2e.json per your manifest
instructions, then snapshot your first pass to snapshots/<PHASE>.diff."` — with `<PHASE>`
  resolved before dispatch (`e2e`, else `e2e-2`, `e2e-3`, …) and used for BOTH files
(use `e2e-2.json`, `e2e-3.json`, … if the phase file already exists).

**Step 5 — Snapshot fallback.** Same block already used by the other four skills:
`git add -N -- <files> && git diff HEAD -- <files> > …/snapshots/<phase>.diff`, executed
**before** any edit of the agent's files. Best-effort, non-blocking. **The `<phase>` must be
whichever manifest name Step 4 chose** (`e2e`, `e2e-2`, …), never a hardcoded `e2e`: the run
directory is shared by ticket prefix with `/oc-fe-create-e2e-test`, which writes the same phase
name, so a fixed filename would silently clobber that run's first-pass snapshot and make its
retention unmeasurable.

**Step 6 — Report and gate** (§4.4).

**Step 7 — Jira tag.** Append `ai_test_front_dev` to `customfield_10613`, using the
read-then-append protocol from the root `CLAUDE.md` (read the array first, skip the write
if the read fails, never send a bare string or single-element array). Resolve the ticket
from the branch name — the skill takes **no ticket argument**, its interface being
`[BASE-BRANCH]` and `--files` only, matching how the sibling `/oc-fe-write-tests` resolves
its own ticket. Skip silently if unresolvable or if no spec was written.

### 4.3 Spec conventions

- Location `tests/e2e/[DOMAIN]/[FEATURE].spec.ts`, page object `tests/pages/[Feature]Page.ts`
  — matching the layout `oc-fe-e2e-expert` already documents and the `e2e` category that
  `/oc-fe-calculate-ai-use` already recognises.
- Per screen: navigate via the boot fixture, assert the screen's key landmarks render,
  then drive the specific interaction the diff touched and assert the resulting DOM state
  and outgoing request.
- **Locators.** Hand-written `data-testid` is nearly absent in widget source (6 occurrences
  across 2 files). The reliable mechanism is the auto-generated one from the `WithTest` HOC
  (`src/components/GenericRenderer/Form/InputRenderer/withTest.tsx:12-16`, composed at
  `InputRenderer.tsx:1355`): every JSON-declared field is addressable as
  `[data-testid="<resource>-<source>-<type>"]`. Prefer that, then `getByRole`/`getByLabel`.
  **Generated specs must not require edits to widget source** to become testable.
- Forbidden: `page.waitForTimeout()`, CSS-structure selectors, cross-test shared state.

### 4.4 Failure policy (D5)

The agent runs `yarn test:e2e` on the specs it wrote and may iterate **at most 3 times** on
its own defects (wrong locator, wrong mock shape, missing await). Then:

- **All green** → report and continue.
- **Still red, cause is the spec** → report honestly as "could not produce a reliable spec
  for `<screen>`", leave the spec out rather than committing a broken one, and continue.
- **Still red, cause is the application** → **stop the workflow** and report the regression
  with the failing assertion and trace path. Do not commit, do not proceed to PR.

Explicitly prohibited: deleting an assertion, replacing it with a weaker one, or adding
`test.skip`/`test.fixme` to reach green. Escalating a genuine failure is the desired
outcome, not a workflow error.

## 5. Part C — wiring

The same block is inserted **immediately after the Vitest step** in four skills:

| Skill | Vitest dispatch at | New step |
|-------|--------------------|----------|
| `plugins/frontend/oc-fe-fix-bug/skills/oc-fe-fix-bug/SKILL.md` | line 153 | after Step 6, before the `ai_Dev_Front` step |
| `plugins/frontend/oc-fe-create-ui/skills/oc-fe-create-ui/SKILL.md` | line 171 | after Step 7, before the `ai_Dev_Front` step |
| `plugins/frontend/oc-fe-fix-pr/skills/oc-fe-fix-pr/SKILL.md` | line 158 | after Step 8, before "Commit & Push" |
| `plugins/frontend/oc-fe-test-writer/skills/oc-fe-write-tests/SKILL.md` | line 77 | after Step 4, before the tag step |

Each block: state the base branch to diff against, invoke the regression step, honour the
blocking gate, and note that it is skipped outside `opencell-portal`. `/oc-fe-fix-pr`
passes `[PR-DEST-BRANCH]`; the others pass `[BASE-BRANCH]`.

Because `/oc-commit` and `/oc-pull-request` run after these steps in every flow, the specs
are part of the PR without touching either skill.

## 6. Part D — docs and registry

- `.claude-plugin/marketplace.json`: new entry, `"source": "./plugins/frontend/oc-fe-regression-test"`.
- `README.md`: row after line 40.
- Root `CLAUDE.md`: add `/oc-fe-regression-test` to the plugin-type list and the workflow
  chain; state the "directly after Vitest" rule and the blocking gate; note that the
  portal keeps Playwright specs at `tests/e2e/**/*.spec.ts`.

**No change to `/oc-fe-calculate-ai-use`.** It already classifies `tests/e2e/**` as the
`e2e` category (its `category()` checks e2e before unit tests precisely because a
Playwright file is also a `*.spec.ts`), already counts Playwright blocks into
`artifacts.e2e`, and already suggests `ai_test_front_dev` when `e2e.added > 0`.

## 7. Risks

| Risk | Mitigation |
|------|------------|
| ~~The `keycloak-js` route stub is fragile against Vite's optimised dep URL~~ — **did not materialise** | The `/keycloak-js/` RegExp matched the optimised-dep URL as written. The Vite-alias fallback was not needed and `vite.config.js` is untouched. Risk closed. |
| Screen resolution (§4.2) fails for widgets reached only through nested resources or non-standard descriptors | The skill reports "no screen resolved" and skips, rather than guessing a URL |
| Dev-server boot makes CI slow | Chromium only, changed screens only, `reuseExistingServer` locally |
| A permissive default API mock hides a real integration break | The default exists so the page settles; each generated spec overrides the endpoints its screen actually calls and asserts on them |

## 8. Verification

1. `yarn test:e2e` green on the A5 smoke spec in `opencell-portal` (gate for Part B).
2. The same command green in the Playwright docker image, matching CI.
3. A dry run of `/oc-fe-regression-test dev` on a branch with a real widget change:
   correct screen resolved, spec written under `tests/e2e/`, run green, `e2e.json` and
   `snapshots/<PHASE>.diff` present in the run directory, sharing the manifest's `<PHASE>`.
4. `/oc-fe-calculate-ai-use --run` on that branch reports a non-zero `e2e` category and
   `e2eAdd` count.
