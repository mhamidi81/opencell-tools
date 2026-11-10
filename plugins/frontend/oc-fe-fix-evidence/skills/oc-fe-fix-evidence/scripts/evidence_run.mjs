#!/usr/bin/env node
/**
 * Browser recorder for /oc-fe-fix-evidence.
 *
 *   login  --portal <url> --server <url> --auth <file> [--repo <dir>]
 *       Opens a VISIBLE browser on the portal. The developer signs in by hand
 *       (Keycloak -> Microsoft, MFA included); the session is then saved to
 *       --auth. Nothing is recorded and no credential is ever read or typed here.
 *
 *   run    --portal <url> --server <url> --auth <file> --scenario <file.mjs>
 *          --out <dir> [--repo <dir>] [--headed]
 *       Reuses the saved session, records a video, runs the scenario and writes
 *       <out>/manifest.json.
 *
 * Exit codes: 0 ok · 1 scenario failed · 2 usage / Playwright missing ·
 *             3 session missing or expired (run `login`) · 4 login timed out ·
 *             5 scenario reported missing test data (DATA_MISSING: ...) ·
 *             6 recorded, but a user setting the scenario changed was NOT restored
 *
 * The scenario is an ES module:
 *   export default async ({ page, step, shot, mark, portalUrl, serverUrl }) => { ... }
 *   export async function restore({ page, portalUrl, serverUrl }) { ...; return changed; }
 * `step(text)` records a human-readable step; `shot(label)` takes a screenshot;
 * `mark(locator)` requires the element to be really visible, scrolls it into
 * view and outlines it, so the next screenshot shows what the step claims.
 *
 * `restore` is optional and is for scenarios that had to change one of the
 * signed-in user's own settings (the portal language, for instance). It runs
 * after the recording in fresh, unrecorded sessions: it must put the setting
 * back and return true when it had to change something, false when everything
 * was already right. The run only counts as restored once a fresh session
 * returns false.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

export const RUNNER_HOME = path.join(
  os.homedir(), '.claude', 'oc-fe-tools', 'evidence', 'runner'
);
const VIEWPORT = { width: 1280, height: 720 };
const LOGIN_TIMEOUT_MS = 5 * 60_000;
const SESSION_TIMEOUT_MS = 45_000;

export function parseArgs(argv) {
  const [command, ...rest] = argv;
  const options = {};
  for (let i = 0; i < rest.length; i++) {
    const arg = rest[i];
    if (!arg.startsWith('--')) throw new Error(`unexpected argument: ${arg}`);
    const key = arg.slice(2);
    if (key === 'headed') options.headed = true;
    else {
      if (i + 1 >= rest.length) throw new Error(`--${key} needs a value`);
      options[key] = rest[++i];
    }
  }
  return { command, options };
}

/** `01-after-save.png` — stable, sortable, safe as a Jira attachment name. */
export function shotFileName(index, label) {
  const slug = String(label).toLowerCase().replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '').slice(0, 40) || 'screenshot';
  return `${String(index).padStart(2, '0')}-${slug}.png`;
}

/** Appended to app-properties.js so every portal version targets `serverUrl`. */
export function serverOverride(serverUrl) {
  return `\n;window._APP_PROPERTIES && (window._APP_PROPERTIES.SERVER_URL = ${
    JSON.stringify(serverUrl)});\n`;
}

/** True once the browser is back on the portal with the Keycloak redirect consumed. */
export function isSettledOnPortal(currentUrl, portalUrl) {
  let url;
  try { url = new URL(currentUrl); } catch { return false; }
  if (url.origin !== new URL(portalUrl).origin) return false;
  return !/[#&?](state|code|session_state)=/.test(url.hash + url.search);
}

function loadChromium(repoDir) {
  const candidates = [];
  if (repoDir) candidates.push([repoDir, '@playwright/test'], [repoDir, 'playwright']);
  candidates.push([RUNNER_HOME, 'playwright']);
  for (const [dir, name] of candidates) {
    try {
      const require = createRequire(path.join(path.resolve(dir), 'package.json'));
      const mod = require(name);
      if (mod.chromium) return mod.chromium;
    } catch { /* try the next location */ }
  }
  console.error(
    'Playwright is not installed. One-time setup:\n' +
    `  mkdir -p "${RUNNER_HOME}" && cd "${RUNNER_HOME}" && npm init -y >/dev/null \\\n` +
    '    && npm install playwright && npx playwright install chromium'
  );
  process.exit(2);
}

async function pinServer(context, serverUrl) {
  await context.route('**/app-properties.js*', async (route) => {
    try {
      const response = await route.fetch();
      await route.fulfill({
        response,
        body: (await response.text()) + serverOverride(serverUrl)
      });
    } catch {
      await route.continue();
    }
  });
}

/** Outline `locator` after proving a person could actually see it. */
async function markVisible(page, locator) {
  const target = locator.first();
  await target.waitFor({ state: 'visible', timeout: 20_000 });
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  const view = page.viewportSize();
  const onScreen = box && box.width > 0 && box.height > 0
    && box.y >= 0 && box.x >= 0 && box.y + box.height <= view.height && box.x + box.width <= view.width;
  const hit = onScreen && await target.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const top = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !!top && (el === top || el.contains(top) || top.contains(el));
  });
  if (!hit) throw new Error('mark(): the element is in the page but not visible on screen');
  await target.evaluate((el) => {
    const box = el.closest('.MuiFormControl-root') || el;
    box.style.outline = '3px solid #e53935';
    box.style.outlineOffset = '4px';
  });
  await page.waitForTimeout(1200);
}

