---
name: oc-fe-fix-evidence
description: Prove a frontend bug fix on the ticket — replay the ticket's reproduction steps in a real browser against a real backend server chosen by the developer, record screenshots and a screencast, attach them to the Jira ticket and post one comment. Runs as Step 6c of /oc-fe-fix-bug and can be used on its own, including on a bug that is already fixed and merged. opencell-portal only, non-blocking.
argument-hint: "<TICKET-ID> [--server <url>] [--line <branch>] [--headed] (e.g. INTRD-36922)"
---

## Purpose

Leave on the ticket what a tester would otherwise have to produce by hand: a recording of the
fixed behaviour, made on a **local portal built from the code that contains the fix**, talking
to a **real backend**.

This is **not** `/oc-fe-regression-test`. That skill mocks every API and boots the app through
`tests/support/app-boot.ts` with Keycloak stubbed; its specs are committed. This skill must not
use `app-boot.ts`, any mock, or any stub — a recording made on a stubbed app proves nothing
about the real product. Its scenario is a throwaway and is **never committed**.

**Non-blocking.** Every failure here is a warning to the developer, never a reason to stop the
fix workflow. The one thing this skill never does to get a recording is fake it.

## Context

Parse `$ARGUMENTS`:

- **[TICKET-NUMBER]** — first positional argument. If absent, take it from the branch name
  (`[A-Z]+-\d+`); if still absent, ask.
- **`--server <url>`** — backend to use; skips the question in Step 3.
- **`--line <branch>`** — version line to record from (`dev`, `15.X`, `18.X`, …) when the fix
  is merged into several.
- **`--headed`** — show the browser while recording.

Paths (all outside the repository, nothing here is ever staged):

| What | Where |
|------|-------|
| Scripts | `${CLAUDE_PLUGIN_ROOT}/skills/oc-fe-fix-evidence/scripts/` → `[SCRIPTS]` |
| Home | `~/.claude/oc-fe-tools/evidence/` → `[HOME]` |
| Settings | `[HOME]/config.json` — `{"portalRoot": "<dir>"}` |
| Saved sign-in, one per server | `[HOME]/auth/<server-host>.json` → `[AUTH]` |
| Recently used servers | `[HOME]/servers.json` (JSON array, most recent first, max 5) |
| This run's output | `[HOME]/runs/[TICKET-NUMBER]-<yyyymmdd-HHMMSS>/` → `[OUT]` |

**Never delete anything under `[HOME]/runs/`.** Every attempt and every probe goes into its own
new folder (`[OUT]`, `[OUT]-2`, `[OUT]-probe-1`, …); clearing a folder to reuse it is not worth
a removal command.

## Tasks

### Step 1: Find the checkout that contains the fix

The recording must show the code that fixes the bug, and it does not have to be the current
directory — this skill is often run on a bug that is already merged.

