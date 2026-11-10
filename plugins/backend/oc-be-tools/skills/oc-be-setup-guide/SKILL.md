---
name: oc-be-setup-guide
description: >
  TRIGGER when user asks to generate, export or regenerate a Postman SETUP (or CATALOG) collection from an Opencell
  environment or database, to export an Opencell configuration (catalog, taxes, sellers, invoice settings, customer
  hierarchy) to Postman, to replicate a configuration from one environment to another with Postman, or to work on
  ExportPostmanCollectionScript, PostmanExportScriptJob or its JSON export configuration (modules, entity
  definitions, filters). Also trigger when reading or planning a Jira ticket whose need is such an export.
  Loads the opencell-setup-export repository (script, definition catalogue, command-line tool), the rules that
  keep the generated collection replayable, and the safety rules for running the export on an instance.
---

# Opencell setup export guide

The tool lives in the **opencell-setup-export** repository (`opencellsoft/opencell-setup-export`): the export
script `ExportPostmanCollectionScript` (an Opencell script of type `JAVA`, run by the `ScriptingJob`
`PostmanExportScriptJob`), the definition catalogue, and `tools/setup_export.py`, the command-line tool that does
every step. This skill locates it and says how to use it safely. It does **not** restate the repository: read its
README.

## 1. Resolve the repository

```bash
REPO=""
# 1. an explicit location (a developer's own working clone)
[ -n "$OC_SETUP_EXPORT" ] && [ -f "$OC_SETUP_EXPORT/tools/setup_export.py" ] && REPO="$OC_SETUP_EXPORT"
# 2. the clone managed by oc-be-tools
MANAGED="$HOME/.claude/oc-be-tools/opencell-setup-export"
URL="git@ssh.bitbucket.org:opencellsoft/opencell-setup-export.git"   # Bitbucket SSH host since 12 Nov 2026
if [ -z "$REPO" ]; then
  if [ -d "$MANAGED/.git" ]; then
    git -C "$MANAGED" remote set-url origin "$URL"   # a clone made on bitbucket.org before the move
    git -C "$MANAGED" fetch -q origin || echo "WARN: could not update $MANAGED, using it as is"
  else
    mkdir -p "$(dirname "$MANAGED")" && git clone -q "$URL" "$MANAGED" || echo "ERROR: could not clone. If the message says 'Host key verification failed', accept the Bitbucket SSH host once with: ssh -T git@ssh.bitbucket.org"
  fi
  [ -f "$MANAGED/tools/setup_export.py" ] && REPO="$MANAGED"
fi
echo "$REPO"
```

- Never `pull` or switch the branch of the developer's own clone (`OC_SETUP_EXPORT`): it may hold work in
  progress. Say which branch it is on.
- If `REPO` is empty (no access to the repository), **stop** and say so.

## 2. Pick the branch of the Opencell version

The script is **compiled by the instance** it is installed on, and the definitions name DTOs, constructors and
endpoints of one Opencell version. The repository has **one branch per Opencell version** (`18.X`, …) and
`tested-versions.json` lists the versions a branch was proven on.

1. Read the instance version: `python3 "$REPO/tools/setup_export.py" --base-url <url> version`.
2. In the managed clone, check out the branch of that version (`git -C "$MANAGED" checkout -q <major>.X &&
   git -C "$MANAGED" pull -q --ff-only`). If there is none, say so and stop: never install a branch made for
   another major version.
3. Exit code 3 of `version` means the minor version is not in `tested-versions.json`: tell the developer it is
   untested and ask before installing. A compile error at install, or entities in failure in the job report, are
   the signs that a definition does not match this version.

## 3. Read, in this order

1. `$REPO/README.md`: content, quick start, presets, safety, configuration in short.
2. `$REPO/catalogue/postman_configuration.json`: the modules and the 31 definitions. A configuration is built from
   it; never write a definition from memory.
3. When a definition is missing or fails, the user guide attached to INTRD-42665 (definition options with
   examples, troubleshooting).

## 4. Rules that are easy to get wrong

| Rule | Why |
|---|---|
| Build the configuration with `setup_export.py build-config` from the catalogue, then `validate` it | It adds the missing dependencies and refuses an inconsistent configuration before anything runs |
| Pass the configuration **for one run** (`setup_export.py run <file>`), never edit the one saved on the job | The saved configuration belongs to the developers of the instance; a run-time configuration changes nothing else |
| Install with `setup_export.py install`, not by sending the script source through a Postman request | Postman replaces every `{{variable}}` of a request body with the installer's values: a password would end up in the script and in every generated collection |
| Never put a `{{` in the script or in a configuration | Same reason; the script builds `{{opencell.url}}` and the credentials variables itself, and derives `opencell.url` from `opencell.base` |
| Keep `excludeInstallData: true` | An empty Opencell already holds the installation rows; only those the project modified are exported |
| The REST API reads DTOs by their fields | A new definition whose DTO has computed getters is fine; a field the API cannot read is "Unrecognized field" |
| A create-only endpoint needs `request.createOnly`; an object without code needs `request.skipIfExists`; a status the create endpoint ignores needs `followUps` | Otherwise the replay fails on « already exists », duplicates rows, or leaves objects in DRAFT |
| Read the job report: `N exported, M failed` per entity | A failed instance does not stop the export; the report is the only place that says it |
| Check the replay **and** the database: on a non-atomic endpoint « already exists » can hide a half-created object | Example: price plan versions created without their lines after a failed first run |
| Credentials only from `OC_USER` / `OC_PASS` in the environment | Never ask for them in the conversation; the tool never prints or keeps them |

## 5. Where the tool may write

`install`, `run` and `replay` write on the instance (the script, the custom field, the job, the job history, the
export files, and for `replay` the configuration itself).

| Instance | Allowed |
|---|---|
| The developer's local instance (`localhost`, `127.0.0.1`) | Yes, after the developer approved the run |
| A shared project instance (dev, test) | Only after an explicit confirmation naming the instance; then `--allow-instance <host>` |
| Production | Never |

`discover`, `version`, `build-config`, `validate` and `download` only read. Never modify the client's Postman
collections; the generated collection is committed by the developer.