async function restoreSettings(chromium, options, scenario, manifest) {
  if (typeof scenario?.restore !== 'function') return;
  manifest.restored = false;
  for (let attempt = 1; attempt <= 3; attempt++) {
    const browser = await chromium.launch({ headless: true });
    try {
      const context = await browser.newContext({ viewport: VIEWPORT, storageState: options.auth });
      await pinServer(context, options.server);
      const page = await context.newPage();
      await page.goto(options.portal, { waitUntil: 'domcontentloaded' });
      if (!(await waitSettled(page, options.portal, SESSION_TIMEOUT_MS))) break;
      const changed = await scenario.restore({
        page, portalUrl: options.portal, serverUrl: options.server
      });
      await page.waitForTimeout(3000);           // let the write reach the server
      if (!changed) { manifest.restored = true; break; }
    } catch (error) {
      manifest.restoreError = String(error?.message || error);
    } finally {
      await browser.close();
    }
  }
}

async function waitSettled(page, portalUrl, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let stableSince = 0;
  while (Date.now() < deadline) {
    if (page.isClosed()) return false;
    if (isSettledOnPortal(page.url(), portalUrl)) {
      stableSince ||= Date.now();
      if (Date.now() - stableSince >= 3000) return true;
    } else {
      stableSince = 0;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

async function login(options) {
  const chromium = loadChromium(options.repo);
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: VIEWPORT });
  await pinServer(context, options.server);
  const page = await context.newPage();
  await page.goto(options.portal, { waitUntil: 'domcontentloaded' });
  console.error('Sign in in the browser window (Microsoft account + MFA). Waiting up to 5 min...');
  const ok = await waitSettled(page, options.portal, LOGIN_TIMEOUT_MS);
  if (ok) {
    fs.mkdirSync(path.dirname(options.auth), { recursive: true, mode: 0o700 });
    await context.storageState({ path: options.auth });
    fs.chmodSync(options.auth, 0o600);
    console.log(`session saved: ${options.auth}`);
  } else {
    console.error('login was not completed in time');
  }
  await browser.close();
  return ok ? 0 : 4;
}

async function run(options) {
  if (!fs.existsSync(options.auth)) {
    console.error('no saved session for this server — run `login` first');
    return 3;
  }
  const chromium = loadChromium(options.repo);
  const outDir = path.resolve(options.out);
  fs.mkdirSync(outDir, { recursive: true });
  const serverHost = new URL(options.server).host;

  const browser = await chromium.launch({ headless: !options.headed });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    storageState: options.auth,
    recordVideo: { dir: outDir, size: VIEWPORT }
  });
  await pinServer(context, options.server);

  const manifest = {
    ok: false, server: options.server, portal: options.portal,
    startedAt: new Date().toISOString(),
    steps: [], screenshots: [], video: null, backendRequests: 0, error: null
  };
  // Proof that the run talked to the chosen backend, not to mocks: count the
  // API calls (XHR/fetch) that actually reached its host.
  context.on('request', (request) => {
    const type = request.resourceType();
    if ((type === 'xhr' || type === 'fetch') && new URL(request.url()).host === serverHost) {
      manifest.backendRequests += 1;
    }
  });

  const page = await context.newPage();
  const shot = async (label) => {
    const file = shotFileName(manifest.screenshots.length + 1, label);
    await page.screenshot({ path: path.join(outDir, file) });
    manifest.screenshots.push({ file, label: String(label) });
  };
  const step = (text) => { manifest.steps.push(String(text)); };
  const mark = (locator) => markVisible(page, locator);

  let code = 0;
  let scenario = null;
  try {
    await page.goto(options.portal, { waitUntil: 'domcontentloaded' });
    if (!(await waitSettled(page, options.portal, SESSION_TIMEOUT_MS))) {
      manifest.error = 'saved session missing or expired';
      code = 3;
    } else {
      scenario = await import(pathToFileURL(path.resolve(options.scenario)).href);
      await scenario.default({
        page, step, shot, mark, portalUrl: options.portal, serverUrl: options.server
      });
      manifest.ok = true;
    }
  } catch (error) {
    manifest.error = String(error?.message || error);
    code = manifest.error.startsWith('DATA_MISSING:') ? 5 : 1;
    try { await shot('failure'); } catch { /* page may be gone */ }
  }

  const video = page.video();
  await context.close(); // flushes the video file
  if (video && code !== 3) {
    const target = path.join(outDir, 'recording.webm');
    try {
      fs.renameSync(await video.path(), target);
      manifest.video = 'recording.webm';
    } catch { /* no video produced */ }
  }
  await browser.close();

  if (code !== 3) {
    await restoreSettings(chromium, options, scenario, manifest);
    if (manifest.restored === false && code === 0) code = 6;
  }

  manifest.backendVerified = manifest.backendRequests > 0;
  manifest.finishedAt = new Date().toISOString();
  fs.writeFileSync(path.join(outDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
  console.log(JSON.stringify(manifest, null, 2));
  return code;
}

async function main() {
  let parsed;
  try { parsed = parseArgs(process.argv.slice(2)); } catch (error) {
    console.error(String(error.message)); return 2;
  }
  const { command, options } = parsed;
  const need = command === 'login'
    ? ['portal', 'server', 'auth']
    : command === 'run' ? ['portal', 'server', 'auth', 'scenario', 'out'] : null;
  if (!need) { console.error('usage: evidence_run.mjs <login|run> ...'); return 2; }
  const missing = need.filter((key) => !options[key]);
  if (missing.length) { console.error(`missing: ${missing.map((k) => `--${k}`).join(' ')}`); return 2; }
  return command === 'login' ? login(options) : run(options);
}

if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(new URL(import.meta.url).pathname)) {
  main().then((code) => process.exit(code), (error) => { console.error(error); process.exit(1); });
}