1. **Portal root.** The developer keeps one checkout per main version (`dev`, `15.X`, `16.X`,
   `17.X`, `18.X`, …) under one folder. Take it from `$OC_PORTAL_ROOT`, else `portalRoot` in
   `[HOME]/config.json`. If neither is set, ask once ("Which folder holds your per-version
   opencell-portal checkouts?") and save the answer to `config.json`.
2. Run:

   ```bash
   python3 [SCRIPTS]/portal_checkout.py select --ticket [TICKET-NUMBER] --cwd . \
     --root [PORTAL-ROOT] [--line <branch>]
   ```

   | Result | Meaning |
   |--------|---------|
   | `mode: current` | The current directory is a portal checkout with work that is on no version line yet (the `/oc-fe-fix-bug` case). Record from it. |
   | `mode: line` | The ticket is merged into that line; the developer's checkout of it was found, was clean and on the line branch, and has been fast-forwarded to `origin`. Record from it. |
   | exit `4`, `ask: …` | A person must decide (merged into several lines, no checkout on that branch, a checkout with local changes, nothing mentions the ticket). Put the `ask` text to the developer with `AskUserQuestion` or plainly, then re-run with `--line`, or stop. |

   → `[CHECKOUT]` = `path`, `[BRANCH]` = `branch`, `[STATE]` = `state`, and note `uncommitted`.
   The script never switches a branch, stashes or resets. Do not do it for it.
3. If the current directory is not a portal checkout **and** no portal root can be resolved,
   report "no opencell-portal checkout to record from — skipping fix evidence" and stop.

`[STATE]` identifies the code being proven: `HEAD`, plus a hash of the uncommitted work when
there is some. An untracked `.claude/` folder is tooling, not a fix, and is ignored.

### Step 2: Preconditions and duplicate check

1. `JIRA_EMAIL` and `JIRA_API_TOKEN` must be set (the Atlassian MCP cannot upload files, so
   the upload uses Jira REST). If either is missing, say so, give the setup lines the script
   prints, and stop — do not record something that cannot be posted.
2. `python3 [SCRIPTS]/jira_evidence.py check --ticket [TICKET-NUMBER] --state [STATE]` —
   exit `10` means this exact code state already has its comment: report that and stop.
   Jira comments are append-only, so this check is what keeps a re-run from posting twice.

### Step 3: Ask which backend server to use

Unless `--server` was given, **always ask** — never assume a server, and never take one from
`app-properties.js` or `.env*` silently.

- Read `[HOME]/servers.json`. With two or more entries, use `AskUserQuestion` ("Which backend
  server should the fix be recorded against (SERVER_URL)?") listing them most recent first;
  the built-in "Other" takes a new URL. With fewer than two, ask in plain text and mention the
  last one used if any.
- Normalise to `scheme://host[:port]` with no trailing slash → `[SERVER]`. Reject anything that
  is not `http(s)`. The server should run the same version line as `[BRANCH]`; say so if the
  host name suggests otherwise.
- Write `[SERVER]` back to the front of `servers.json` (dedupe, keep 5).

### Step 4: Prepare and start the local portal

```bash
python3 [SCRIPTS]/portal_checkout.py prepare --path [CHECKOUT]
```

This installs the checkout's dependencies with **`oc-install`** (it links them from the shared
pnpm store, a few seconds when nothing changed) and returns the Node to start the portal with:

- `nodeBin` — the `bin` folder of the Node this line needs (`.nvmrc`; Node ≤ 16 for the
  webpack-4 lines, which die on newer Node with `digital envelope routines::unsupported`).
  `null` means the current Node is right.
- `start` — the command, its environment and the port.
- exit `4` — `oc-install` or the needed Node is missing: relay the `ask` text and stop.

Then:

1. If something already answers on the port, ask the developer whether it may be stopped or
   reused. A reused server must be **this** checkout's, and on Vite lines must have been started
   with `VITE_SERVER_URL=[SERVER]`. If they cannot confirm, ask them to stop it.
2. Start it in the background from `[CHECKOUT]`, with the backend passed by environment so
   **no tracked file is edited**:

   ```bash
   cd [CHECKOUT] && PATH="<nodeBin>:$PATH" VITE_SERVER_URL=[SERVER] <start.env> <start.argv>
   ```

   Wait for the **first compile to finish**, not just for the port: the webpack lines open the
   port minutes before they can serve a page. Watch the server output for `Compiled` /
   `ready in`; `Failed to compile` means stop and report the error.
3. Do **not** edit `public/app-properties.js` or any `.env*` file. The recorder appends the
   `SERVER_URL` override to `app-properties.js` in the browser, which covers the lines that do
   not read `VITE_SERVER_URL`.
4. `[PORTAL]` = `http://localhost:<start.port>`. Remember that this skill started the server.

### Step 5: Sign in (developer, by hand, once per server)

Login is the developer's own Microsoft account through Keycloak. **Never ask for, read, type or
store a password or an MFA code.**

- If `[AUTH]` does not exist, tell the developer **before** running the command that a browser
  window is about to open and that they have 5 minutes to sign in, then run:

  ```bash
  node [SCRIPTS]/evidence_run.mjs login --portal [PORTAL] --server [SERVER] --auth [AUTH] --repo [CHECKOUT]
  ```

  The session is saved with file mode 600. Nothing is recorded during sign-in.
- Exit `2` = Playwright missing: run the one-time setup the script prints, then retry.
- Exit `4` = not completed in time, or no display available: warn and stop the skill.

### Step 6: Write the scenario

Read the ticket's **steps to reproduce** and expected behaviour (`/oc-cache-jira` cache or
`getJiraIssue`) and the fix diff. Then find the screen on the real server.

**Probe first.** You do not know this server's data or the screen's markup. Run short throwaway
scenarios into `[OUT]-probe-N` that navigate, dump what they see to a JSON file and take a
screenshot — to find the route, a record that reproduces the bug, and real selectors. Probes
are never posted. Prefer selectors from the markup (`title`, `role`, labels) over coordinates.

Then write `[OUT]/scenario.mjs`:

```js
export default async ({ page, step, shot, mark }) => {
  step('Open customer ACME from the customers list');
  await page.getByText('ACME', { exact: true }).click();
  // ...
  step('Save — the total now includes the tax line');
  await page.getByRole('button', { name: 'Save' }).click();
  await mark(page.getByText('120.00'));   // the assertion: visible on screen, then outlined
  await shot('Total after save');
};
```

