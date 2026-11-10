# Generate a script draft from a Jira ticket

You generate a **developer-ready draft** of the Opencell script(s) a Jira ticket needs: the hook point
each script plugs into, the right starting point (business template or starter), the script type and
transaction strategy, the code, a compile check on an instance, and the configuration to do. It is a
draft for the developer to refine, not final code.

The knowledge comes from the Opencell script library, loaded by the `oc-be-script-guide` skill.

## Input

A Jira ticket key (e.g. `INTRD-41234`). If none is given, ask for one. Optional arguments:

- `--base-url <url>`: REST base URL of the development instance for the compile check (default:
  `$OC_BASE`, else `http://localhost:8080/opencell/api/rest`).
- `--no-compile`: skip the compile check (say so in the wrap-up). Refused when the library branch is not
  the one of the target Opencell version (`oc-be-script-guide` § 1).

## Critical rules

1. **Never invent a business rule, an entity field or a service method.** When the ticket does not say,
   stop and ask. Check every service and method you use in the library or in the core.
2. **Never write on a live instance.** The compile check creates each script **disabled** and deletes it;
   never use `--keep`, never deploy or enable a script, never run `mvn opencell:deploy-scripts`.
   Deployment is the developer's action.
3. **Write nothing to Jira** except the summary comment of Phase 7, after the developer's
   confirmation; never attach or post the code.
