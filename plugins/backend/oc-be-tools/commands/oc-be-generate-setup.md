# Generate a Postman SETUP collection from an Opencell environment

You generate the **Postman SETUP collection** of a client project from an Opencell environment that is already
configured: the developer chooses what to export, you build and validate the export configuration, install the
export tool, run the job, download the collection and replay it. The developer reviews and commits the result.

The knowledge comes from the opencell-setup-export repository, loaded by the `oc-be-setup-guide` skill.

## Input

Optional arguments:

- `--base-url <url>`: REST base URL of the instance to export (default: `$OC_BASE`, else
  `http://localhost:8080/opencell/api/rest`).
- `--preset SETUP|CATALOG|CUSTOMER|FULL`: skip the module question.
- `--replay-url <url>`: an **empty** Opencell to replay on (the real proof). Without it, the replay runs on the
  exported instance itself, which only proves that the API accepts the requests and that a second run does no
  harm.
- `--out <dir>`: where the collection goes in the developer's checkout (default: `./postman/setup/`).
- A Jira ticket key, when the export is done for a ticket: only used to name the files and the session.

## Critical rules

1. **Never write on production.** On a non-local instance, write only after the developer confirmed it by name
   (Phase 0); `setup_export.py` refuses otherwise.
2. **Credentials only from `OC_USER` / `OC_PASS`** in the environment of the session. Never ask the developer to
   paste them; if they are missing, explain how to set them and stop.
3. **Never send the script or a configuration through a Postman request**, never put a `{{` in them: Postman would
   replace it with the installer's values (password leak found by the INTRD-42665 tests). Use
   `setup_export.py install` and `run`.
4. **Never edit the configuration saved on the job**, never modify the client's Postman collections, never commit:
   the developer commits the generated collection.
5. **Never write a definition from memory.** Configurations are built from the catalogue with `build-config`. A
   missing entity is reported as a gap, not improvised.
6. Every checkpoint below is a **hard pause** with the `AskUserQuestion` tool, in every permission mode including
   auto mode. A prose question is not enough. `AskUserQuestion` offers at most 4 options per question: ask the
   modules in two multiple-choice questions, and the entities of a module as a numbered list answered in one line.
7. Write nothing to Jira.

## Phase 0: Instance (checkpoint)

1. Invoke the `oc-be-setup-guide` skill: resolve `$REPO` (§ 1).
2. Check `OC_USER` / `OC_PASS` and that the instance answers: `python3 "$REPO/tools/setup_export.py" --base-url
   <url> version`. Pick the branch of that version (skill § 2); exit code 3 means untested: say so.
3. Classify the instance: **local** (`localhost`, `127.0.0.1`), **shared** (any other host), or **production**
   (the developer says so, or the host or name says `prod`). Production: stop.
4. **`AskUserQuestion`: "Export from <url> (Opencell <version>, <local | shared: host>)?"** — **Go** / **Another
   instance** / **Stop**. For a shared instance the question names the host and says the tool will install a
   script and a job there, with the project's agreement. Block until answered. On a shared instance, pass
   `--allow-instance <host>` to every writing sub-command afterwards.

Show once, without waiting: `/rename setup export <host>` (or `/rename {TICKET} setup`).

## Phase 1: Discover (read-only)

Run `setup_export.py discover`. Show the modules and entities **that have rows**, with their counts; say that the
counts include the installation rows, which the export skips unless the project modified them. Entities with 0 rows
are not proposed.

## Phase 2: Choose (checkpoint)

1. Unless `--preset` was given: **`AskUserQuestion`** (multi-select) with the presets **SETUP** (modules 1–4),
   **CATALOG** (5), **Customer hierarchy** (6), **Full**; "Other" lets the developer name modules.
2. For each chosen module with more than one entity, show the numbered list of its entities (with counts) and ask
   in one line: all (empty answer), exclude (`-3,5`), or only (`2,4`). Then ask whether a code filter is needed
   (`OfferTemplate=off_cyber_%`, `Product=CODE1,CODE2`); none by default.