Rules:

- `step()` text is what the ticket reader sees — plain language, the user's action and the
  result, no selectors.
- Take a `shot()` at the exact place the bug used to show. A contrasting one (the state where
  the bug did not show, e.g. the other language) makes the fix obvious.
- **Assert the fixed behaviour with `mark()`** before the final screenshot. `mark()` fails
  unless the element is really visible on screen. **Never assert on a DOM value alone**
  (`input.value`, `evaluate`, `waitForFunction`): a field inside a collapsed panel or a hidden
  tab has the right value and is invisible, and the screenshot then shows nothing. Expand the
  panel / open the tab the way a user would, first.
- Read-only observation of real API answers (`page.on('response')`) is fine, for instance to
  learn the expected label from the server instead of hard-coding it. **Altering** traffic is
  not: no `page.route`, no mocks, no `app-boot.ts`.
- Use real data that exists on `[SERVER]`. If the data the bug needs is not there,
  `throw new Error('DATA_MISSING: <what is needed>')`.
- **Do not create, modify or delete data on the server** beyond what the reproduction steps
  themselves do. If reproducing requires creating or changing records on a shared server, ask
  the developer first and name the records.
- **The signed-in user's own settings are server data too.** The portal's language flag, for
  one, writes the developer's locale on the backend (`PUT …/api/rest/user`). When the
  reproduction needs such a change, export a `restore` function that puts it back:

  ```js
  export async function restore({ page }) {
    if ((await currentLanguage(page)) === 'EN') return false;   // already right
    await setLanguage(page, 'EN');
    return true;                                                // had to change it
  }
  ```

  The recorder runs it after the recording in fresh, unrecorded sessions until one of them
  returns `false`. Restoring inside the scenario itself is **not enough** — it was observed not
  to stick. Record what the original value was before you change it.
- Keep it short: the video should run well under two minutes.

### Step 7: Record

```bash
node [SCRIPTS]/evidence_run.mjs run --portal [PORTAL] --server [SERVER] --auth [AUTH] \
  --scenario [OUT]/scenario.mjs --out [OUT] --repo [CHECKOUT] [--headed]
```

| Exit | Meaning | Do |
|------|---------|----|
| `0` | Recorded | Continue |
| `3` | Session expired | Move `[AUTH]` aside, redo Step 5 once, re-run |
| `5` | Test data missing | Tell the developer what is missing on `[SERVER]`; offer another server; otherwise stop |
| `6` | Recorded, but a user setting was **not restored** | Tell the developer exactly which setting and its original value. Do not post until it is restored or they accept it |
| `1` | Scenario failed | Read `manifest.json` → `error` and `NN-failure.png`. A wrong selector or timing is yours to fix (at most 3 attempts, each in a new folder). If the **fixed behaviour is really not there** on a real backend, say so plainly — that is a finding about the fix, not something to work around |

Then **look at every screenshot yourself** (`Read` the PNG files) and confirm each shows what
its step claims — the outlined element, with the expected text readable. A passing run whose
screenshots do not show the fix is a failed run: fix the scenario and record again.
`manifest.json` must have `backendVerified: true` — it counts the API calls that reached
`[SERVER]`; the upload script refuses a run without them.

**Never** loosen the assertion, crop the scenario, or record a different screen to obtain a
passing run.

### Step 8: Attach and comment

```bash
python3 [SCRIPTS]/jira_evidence.py post --ticket [TICKET-NUMBER] --state [STATE] \
  --manifest [OUT]/manifest.json --branch [BRANCH] \
  --summary "<one sentence: what was verified>" [--uncommitted]
```

Pass `--uncommitted` when Step 1 reported `uncommitted: true`. The script uploads the
screenshots and the video as attachments, then posts one comment (what was tested, the backend,
the branch and commit, the steps, the screenshots inline, the video link).

If the upload or the comment fails, warn, and give the developer `[OUT]` so the files can be
attached by hand. Do not retry a failed comment blindly — check the ticket first.

### Step 9: Clean up and report

- Stop the dev server **only if this skill started it** — by the process id listening on the
  port, never with a pattern kill.
- Confirm `git -C [CHECKOUT] status` shows nothing from this skill.
- Report: the checkout and branch used (and whether it was fast-forwarded), the server, the
  number of screenshots, video yes/no, any user setting changed and restored, comment posted or
  why not, and the `[OUT]` path.

## Examples

```bash
/oc-fe-fix-evidence INTRD-36922
/oc-fe-fix-evidence INTRD-49410 --server https://15x.oc-nsb.eu
/oc-fe-fix-evidence INTRD-36922 --line 18.X --headed
```
