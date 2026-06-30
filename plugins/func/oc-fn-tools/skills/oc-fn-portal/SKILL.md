---
name: oc-fn-portal
version: 1.1.0
updated: 2026-06-27T12:00:00+02:00
author: Stéphane Chambrin
description: >
  Drive the Opencell Portal (React SPA) through the Playwright MCP server to navigate
  pages, explore the UI, and capture screenshots — in support of design assistance and
  Confluence/Jira documentation, NOT automated testing. Load this skill whenever the user
  asks to open / navigate / log in to the portal or the sandbox, to take or capture a
  screenshot of a portal page, to see "what a page looks like", to explore the portal UI,
  or whenever a Playwright `browser_*` tool is about to be used against the Opencell Portal.
  Carries the token-discipline rules for using Playwright frugally and the persistent-login
  / screenshot conventions.
---

# Opencell Portal — navigate, explore, screenshot

Drive the Opencell Portal via the **Playwright MCP server** (registered as `oc-fn-playwright`)
to look at the live UI and capture screenshots. The output feeds **design assistance** and
**documentation** (`oc-fn-func-design` → Jira, `oc-fn-documentation` → Confluence).

## When this skill applies

Load whenever any of the following is true:
- The user asks to open, navigate, log in to, or explore the Opencell Portal / the sandbox.
- The user asks to take, capture, or look at a screenshot of a portal page, or "what does *X* look like".
- A Playwright `browser_*` tool is about to run against the portal.

## Scope & boundaries

- **Purpose:** design assistance + documentation screenshots. **No** test assertions, **no** CI, **no** regression suites.
- **Sandbox only.** The credentials and profile point at a **non-production sandbox tenant you configure** (`OC_PORTAL_URL`). Never aim this skill at a production tenant.
- **Read-mostly.** Navigate, observe, screenshot. Treat the portal as read-only by default.
- **Confirm before mutating.** Submitting a form, creating/editing/deleting a record, running a billing/rating job, or any state-changing action requires an explicit go-ahead from the user first — even on the sandbox. Logging in is the one routine exception.
- **Companion lanes.** For generic, ad-hoc browser automation against arbitrary sites, the marketplace ships a separate slash command (`/oc-playwright`); for Playwright/Cypress end-to-end *tests*, use the frontend E2E plugins (`oc-fe-*`). This skill is the Opencell-Portal-specific, token-frugal lane for design/docs screenshots — not generic automation, not test authoring.

## Prerequisites

One-time setup (system deps, MCP registration, credentials, runtime dirs) lives in **`setup.md`** — load it only when setting up a machine or troubleshooting a launch failure. In a ready machine you can assume:
- MCP server `oc-fn-playwright` is registered (user scope). When that server is the one in use, it is headless with `--image-responses=omit` (see Token discipline for how to detect this at runtime).
- Credentials file: `~/.config/oc-fn-portal/credentials` (dotenv: `OC_PORTAL_URL`, `OC_PORTAL_USER`, `OC_PORTAL_PASS`).
- Persistent profile: `~/.local/state/oc-fn-portal/profile` (keeps you logged in across sessions, best-effort — re-login when the session has lapsed).
- Screenshots / output dir: `~/.local/state/oc-fn-portal/output`.

If a `browser_*` call fails because the server isn't registered or Chromium isn't installed, switch to `setup.md`.

## Token discipline — the whole point of this skill

Playwright is cheap to *drive*. **When the `oc-fn-playwright` server is in use** (configured
with `--image-responses=omit` and an `--output-dir`), **both** screenshots **and** accessibility
snapshots are written to the output dir and returned to you as a **disk-path link, not inline
content** — plus a cheap line of page URL/title. So a `browser_*` call costs almost nothing in
context; the token cost lands only when you deliberately **`Read`** the file it produced. *The
cost is in the reading, not the driving.* (Verified against the installed `@playwright/mcp` —
navigation, clicks, and `browser_snapshot` all emit a `.yml` snapshot link; screenshots emit a
`.png`/`.jpeg` link.)

**Detect the config you actually have.** These guarantees hold only when the configured server
carries those flags — they are *not* universal to every Playwright MCP server that might resolve
to this name. On the **first `browser_take_screenshot`** of a session, check the result: if it
returns an **inline image** rather than a file path, the `--image-responses=omit` / `--output-dir`
guarantees are **not** in effect (a bare-args server is registered). When that happens, fall back
to the resilient behaviour below; the token math above no longer applies. Regardless of which
server you get:
- **Always pass an explicit absolute `filename`** to `browser_take_screenshot` (see Screenshots
  below) — don't rely on a default output dir being configured.
- **Treat persistent login as best-effort.** A persistent profile may or may not be configured;
  assume you may need to **re-login each session** rather than counting on a surviving session.

| You need… | Use | Context cost |
|---|---|---|
| A screenshot for docs / the record | `browser_take_screenshot` (absolute path under the output dir) | **~0** — link only; **never `Read`** it for doc captures |
| To actually *see* a page yourself | `browser_take_screenshot`, then **`Read`** the saved image | vision tokens — only when you `Read` |
| To *locate* a control / read page structure | the snapshot link from the last action (or `browser_snapshot`), then **`Read`** the `.yml` | proportional to page complexity — only when you `Read` |
| To act on a known element | `browser_click` / `browser_type` with a `ref` from the **last snapshot you read** | low — link-only result |

