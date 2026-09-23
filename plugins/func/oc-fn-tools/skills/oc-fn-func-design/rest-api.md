# Direct Jira REST API — token-efficient reads & light writes

> **This direct REST path is an OPTIONAL token-saving optimisation.** If you only have the Atlassian
> connector (Rovo MCP), skip this file — the MCP covers every operation here on its own, with no token
> or `~/.netrc` setup. This path (the `jira` helper or raw `curl`) just filters responses in the shell
> so they cost fewer tokens than the MCP, which injects every response into context in full.

Load this file whenever the current INTRD task is a **read, JQL search,
metadata lookup, transition, plain-text comment, simple plain-field edit, or an ADF write you intend to
post from a file** **and** you have the optional direct path set up.
Per the transport policy in `SKILL.md`, these can go through the `jira` helper (or
raw `curl`) when installed, otherwise through the Rovo MCP. **A rich ADF body does not force you onto
the MCP** — it posts from a file through `jira raw`, see
[Writing ADF through `jira raw`](#writing-adf-through-jira-raw--the-cheap-path); only the narrow set in
[What stays on the MCP](#what-stays-on-the-mcp) is MCP-only.

## Why this is cheaper

The Rovo MCP injects every tool response into the model context in full, so a
single `getJiraIssue` can cost thousands of tokens of ADF/schema/expansion
even with a `fields` allowlist. With `curl | jq`, the raw response is filtered
**in the shell** and only the projection reaches context. Edits return
`204 No Content` — zero response tokens.

## One-time auth setup (only if using the direct path)

HTTP Basic via `~/.netrc` so `curl -n` never exposes the token in argv/history.

1. Create an API token at https://id.atlassian.com/manage/api-tokens
2. Add one line to `~/.netrc` and lock it down (use your own Opencell Atlassian account email and the token from step 1):

   ```
   machine opencellsoft.atlassian.net login you@opencellsoft.com password <API_TOKEN>
   ```
   ```sh
   chmod 600 ~/.netrc
   ```
3. Verify: `jira raw GET /myself | jq .displayName` (or `curl -ns https://opencellsoft.atlassian.net/rest/api/3/myself`).

The `jira` helper prints this hint to stderr if no `~/.netrc` entry for the site is found.

## The `jira` helper

An optional `jira` helper installed at `~/.local/bin/jira` (a thin curl/jq wrapper; its full source is
reproducible from the recipe in this file). It is a convenience, not a dependency — raw `curl -n` (below)
covers the same operations, and the Rovo MCP covers them with no setup at all. Defaults to project
`INTRD` and site `opencellsoft.atlassian.net`; override with `JIRA_PROJECT` /
`JIRA_SITE`. All subcommands emit token-thin output by default.

| Command | Does | Default output |
|---|---|---|
| `jira get KEY [fields] [--json]` | Fetch one issue | `name: value` lines, ADF flattened to text; `--json` = raw ADF JSON |
| `jira jql 'QUERY' [--fields=a,b] [--max=N] [--token=T] [--all] [--json]` | Enhanced JQL search | one `KEY ⇥ status ⇥ summary` line per issue (+ paging hint) |
| `jira count 'QUERY'` | Approximate match count | a single number |
| `jira transitions KEY` | List available transitions | `id ⇥ name` lines |
| `jira transition KEY ID` | Apply a transition | `ok: …` (API returns 204) |
| `jira comment KEY 'TEXT'` | Add a plain-text comment | `ok: comment #…` |
| `jira meta ISSUETYPE_ID` | Create-fields for an issue type | `fieldId ⇥ name ⇥ required=…` |
| `jira raw METHOD PATH [DATA\|@file.json]` | Escape hatch — **`PATH` is relative to `/rest/api/3`** | raw response |
| `jira aliases` | List the built-in JQL aliases | `name ⇥ expansion` lines |

Examples:

```sh
jira get INTRD-1486                                   # read preset, ADF as text
jira get INTRD-1486 summary,status                    # narrower allowlist
jira get INTRD-42531 customfield_10137 --json         # true ADF of a Story field
jira jql 'project = INTRD AND statusCategory != Done ORDER BY updated DESC' --max=15
jira jql 'project = INTRD AND fixVersion = "19.0.0"' --all --fields=summary,status,fixVersions --json \
  | jq -r '.issues[] | [.key, .fields.status.name] | @tsv'   # every match, no cursor juggling
jira count 'project = INTRD AND created >= -7d'
jira meta 10001                                        # find customfield_* IDs for an issue type
jira raw GET '/issue/INTRD-1486?expand=renderedFields&fields=description'
```

### `--all` — drain every page

`jql` returns **one page** by default (`--max=10`) and prints
`…more (rerun with --token=<cursor>)` when there is more. **`--all` follows that cursor for you** and
returns the complete result set. Reach for it whenever you need a count-complete answer — a roster, a
rollup, "every Story on this fixVersion" — instead of hand-carrying `--token=` between calls.

- Under `--all`, **`--max` is the page size, not a total**, and defaults to **100** (the API maximum) so
  a drain costs the fewest round trips. An explicit `--max=N` still wins.
- **`--json` returns one JSON document either way**, so `jq '.issues[]'` and `.isLast` read the same
  with or without `--all`. A single page is the raw envelope (`isLast`, `issues`, `nextPageToken`);
  `--all` returns `{isLast, issues}` — the cursor is spent, so it is omitted.
- In line mode the `…more` hint is **suppressed**, because nothing is left.
- **Runaway guard:** `JIRA_MAX_PAGES` (default 100 pages = 10k issues). If it trips, the warning goes to
  **stderr**, `isLast` is `false`, and **the exit status is 2** — so a truncated drain never looks like a
  complete one. The message carries the live cursor, so you can resume with `--token=`.
- Aliases inherit it: `jira children INTRD-1949 --all` returns every child, not the first ten.

**`--all` is cheap in context, not free in time.** It is N sequential API calls, and `jq` still projects
in the shell so only your projection reaches the model — but do not drain a query you have not scoped.
Run `jira count` first when you are unsure of the magnitude.

**`raw` takes a path relative to `/rest/api/3` — the helper prepends the base itself**
(`BASE="https://$SITE/rest/api/3"`). Passing the full path doubles the prefix and fails with a 404
whose body names the doubling:

```console
$ jira raw GET "/rest/api/3/project/INTRD"
No endpoint GET /rest/api/3/rest/api/3/project/INTRD
```

Correct form: `jira raw GET "/project/INTRD"`. Every path in the [endpoint
catalog](#endpoint-catalog-raw-curl-for-what-the-helper-doesnt-cover) below is already written that way.

### JQL aliases

Common queries have short aliases, runnable either as a top-level shortcut
(`jira mine`) or under `jql` (`jira jql mine`) — both are identical. Aliases
inherit every `jql` flag (`--max`, `--fields`, `--json`, `--token`, `--all`). All are
scoped to `$JIRA_PROJECT` (INTRD by default) except `children`, which scopes by
`parent`. `jira aliases` prints the live list.

| Alias | Query |
|---|---|
| `mine` | my open issues — `assignee = currentUser() AND statusCategory != Done`, newest-updated first |
| `open` | all open — `statusCategory != Done`, newest-updated first |
| `recent` | everything, `ORDER BY updated DESC` |
| `unassigned` | open & unassigned — `assignee IS EMPTY AND statusCategory != Done` |
| `new` | `created >= -7d`, newest first |
| `children KEY` | `parent = KEY` — an Epic's child Stories **or** an issue's subtasks (INTRD links Story→Epic via `parent`) |

```sh
jira mine                       # == jira jql mine
jira open --max=20
jira children INTRD-1949        # the Epic's Stories
jira new --json
```

`children` is parametric: the KEY is the next positional arg
(`jira children INTRD-1949`), so it must come before any `--flag`.

### Token discipline still applies

The same field-allowlist rule from `SKILL.md` § *Reading efficiency* governs the
helper: keep `get`'s `fields` and `jql`'s `--fields` tight, raise `--max` only
when needed. The helper's defaults are deliberately small. Reach for `--json`
only when you truly need raw ADF (e.g. copying a template's structure verbatim).

**`--all` does not break that discipline — a tight `--fields` matters more with it, not less.** The
cost of a drain is API round trips plus whatever your projection emits; the response bodies never
enter context. So `--all` with a two-field allowlist is cheap even over hundreds of issues, while
`--all` with no `--fields` and no `jq` is how you flood the window.

**One exception: when a field's value must be relied on, read it with `--json` and `jq` rather than
trusting the default projection.** The default projection filters through `map(select(.value != null))`
(`bin/jira:150`), so it **drops any field whose value is `null`** — `jira get INTRD-45541 resolution`
prints the key and nothing else, while `jira raw GET '/issue/INTRD-45541?fields=resolution'` returns
`{"resolution":null}`. Read a near-empty result as `null`, not as an error or a mistyped field name:

```sh
jira get INTRD-26660 status --json | jq -r .fields.status.name
```

## Endpoint catalog (raw `curl`, for what the helper doesn't cover)

Base: `https://opencellsoft.atlassian.net/rest/api/3`. All calls take `curl -n`.
**Use v3** (ADF for rich text); v2 returns rich fields as plain strings.

| Operation | Method & path | Notes |
|---|---|---|
| Get issue | `GET /issue/{key}?fields=a,b&expand=renderedFields` | `fields` is a comma list; `expand=renderedFields` adds HTML |
| **Search** | `POST /search/jql` | body `{jql, fields:[...], maxResults, nextPageToken}` |
| Count | `POST /search/approximate-count` | body `{jql}` → `{count}` |
| Create | `POST /issue` | body `{fields:{project,issuetype,summary,description,…}}` → `201 {key}` |
| Edit | `PUT /issue/{key}` | body `{fields:{…}}` or `{update:{…}}` → **`204` empty** |
| Comment | `POST /issue/{key}/comment` | body `{body:<ADF doc>}` |
| Transitions | `GET` / `POST /issue/{key}/transitions` | POST body `{transition:{id}}` → `204` |
| Create-meta | `GET /issue/createmeta/{project}/issuetypes/{issueTypeId}` | per-issuetype field metadata + `customfield_*` IDs |

### Critical gotchas

- **The classic search endpoint is GONE.** `GET`/`POST /rest/api/3/search` was
  removed in Jira Cloud (returns `410 Gone`, rollout completed late 2025). Use
  `POST /search/jql`. It is **cursor-paged**: pass the previous response's
  `nextPageToken`; `startAt` no longer exists. It **does not return `total`** —
  get counts from `/search/approximate-count`.
- **`createmeta` without a project is deprecated.** Use the per-issuetype path
  `…/createmeta/{project}/issuetypes/{id}` (the `jira meta` subcommand).
- **`createmeta` is authoritative for *required* fields, not for what `POST /issue` accepts.** It
  reports the issue type's **create screen**, and a field absent from that screen can still be set at
  creation. `description` does **not** appear in `createmeta` for `Bug` (`10004`) or `Sub-bug`
  (`10071`), yet `POST /issue` accepts an ADF `description` on both — verified on INTRD-45541, created
  with a 33-node ADF description whose changelog holds no `description` entry. So read `createmeta` to
  learn what you *must* send, never to conclude what you *may* send. Required fields differ by issue
  type; `bugs.md` carries the Bug-vs-`Sub-bug` breakdown.
- **Edits and transitions return `204` with no body** — success is the status
  code, not JSON. (`PUT /issue/{key}?returnIssue=true` returns the issue if you
  need it, at a token cost.)
- **ADF is native in v3.** Rich-text fields (`description`, comment `body`,
  Story `customfield_10134`–`10137`) are ADF JSON objects directly — top-level
  `{"type":"doc","version":1,"content":[…]}`, no envelope.

## Reading ADF — better here than via the MCP

`SKILL.md` § *Reading templates* documents an MCP quirk: `responseContentFormat:
"adf"` is **not** honoured for `description`, so templates fetch back as
flattened Markdown. **Direct REST v3 has no such quirk** — `GET /issue/{key}`
returns `description` (and all rich fields) as true ADF. To inspect a template's
real structure cheaply: `jira get KEY <richfield> --json`. This is the
recommended way to read a template's ADF before authoring the write that clones it — on either
transport.

## Writes via `curl` (the simple ones)

Plain-field edits and plain comments are in-scope for direct calls.

```sh
# Plain-field edit — returns 204, no body
echo '{"fields":{"summary":"Updated summary"}}' \
  | jira raw PUT /issue/INTRD-1486 @-
# (or: jira raw PUT /issue/INTRD-1486 '{"fields":{"summary":"Updated summary"}}')

# Plain comment
jira comment INTRD-1486 'Confirmed with QA — proceeding.'

# Apply a transition (after `jira transitions INTRD-1486` to find the id)
jira transition INTRD-1486 31
```

Rich payloads are not excluded from this path — see the next section.

## Writing ADF through `jira raw` — the cheap path

A full ADF body posts perfectly well through the direct path. `jira raw` hands its third argument
straight to `curl --data` (`bin/jira:232`), so `@file.json` sends the file's contents with newlines
stripped — harmless for JSON, where they are only inter-token whitespace (`--data-binary` is the
byte-verbatim form, for payloads where they are not):

```sh
jira raw POST /issue @payload.json                    # create with an ADF description
jira raw POST /issue/<KEY>/comment @comment.json      # ADF comment
```

**For anything large, generate the ADF with a throwaway script rather than writing it inline.** A small
Python file with `heading()` / `rule()` / `panel()` / `table()` helpers, dumped to `payload.json`, then
posted by `@file`. The point is not the script — it is that **the ADF never enters the model context**:
you author the generator, not the blob. The INTRD-26660 review produced four issues and a ~20 KB comment
this way with no ADF in context at all.

```sh
python3 mk_payload.py > payload.json                                          # your generator
jq -e '.fields.description | .type == "doc" and .version == 1' payload.json   # validate, then post
jira raw POST /issue @payload.json
```

| Situation | Path |
|---|---|
| Large, repetitive or generated body — long tables, many panels, a full template clone | `jira raw` + `@file` |
| A batch of issues sharing one structure | `jira raw` + `@file` — one generator, one file per issue |
| One short rich comment or panel, hand-written | either; the MCP needs no generator, so it usually wins |
| Story fields `customfield_10134`–`10137` — all four, inside `POST /issue` | `jira raw` + `@file` **preferred**; MCP `createJiraIssue` also works |
| An edit under the inline-media safety rule | **Rovo MCP** — see below |

**With `raw` you own ADF correctness.** The MCP validates the document it builds for you; `curl` does
not. Jira rejects some malformed documents with a `400`, but a *structurally valid* document carrying
the wrong marks or nesting posts silently and renders wrong. Validate the structure before posting:
confirm the top-level `{"type":"doc","version":1}` envelope, and for a template clone diff your
generated structure against the template's own ADF (`jira get <TEMPLATE-KEY> description --json`, per
[Reading ADF](#reading-adf--better-here-than-via-the-mcp) above).

## What stays on the MCP

One thing is MCP-only:

- Any edit covered by the **inline-media safety rule** in `SKILL.md`
  § *Destructive edits on fields containing inline media* — that check and its
  `attachment[]` cross-reference assume the MCP read/edit flow.

**Story rich-text custom fields `customfield_10134`–`10137` are *not* MCP-only.** Direct REST writes
ADF to all four correctly — verified across nine Stories plus a template rewrite, with dark-red
headings, rules, panels, tables and links confirmed intact via `expand=renderedFields`. Since these
payloads are large (~330 KB of ADF for seven Stories) and the MCP injects whole responses into
context, **`jira raw` with a generated `@file` payload is the preferred path for bulk Story
creation** — the ADF never enters the context at all. Note the four fields must be sent **inside the
create call**, not a follow-up edit — see `stories.md` § *Template-seeding automation*.

Everything else may go either way. **Issues created or rewritten from a template** — the ones that must
reproduce the dark-red `#bf2600` headings, `rule` nodes and note/warning panels (`SKILL.md`
§ *Templates index § Writing templates*) — are a judgement call, not an MCP mandate: the MCP is fine,
and `jira raw` with an `@file` payload is the preferred path once the body is large or repetitive. The
trade is the validation risk above — on `raw`, ADF correctness is yours.

## The `twg` CLI — a third transport, for two things only

Atlassian ships its own CLI, **`twg`** (Teamwork Graph CLI, GA, Apache-2.0, `atlassian/twg-cli`): one
self-contained binary, ~920 commands across Jira, Confluence, JSM and Bitbucket, installed with
`bash <(curl -fsSL https://teamwork-graph.atlassian.com/cli/install)`. Auth is OAuth 2.1 device flow
(`twg login`) with per-product read/write/delete scopes — it works over SSH, since the device flow
just prints a URL to open anywhere, **but it has to be run by a human at an interactive terminal**
(see *Installing and authenticating from a session* below). `TWG_TOKEN` / `TWG_USER` / `TWG_SITE`
are the alternative for a headless box that should reuse the existing `~/.netrc` API token and skip
OAuth refresh entirely. Note `read:account` is a **required base scope**: grant it or `twg login` fails to resolve
your identity after issuing the tokens.

### Installing and authenticating from a session

Two things bite an agent-run install. Both were found on a headless box (2026-09-17) and one of them
silently undoes the whole install.

- **Pass `-y`, or the install rolls itself back.** The installer shells out to `twg consent` (the
  Atlassian Customer Agreement / Privacy Policy acknowledgement), which refuses to prompt without a
  controlling terminal — the install then **fails and reverts**, leaving no binary and no
  explanation beyond `Command failed: … twg consent`. `-y` records consent non-interactively, and
  only takes effect alongside `--skip-login --skip-skills`:
  `bash <(curl -fsSL https://teamwork-graph.atlassian.com/cli/install) --skip-skills --skip-login -y`.
- **`twg login` cannot be driven by a session — and relaying its URL does not work either.** It
  times out after **2 minutes** and detects the environment, failing with *"This looks like a
  non-interactive/agent environment — run `twg login` yourself in an interactive terminal"*. The
  reason relaying fails is worth knowing: the browser approval only marks the code approved
  **server-side**, and it is the *local* process that exchanges it for tokens — so a code approved
  after that process was killed or restarted yields nothing, however promptly the user acted.
  Hand the step over whole (in Claude Code, `! twg login`), and on a headless box tell them to
  answer **`n`** to the `Open in browser?` prompt.

Then confirm before relying on it: an unauthenticated call fails fast and unambiguously with
`AUTH_REQUIRED` and **exit 77**, so `twg jira workitem field update-metadata --id <any Story>`
doubles as the auth check and the capability check.

**It does not replace the `jira` helper.** Measured against this project, same issue and same query
(2026-09-17, `twg` 1.3.0):

| Operation | `jira` | `twg` | ratio |
|---|---|---|---|
| Read one issue, defaults | 5,510 B | 68,742 B | **12.5×** |
| Read one issue, same 8-field allowlist | 5,510 B | 41,015 B | **7.4×** |
| JQL, 10 issues, `summary,status` | 1,402 B | 10,961 B | **7.8×** |

`twg jira workitem get` and `workitem query` **ignore the global `-o text`** and always emit raw JSON
— full `self` and avatar URLs, nested `statusCategory` objects, and **unflattened ADF**. The `jira`
helper's jq projection has no equivalent, so reads, JQL, counts, transitions and bulk ADF writes all
stay here. Atlassian's "48% fewer tokens" is measured against the **MCP**, which injects whole
responses; against a projecting wrapper the comparison inverts.

### The two things it is for

| Use `twg` for | Why |
|---|---|
| `twg jira workitem field update-metadata --id KEY` | Lists the **edit-only** fields with IDs, types and allowed operations — including `Requirement` (10134), `Functional design` (10135), `Acceptance` (10136), `Technical design` (10137). `jira meta` reads the *create* screen and structurally cannot show these. |
| `twg jira workitem comment create --issue-id KEY --body '<markdown>' --body-format markdown` | Converts Markdown → ADF client-side. Verified: heading, `strong`, inline code, link, bullet list and a fenced Java block all rendered correctly. `jira comment` builds trivial plain-text ADF only. |

`twg jira workitem field create-metadata --space INTRD --type Story` returns the same field set as
`jira meta 10001` at the same cost, with types and a ready-made `--field` example — use either.

Confluence is a separate question, deliberately left open: `twg confluence content *` uses the
compact text renderer (a 3-page listing cost 235 B) and carries Markdown bodies and snapshot-token
concurrency. Worth evaluating against the Rovo MCP for `oc-fn-documentation`; out of scope here.

### The trap — a `twg` write can report success and land nothing

**`twg jira workitem create` filters fields against the create screen and drops the rest silently,
while returning `{"success": true}`.** Verified 2026-09-17: a Story created with
`--description '<markdown>' --description-format markdown` came back showing the project's default
"DO NOT USE" panel — the description never landed, and nothing in the output said so. The *same*
description sent as ADF through `jira raw POST /issue` **does** land (both probe issues deleted
after the check). That is the `createmeta`-omits-`description` row already in
[Troubleshooting](#troubleshooting) below, and it is precisely the case `twg` gets wrong.

So: **never use `twg` for a create carrying a field `createmeta` does not list.** `jira raw` surfaces
Jira's own error; `twg` manufactures a success.

Two smaller edges:

- **`--field NAME=VALUE` does not convert.** It passes the string straight through, so an ADF field
  answers `400 … must be an Atlassian Document`. Raw ADF via
  `--fields-json '{"customfield_10134": {…}}'` works and renders correctly (`#bf2600` heading +
  `rule` verified intact) — but that is what `jira raw` already does, from a payload file rather
  than an argv string.
- **`twg jira workitem delete --id KEY` has no confirmation flag at all** (`--yes` is rejected as an
  unknown option) and deletes immediately.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `401 Unauthorized` | Missing or wrong `~/.netrc` entry, or token revoked. Re-check the `machine` host and recreate the token. |
| You are pasting `--token=…` from one `jira jql` call into the next | Stop — use `--all`, which follows the cursor itself. Hand-carrying the cursor is the failure mode it exists to remove. |
| A `jql` result looks suspiciously round (exactly 10, 50, 100 rows) | You read one page. Confirm with `jira count` on the same query; add `--all` if they disagree. |
| `jira jql --all` exits `2` | The `JIRA_MAX_PAGES` guard truncated the drain — the result is **incomplete**. Raise `JIRA_MAX_PAGES`, narrow the query, or resume from the `--token=` printed on stderr. |
| `410 Gone` on search | You hit the removed `/search` endpoint — use `POST /search/jql`. |
| `404` whose body reads `No endpoint <METHOD> /rest/api/3/rest/api/3/…` | You passed a full path to `jira raw`, which prepends `/rest/api/3` itself. Drop the prefix: `jira raw GET "/project/INTRD"`. |
| `jira get KEY <fields>` prints the key and nothing else, or omits a field you asked for | The default projection drops `null`-valued fields (`bin/jira:150`). The value is `null`, not an error — re-read with `--json` + `jq` (or `jira raw GET '/issue/KEY?fields=<field>'`) whenever the value must be relied on. |
| `createmeta` lists no `description` for `Bug` / `Sub-bug` | Expected — `description` is not on their create screen. `POST /issue` accepts an ADF `description` at creation anyway; send it. |
| `400` on a write with `"…must be an Atlassian Document…"` | The field needs ADF, not a string — build a `{"type":"doc",…}` object (or route the write to the MCP). |
| A `twg` create returned `{"success": true}` but a field came back empty | `twg` drops fields absent from `createmeta` without saying so — see [The trap](#the-trap--a-twg-write-can-report-success-and-land-nothing). Re-send through `jira raw POST /issue`, which reports Jira's own error. |
| `400 … must be an Atlassian Document` from `twg … --field "Name=<markdown>"` | `--field` does not convert. Pass raw ADF via `--fields-json`, or use `jira raw` with an `@file` payload. |
| Empty body on a successful edit/transition | Expected — `204 No Content`. |
