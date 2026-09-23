# oc-fn-portal — one-time setup & tuning

Load this when preparing a machine for portal navigation, or when a `browser_*` call
fails because the server isn't registered or the browser/deps are missing. Day-to-day
navigation does not need this file.

All flag names below were verified against the installed `@playwright/mcp`. If the
package has since updated, re-check with `npx @playwright/mcp@latest --help` before
trusting a flag.

## 1. Browser (per machine, once)

**Prefer `@playwright/mcp`'s bundled Chromium over the system Chrome channel.** The two drift
apart independently — system Chrome auto-updates on its own schedule, `@playwright/mcp` pins a
specific bundled Chromium revision — and that drift is a **confirmed** cause of a silent failure:
`browser_click` reports success (URL/title even update on plain navigations) but real in-page
state changes (a tab switch, a row click) never fire, with no error anywhere. Reproduced and fixed
on `sabretooth` 2026-09-16 against `18x.oc-nsb.eu`: switching from Chrome-channel to matched
bundled Chromium turned a dead click-probe (no reaction, confirmed via `browser_network_requests`
showing nothing fired) into a working one (`tab "Refund" [selected]` right after the click).

Install the browser **already matched** to the registered `@playwright/mcp` version — do not use
the generic `playwright` CLI for this, see the gotcha below:

```bash
npx @playwright/mcp install-browser chrome-for-testing
```

This downloads to your own cache (`~/.cache/ms-playwright/chromium-<rev>`), never root's, and
needs no `sudo`. Then register with `--browser chromium` (§3) instead of leaving the channel at
its Chrome-channel default.