Rules:
1. **Everything is written to disk; you pay only on `Read`.** Actions hand back a link and the page URL/title. `Read` a produced file *only* when you actually need its content. For doc captures destined for Confluence/Jira, never `Read` them — just note the path.
2. **`Read` a snapshot `.yml` deliberately, not reflexively.** Read *one* when you reach a new page state to get element `ref`s, then reuse those refs for the clicks/types that follow. Don't re-read a fresh snapshot after every micro-action.
3. **Match the tool to the question.** "What does it look like?" → screenshot (+ `Read` if needed). "What controls are on the page / what's the field called?" → snapshot `.yml`. Don't read a snapshot when an image answers the question, or vice-versa.
4. **Reuse what the catalogues already record.** Check the shipped seed `pages.md` and your user catalog (`~/.local/state/oc-fn-portal/catalog/pages.md`); if a page's path and key selectors are catalogued, navigate straight there and act without reading an exploratory snapshot.
5. **Heavy navigation session?** Consider the `--snapshot-mode none` lever (see `setup.md`) so actions stop emitting snapshots entirely — then call `browser_snapshot` only on demand.

## Login & session

Auth is handled by **Keycloak (OpenID Connect)**: navigating to `OC_PORTAL_URL` redirects to
a `…/auth/realms/opencell/protocol/openid-connect/auth?…` URL that serves a hosted login form.
The persistent profile usually keeps the Keycloak session alive, so **most sessions need no login**.

1. **Check first.** `browser_navigate` to `OC_PORTAL_URL`. If the result URL is the portal (page title `Opencell | Portal`), you're already in — skip to the task. If it's an `…/auth/realms/opencell/…` URL, log in.
2. **The Keycloak form** has a `Username or email` textbox, a `Password` textbox, and a `Sign In` button — plus an `Opencell Internal` broker link for SSO, which you **ignore** (use the username/password form). `Read` the snapshot `.yml` once to get the field refs, then `browser_fill_form` both fields and click `Sign In`.
3. **Credentials:** read `OC_PORTAL_USER` from the credentials file (Bash — not sensitive). The password (`OC_PORTAL_PASS`) by default transits the fill/`browser_type` arguments (acceptable for a low-risk sandbox you control; for any shared or sensitive tenant, use the `--secrets` lever in `setup.md` to keep it out of context).
4. **Settle, then verify.** After the redirect the SPA renders — the page title goes `Opencell | Portal` → `- Opencell` and the home hub appears. Give it a moment (`browser_wait_for`) before screenshotting; a capture can take several seconds on slower hardware (hence `--timeout-action=30000`).

## Screenshots — conventions

- **Pass an absolute path under the output dir as `filename`** — `~/.local/state/oc-fn-portal/output/oc-<area>-<page>-<state>.png`. A *relative* `filename` is saved relative to the current working directory (verified — it landed in the repo), dumping the image into whatever directory the session runs in. Always use the absolute output-dir path.
- Naming: `oc-<area>-<page>-<state>.png` (e.g. `oc-billing-invoice-list.png`).
- **Viewport** (default 1280×720) for most captures; `fullPage: true` only when the user wants the whole scrollable page.
- For documentation: capture, record the file path, and hand it to the documentation workflow — do **not** `Read` it into context just to "confirm" it.

## Record what you learn

The catalogues shipped with this skill (`pages.md`, `ui-patterns.md`) are **read-only seed
catalogues** — read them, never edit them (they ship inside the plugin and are not writable).
Append everything you *learn* to a **user-writable catalog** instead, created on first use:
- **`~/.local/state/oc-fn-portal/catalog/pages.md`** — append a row whenever you confirm a page's URL path, its functional role, and any stable selectors/landmarks worth reusing.
- **`~/.local/state/oc-fn-portal/catalog/ui-patterns.md`** — append a note when you observe how a recurring Material UI pattern (nav, data grid, dialog, save bar, filters…) actually behaves in this portal.

Create the `catalog/` dir and either file the first time you have something to record (`mkdir -p ~/.local/state/oc-fn-portal/catalog`). On a new page, consult both the shipped seed file and your user catalog. Recording a page once turns future visits into a direct navigate-and-act (rule 4 above), which is the biggest long-term token saving.

## Reference files

- `setup.md` — one-time machine setup, the exact MCP registration command + flags, credential file format, token-tuning levers, security hardening (`--secrets`), and troubleshooting. **Load when setting up or when a launch fails.**
- `pages.md` — read-only **seed** catalogue of known portal pages (path → role → selectors). **Read before navigating to a non-trivial page.** Record newly confirmed pages in your user catalog (`~/.local/state/oc-fn-portal/catalog/pages.md`), not here — the shipped file is read-only.
- `ui-patterns.md` — read-only **seed** catalogue of recurring Opencell Portal UI patterns and how to interact with them. **Read when reasoning about how to drive an unfamiliar control.** Record new observations in `~/.local/state/oc-fn-portal/catalog/ui-patterns.md`.
