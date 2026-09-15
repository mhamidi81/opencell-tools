# Frontend Playwright Regression Tests — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every frontend workflow that writes Vitest tests then writes and runs Playwright regression specs for the screens the diff touched, so those specs land in the pull request.

**Architecture:** Two repos, in order. Phase 1 bootstraps Playwright inside `opencell-portal`: a boot fixture stubs the `keycloak-js` module and the runtime properties file so the SPA boots against the Vite dev server with every API mocked. Phase 2 adds a marketplace plugin `oc-fe-regression-test` whose skill maps a git diff to screen URLs and dispatches the existing `oc-fe-e2e-expert` agent, and wires that step into the four skills that dispatch `oc-fe-test-writer`.

**Tech Stack:** Playwright (`@playwright/test`), Vite 5 dev server, React 17 + React-Admin (`ra-core`) + react-router v5, Keycloak (stubbed), Claude Code plugin markdown/JSON.

**Spec:** `docs/superpowers/specs/2026-08-29-fe-playwright-regression-design.md`

## Global Constraints

- **Two repos, two branches.** Phase 1 in `/home/mhamidi/workspace/oc/portal/source/opencell-portal`, branched from `dev`. Phase 2 in `/home/mhamidi/workspace/oc/ai/marketplace/ccode-marketplace`, branched from `main`. Never mix them in one commit.
- **Phase 1 gate.** Task 2 must be green before Task 5 starts. If the `keycloak-js` stub cannot be made to work, stop and report — do not start Phase 2 on an unproven harness.
- **Playwright version is pinned exactly** (no caret). The `mcr.microsoft.com/playwright` image tag in Task 4 must be that same `X.Y.Z`.
- **`window.KEYCLOAK_BYPASS` must stay unset.** `src/configuration/app/render.tsx:31-33` replaces `onAuthSuccess` with a stub when it is on, so `new Keycloak(...)` never runs and the app deadlocks on `<GlobalLoadingScreen/>`. The stub in Task 2 exists precisely so the *real* auth path runs.
- **Vitest vs Playwright naming.** Portal unit tests are `src/**/*.test.{ts,tsx}` (`vitest.config.ts` collects nothing else). Playwright specs are `tests/e2e/**/*.spec.ts` at the repo root — invisible to Vitest, and the extension Playwright expects. Never rename either.
- **`customfield_10613` is append-only.** Read the existing array with `getJiraIssue` first, write back every existing value plus the new one; skip the write entirely if the read fails.
- **Commit conventions.** Portal: `INTRD-XXXXX: [Front] <summary>` on branch `mhamidi/feature/dev/INTRD-XXXXX-<slug>`. If no Jira ticket is available for this bootstrap, use branch `mhamidi/feature/dev/e2e-playwright-bootstrap` and drop the ticket prefix from the subject. Marketplace: `<plugin-name> <version>: <summary>` and keep the `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` trailer (44 of the last 50 commits carry it).
- **Never weaken a failing assertion.** No `test.skip`, no `test.fixme`, no deleted expectation to reach green. A genuine app failure is the deliverable, not an obstacle.

---

# Phase 1 — `opencell-portal` bootstrap

Working directory for every Phase 1 task:
`/home/mhamidi/workspace/oc/portal/source/opencell-portal`

### Task 1: Install Playwright and configure the runner

**Files:**
- Modify: `package.json` (devDependencies, scripts)
- Modify: `vite.config.js:57-62` (the `server` block)
- Create: `playwright.config.ts`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: the `yarn test:e2e` script; `playwright.config.ts` exporting a config with `testDir: './tests/e2e'` and `use.baseURL: 'http://localhost:3000'`; the env var `E2E=1` set by the webServer, which `vite.config.js` reads.

- [ ] **Step 1: Create the branch**

```bash
cd /home/mhamidi/workspace/oc/portal/source/opencell-portal
git checkout dev && git pull
git checkout -b mhamidi/feature/dev/e2e-playwright-bootstrap
```

- [ ] **Step 2: Install Playwright, pinned exactly**

```bash
yarn add -D --exact @playwright/test
npx playwright install --with-deps chromium
node -p "require('./package.json').devDependencies['@playwright/test']"
```

Record the printed version as `X.Y.Z`. It has no caret. You need it again in Task 4.

- [ ] **Step 3: Add the scripts**

In `package.json`, next to the existing `"test": "vitest run"`:

```json
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui"
```

- [ ] **Step 4: Stop the dev server opening a browser under Playwright**

`vite.config.js` currently has `server: { open: true, port: 3000 }`. Under Playwright's
`webServer` that pops a real browser on every run and breaks CI. Change the `server` block to:

```js
    server: {
      // this ensures that the browser opens upon server start — except under
      // Playwright, whose webServer sets E2E=1 and drives its own browser
      open: process.env.E2E !== '1',
      // this sets a default port to 3000
      port: 3000
    },
```

- [ ] **Step 5: Write `playwright.config.ts`**

```ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [['html', { open: 'never' }], ['list']],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off'
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'yarn start',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: { E2E: '1' }
  }
});
```

- [ ] **Step 6: Ignore Playwright output**

Append to `.gitignore`, under the existing `# testing` group:

```
# playwright
/test-results
/playwright-report
/blob-report
/tests/.auth
```

- [ ] **Step 7: Verify the runner starts and finds no tests yet**

Run: `yarn test:e2e --list`

`tests/` does not exist yet, so Playwright reports "no tests found" and **exits non-zero.
That is the expected result at this point** — do not create a placeholder spec to make it
exit 0, and do not treat it as a failure.

The binding assertions for this step are:
1. Playwright starts and prints its own "no tests found" error — not a config parse error,
   not a missing-module error.