4. **Read an attachment only when the developer names it**: sample files may hold real customer data.
5. Explicit types (never `var`), `jakarta.*` (never `javax.*`, except the JDK's own `javax.xml.*`),
   Javadoc on every method.
6. Every checkpoint below is a **hard pause** with the `AskUserQuestion` tool, in every permission mode
   including auto mode. A prose question is not enough.

## Phase 0: Setup

1. **Where the scripts go.** Find out whether the current directory is an overlay repository (see
   `oc-be-script-guide` § 3).
   - Overlay: the scripts go in its script module (package from its profile), and a `JAVA_CLASS` in the
     module the profile uses for compiled code.
   - `opencell-core` (modules `opencell-admin`, `opencell-model`): a standard core script is a
     `JAVA_CLASS` in its module, `opencell-admin/ejbs/src/main/java/org/meveo/service/script/<category>/`,
     registered by a Liquibase changeset in `opencell-model/src/main/resources/db_resources/changelog/current/structure.xml`
     (and `rebuild/data-demo.xml` when the script is part of the demo data). If a class with the same name
     exists, stop and ask: never overwrite it.
   - Anywhere else: write them under `./scripts/{TICKET}/` in the current directory.
2. **Branch** (only when the target is a git repository). Resolve the branch type from the Jira issue
   type (`getJiraIssue({TICKET}, fields: ["issuetype", "summary"])`: Story or Enabler → `feature/`, Bug
   or Sub-bug → `bugfix/`; anything else: ask). Then **`AskUserQuestion`**: *"For {TICKET}, create a new
   branch or use the branch you're already on?"* (**New branch** / **Use current branch**). Do nothing
   else until answered. New branch: ask for a short description and create
   `{username}/{type}/{TICKET}-{description}`.
3. **AI-stats run directory**: `RUN_ID={TICKET}-$(date -u +%Y%m%d-%H%M%S)`, create
   `.claude/cache/ai-stats/{RUN_ID}/`. Best-effort, non-blocking.
4. Show once, without waiting: `/rename {TICKET} script`.

## Phase 1: Read the ticket

Same reading as `/oc-be-implement` Phase 1:

- `getJiraIssue` with `fields: ["*all"]` (cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`). Read the
  `description` and the custom fields `customfield_10134` (Requirement), `customfield_10135`
  (Functional design), `customfield_10136` (Acceptance), `customfield_10137` (Technical design); an
  Enabler often has only the `description`. The response is large: parse it with a script.
- Read the **sub-tasks and comments**: a comment may refine or override the design.
- List the attachments **by name only**; ask before reading one.
- **Hard stop** if the ticket cannot be read: report the error, do not guess.

Extract: what triggers the script (an event, a job, a screen button, a REST call, a core processing),
the input and output data, the business rules, the error handling, the volumes.

## Phase 2: Load the script knowledge

Invoke the `oc-be-script-guide` skill (or apply it: resolve `$LIB`, read the root README sections and,
in an overlay, `OVERLAY_PROFILES.md` and `OVERLAY_SCRIPTS.md`). Then, for each candidate category, read
its README (contracts, services, business objects, patterns), its starters and its templates.

## Phase 3: Script plan (checkpoint)

Present the plan:

```
## Ticket: {TICKET} - {Title}

### Understanding
[What the ticket asks for, in your own words]

### Script 1: <ClassName>
- Hook point: <id> — <name> (<category>/README.md), configured on <entity field | job parameter | notification | inbound request>
  Why this one: <the trigger in the ticket, matched to the contract>
- Script type: JAVA | JAVA_CLASS — because <the library rule that applies>
- Transactions: <the caller's transaction | a new transaction per item | ...>; core methods in REQUIRES_NEW avoided: <which>
- Starting point: <template path> (closest business template) | <starter path> (no template is close enough: why)
- Context in: <keys> — Context out: <keys and types the core expects>
- Services / business objects: <ServiceName.method(...)>, <Entity> — each checked in <library README | core class>
- Script parameters: <code: type, meaning>
- Package and file: <package>.<ClassName> in <path>

### Configuration to do
- ScriptInstance: code, type, script category
- Where it is referenced, ScriptParameters, JobInstance if a job is needed

### Questions
[Every point the ticket does not settle. STOP here if a business rule is missing.]
```

**`AskUserQuestion`: "Script plan ready — generate the draft, or revise the plan?"** Block until
answered. On a revision, update the plan and present it again.

**After approval, write the planning checkpoint** `.claude/cache/ai-stats/{RUN_ID}/_planning.json`, in
the same format as `/oc-be-implement` (`"agent": "oc-be-generate-script"`): `planning_started`,
`plan_approved`, `revision_rounds`, `plan_word_count`, `plan_text`, `acceptance[]` (from the ticket and
the plan), `deliverables` (`unit_tests`: not applicable to a `JAVA` script, which only runs on an
instance; `postman`: not applicable unless the ticket asks for one), `notes`. Best-effort,
non-blocking.

## Phase 4: Generate the draft

For each script of the approved plan:

1. Copy the starting point (template, else starter) into the target path. Rename the class (a business
   name ending with `Script`, never `StarterScript` or `TemplateScript`, which are the library's own
   suffixes) and set the package of the target. Keep the starter's Javadoc structure (contract,
   extension point) and update it to the ticket.
2. Implement the business logic in the extension points of the starting point. Follow the rules of
   `oc-be-script-guide` § 4 and the readiness checklist of the library.
3. Put the library metadata header on the class (category, business purpose, hook point, source type,
   transaction, required configuration, services and business objects).
4. Write nothing else: no test under an overlay's script module (it never runs), no Postman collection
   unless the plan has one.

Present the files, then **`AskUserQuestion`: "Draft written — run the compile check, or changes
first?"** Block until answered.

## Phase 5: Compile check

Skip only with `--no-compile`, and say so. When the library branch is not the one of the target Opencell
version, the check is mandatory and runs on an instance of the target version.

- **`JAVA`**: the credentials come from `OC_USER` / `OC_PASS` in the environment of the Claude Code
  session (never ask the developer to paste them in the conversation; if they are missing, explain how
  to set them and stop this phase). Check that the instance answers, then run:

  ```bash
  python3 "$LIB/tools/compile_on_instance.py" <script files> --base-url <url>
  ```

  On compilation errors, fix the draft and run again: **at most 3 correction rounds**. After the third
  failed round, stop and report the remaining errors instead of guessing further. If the tool refuses
  because a ScriptInstance with the same code exists, do not pass `--overwrite`: ask the developer.
- **`JAVA_CLASS`**: compile it with the module that ships it (overlay or project module, for example
  `mvn -q compile -pl <module>`), or with `javac` against the `WEB-INF/lib` of an exploded war of the
  target core version.

Report the result per script: compiled at round N, or the remaining errors.

## Phase 6: Wrap-up

```
## Script draft: {TICKET}

### Files
Branch: <branch> in <repository root>
Script library: branch <library branch> for Opencell <target version> (<tested | not the target version: a contract may differ>)
- [<FileName>](<absolute path>) (Created) — <hook point id>, <JAVA | JAVA_CLASS>, compiled on <url> at round <N> | not compiled: <why>

Give each file as a link to its **absolute path**, so the developer opens it in one click from the
terminal or the IDE. Do not print the code.

### Script summary
One table per script; every row is filled, with "none" when it does not apply.

| Item | <ClassName> |
|---|---|
| Hook point | <id> — <name>, configured on <entity field / job parameter / notification / inbound request> |
| Starting point | <template or starter path> |
| Script type | <JAVA / JAVA_CLASS> — <why> |
| Transactions | <caller's transaction / new transaction per item / ...>; <REQUIRES_NEW core methods avoided>; what is rolled back on error |
| Inputs | <context keys and their types>; script parameters <code: type, mandatory, default> |
| Outputs | <context keys set and their types>; HTTP status and body for an inbound request |
| Entities read | <Entity (how: query / service method)> |
| Entities created, updated or deleted | <Entity: field(s) changed, status transitions> / none (read only) |
| Services called | <ServiceName.method(...)> |
| Errors and edge cases | <case: behaviour (exception, status, message)> |
| Business rules taken from | <ticket section / developer answer at the checkpoint> |
| Business rules still assumed | <rule: what was assumed and why> / none |

### Configuration to do (developer)
- ScriptInstance <code>: type <JAVA | JAVA_CLASS>, category <...>
  createOrUpdate payload: {"code": "<code>", "type": "JAVA", "script": "<source>", "disabled": true, ...}
- Reference: <entity field / job parameter / notification / inbound request> = <code>
- ScriptParameters: <...>
- JobInstance: <job template, parameters> | none

### What the developer still has to decide or check
- <open questions, assumptions, behaviours to test on real data>
```

In an overlay, add the overlay deployment note from `OVERLAY_SCRIPTS.md`, and that it **writes to a
live instance**.

Then suggest, in this order:

```
Next steps:
  1. Review:            /oc-be-tools:oc-be-review   (/oc-ov-tools:oc-ov-review in an overlay)
  2. Record AI usage:   /oc-be-tools:oc-be-calculate-ai-use --working --ticket {TICKET}
  3. Commit:            {TICKET}: {brief description}
```

## Phase 7: Jira summary

The summary keeps the design of the script on the ticket for the reviewer and the product owner: run
this phase on every real ticket.

1. Build the comment from the wrap-up: the **Script summary** table of each script, the configuration
   to do, the open questions, the branch name, and the statement *"AI-generated draft, not yet reviewed"*.
   Never put the code, a secret, a credential or a value read from an attachment in it.
2. Show the exact comment, then **`AskUserQuestion`: "Post this summary as a comment on {TICKET}?"**
   (**Post** / **Change it first** / **Do not post**). Block until answered; post nothing without
   **Post**.
3. On **Post**: `addCommentToJiraIssue` (cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`) with the
   comment, and give the developer the link to it. On failure, report the error and leave the comment
   text in the conversation; do not retry blindly.

This comment is the only write the command makes outside the developer's checkout.