3. Ask, in one line, for which instance and user the generated environment is made: the base URL (for example
   `https://<project>-dev.opencell.com/opencell`) and the user; default: the catalogue values
   (`http://localhost:8080/opencell`, `opencell.admin`). Never ask for the password: it is always written empty,
   the developer types it in Postman (current value) or passes it at replay time.
4. Build the configuration:

   ```bash
   python3 "$REPO/tools/setup_export.py" build-config --preset <P> | --modules "<M1>,<M2>" \
     [--exclude <E1,E2>] [--only <E1,E2>] [--filter "<Entity>=<pattern>"] \
     [--collection-name "<name>"] [--target-base <url>] [--target-user <user>] \
     --out <work dir>/setup-config.json
   ```

5. Show the result: modules and entities in replay order, **the dependencies the tool added and why**, the
   filters, the target URL and user of the generated environment, and any warning (an excluded entity another
   one depends on).
6. **`AskUserQuestion`: "Approve this choice?"** — **Approve** / **Change** / **Stop**. On Change, go back to
   step 2.

## Phase 3: Configure (checkpoint)

1. `setup_export.py validate <work dir>/setup-config.json`. An invalid configuration is a bug of the catalogue or
   of the choice: report it, do not patch definitions by hand.
2. Show what will happen on the instance: install or update the script `ExportPostmanCollectionScript`, the custom
   field `ScriptingJob_json_variable` and the job `PostmanExportScriptJob`; run the job with this configuration for
   this run only; files written under the export directory of the instance.
3. **`AskUserQuestion`: "Run the export on <url>?"** — **Run** / **Change the choice** / **Stop**. Block until
   answered.

## Phase 4: Export

1. `setup_export.py install`. A compilation error means this branch does not match the instance version: stop and
   report the errors; never edit the script to make it compile.
2. `setup_export.py run <work dir>/setup-config.json`. Show the job report (`Entity: N exported, M failed`). If an
   entity failed, read the reason in the report or in the server log (when the instance is local) and report it;
   do not run again without a change.

## Phase 5: Download

`setup_export.py download --out <work dir>/export`. It refuses a collection holding a secret value. Count the
requests per module.

## Phase 6: Replay

```bash
python3 "$REPO/tools/setup_export.py" --base-url <replay url> replay <work dir>/export/collection.json \
  --log <work dir>/replay.log
```

- With `--replay-url` (empty instance, preferred): the real proof. Before, check it is empty (`discover`: no
  project rows) and that the developer confirmed it in Phase 0 if it is not local.
- Without it: replay on the exported instance. Requests answered « already exists » and existence checks are
  expected; say what this replay proves and what it does not.
- A failure: read the log, explain the cause (missing definition, version mismatch, data the API refuses). A fix
  belongs to the catalogue or the script in the repository, through a change the developer reviews: do not patch
  the generated collection. At most 3 rounds back to Phase 2 or 3.

## Phase 7: Review (key checkpoint)

1. Copy `collection.json` and `environment.json` to `--out` (default `./postman/setup/`), named after the
   collection (`<name>.postman_collection.json`, `<name>.postman_environment.json`). Never overwrite a file
   without asking.
2. Show the wrap-up:

   ```
   ## Setup export: <collection name>
   Source: <url> (Opencell <version>, branch <branch> of opencell-setup-export)
   Files: [<collection>](<absolute path>) · [<environment>](<absolute path>)

   | Module | Entities | Requests |
   Job report: <N exported, M failed per entity>
   Replay on <url>: <requests, tests, failures> — <what it proves>
   Not exported: <entities chosen but without a definition, parts of the setup the tool does not cover:
   custom fields, scripts, notifications, jobs, dunning, payment gateways, files; Keycloak users and secrets>
   ```

3. **`AskUserQuestion`: "Review the setup: keep these files?"** — **Keep** / **Change the choice** / **Discard**.
   On Keep, suggest the commit (`{TICKET}: Add the generated SETUP collection` when a ticket was given); do not
   commit.