2. **No browser window opens.** If one does, Step 4 did not take effect — check that
   `webServer.env` sets `E2E` and that `vite.config.js` reads `process.env.E2E`.

- [ ] **Step 8: Commit**

```bash
git add package.json yarn.lock playwright.config.ts vite.config.js .gitignore
git commit -m "[Front] Add Playwright test runner and configuration"
```

---

### Task 2: The boot fixture and the smoke spec — **the gate**

This is the load-bearing task. Its acceptance criterion is a real browser reaching a real
route with no Keycloak server.

**Files:**
- Create: `tests/support/app-boot.ts`
- Create: `tests/e2e/smoke/app-boot.spec.ts`

**Interfaces:**
- Consumes: `playwright.config.ts` from Task 1.
- Produces:
  - `export const MOCK_JWT: string`
  - `export const installAppBoot(page: Page, overrides?: { serverUrl?: string }): Promise<void>`
  - `export const test` — a `@playwright/test` fixture exposing `appPage: Page`, already booted
  - `export { expect }`

- [ ] **Step 1: Write the failing smoke spec first**

Create `tests/e2e/smoke/app-boot.spec.ts`:

```ts
import { expect, test } from '../../support/app-boot';

test.describe('application boot', () => {
  test('reaches the B2B billing-accounts list with no Keycloak server', async ({
    appPage
  }) => {
    await appPage.goto('/B2B/billing-accounts/list');

    // index.html renders #ipl-progress-indicator as the loading screen and the app
    // removes it once currentUser.profile is set. Its disappearance is the single
    // honest proof that the whole auth + profile bootstrap completed.
    await expect(appPage.locator('#ipl-progress-indicator')).toBeHidden({
      timeout: 60_000
    });

    // The SPA actually mounted something.
    await expect(appPage.locator('#root')).not.toBeEmpty();

    // We are on the route we asked for — no Keycloak redirect happened.
    await expect(appPage).toHaveURL(/\/B2B\/billing-accounts\/list$/);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `yarn test:e2e tests/e2e/smoke/app-boot.spec.ts`
Expected: FAIL — `Cannot find module '../../support/app-boot'`.

- [ ] **Step 3: Extract the mock JWT**

The portal already ships a usable token. Copy the single-quoted string passed to
`setToken(...)` at `src/test-utils/mock/data/user/mockGetUser.js:78` verbatim.

Verify what it decodes to before using it:

```bash
node -e "const t=require('fs').readFileSync('src/test-utils/mock/data/user/mockGetUser.js','utf8').match(/setToken\(\s*'([^']+)'/)[1]; const p=JSON.parse(Buffer.from(t.split('.')[1],'base64').toString()); console.log(p.preferred_username, p.locale, JSON.stringify(p.realm_access));"
```

Expected output: `opencell.admin en {"roles":["SUPER_ADMIN"]}`.
No signature is verified client-side, so an expired token is fine.

- [ ] **Step 4: Write `tests/support/app-boot.ts`**

```ts
import { test as base, expect, Page } from '@playwright/test';

/**
 * Token copied from src/test-utils/mock/data/user/mockGetUser.js:78.
 * Decodes to preferred_username "opencell.admin", locale "en",
 * realm_access.roles ["SUPER_ADMIN"]. Nothing verifies its signature in the browser.
 */
export const MOCK_JWT = '<paste the token from Step 3 here>';

const DEV_ORIGIN = 'http://localhost:3000';

/**
 * Replacement for public/app-properties.js.
 *
 * Two values differ from the shipped file and both are mandatory:
 *  - ASSETS_URL: '/'  — it becomes the router basename (src/providers/historyProvider.js:6).
 *    With the shipped '/opencell/frontend/DEMO/portal/', no http://localhost:3000/B2B/...
 *    URL resolves at all.
 *  - SERVER_URL: the dev origin — so every API call is same-origin and one route glob
 *    catches it.
 * The script REPLACES window._APP_PROPERTIES wholesale, exactly as the real file does
 * (index.html:36 runs after the inline script at index.html:7-21).
 */
const appPropertiesScript = (serverUrl: string) =>
  `window._APP_PROPERTIES = ${JSON.stringify({
    KEYCLOAK_CLIENT_ID: 'opencell-portal',
    KEYCLOAK_APP_REALM: 'opencell',
    KEYCLOAK_APP_AUTH_URL: '/auth',
    KEYCLOAK_APP_TOKEN_REFRESH_RATE: 270000,
    ASSETS_URL: '/',
    SERVER_URL: serverUrl,
    CHATBOT_URL: '',
    PROJECT: {
      LOGO_NAME: 'logo.svg',
      DEFAULT_APP_NAME: 'B2B-customer-care',
      HIDE_ALL_MENU_ICON: true,
      THEME: {
        PRIMARY: {
          MAIN_COLOR: '#B41D0A',
          LIGHT_COLOR: '#EB5048',
          DARK_COLOR: '#8f1404'
        }
      },
      CUSTOM_THEME: { ENABLE_RGAA: false },
      REGISTERED_LANGUAGES: 'en;fr',
      BREADCRUMBS: { MAX_ITEMS: 5, ITEMS_AFTER_COLLAPSE: 2 },
      AUTO_CLOSE_LEFT_MENU: true,
      APP_ROLES_CONFIGURATION_FILE_PATH: '',
      VERSIONS_CONFIGURATION_FILE_PATH: '',
      DEFAULT_LOCALE: 'en',
      LOCALE: 'en',
      TIMEZONE: 'Europe/Paris'
    },
    QUERY_BUILDER_EXECUTION_LIMIT: 10000,
    QUERY_BUILDER_EXECUTION_LIMIT_DOWNLOAD: 1000
  })};`;

