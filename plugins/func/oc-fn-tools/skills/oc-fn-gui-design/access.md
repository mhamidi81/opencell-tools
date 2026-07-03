# Figma access — connector, files, and the node-URL constraint

Read together with `SKILL.md`. Load this when connecting, adding a file, or on any access error.

## The connector

Figma is reached through the **claude.ai Figma connector** — the official Figma **remote** MCP
server (`https://mcp.figma.com/mcp`, OAuth). It surfaces tools as `mcp__…Figma__<verb>`
(`whoami`, `get_libraries`, `search_design_system`, `get_variable_defs`, `get_metadata`,
`get_design_context`, `get_screenshot`, `download_assets` for reads; `use_figma`, `create_new_file`,
`generate_figma_design`, `upload_assets` for writes).

- **Enabled in claude.ai, not bundled.** Authorize it with `/mcp` → "claude.ai Figma" → complete the
  OAuth sign-in. This is the same "enable it in claude.ai" pattern as the Atlassian Rovo connector —
  so the `oc-fn-tools` marketplace bundle does **not** ship a Figma MCP server.
- **Check at session start.** Call `whoami`. It returns the authenticated handle, email, and the
  teams/seats. If it errors, the connector is not authorized — ask the user to run `/mcp`.

## Seats & write capability

`whoami` for this account returns **Full seats** on the Opencell teams (*OC* ×2, starter tier;
*Opencell Product*, pro tier). A **Full seat is required to write outside drafts** (Mode B); a Dev
seat is read-only outside drafts. Reads work on any seat. MCP `get_variable_defs` reads tokens on
any tier — the REST Variables API is Enterprise-only, but this skill never needs it.

OAuth scopes that matter: `file_content:read`, `file_metadata:read`, `library_content:read` (reads);
write capability for `use_figma`. `file_variables:read` (REST tokens) is Enterprise-only and unused.
Scopes never exceed the user's own access — a file must be shared with the authenticated user to be
readable.

## Known files

| File | Key | What it is |
|---|---|---|
| **Opencell — Design System** | `La67u40TTxeEy8HAcXMOeC` | The published team library (below). Components, tokens, styles. |
| **NewUI — already dev AND To come** | `DZ7EnuPmWBlkAsjHgEsoqI` | Real product screens — "already dev" + "to come" (Apollo 18.1). |
| **To come** | `ChRmR0xhYt8rPLjvLd2mGr` | Upcoming screen designs. |

**Design System library key** (pass to `search_design_system` as `includeLibraryKeys`):

```
lk-63112bc6220faa9e4bbfca81589ac9e92db21a5b7aaaa906d7aaa77f9aa6511168b451fd7e581349133d239790fdfa46d367cd963ddf65a1d40289c5429fdb94
```

To confirm the library set on any file, call `get_libraries(fileKey)` — it returns the libraries the
file subscribes to plus org libraries available to add, each with its `libraryKey`. The Opencell DS
is the only *team* library in use; the Material 3 / Apple / Figma "Simple Design System" entries are
community kits merely *available*, not part of the Opencell system — ignore them.

**Adding a file.** The MCP has no "list my files" tool, but **REST does**: `GET
/v1/teams/<team_id>/projects` then `GET /v1/projects/<project_id>/files` enumerate a team's projects
and files (team ids are the `team::<id>` keys from `whoami`). For a one-off, take the file's URL from
the user and extract the `fileKey` from `…/design/<fileKey>/<name>…`. Record recurring files in the
table above.

## Page & screen discovery — via REST, not the MCP

The Figma **MCP** connector cannot list a file's pages: `get_metadata` with **no** `nodeId` returns
only the first/*Cover* page (confirmed on all three files), and there is no pagination to reach the
rest. **This is an MCP tool gap, not a Figma limitation** — the Figma **REST API** returns the whole
tree, every page and the frames (screens) on it.

**So discovery is a solved problem — do it yourself over REST**, via the `figma` helper (or raw
`curl`); full recipes in **`figma-rest.md`**:

- `figma pages FILEKEY` — list the pages.
- `figma find FILEKEY REGEX` — locate a feature's page by name.
- `figma screens FILEKEY PAGEID` — list the screens (frames) on a page.

Then hand a discovered node id to the MCP for the picture and the styling detail (`get_screenshot`,
`get_design_context`, `get_variable_defs`). Net division:

- **Design-system reads** — library-scoped `search_design_system` / `get_variable_defs`, page-independent (as before).
- **Screen discovery** — REST (`figma pages` / `find` / `screens`); no longer blocked. Enumerate screens yourself; don't ask the user to hunt for node-URLs.
- **A frame the user points at** — a node-specific URL still works directly and is what becomes the Story's source-of-truth link.

### Node-URL — build it or receive it

`figma url FILEKEY NODEID` builds the node-specific URL from a discovered id. Or the user supplies one:

> In Figma, click the screen's top-level **frame**, then **right-click → Copy link to selection**
> (⌘L / Ctrl+L) — `https://www.figma.com/design/<fileKey>/<name>?node-id=<id>`.

Either way, extract `fileKey` + `node-id` (the `123-456` and `123:456` forms are interchangeable —
the MCP tools accept both) and pass them to `get_metadata` / `get_design_context` / `get_screenshot`
/ `get_variable_defs`.

## Quick reference — which tool for which question

| You need… | Tool | Notes |
|---|---|---|
| Confirm auth / identity / seats | `whoami` (MCP) / `figma me` (REST) | No fileKey needed. |
| **List a file's pages** | `figma pages FILEKEY` (REST) | The MCP can't — see `figma-rest.md`. |
| **Find a page by name** | `figma find FILEKEY REGEX` (REST) | Case-insensitive name match. |
| **List screens on a page** | `figma screens FILEKEY PAGEID` (REST) | The frames on that page. |
| The libraries on a file | `get_libraries(fileKey)` | Returns `libraryKey`s to scope searches. |
| Find a component / token / style by name | `search_design_system(query, fileKey, includeLibraryKeys=[DS])` | Scope to the DS key; toggle `includeComponents/Variables/Styles`. |
| Live token values on a frame | `get_variable_defs(fileKey, nodeId)` | `{}` on frames that bind no variables — use a real component/screen node. |
| The structure of a node | `get_metadata(fileKey, nodeId)` | Cheap XML (ids, types, names, sizes). No `nodeId` → only the Cover page. |
| Styling + framework code for a node | `get_design_context(fileKey, nodeId)` | Verbose; drill only where needed. |
| A picture of a frame | `get_screenshot(fileKey, nodeId)` | Returns a URL + curl; keep `enableBase64Response` off. |
| Author into Figma (Mode B) | `use_figma`, `create_new_file`, … | Read `/figma-use` first; safety gate in `workflow-author.md`. |
