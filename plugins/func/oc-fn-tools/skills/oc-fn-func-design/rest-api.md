# Direct Jira REST API — token-efficient reads & light writes

> **This direct REST path is an OPTIONAL token-saving optimisation.** If you only have the Atlassian
> connector (Rovo MCP), skip this file — the MCP covers every operation here on its own, with no token
> or `~/.netrc` setup. This path (the `jira` helper or raw `curl`) just filters responses in the shell
> so they cost fewer tokens than the MCP, which injects every response into context in full.

Load this file whenever the current INTRD task is a **read, JQL search,
metadata lookup, transition, plain-text comment, or simple plain-field edit**
**and** you have the optional direct path set up.
Per the transport policy in `SKILL.md`, these can go through the `jira` helper (or
raw `curl`) when installed, otherwise through the Rovo MCP. Complex ADF writes stay on the MCP — see
[What stays on the MCP](#what-stays-on-the-mcp).

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
| `jira jql 'QUERY' [--fields=a,b] [--max=N] [--token=T] [--json]` | Enhanced JQL search | one `KEY ⇥ status ⇥ summary` line per issue (+ paging hint) |
| `jira count 'QUERY'` | Approximate match count | a single number |
| `jira transitions KEY` | List available transitions | `id ⇥ name` lines |
| `jira transition KEY ID` | Apply a transition | `ok: …` (API returns 204) |
| `jira comment KEY 'TEXT'` | Add a plain-text comment | `ok: comment #…` |
| `jira meta ISSUETYPE_ID` | Create-fields for an issue type | `fieldId ⇥ name ⇥ required=…` |
| `jira raw METHOD PATH [DATA\|@file.json]` | Escape hatch | raw response |
| `jira aliases` | List the built-in JQL aliases | `name ⇥ expansion` lines |

Examples:

```sh
jira get INTRD-1486                                   # read preset, ADF as text
jira get INTRD-1486 summary,status                    # narrower allowlist
jira get INTRD-42531 customfield_10137 --json         # true ADF of a Story field
jira jql 'project = INTRD AND statusCategory != Done ORDER BY updated DESC' --max=15
jira count 'project = INTRD AND created >= -7d'
jira meta 10001                                        # find customfield_* IDs for an issue type
jira raw GET '/issue/INTRD-1486?expand=renderedFields&fields=description'
```

### JQL aliases

Common queries have short aliases, runnable either as a top-level shortcut
(`jira mine`) or under `jql` (`jira jql mine`) — both are identical. Aliases
inherit every `jql` flag (`--max`, `--fields`, `--json`, `--token`). All are
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
recommended way to read a template's ADF before authoring its MCP write.

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

For a create/edit whose payload is **plain** (no rich panels/colours), raw curl
with an `@adf.json` file works too — but if the field is one of the ADF-mandated
ones below, prefer the MCP.

## What stays on the MCP

Per the hybrid policy, keep these on the Rovo MCP, where ADF construction and
validation lower the risk:

- **Story rich-text custom fields** `customfield_10134`–`10137` (the ADF-only
  fields — see `SKILL.md` § *Content format policy* and `stories.md`).
- **Issues created or rewritten from a template** that must reproduce the
  dark-red `#bf2600` headings, `rule` nodes, and note/warning panels
  (`SKILL.md` § *Templates index § Writing templates*).
- Any edit covered by the **inline-media safety rule** in `SKILL.md`
  § *Destructive edits on fields containing inline media* — that check and its
  `attachment[]` cross-reference assume the MCP read/edit flow.

You *can* do these via raw curl + `@adf.json`, but only do so on explicit
request; the default for rich ADF writes is the MCP.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `401 Unauthorized` | Missing or wrong `~/.netrc` entry, or token revoked. Re-check the `machine` host and recreate the token. |
| `410 Gone` on search | You hit the removed `/search` endpoint — use `POST /search/jql`. |
| `400` on a write with `"…must be an Atlassian Document…"` | The field needs ADF, not a string — build a `{"type":"doc",…}` object (or route the write to the MCP). |
| Empty body on a successful edit/transition | Expected — `204 No Content`. |