/**
 * ES-module replacement for keycloak-js.
 *
 * src/user/utils/keycloak.js:1 is the only import of the package, :37 the only
 * `new Keycloak(...)`, and getKeycloakInstance() (:80) is what the whole app reads —
 * so this class is the single choke point for auth. init() resolving `true` lets the
 * real onAuthSuccess path run, which is what makes getPreferredUsername()
 * (src/user/utils/authentification.js:35-39) resolve.
 *
 * Built by concatenation rather than one template literal so the token interpolation
 * cannot collide with the stub's own `${}` usage.
 */
const keycloakStubModule = (token: string) =>
  [
    "const TOKEN = '" + token + "';",
    "const tokenParsed = JSON.parse(",
    "  decodeURIComponent(escape(atob(TOKEN.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))))",
    ');',
    'export default class Keycloak {',
    '  constructor(options) {',
    '    this.options = options;',
    '    this.authenticated = true;',
    '    this.token = TOKEN;',
    '    this.tokenParsed = tokenParsed;',
    '    this.idToken = TOKEN;',
    '    this.idTokenParsed = tokenParsed;',
    '    this.refreshToken = TOKEN;',
    '    this.subject = tokenParsed.sub;',
    '    this.realmAccess = tokenParsed.realm_access;',
    '    this.resourceAccess = tokenParsed.resource_access;',
    '  }',
    '  init() { return Promise.resolve(true); }',
    '  login() { return Promise.resolve(); }',
    '  logout() { return Promise.resolve(); }',
    '  register() { return Promise.resolve(); }',
    '  accountManagement() { return Promise.resolve(); }',
    '  updateToken() { return Promise.resolve(false); }',
    '  clearToken() {}',
    '  isTokenExpired() { return false; }',
    '  createLoginUrl() { return window.location.href; }',
    '  createLogoutUrl() { return window.location.href; }',
    '  createAccountUrl() { return window.location.href; }',
    '  hasRealmRole(role) {',
    '    return ((tokenParsed.realm_access || {}).roles || []).indexOf(role) !== -1;',
    '  }',
    '  hasResourceRole(role, client) {',
    '    const res = (tokenParsed.resource_access || {})[client] || {};',
    '    return (res.roles || []).indexOf(role) !== -1;',
    '  }',
    '}'
  ].join('\n');

/** The user payload usePermissionsKEYCLOAKAndSetProfile.tsx:52-75 awaits before it
 *  dispatches setUserProfile. Until it lands, withConfigurationProvider.tsx:27-29
 *  holds the loading screen. */
const USER_RESPONSE = {
  actionStatus: { status: 'SUCCESS' },
  user: {
    username: 'opencell.admin',
    firstName: 'Opencell',
    lastName: 'Admin',
    email: 'opencell.admin@opencellsoft.com',
    userLevel: null,
    attributes: {},
    permission: ['SUPER_ADMIN']
  }
};

/**
 * Installs everything the SPA needs to boot with no backend and no Keycloak.
 *
 * Playwright matches route handlers in REVERSE registration order (most recently
 * registered wins), so the broad catch-all is registered FIRST and the specific
 * endpoints after it.
 */
export const installAppBoot = async (
  page: Page,
  overrides: { serverUrl?: string } = {}
): Promise<void> => {
  const serverUrl = overrides.serverUrl ?? DEV_ORIGIN;

  // 1. Catch-all for business API traffic. Everything funnels through
  //    src/providers/dataProvider.js:125-131 as `${SERVER_URL}/opencell/api/rest/...`.
  await page.route('**/opencell/api/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: [], total: 0 })
    })
  );

  // 2. The {maco} provider prefix.
  await page.route('**/maco/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ data: [], total: 0 })
    })
  );

  // 3. Required for boot — registered after the catch-all so it wins.
  await page.route('**/opencell/api/rest/user*', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(USER_RESPONSE)
    })
  );

  // 4. Runtime properties (index.html:36).
  await page.route('**/app-properties.js', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/javascript',
      body: appPropertiesScript(serverUrl)
    })
  );

  // 5. The keycloak-js module. A RegExp, not a glob: Vite serves it from
  //    /node_modules/.vite/deps/keycloak-js.js?v=<hash>.
  await page.route(/keycloak-js/, (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/javascript',
      body: keycloakStubModule(MOCK_JWT)
    })
  );

  // 6. Third-party scripts that would otherwise keep the page busy.
  await page.route('https://chatbot.opencell.eu/**', (route) => route.abort());
  await page.route('https://unpkg.com/**', (route) => route.abort());
};

/** Per-spec override: answer one endpoint with a specific body. Register it inside the
 *  test — later registration wins over installAppBoot's catch-all. */
export const mockApi = async (
  page: Page,
  urlPattern: string | RegExp,
  body: unknown,
  status = 200
): Promise<void> => {
  await page.route(urlPattern, (route) =>
    route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body)
    })
  );
};

export const test = base.extend<{ appPage: Page }>({
  appPage: async ({ page }, use) => {
    await installAppBoot(page);
    await use(page);
  }
});

