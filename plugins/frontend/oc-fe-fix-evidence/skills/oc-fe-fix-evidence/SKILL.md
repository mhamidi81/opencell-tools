---
name: oc-fe-fix-evidence
description: Prove a frontend bug fix on the ticket — replay the ticket's reproduction steps in a real browser against a real backend server chosen by the developer, record screenshots and a screencast, attach them to the Jira ticket and post one comment. Runs as Step 6c of /oc-fe-fix-bug and can be used on its own. opencell-portal only, non-blocking.
argument-hint: "<TICKET-ID> [--server <url>] [--headed] (e.g. INTRD-36922)"
---

## Purpose

Leave on the ticket what a tester would otherwise have to produce by hand: a recording of the
fixed behaviour, made on the **local portal of the fix branch** talking to a **real backend**.

This is **not** `/oc-fe-regression-test`. That skill mocks every API and boots the app through
`tests/support/app-boot.ts` with Keycloak stubbed; its specs are committed. This skill must not
use `app-boot.ts`, any mock, or any stub — a recording made on a stubbed app proves nothing
about the real product. Its scenario is a throwaway and is **never committed**.

**Non-blocking.** Every failure here is a warning to the developer, never a reason to stop the
fix workflow. The one thing this skill never does to get a recording is fake it.

**Repository gate.** Only **opencell-portal**. If `git remote get-url origin` does not name that
repository, report "not opencell-portal — skipping fix evidence" and stop.

## Context

Parse `$ARGUMENTS`:

- **[TICKET-NUMBER]** — first positional argument. If absent, take it from the branch name
  (`[A-Z]+-\d+`); if still absent, ask.
- **`--server <url>`** — backend to use; skips the question in Step 2.
- **`--headed`** — show the browser while recording.

Paths (all outside the repository, nothing here is ever staged):

| What | Where |
|------|-------|
| Scripts | `${CLAUDE_PLUGIN_ROOT}/skills/oc-fe-fix-evidence/scripts/` → `[SCRIPTS]` |
| Home | `~/.claude/oc-fe-tools/evidence/` → `[HOME]` |
| Saved sign-in, one per server | `[HOME]/auth/<server-host>.json` → `[AUTH]` |
| Recently used servers | `[HOME]/servers.json` (JSON array, most recent first, max 5) |
| This run's output | `[HOME]/runs/[TICKET-NUMBER]-<yyyymmdd-HHMMSS>/` → `[OUT]` |

## Tasks

### Step 1: Preconditions and duplicate check

1. `JIRA_EMAIL` and `JIRA_API_TOKEN` must be set (the Atlassian MCP cannot upload files, so
   the upload uses Jira REST). If either is missing, say so, give the setup lines the script
   prints, and stop — do not record something that cannot be posted.
2. Compute the code state being proven. The fix is usually still uncommitted at this point:

   ```bash
   HEAD7=$(git rev-parse --short=7 HEAD)
   if [ -n "$(git status --porcelain)" ]; then
     STATE="$HEAD7+$( (git diff HEAD; git ls-files --others --exclude-standard) | sha1sum | cut -c1-8)"
   else
     STATE="$HEAD7"
   fi
   ```
3. `python3 [SCRIPTS]/jira_evidence.py check --ticket [TICKET-NUMBER] --state "$STATE"` —
   exit `10` means this exact code state already has its comment: report that and stop.
   Jira comments are append-only, so this check is what keeps a re-run from posting twice.

### Step 2: Ask which backend server to use

Unless `--server` was given, **always ask** — never assume a server, and never take one from
`app-properties.js` or `.env*` silently.

