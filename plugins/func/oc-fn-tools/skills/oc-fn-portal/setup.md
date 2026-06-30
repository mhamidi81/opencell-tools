# oc-fn-portal — one-time setup & tuning

Load this when preparing a machine for portal navigation, or when a `browser_*` call
fails because the server isn't registered or the browser/deps are missing. Day-to-day
navigation does not need this file.

All flag names below were verified against the installed `@playwright/mcp`. If the
package has since updated, re-check with `npx @playwright/mcp@latest --help` before
trusting a flag.

## 1. Browser (per machine, once)

`@playwright/mcp` defaults to the **Chrome channel** (branded Google Chrome at
`/opt/google/chrome/chrome`), *not* Playwright's bundled Chromium. Install it system-wide —
the `.deb` pulls its own OS dependencies via apt:

```bash
sudo npx playwright install chrome
```

The MCP server does **not** auto-install the browser — run this first. Verify:
`google-chrome --version`.

> Do **not** use `sudo npx playwright install chromium`: it (a) installs the *bundled
> Chromium*, which the server won't use unless you also pass `--browser chromium`, and (b)
> when run under `sudo`, downloads it into **root's** cache (`/root/.cache/ms-playwright`),
> where the user-run MCP server can't find it. The Chrome channel above avoids both traps.

## 2. Runtime dirs + credentials (per machine, once)

```bash
mkdir -p ~/.config/oc-fn-portal ~/.local/state/oc-fn-portal/profile ~/.local/state/oc-fn-portal/output
```

Create `~/.config/oc-fn-portal/credentials` (dotenv format) and lock it down:

```dotenv
OC_PORTAL_URL=https://<your-sandbox-host>
OC_PORTAL_USER=<login>
OC_PORTAL_PASS=<password>
```

```bash
chmod 600 ~/.config/oc-fn-portal/credentials
```

These paths live **outside** any tracked repository — secrets and browser state are never committed.

## 3. Register the Playwright MCP server (per machine, once)

Run this command — it is the canonical registration procedure and the single source of truth
for the flags:

```bash
claude mcp add -s user oc-fn-playwright -- \
  npx -y @playwright/mcp@latest \
  --headless \
  --image-responses=omit \
  --console-level=error \
  --viewport-size=1280x720 \
  --timeout-action=30000 \
  --user-data-dir="$HOME/.local/state/oc-fn-portal/profile" \
  --output-dir="$HOME/.local/state/oc-fn-portal/output"
```

This skill deliberately registers under its **own** server key (`oc-fn-playwright`) rather than
the bare `playwright`, so it coexists cleanly with the marketplace `oc-playwright-mcp` plugin —
which registers a separate server named `playwright` with different (bare) args. Using a distinct
key means neither registration overwrites the other's config.

- **User scope** (`-s user`) → available in every Claude Code session on the machine, not
  just inside one repo. `settings.json` is **not** a valid place for `mcpServers`; only
  `.mcp.json` (project) and `~/.claude.json` (user/local, written by `claude mcp add`) are.
- Restart Claude Code after registering so the new server loads.
- Verify: `claude mcp get oc-fn-playwright`.

Why these flags:
- `--headless` — no display on the server.
- `--image-responses=omit` — screenshots are written to `--output-dir` but **not** returned
  inline, so capturing costs ~0 context tokens. View one with the `Read` tool on demand.
- `--user-data-dir` — persistent profile; log in once and the session survives across runs.
  (Do **not** add `--isolated` — it keeps the profile in memory only, defeating persistent login.)
- `--console-level=error` — drop info/warning console chatter from responses.
- `--timeout-action=30000` — raise the per-action timeout from the 5000 ms default; screenshotting
  a heavy SPA page can exceed the 5 s default on modest hardware. Raise it further if you still see
  action timeouts.
- `--output-dir` — where screenshots (and, if enabled, traces/sessions) land.

## 4. First login smoke test

After steps 1–3, ask Claude to: navigate to `OC_PORTAL_URL`, log in with the credentials,
and screenshot the dashboard to `~/.local/state/oc-fn-portal/output/oc-smoke-dashboard.png`.
Confirm the file exists and (optionally) `Read` it once to eyeball it. Subsequent sessions
should skip login thanks to the persistent profile.

## 5. Token-tuning levers (optional)

Add to the `claude mcp add` args (then re-register) when a workload is snapshot-heavy:
- `--snapshot-mode=none` — actions stop auto-attaching the accessibility tree; you call
  `browser_snapshot` only when you actually need to locate elements. Biggest saver for
  click-through-heavy navigation; the trade-off is less automatic feedback per action.
- `--output-mode=file` — route snapshots / console / network logs to disk instead of stdout
  (default `stdout`). Aggressive; you lose inline access to the tree.
- `--caps=…` — only `vision`, `pdf`, `devtools` are addable (core is always on). Leave unset;
  none are needed for navigation + screenshots.
- `--timeout-action=<ms>` (default 5000) / `--timeout-navigation=<ms>` (default 60000) —
  raise if the SPA renders slowly.

## 6. Security hardening — keep the password out of context

`@playwright/mcp` accepts `--secrets <path>` pointing at a dotenv file; secrets can then be
referenced rather than typed literally, so the password never enters the conversation. To
use it, point `--secrets` at the credentials file (or a secrets-only subset) and reference
the secret in place of the literal value when typing. Confirm the exact reference syntax for
the installed version against its docs/`--help` before relying on it — until then, the
default (reading `OC_PORTAL_PASS` and typing it) works for a low-risk sandbox you control;
use `--secrets` for any shared or sensitive tenant.

## 7. Troubleshooting

- **Chromium fails to launch (namespace / sandbox error):** add `--no-sandbox` to the args.
  It lowers browser isolation — an acceptable trade-off only on a sandbox you trust; weigh it
  yourself before enabling on a shared host.
- **Profile lock / "already in use":** another session holds the profile. Use one session at
  a time, or run a throwaway `--isolated` session (no persistence) for the one-off.
- **Logged out unexpectedly:** the persisted session expired — just log in again; the profile
  re-captures it.
- **Server flag rejected after a package update:** re-check `npx @playwright/mcp@latest --help`
  and update the args in the `claude mcp add` command in §3 above.
