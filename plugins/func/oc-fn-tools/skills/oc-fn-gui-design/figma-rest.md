# Figma REST — page & screen discovery

Read together with `SKILL.md` and `access.md`. Load this whenever you need to **discover** what
is in a Figma file — its pages and the frames (screens) on them. This is the gap the Figma **MCP**
connector cannot fill (its `get_metadata` returns only the first/Cover page); the Figma **REST API**
returns the whole tree, so discovery lives here.

**Division of labour:** REST **discovers** (pages → screens → node IDs); the **MCP** then does the
visual/styling work on a discovered node (`get_screenshot`, `get_design_context`, `get_variable_defs`)
and all **authoring** (`use_figma`). REST cannot write design content (read-only for file content;
the Variables write API is Enterprise-only) — never try to author through REST.

## Auth

A **Personal Access Token** in `~/.netrc`, keyed by `machine api.figma.com` (same store as the Jira
helper; see `access.md`). Figma requires the **`X-Figma-Token`** header — **not** HTTP Basic — so
`curl -n` does *not* work; the token must be read out and sent as a header. Create the PAT at
Figma → *Settings → Security → Personal access tokens*, scope **File content: Read-only**.

## The `figma` helper (accelerator)

An optional wrapper, `bin/figma` in this repo → `~/.local/bin/figma` (symlinked by `install.sh`),
the exact analogue of `bin/jira`. It reads the PAT from `~/.netrc` and projects with `jq`. Run
`figma help` for the full list. The ones you need:

| Command | What it returns |
|---|---|
| `figma pages FILEKEY` | The file's pages — `id  name` — plus a header (name, role, page count). |
| `figma find FILEKEY REGEX` | Pages whose name matches REGEX (case-insensitive) — the fast way to locate a feature's page. |
| `figma screens FILEKEY PAGEID` | A page's top-level children/frames — `id  [TYPE]  name` — i.e. the screens on it. |
| `figma node FILEKEY NODEID [DEPTH]` | The `id/type/name` tree under a node to DEPTH (default 2). |
| `figma url FILEKEY NODEID` | Builds the node-specific Figma URL (offline). |
| `figma me` | The authenticated user (auth sanity check). |
| `figma raw METHOD PATH [DATA]` | Escape hatch — raw response. |

`FILEKEY` is the `figma.com/design/<FILEKEY>/…` segment; `NODEID` accepts colon (`123:456`) or dash
(`123-456`) form.

**Typical discovery flow:** `figma find <key> "<feature>"` → get the page id → `figma screens <key>
<pageId>` → get the screen's node id → hand `<key>` + node id to the MCP (`get_screenshot` /
`get_design_context`) for the picture and the component/token detail. `figma url` turns the node id
into the link that becomes the Story's source-of-truth Figma reference.

## Raw `curl` recipes (the fallback — no helper needed)

The helper is a convenience. Anyone with the PAT + `curl`/`jq` (including teammates who install the
marketplace bundle, which does **not** ship `bin/`) can do the same directly. Read the token first:

```bash
TOK="$(awk 'END{for(j=1;j<=n;j++){if(tok[j]=="machine")c=(tolower(tok[j+1])=="api.figma.com");if(c&&tok[j]=="password"){print tok[j+1];exit}}} {for(i=1;i<=NF;i++)tok[++n]=$i}' ~/.netrc)"
H=(-H "X-Figma-Token: $TOK" -H "Accept: application/json")
```

- **Pages** (document → pages; `depth=1` keeps it light):
  ```bash
  curl -sS "${H[@]}" "https://api.figma.com/v1/files/<KEY>?depth=1" \
    | jq -r '.document.children[] | "\(.id)\t\(.name)"'
  ```
- **Screens on a page** (`/nodes` with `depth=2` = the page and its direct children):
  ```bash
  curl -sS "${H[@]}" "https://api.figma.com/v1/files/<KEY>/nodes?ids=<PAGEID>&depth=2" \
    | jq -r '.nodes["<PAGEID>"].document.children[] | "\(.id)\t[\(.type)]\t\(.name)"'
  ```
- **Node-specific URL** (for the Story link): `https://www.figma.com/design/<KEY>/?node-id=<ID>`
  — with the node id in **dash** form (`123-456`).

## Token discipline

The full-file JSON can be large. Stay shallow and drill on demand — the same ethos as the rest of
the skill:

- **Never fetch the whole file** (`GET /v1/files/:key` with no `depth`). Use `depth=1` for pages,
  then `/nodes?ids=…&depth=2` per page for screens.
- **Enumerate pages once**, reuse the ids; don't re-list per screen.
- **Hand off to the MCP** for anything visual or styling-level — don't pull deep node geometry over
  REST when a `get_screenshot` / `get_design_context` answers the question.
- REST is for **structure discovery**; MCP is for **content**. Keep each to its job.