- Read `[HOME]/servers.json`. With two or more entries, use `AskUserQuestion` ("Which backend
  server should the fix be recorded against (SERVER_URL)?") listing them most recent first;
  the built-in "Other" takes a new URL. With fewer than two, ask in plain text and mention the
  last one used if any.
- Normalise to `scheme://host[:port]` with no trailing slash → `[SERVER]`. Reject anything that
  is not `http(s)`.
- Write `[SERVER]` back to the front of `servers.json` (dedupe, keep 5).

### Step 3: Start the local portal against that server

The recording must show **this branch's code**, so the portal is always the local dev server —
never a deployed portal.

1. Find the dev command and port from the checkout: Vite branches run `yarn start` (`vite`,
   port from `vite.config.js`, default 3000); 15.x-style branches run `yarn start`
   (`react-app-rewired`, port 3000). → `[PORTAL]` = `http://localhost:<port>`.
2. If something already answers on that port, ask the developer whether it is this checkout's
   dev server and may be reused. On Vite branches a reused server must have been started with
   `VITE_SERVER_URL=[SERVER]`; if the developer cannot confirm, ask them to stop it.
3. Otherwise start it in the background, with the backend passed by environment so **no tracked
   file is edited**:

   ```bash
   VITE_SERVER_URL=[SERVER] BROWSER=none yarn start      # run_in_background
   ```

   Wait until `[PORTAL]` answers (up to 3 min). Remember that this skill started it.
4. Do **not** edit `public/app-properties.js` or any `.env*` file. The recorder appends the
   `SERVER_URL` override to `app-properties.js` in the browser, which covers the branches that
   do not read `VITE_SERVER_URL`.

### Step 4: Sign in (developer, by hand, once per server)

Login is the developer's own Microsoft account through Keycloak. **Never ask for, read, type or
store a password or an MFA code.**

- If `[AUTH]` does not exist, run:

  ```bash
  node [SCRIPTS]/evidence_run.mjs login --portal [PORTAL] --server [SERVER] --auth [AUTH] --repo .
  ```

  Tell the developer a browser window is opening and to sign in there; the command waits up to
  5 minutes and saves the session (file mode 600). Nothing is recorded during sign-in.
- Exit `2` = Playwright missing: run the one-time setup the script prints, then retry.
- Exit `4` = not completed in time, or no display available: warn and stop the skill.

### Step 5: Write the scenario

Write `[OUT]/scenario.mjs` from the ticket's **steps to reproduce** and expected behaviour
(ticket data from the `/oc-cache-jira` cache or `getJiraIssue`), informed by the fix diff:

```js
export default async ({ page, step, shot }) => {
  step('Open customer ACME from the customers list');
  await page.getByRole('link', { name: 'Customers' }).click();
  // ...
  await shot('Before saving');
  step('Save — the total now includes the tax line');
  await page.getByRole('button', { name: 'Save' }).click();
  await page.getByText('120.00').waitFor();   // the assertion: fails if the fix is not there
  await shot('Total after save');
};
```

Rules:

- `step()` text is what the ticket reader sees — plain language, the user's action and the
  result, no selectors.
- Take a `shot()` at the exact place the bug used to show, plus one of the starting state.
- **Assert the fixed behaviour** before the final screenshot (`waitFor` on the correct value or
  element). A scenario with no assertion can "pass" on a screen that is still broken.
- Use real data that exists on `[SERVER]`. Find it through the UI (search, lists). If the data
  the bug needs is not there, `throw new Error('DATA_MISSING: <what is needed>')`.
- **Do not create, modify or delete data on the server** beyond what the reproduction steps
  themselves do. If reproducing requires creating or changing records on a shared server, ask
  the developer first and name the records.
- No `page.route` mocks, no request interception, no `app-boot.ts`.
- Keep it short: the video should run well under two minutes.

### Step 6: Record

```bash
node [SCRIPTS]/evidence_run.mjs run --portal [PORTAL] --server [SERVER] --auth [AUTH] \
  --scenario [OUT]/scenario.mjs --out [OUT] --repo . [--headed]
```

| Exit | Meaning | Do |
|------|---------|----|
| `0` | Recorded | Continue |
| `3` | Session expired | Delete `[AUTH]`, redo Step 4 once, re-run |
| `5` | Test data missing | Tell the developer what is missing on `[SERVER]`; offer another server; otherwise stop |
| `1` | Scenario failed | Read `manifest.json` → `error` and `NN-failure.png`. A wrong selector or timing is yours to fix (at most 3 attempts). If the **fixed behaviour is really not there** on a real backend, say so plainly — that is a finding about the fix, not something to work around |

Then look at the screenshots yourself (`Read` the PNG files) and confirm they show what the
steps claim. `manifest.json` must have `backendVerified: true` — it counts the API calls that
reached `[SERVER]`; the upload script refuses a run without them.

**Never** loosen the assertion, crop the scenario, or record a different screen to obtain a
passing run.

### Step 7: Attach and comment

```bash
python3 [SCRIPTS]/jira_evidence.py post --ticket [TICKET-NUMBER] --state "$STATE" \
  --manifest [OUT]/manifest.json --branch "$(git branch --show-current)" \
  --summary "<one sentence: what was verified>" [--uncommitted]
```

Pass `--uncommitted` when `$STATE` contains `+`. The script uploads the screenshots and the
video as attachments, then posts one comment (what was tested, the backend, the branch and
commit, the steps, the screenshots inline, the video link).

If the upload or the comment fails, warn, and give the developer `[OUT]` so the files can be
attached by hand. Do not retry a failed comment blindly — check the ticket first.

### Step 8: Clean up and report

- Stop the dev server **only if this skill started it**.
- Confirm `git status` shows nothing from this skill.
- Report: server used, number of screenshots, video yes/no, comment posted or why not, and the
  `[OUT]` path.

## Examples

```bash
/oc-fe-fix-evidence INTRD-36922
/oc-fe-fix-evidence INTRD-36922 --server https://dev.oc-nsb.eu --headed
```