> **Gotcha — `npx playwright install chromium` is NOT the same install.** It resolves through
> whatever `playwright` core version `npx` happens to fetch, which can pin a *different* bundled
> Chromium revision than the one your already-registered `@playwright/mcp` version expects.
> Observed: `npx playwright install chromium` fetched revision `1243`; the registered
> `@playwright/mcp@0.0.81` demanded `1244` and refused to launch ("Browser 'chrome-for-testing' is
> not installed; expected executable at .../chromium-1244/..."). Always install *through*
> `@playwright/mcp` itself (the command above), which guarantees the matching revision. Re-run it
> after every `@playwright/mcp` version bump — the pin can move.

**Alternative — system Chrome channel.** Still supported if you deliberately want branded Chrome
(e.g. to match a proprietary codec or DRM dependency the bundled Chromium lacks — irrelevant for
Portal navigation). The `.deb` pulls its own OS dependencies via apt:

```bash
sudo npx playwright install chrome
```

Verify: `google-chrome --version`. Leave `--browser` unset in the registration (§3) to use this
channel (the `@playwright/mcp` default).

> Do **not** run `sudo npx playwright install chromium` while intending to use the Chrome
> channel — it downloads Chromium (not Chrome) into **root's** cache
> (`/root/.cache/ms-playwright`), where the user-run MCP server can't find it, and the server
> won't use it anyway unless you also pass `--browser chromium`.

**Either way, the MCP server does not auto-install the browser** — run one of the two installs
above first.

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
  --browser chromium \
  --image-responses=omit \
  --console-level=error \
  --viewport-size=1280x720 \
  --timeout-action=30000 \
  --secrets="$HOME/.config/oc-fn-portal/credentials" \
  --user-data-dir="$HOME/.local/state/oc-fn-portal/profile" \
  --output-dir="$HOME/.local/state/oc-fn-portal/output"
```

**`--browser chromium`** pairs with the bundled-Chromium install in §1 (the now-default choice —
drop this flag only if you deliberately installed the system Chrome channel instead).

**`--secrets` is required, not optional** — it is what makes login possible at all without the
password entering the conversation. See § 6 for the mechanism and for why the alternatives are
blocked.

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

## 6. `--secrets` — the login mechanism, not optional hardening

**`--secrets` belongs in the registration in § 3.** Without it there is no way to log in: reading
`OC_PORTAL_PASS` with Bash so it can be typed into the form is **refused by the permission
classifier**, and it refuses every reformulation of the same idea — a heredoc piping the file into
Python, a generator script that writes the value into a `login.js`, a `browser_run_code_unsafe`
snippet that reads the file itself (which fails regardless: that VM has neither `require` nor a
dynamic-import callback). Three denials in one session, 2026-08-10. **Do not attempt those
workarounds.** The classifier is right — the password would land in the conversation — and
`--secrets` removes the need for it to.

**How it works** (verified against `@playwright/mcp` 0.0.79; mechanism lives in
`playwright-core/lib/coreBundle.js`):

- `--secrets <path>` loads a **dotenv** file into `config.secrets`.
- On **input**, `browser_fill_form` (field `value`) and `browser_type` (`text`) pass that string
  through `lookupSecret(name)`: if it matches a key in the file, Playwright fills the **real value**;
  if it doesn't, it fills the literal you passed. So you **pass the key name, never the value**.
- On **output**, `redactSecrets()` rewrites any occurrence of a secret value in tool responses as
  `<secret>NAME</secret>`, and generated code renders it as `process.env['NAME']`.

The login form is therefore filled like this, with nothing sensitive in the conversation:

```jsonc
// browser_fill_form
{"fields": [
  {"name": "Username or email", "type": "textbox", "target": "<ref>", "value": "opencell.superadmin"},
  {"name": "Password",          "type": "textbox", "target": "<ref>", "value": "OC_PORTAL_PASS"}
]}
```

`OC_PORTAL_PASS` is the **key name** in `~/.config/oc-fn-portal/credentials`, which `--secrets`
already points at — no separate secrets file is needed, and the other keys in it (`OC_PORTAL_URL`,
`OC_PORTAL_USER`) are harmless.

**Caveats.**
- **It is a convenience, not a security boundary** — upstream says so in as many words. It keeps the
  value away from the model; it does not protect the file.
- **Re-registering needs a session restart.** MCP servers are spawned at session start, so a server
  re-registered mid-session keeps its old args for the rest of that session — and `claude mcp get`
  will still say *Connected*, because that is a fresh probe and not the running process. Restart, or
  reconnect from `/mcp`.
- **The fallback is a person, not a workaround.** If `--secrets` isn't in effect yet, don't go after
  the password — hand the user a numbered checklist to run in their own browser. For any *negative*
  observation that is the stronger evidence anyway (`SKILL.md` § *What you observe is not evidence
  about the product*).

## 7. Reaping leaked browsers (per machine, once — POSIX only)

A headless Chrome left behind by a finished task is **not** orphaned: the MCP server still owns it,
so nothing reaps it and it holds ~500–800 MB resident until the session exits. `browser_close` is
the primary discipline (see `SKILL.md` § *Close the browser when you are done*); this is the
backstop for a session simply abandoned at a prompt, where no instruction can fire.

`reap-idle-browser.sh` ships with this skill. Inspect before trusting it:

```bash
# what it can see, and how long each browser has been idle (changes nothing)
./reap-idle-browser.sh --status
# what it would kill (kills nothing)
./reap-idle-browser.sh --dry-run
```

It kills only the Chrome **browser** process — which takes its tree down with it — never the MCP
server, and never on first sight. Default threshold 15 min (`--idle-minutes N` or
`$OC_PORTAL_IDLE_MINUTES`).

**It must run repeatedly to work at all.** A browser sits at 0% CPU both when leaked *and* during
the pause between two tool calls, so a single run can never tell those apart; idleness is only
established by seeing the CPU counter unchanged across successive runs. State lives in
`~/.local/state/oc-fn-portal/reaper-state`. (And it is CPU, not file mtimes: Chrome flushes its
caches minutes after going quiet, so mtimes report "active" for a tree doing nothing.)

**a. `SessionStart` hook — portable, no init system.** Reaps stale browsers as a new session starts,
i.e. just before it adds its own footprint. Add to `settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command", "async": true,
                     "command": "$CLAUDE_PLUGIN_ROOT/skills/oc-fn-portal/reap-idle-browser.sh --hook" } ] }
    ]
  }
}
```

`async: true` keeps it off the startup path. `--hook` stays silent unless it reaps something, in
which case it reports via `systemMessage`. Use `${CLAUDE_PLUGIN_ROOT}` when installed as a plugin;
point at `~/.claude/skills/oc-fn-portal/…` for a directly-installed skill.

Understand the limit before relying on it: the hook only fires when a session **starts**. A box left
with one idle session never reaps. It is a real improvement, not a guarantee.

**b. A timer — the reliable half.** Only a periodic run gives the repeated observations the CPU test
needs. Linux/systemd (`--user` units, `OnUnitActiveSec=5min`) or macOS/launchd
(`StartInterval`) — both call the same script, so pick whichever your machine has. Windows without
WSL is out of scope: this skill's setup is POSIX throughout (`chmod`, `$HOME`, XDG paths), so there
is nothing here for a pure-PowerShell install to hook into.

## 8. Troubleshooting

- **Chromium fails to launch (namespace / sandbox error):** add `--no-sandbox` to the args.
  It lowers browser isolation — an acceptable trade-off only on a sandbox you trust; weigh it
  yourself before enabling on a shared host.
- **Profile lock / "already in use":** another session holds the profile. Use one session at
  a time, or run a throwaway `--isolated` session (no persistence) for the one-off.
- **Logged out unexpectedly:** the persisted session expired — just log in again; the profile
  re-captures it.
- **Clicks are accepted but nothing happens:** `browser_click` returns success and the generated
  Playwright locator line looks correct (e.g. `getByRole('button', { name: 'Edit' }).click()`), yet
  the app does not react — no re-render, no state change, no network request. React synthetic events
  are not firing; most likely a Chromium / `@playwright/mcp` version mismatch against the Portal's
  React build. **Confirm with `browser_network_requests`:** no new request after the click. What
  marks it as environmental rather than one broken control is that it repeats on unrelated controls
  — observed in a single session on a button, a tab strip and a data-grid row. When it happens, the
  session **cannot drive this app**: fall back to read-only screenshots and tell the user. **Never
  report it as a Portal bug** — see `SKILL.md` § *What you observe is not evidence about the
  product*.

  **Confirmed fix (2026-09-16, `sabretooth` against `18x.oc-nsb.eu`):** switch from the system
  Chrome channel to `@playwright/mcp`'s own bundled Chromium — §1's `npx @playwright/mcp
  install-browser chrome-for-testing` + `--browser chromium` in the registration (§3), then
  reconnect (`/mcp` or restart). Re-ran the same click-probe (a tab switch) immediately after and
  it worked (`tab "Refund" [selected]`), where it had previously done nothing at all. Root cause
  read as system-Chrome-channel drift: `@playwright/mcp` pins a specific bundled Chromium
  revision, while the Chrome channel auto-updates independently — the two fall out of sync with no
  warning, and that skew is what breaks synthetic event dispatch. If you still hit this after
  switching, the bundled Chromium itself may now be behind the registered `@playwright/mcp` — rerun
  the install-browser command in §1 to re-pin it.
- **Server flag rejected after a package update:** re-check `npx @playwright/mcp@latest --help`
  and update the args in the `claude mcp add` command in §3 above.
