#!/usr/bin/env node
// launch-mcp.mjs — start the `oc-fn-playwright` MCP server with the oc-fn-portal flags.
//
// This file is the ONLY copy of the server's flag list. The oc-fn-tools plugin runs it
// (plugin.json, written by ai-config's publish.sh), and a skill-directory install registers it
// (setup.md § 3, ai-config's install.sh). Before it existed there were three hand-kept copies,
// and they drifted: the plugin shipped for weeks without --secrets or the pinned Chromium, so a
// colleague on the plugin could not log in and saw clicks that did nothing.
//
// Why a launcher and not static args:
//   - the credentials file, the profile and the output dir are per user, resolved at launch
//     from the home directory — portable to native Windows, where $HOME is not dependable;
//   - @playwright/mcp EXITS at startup when the --secrets file is missing (ENOENT, verified on
//     0.0.82). So --secrets is passed only when the file exists: without it the server still
//     starts and navigates, and only login is unavailable until setup.md § 2 is done;
//   - @playwright/mcp is PINNED, not @latest. The bundled Chromium is pinned per @playwright/mcp
//     release, so @latest broke every install at each upstream release until the browser was
//     reinstalled (0.0.82 moved it from revision 1244 to 1246, seen 2026-09-23). A bump here is a
//     deliberate act: change PIN, run --install-browser, check a click (setup.md § 8).
//
// Node is the runtime because npx already requires it — no new dependency, and no shell.
//
// Overrides (environment):
//   OC_PORTAL_CREDENTIALS  credentials dotenv file  (default ~/.config/oc-fn-portal/credentials)
//   OC_PORTAL_STATE_DIR    profile + output parent  (default ~/.local/state/oc-fn-portal)
//   OC_PORTAL_BROWSER      --browser value          (default chromium; set it EMPTY to use the
//                                                    system Chrome channel, see setup.md § 1)
//
// `node launch-mcp.mjs --dry-run`         prints the command it would run, and exits.
// `node launch-mcp.mjs --install-browser` installs the Chromium matched to PIN (setup.md § 1).

import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const PIN = '0.0.81';   // @playwright/mcp version; its bundled Chromium revision is 1244

const win = process.platform === 'win32';
// On Windows npx is npx.cmd, which Node only spawns through a shell — so quote each argument
// for cmd (a profile path under C:\Users\<First Last>\ contains a space).
const npx = (argv, opts) =>
  spawn(win ? 'npx.cmd' : 'npx', win ? argv.map((a) => `"${a}"`) : argv, { shell: win, ...opts });

if (process.argv.includes('--install-browser')) {
  npx(['-y', `@playwright/mcp@${PIN}`, 'install-browser', 'chrome-for-testing'], { stdio: 'inherit' })
    .on('exit', (code) => process.exit(code ?? 1));
} else {
  launch();
}

function launch() {
  const home = homedir();
  const cred = process.env.OC_PORTAL_CREDENTIALS || join(home, '.config', 'oc-fn-portal', 'credentials');
  const state = process.env.OC_PORTAL_STATE_DIR || join(home, '.local', 'state', 'oc-fn-portal');
  const browser = process.env.OC_PORTAL_BROWSER ?? 'chromium';

  const args = [
    '-y', `@playwright/mcp@${PIN}`,
    '--headless',
    '--image-responses=omit',       // screenshots go to --output-dir, not into the context
    '--console-level=error',
    '--viewport-size=1280x720',
    '--timeout-action=30000',       // a heavy SPA page can exceed the 5 s default
    `--user-data-dir=${join(state, 'profile')}`,   // persistent profile: the Keycloak login survives
    `--output-dir=${join(state, 'output')}`,
  ];
  if (browser) args.push(`--browser=${browser}`);  // bundled Chromium matched to @playwright/mcp
  const hasCred = existsSync(cred);
  if (hasCred) args.push(`--secrets=${cred}`);    // login without the password entering the chat

  if (process.argv.includes('--dry-run')) {
    process.stdout.write(['npx', ...args].join(' ') + '\n');
    if (!hasCred) process.stdout.write(`# no credentials at ${cred}: --secrets omitted, login unavailable\n`);
    return;
  }
  if (!hasCred) {
    // stderr only: stdout is the MCP protocol channel and must carry nothing else.
    process.stderr.write(`oc-fn-playwright: no credentials at ${cred}; Portal login is unavailable until setup.md § 2 is done\n`);
  }

  const child = npx(args, { stdio: 'inherit' });
  for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) process.on(sig, () => child.kill(sig));
  child.on('error', (e) => {
    process.stderr.write(`oc-fn-playwright: cannot start npx (${e.message}) — is Node.js on the PATH?\n`);
    process.exit(1);
  });
  child.on('exit', (code) => process.exit(code ?? 1));
}