export { expect };
```

- [ ] **Step 5: Substitute the real token (scripted — do not paste by hand)**

```bash
node - <<'JS'
const fs = require('fs');
const src = fs.readFileSync('src/test-utils/mock/data/user/mockGetUser.js', 'utf8');
const token = src.match(/setToken\(\s*'([^']+)'/)[1];
const fixture = 'tests/support/app-boot.ts';
const out = fs.readFileSync(fixture, 'utf8')
  .replace("'<paste the token from Step 3 here>'", JSON.stringify(token).replace(/"/g, "'"));
fs.writeFileSync(fixture, out);
const parsed = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
console.log('token written for', parsed.preferred_username);
JS
grep -c "paste the token" tests/support/app-boot.ts
```

Expected: `token written for opencell.admin`, then `0` (grep finds no placeholder left).

- [ ] **Step 6: Run the smoke spec**

Run: `yarn test:e2e tests/e2e/smoke/app-boot.spec.ts`
Expected: PASS.

- [ ] **Step 7: If it fails, debug in this order — do not skip ahead**

Run `yarn test:e2e tests/e2e/smoke/app-boot.spec.ts --headed --debug` and check, in order:

1. **Did the keycloak stub load?** In the browser console, `window._APP_PROPERTIES.ASSETS_URL`
   should be `'/'`. If it is `'/opencell/frontend/DEMO/portal/'`, the `app-properties.js`
   route did not match — widen the pattern to `/app-properties\.js/`.
2. **Redirected to a Keycloak login URL?** The `keycloak-js` route did not match. Print the
   requests with `page.on('request', r => console.log(r.url()))` and match the real dep URL.
   **Fallback if the route cannot be made to match:** add a test-only alias in
   `vite.config.js` — `resolve: { alias: process.env.E2E === '1' ? { 'keycloak-js': path.resolve(__dirname, 'tests/support/keycloak-stub.ts') } : {} }` —
   and move the stub class into that file. This is the documented fallback in spec §7; take
   it rather than fighting the glob.
3. **Stuck on the loading screen?** The profile never arrived. Confirm the `/rest/user`
   route matched the real request (it carries `?username=opencell.admin`), and that
   `window.KEYCLOAK_BYPASS` is `undefined` — if something set it, boot is short-circuited
   by `render.tsx:31-33` and will hang forever.

- [ ] **Step 8: Strengthen the assertion with a real landmark**

Once green, capture what actually rendered:

```bash
npx playwright test tests/e2e/smoke/app-boot.spec.ts --trace on
npx playwright show-trace test-results/*/trace.zip
```

Pick one stable, visible element of the list screen (a heading, the breadcrumb, or the
datagrid container) and add one assertion for it to the spec, replacing nothing that is
already there. Re-run and confirm PASS.

- [ ] **Step 9: Commit**

```bash
git add tests/support/app-boot.ts tests/e2e/smoke/app-boot.spec.ts
git commit -m "[Front] Add Playwright boot fixture and application smoke test"
```

---

### Task 3: Screen-URL helper

**Files:**
- Create: `tests/support/routes.ts`
- Create: `tests/support/__checks__/routes.check.spec.ts`

**Interfaces:**
- Consumes: nothing from Task 2 (pure string helper).
- Produces: `export const screenUrl(modulePath: string, resource: string, pageKey?: string, opts?: { menuPath?: string; id?: string }): string`

- [ ] **Step 1: Write the failing check spec**

Create `tests/support/__checks__/routes.check.spec.ts`. It is a Playwright spec with no
browser use — it guards the URL formula that every generated spec depends on.

```ts
import { expect, test } from '@playwright/test';
import { screenUrl } from '../routes';

test.describe('screenUrl', () => {
  test('builds a list URL', () => {
    expect(screenUrl('B2B', 'billing-accounts', 'list')).toBe(
      '/B2B/billing-accounts/list'
    );
  });

  test('defaults to the list page', () => {
    expect(screenUrl('B2B', 'billing-accounts')).toBe(
      '/B2B/billing-accounts/list'
    );
  });

  test('passes a custom page key through verbatim', () => {
    // All ten layouts use PATH_CREATE = 'new' from their url-helper.js, which
    // Resource.tsx:93 mounts verbatim rather than through React-Admin.
    expect(screenUrl('B2B', 'billing-accounts', 'new')).toBe(
      '/B2B/billing-accounts/new'
    );
    expect(screenUrl('B2B', 'billing-accounts', 'new-billing-account')).toBe(
      '/B2B/billing-accounts/new-billing-account'
    );
  });

  test('substitutes :id when an id is given', () => {
    expect(screenUrl('B2B', 'billing-accounts', ':id/modify', { id: 'BA1' })).toBe(
      '/B2B/billing-accounts/BA1/modify'
    );
  });

  test('inserts the inMenu path segment', () => {
    // src/srcProject/layout/B2B/modules/dunning-policies/index.js:16-34
    expect(
      screenUrl('B2B', 'dunning-policies', 'list', { menuPath: 'dunning' })
    ).toBe('/B2B/dunning/dunning-policies/list');
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `yarn test:e2e tests/support/__checks__/routes.check.spec.ts`
Expected: FAIL — `Cannot find module '../routes'`.

- [ ] **Step 3: Implement `tests/support/routes.ts`**

```ts
/**
 * Screen URLs are not declared anywhere — they are derived at runtime from module
 * configs by src/components/App/Resource/Resource.tsx:87-166. The formula, from
 * src/configuration/layout/utils/buildModules.js:6-20, is:
 *
 *   /<layout modulePath>/<inMenu.path?>/<module resource>/<pages key>
 *
 * Only the literal keys list | show | edit | create become React-Admin pages with the
 * suffixes in src/utils/routing.js:167-172. Every other `pages` key is mounted verbatim
 * at `${match.url}/${key}` (Resource.tsx:93) — and in practice all ten layouts use the
 * custom keys 'new' and ':id/modify' from their url-helper.js.
 */
export const screenUrl = (
  modulePath: string,
  resource: string,
  pageKey = 'list',
  opts: { menuPath?: string; id?: string } = {}
): string => {
  const segments = [modulePath, opts.menuPath, resource, pageKey]
    .filter((segment): segment is string => Boolean(segment))
    .join('/');

  const withId = opts.id ? segments.replace(':id', opts.id) : segments;

  return `/${withId}`;
};
```

- [ ] **Step 4: Run the check spec**

Run: `yarn test:e2e tests/support/__checks__/routes.check.spec.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Point the config at the checks directory**

`playwright.config.ts` has `testDir: './tests/e2e'`, so the check spec above is not
collected. Change `testDir` to `'./tests'` and add `testMatch: ['e2e/**/*.spec.ts', 'support/__checks__/*.spec.ts']`.

Run: `yarn test:e2e`
Expected: PASS — both the smoke spec and the 5 route checks run.

- [ ] **Step 6: Commit**

```bash
git add tests/support/routes.ts tests/support/__checks__/routes.check.spec.ts playwright.config.ts
git commit -m "[Front] Add screen-URL helper for Playwright specs"
```

---

### Task 4: Run the specs in CI

**Files:**
- Modify: `bitbucket-pipelines.yml`

**Interfaces:**
- Consumes: `yarn test:e2e` from Task 1; version `X.Y.Z` from Task 1 Step 2.
- Produces: an `e2e` pipeline step that runs on every pull request.

- [ ] **Step 1: Add the step definition**

In `bitbucket-pipelines.yml`, after the existing `- step: &test` block, add the block below
**verbatim, keeping the literal `vX.Y.Z`** — Step 3 substitutes the real version by script.
Do not hand-substitute it here, or Step 3's replacement silently finds nothing:

```yaml
    - step: &e2e
        name: E2E (Playwright)
        image: mcr.microsoft.com/playwright:vX.Y.Z-jammy
        caches:
          - node
        script:
          # Skip Husky git-hook installation in CI (no commits happen here).
          - export HUSKY=0
          - yarn install --frozen-lockfile
          - yarn test:e2e
        artifacts:
          - playwright-report/**
          - test-results/**
```

- [ ] **Step 2: Add it to the pull-request pipeline**

```yaml
pipelines:
  pull-requests:
    '**':
      - step: *test
      - step: *e2e
```

- [ ] **Step 3: Substitute the real version into the image tag (scripted)**

```bash
node - <<'JS'
const fs = require('fs');
const v = require('./package.json').devDependencies['@playwright/test'].replace(/^[^0-9]*/, '');
const f = 'bitbucket-pipelines.yml';
fs.writeFileSync(f, fs.readFileSync(f, 'utf8').replace('playwright:vX.Y.Z-jammy', `playwright:v${v}-jammy`));
console.log('pinned image to v' + v);
JS
grep -o 'playwright:v[0-9.]*' bitbucket-pipelines.yml
node -p "'v' + require('./package.json').devDependencies['@playwright/test']"
```

Expected: the last two lines print the identical version string. If they differ, the image's
browser binaries and the test runner disagree and every CI run fails with a version mismatch.

- [ ] **Step 3b: Make ESLint aware of the new directory**

`eslint.config.mjs` was written before `tests/` existed. Check whether it flags the new files:

```bash
npx eslint tests/ --ext .ts
```

If it reports parser or `no-undef` errors on Playwright globals, add a block scoping
`tests/**/*.ts` to the TypeScript parser with `globals: { ...globals.node }`. If it reports
nothing, or ignores the directory entirely, change nothing — do not restructure the config to
suit this plan.

- [ ] **Step 4: Verify the YAML parses**

```bash
python3 -c "import yaml,sys; yaml.safe_load(open('bitbucket-pipelines.yml')); print('valid')"
```

Expected: `valid`.

- [ ] **Step 5: Commit and push**

```bash
git add bitbucket-pipelines.yml
git commit -m "[Front] Run Playwright specs on pull requests"
git push -u origin mhamidi/feature/dev/e2e-playwright-bootstrap
```

- [ ] **Step 6: Confirm the pipeline is green before Phase 2**

Open the pipeline for the pushed branch. The `E2E (Playwright)` step must pass. If it fails
only in CI, reproduce locally in the same image before changing anything:

```bash
docker run --rm -v "$PWD":/w -w /w mcr.microsoft.com/playwright:vX.Y.Z-jammy \
  bash -c "export HUSKY=0 && yarn install --frozen-lockfile && yarn test:e2e"
```

---

# Phase 2 — marketplace plugin

Working directory for every Phase 2 task:
`/home/mhamidi/workspace/oc/ai/marketplace/ccode-marketplace`

**Do not start until Task 2 and Task 4 are green.**

### Task 5: Plugin scaffold and registry entry

**Files:**
- Create: `plugins/frontend/oc-fe-regression-test/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

**Interfaces:**
- Consumes: nothing.
- Produces: plugin name `oc-fe-regression-test`, discoverable from the marketplace.

- [ ] **Step 1: Create the branch**

```bash
cd /home/mhamidi/workspace/oc/ai/marketplace/ccode-marketplace
git checkout main && git pull
git checkout -b feature/oc-fe-regression-test
```

- [ ] **Step 2: Write the plugin manifest**

Create `plugins/frontend/oc-fe-regression-test/.claude-plugin/plugin.json`:

```json
{
  "name": "oc-fe-regression-test",
  "description": "Create and run Playwright regression tests for the screens changed by the current diff, on the current branch, so they land in the pull request",
  "version": "1.0.0"
}
```

- [ ] **Step 3: Register it in the marketplace**

Add to the `plugins` array in `.claude-plugin/marketplace.json`, immediately after the
`oc-fe-create-e2e-test` entry:

```json
    {
      "name": "oc-fe-regression-test",
      "source": "./plugins/frontend/oc-fe-regression-test",
      "description": "Diff-driven Playwright regression tests for changed OpenCell Portal screens, written on the current branch after the Vitest step so they are part of the PR"
    }
```

- [ ] **Step 4: Verify both JSON files parse and the entry resolves**

```bash
python3 - <<'PY'
import json, os
m = json.load(open('.claude-plugin/marketplace.json'))
entry = next(p for p in m['plugins'] if p['name'] == 'oc-fe-regression-test')
src = entry['source'].lstrip('./')
manifest = os.path.join(src, '.claude-plugin', 'plugin.json')
assert os.path.isfile(manifest), manifest
assert json.load(open(manifest))['name'] == entry['name']
print('registry OK')
PY
```

Expected: `registry OK`.

- [ ] **Step 5: Commit**

```bash
git add plugins/frontend/oc-fe-regression-test .claude-plugin/marketplace.json
git commit -m "oc-fe-regression-test 1.0.0: register the plugin

Diff-driven Playwright regression tests for changed OpenCell Portal screens.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: The skill

**Files:**
- Create: `plugins/frontend/oc-fe-regression-test/skills/oc-fe-regression-test/SKILL.md`

**Interfaces:**
- Consumes: the plugin name from Task 5; the agent `oc-fe-create-e2e-test:oc-fe-e2e-expert`;
  `tests/support/app-boot.ts` and `tests/support/routes.ts` from Phase 1.
- Produces: skill `/oc-fe-regression-test [BASE-BRANCH] [--files <paths>]`, which the four
  orchestrators in Task 7 invoke.

- [ ] **Step 1: Write the skill**

Create the file with exactly this content:

````markdown
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
- **`--files <path> ...`** — optional explicit file list. When given, use exactly those paths
  and do not expand to the diff.

## Tasks

### Step 1: Resolve the changed source files

```bash
git diff --name-only [BASE-BRANCH]...HEAD
git diff --name-only HEAD          # unstaged, so the skill also works pre-commit
git ls-files --others --exclude-standard
```

Union the three lists, then keep only paths that:

- start with `src/`, and
- end in `.ts` or `.tsx`, and
- are **not** `*.test.ts(x)`, not under `__tests__/`, not under `src/test-utils/`,
  not i18n JSON, not under `tests/`.

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

For each file in `[CHANGED-FILES]`:

1. Walk up to `src/srcProject/widgets/<DOMAIN>/<FEATURE>/index.ts` and read the exported
   component names.
2. Grep each name in `src/components/GenericRenderer/Widgets/defaultWidgets.ts` to find the
   registry key constant.
3. Resolve that constant in `src/constants/generic.js` to its string literal
   (e.g. `B2B_DUNNING_POLICY_CREATE = 'CreateDunningPolicy'`).
4. Grep the literal across `src/srcProject/layout/**` — `"type": "<literal>"` in the page
   descriptor JSON, or `type: '<literal>'` in `create.js` / `list.js`.
5. Read the descriptor directory's `index.js` for `resource`, the `pages` keys and
   `inMenu.path`; read the layout root (`src/srcProject/layout/<X>/constant/paths.js`) for
   `modulePath`.
6. Compose the URL with `screenUrl()` from `tests/support/routes.ts`.

Worked example in the repo:
`src/srcProject/layout/B2B/modules/apollo2/billing-accounts/__tests__/create-billing-account-route.test.ts:36-43`.

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
  and use the `appPage` fixture. It already stubs `keycloak-js`, replaces
  `app-properties.js` and installs a permissive API catch-all. Override individual endpoints
  with `mockApi(page, pattern, body)` — Playwright matches route handlers in reverse
  registration order, so a handler you register inside the test wins over the fixture's."
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
- Manifest: "Write your file manifest to `.claude/cache/ai-stats/[RUN_ID]/<PHASE>.json` per your
  manifest instructions, then snapshot your first pass to `snapshots/<PHASE>.diff`." Resolve
  `<PHASE>` **before** dispatching: `e2e` if that manifest name is free in the run directory,
  otherwise `e2e-2`, `e2e-3`, … — and use the same `<PHASE>` for both the `.json` and the
  `.diff`, never a numbered manifest beside a hardcoded `e2e.diff`.

### Step 5: Verify the snapshot before touching the agent's files

**The snapshot filename must track the manifest filename in lockstep** — manifest `e2e.json` →
`snapshots/e2e.diff`, manifest `e2e-2.json` → `snapshots/e2e-2.diff`, and so on. Step 3
deliberately *reuses* the run directory by `[TICKET-NUMBER]-*` prefix, and the sibling skill
`/oc-fe-create-e2e-test` writes the identical phase name and paths into it. A hardcoded
`e2e.diff` would silently overwrite that run's first-pass snapshot and make its retention
unmeasurable — a breach of the shared AI-usage contract in the root `CLAUDE.md`.

```bash
PHASE=e2e            # or e2e-2, e2e-3 … — whichever manifest name Step 4 actually used
mkdir -p .claude/cache/ai-stats/[RUN_ID]/snapshots
git add -N -- <files from $PHASE.json>   # REQUIRED: git diff HEAD ignores untracked files,
                                         # so brand-new specs would otherwise diff to nothing
git diff HEAD -- <files from $PHASE.json> > .claude/cache/ai-stats/[RUN_ID]/snapshots/$PHASE.diff
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

**Resolving the ticket:** match `XXX-NNNNN` in `git rev-parse --abbrev-ref HEAD`. This skill
takes **no ticket argument** — its interface is `[BASE-BRANCH]` and `--files` only, and the
sibling `/oc-fe-write-tests` resolves its ticket the same way. If no ticket can be resolved from
the branch, skip this step and say so.
Skip it too when no spec was written.

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
````

- [ ] **Step 2: Verify the frontmatter parses and the name matches the directory**

```bash
python3 - <<'PY'
import re
p = 'plugins/frontend/oc-fe-regression-test/skills/oc-fe-regression-test/SKILL.md'
text = open(p).read()
assert text.startswith('---\n'), 'missing frontmatter'
fm = text.split('---\n')[1]
name = re.search(r'^name:\s*(\S+)', fm, re.M).group(1)
assert name == 'oc-fe-regression-test', name
assert 'description:' in fm
assert 'oc-fe-create-e2e-test:oc-fe-e2e-expert' in text, 'agent reference missing'
assert 'ai_test_front_dev' in text
print('skill OK')
PY
```

Expected: `skill OK`.

- [ ] **Step 3: Commit**

```bash
git add plugins/frontend/oc-fe-regression-test/skills
git commit -m "oc-fe-regression-test 1.0.0: add the /oc-fe-regression-test skill

Diff-driven Playwright regression specs for changed screens: resolves changed
files to screen URLs through the module configs, dispatches oc-fe-e2e-expert
with the boot-fixture contract, and blocks the workflow on a genuine app
regression rather than weakening the assertion.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Wire the step into the four workflows

**Files:**
- Modify: `plugins/frontend/oc-fe-fix-bug/skills/oc-fe-fix-bug/SKILL.md` (after the Step 6 block, ~line 168)
- Modify: `plugins/frontend/oc-fe-create-ui/skills/oc-fe-create-ui/SKILL.md` (after the Step 7 block, ~line 186)
- Modify: `plugins/frontend/oc-fe-fix-pr/skills/oc-fe-fix-pr/SKILL.md` (after the Step 8 block, before "Step 9: Commit & Push")
- Modify: `plugins/frontend/oc-fe-test-writer/skills/oc-fe-write-tests/SKILL.md` (after "Step 4: Present the Report")

**Interfaces:**
- Consumes: `/oc-fe-regression-test` from Task 6.
- Produces: nothing consumed later.

- [ ] **Step 1: Insert into `/oc-fe-fix-bug`**

Immediately after the Vitest step's snapshot-fallback paragraph and **before**
"### Step 7: Mark the Ticket as Handled by the Frontend AI Dev", insert:

```markdown
### Step 6b: Playwright Regression Tests for the Changed Screens

Directly after the Vitest step, protect the screens the fix touched:

- Run `/oc-fe-regression-test [BASE-BRANCH]`.
- It stays on the current branch, so the specs are part of this ticket's PR.
- It skips itself on any repository other than opencell-portal, and when no changed file
  resolves to a screen.
- **This step is blocking.** If it reports a genuine application regression, stop and fix the
  regression before continuing to the tag and commit steps — do not weaken the spec.
```

Then renumber nothing: the following heading stays "Step 7".

- [ ] **Step 2: Insert into `/oc-fe-create-ui`**

This file uses `####` for its step headings. Insert after the Vitest step's snapshot-fallback
paragraph and **before** "#### Step 8: Mark the Ticket as Handled by the Frontend AI Dev":

```markdown
#### Step 7b: Playwright Regression Tests for the New Screens

Directly after the Vitest step, cover the screens the page introduces:

- Run `/oc-fe-regression-test [BASE-BRANCH]`.
- It stays on the current branch, so the specs are part of this ticket's PR.
- It skips itself on any repository other than opencell-portal, and when no changed file
  resolves to a screen.
- **This step is blocking.** If it reports a genuine application regression, stop and fix the
  regression before continuing to the tag and commit steps — do not weaken the spec.
```

- [ ] **Step 3: Insert into `/oc-fe-fix-pr`**

Insert after the Step 8 snapshot-fallback paragraph and **before** "### Step 9: Commit & Push
to the PR Branch". Note the base branch differs here — this flow diffs against the PR's
destination branch:

```markdown
### Step 8b: Playwright Regression Tests for the Fixed Screens

Directly after the Vitest step, protect the screens the remarks touched:

- Run `/oc-fe-regression-test [PR-DEST-BRANCH]`.
- It stays on the PR's own source branch, so the specs are pushed with the fixes.
- It skips itself on any repository other than opencell-portal, and when no changed file
  resolves to a screen.
- **This step is blocking.** If it reports a genuine application regression, stop and fix the
  regression before committing and pushing — do not weaken the spec.
```

- [ ] **Step 4: Insert into `/oc-fe-write-tests`**

Insert after "### Step 4: Present the Report" and **before** "### Step 5: Mark the Ticket as
Tested by the Frontend AI Test Writer":

```markdown
### Step 4b: Playwright Regression Tests

Directly after the Vitest run, cover the screens the changed code renders:

- Run `/oc-fe-regression-test [BASE-BRANCH]`. In file mode, pass the same paths through:
  `/oc-fe-regression-test --files [FILES]`.
- It stays on the current branch.
- It skips itself on any repository other than opencell-portal, and when no changed file
  resolves to a screen.
- **This step is blocking.** If it reports a genuine application regression, stop and report
  it rather than weakening the spec.
```

- [ ] **Step 5: Verify all four insertions and their ordering**

```bash
python3 - <<'PY'
targets = {
 'plugins/frontend/oc-fe-fix-bug/skills/oc-fe-fix-bug/SKILL.md': 'Mark the Ticket as Handled',
 'plugins/frontend/oc-fe-create-ui/skills/oc-fe-create-ui/SKILL.md': 'Mark the Ticket as Handled',
 'plugins/frontend/oc-fe-fix-pr/skills/oc-fe-fix-pr/SKILL.md': 'Commit & Push',
 'plugins/frontend/oc-fe-test-writer/skills/oc-fe-write-tests/SKILL.md': 'Mark the Ticket as Tested',
}
for path, following in targets.items():
    t = open(path).read()
    assert '/oc-fe-regression-test' in t, f'{path}: step not inserted'
    vitest = t.index('oc-fe-test-writer:oc-fe-test-writer')
    regression = t.index('/oc-fe-regression-test')
    nxt = t.index(following, regression)
    assert vitest < regression < nxt, f'{path}: wrong order'
    assert 'blocking' in t[regression:nxt].lower(), f'{path}: blocking gate missing'
print('wiring OK — 4/4 after Vitest, before the next step, gate stated')
PY
```

Expected: `wiring OK — 4/4 after Vitest, before the next step, gate stated`.

- [ ] **Step 6: Commit**

```bash
git add plugins/frontend/oc-fe-fix-bug plugins/frontend/oc-fe-create-ui \
        plugins/frontend/oc-fe-fix-pr plugins/frontend/oc-fe-test-writer
git commit -m "oc-fe-*: run /oc-fe-regression-test directly after the Vitest step

Wires the Playwright regression step into the four skills that dispatch
oc-fe-test-writer, in each case after the Vitest step and before that flow's
commit/tag step, so the specs land in the pull request. The step is blocking on
a genuine application regression.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Documentation

**Files:**
- Modify: `README.md` (after line 40)
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

- [ ] **Step 1: Add the README row**

Immediately after the `oc-fe-create-e2e-test` row:

```markdown
| **oc-fe-regression-test** | `/oc-fe-regression-test` | Diff-driven Playwright regression specs for changed OpenCell Portal screens, written on the current branch right after the Vitest step so they ship in the PR |
```

- [ ] **Step 2: Update `CLAUDE.md` — the skill list**

In the "**Skills & commands**" paragraph of the **Plugin Types** section, add
`/oc-fe-regression-test` to the list of frontend slash commands.

- [ ] **Step 3: Update `CLAUDE.md` — the workflow chain**

Replace the workflow diagram in **Key Workflow: Jira-Driven Development** with:

```
/oc-cache-jira TICKET  →  /oc-fe-fix-bug TICKET  →  [fix code]  →  [Vitest tests]  →  [Playwright regression specs]  →  /oc-commit TICKET  →  /oc-pull-request TICKET (+ auto /oc-fe-calculate-ai-use)  →  /oc-review-pr TICKET  →  /oc-fe-fix-pr PR-ID
```

- [ ] **Step 4: Update `CLAUDE.md` — the behavioural bullet**

Add to the bullet list under the workflow chain:

```markdown
- `/oc-fe-regression-test` writes and runs Playwright specs for the **screens the diff
  touches**, and runs **directly after the Vitest step** in `/oc-fe-fix-bug`,
  `/oc-fe-create-ui`, `/oc-fe-fix-pr` and `/oc-fe-write-tests` — on the current branch, so
  the specs are part of the PR. It is **diff-driven**, unlike `/oc-fe-create-e2e-test`, which
  is ticket-driven and cuts its own `test/TICKET` branch. It applies to **opencell-portal
  only** and skips itself elsewhere. Specs live at `tests/e2e/**/*.spec.ts` and boot the SPA
  through `tests/support/app-boot.ts`, which stubs the `keycloak-js` module and replaces
  `app-properties.js` — note that `window.KEYCLOAK_BYPASS` must stay **unset**, since it
  short-circuits `onAuthSuccess` and deadlocks the profile bootstrap. The step is
  **blocking**: a genuine screen regression stops the workflow, and weakening or skipping an
  assertion to reach green is forbidden.
```

- [ ] **Step 5: Verify the docs mention it consistently**

```bash
grep -c "oc-fe-regression-test" README.md CLAUDE.md
grep -n "KEYCLOAK_BYPASS" CLAUDE.md
```

Expected: `README.md:1` or more, `CLAUDE.md:2` or more, and the `KEYCLOAK_BYPASS` note present.

(Two, not three: Step 3's workflow diagram deliberately uses the label
`[Playwright regression specs]` rather than the literal command name, which reads better in a
pipeline diagram. The two literal mentions are the skill list in Step 2 and the behavioural
bullet in Step 4. Do not pad the text to raise the count.)

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document /oc-fe-regression-test and the Playwright regression step

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: End-to-end verification

**Files:** none — this task only runs things.

- [ ] **Step 1: Verify the marketplace still parses in full**

```bash
python3 - <<'PY'
import json, os
m = json.load(open('.claude-plugin/marketplace.json'))
for p in m['plugins']:
    src = p['source'].lstrip('./')
    mf = os.path.join(src, '.claude-plugin', 'plugin.json')
    assert os.path.isfile(mf), f"{p['name']}: missing {mf}"
    assert json.load(open(mf))['name'] == p['name'], p['name']
print(f"{len(m['plugins'])} plugins OK")
PY
```

Expected: every plugin resolves, count is one higher than before Task 5.

- [ ] **Step 2: Reinstall the marketplace locally and confirm the skill is listed**

In a Claude Code session, run `/plugin marketplace update` (or reinstall from this path) and
confirm `/oc-fe-regression-test` appears in the skill list.

- [ ] **Step 3: Dry run on a real portal change**

In the portal repo, on a branch with a real widget change:

```bash
cd /home/mhamidi/workspace/oc/portal/source/opencell-portal
/oc-fe-regression-test dev
```

Confirm all of:
- the changed widget resolved to the correct screen URL;
- a spec was created under `tests/e2e/`;
- `yarn test:e2e` ran and the result was reported;
- `.claude/cache/ai-stats/<RUN_ID>/e2e.json` exists and lists the spec;
- `.claude/cache/ai-stats/<RUN_ID>/snapshots/<PHASE>.diff` exists and is non-empty, with the
  same `<PHASE>` as the manifest written beside it.

- [ ] **Step 4: Confirm the AI-usage analyzer sees the work**

```bash
/oc-fe-calculate-ai-use --run
```

Expected: a non-zero `e2e` category line and a non-zero `e2eAdd` test count. No change to
that skill was needed — it already classifies `tests/e2e/**` as `e2e` and counts Playwright
blocks.

- [ ] **Step 5: Push and open the PR**

```bash
cd /home/mhamidi/workspace/oc/ai/marketplace/ccode-marketplace
git push -u origin feature/oc-fe-regression-test
```
