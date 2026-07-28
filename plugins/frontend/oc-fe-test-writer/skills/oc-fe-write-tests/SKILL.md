---
name: oc-fe-write-tests
description: Write Vitest tests for changed code (git diff) or for specific files, using the oc-fe-test-writer agent
argument-hint: "[FILE... | BASE-BRANCH] (e.g., src/widgets/.../Form.tsx  or  dev)"
---

## Sub-agent Configuration

Use the `oc-fe-test-writer` sub-agent (via Task tool with `subagent_type: oc-fe-test-writer:oc-fe-test-writer`) to write and verify the Vitest tests. This skill only resolves the scope (which files to test) and then delegates everything else — reading the code, writing `*.spec.tsx` / `*.spec.ts`, and running Vitest — to the agent.

## Purpose

Generate Vitest tests for the OpenCell Portal on demand, without going through the Jira-driven workflow. Two modes:

1. **Changed-code mode** — test whatever changed in the working tree / branch (the default).
2. **File mode** — test one or more explicit files you pass in.

## Context

Parse `$ARGUMENTS` to determine the mode and scope.

**Argument forms:**

| `$ARGUMENTS` | Mode | Meaning |
|--------------|------|---------|
| _(empty)_ | Changed-code | Diff against base branch `dev` (default) |
| `dev` / `master` / `release/18.0` | Changed-code | Diff against the given base branch |
| `src/.../Form.tsx` | File | Write tests for that file |
| `src/.../Form.tsx src/.../mappers.ts` | File | Write tests for each listed file |

**Disambiguation rule** — treat an argument as a **file** when any of these hold:
- it ends in `.ts` or `.tsx`, **or**
- it contains a path separator (`/` or `\`), **or**
- it resolves to an existing file on disk.

Otherwise treat the (single) argument as a **base branch** name for changed-code mode.

If file and branch-like arguments are mixed, treat it as file mode and ignore the non-file token (warn the user).

## Tasks

### Step 1: Parse Arguments and Resolve Scope

- Apply the disambiguation rule above to classify `$ARGUMENTS`.
- Set:
  - `[MODE]` = `changed` or `file`
  - `[BASE-BRANCH]` = the given branch, or `dev` if not provided (changed mode only)
  - `[FILES]` = the list of file paths (file mode only)
- Display the resolved plan in key-value format, e.g.:

  ```
  MODE:        changed
  BASE-BRANCH: dev
  ```

  or

  ```
  MODE:  file
  FILES: src/srcProject/widgets/b2b/contracts/Form.tsx
         src/srcProject/widgets/b2b/contracts/mappers.ts
  ```

### Step 2: Validate

- **File mode:** verify each path in `[FILES]` exists and is a `.ts`/`.tsx` source file (not a `*.spec.*`/`*.test.*` file, not config, not i18n JSON). If a path does not exist, report it and ask the user to correct it before continuing.
- **Changed mode:** no validation needed here — the agent computes and filters the diff itself. If you already know there are no changes, you may inform the user, but still let the agent confirm.

### Step 3: Invoke the oc-fe-test-writer Agent

Launch the `oc-fe-test-writer` sub-agent (`subagent_type: oc-fe-test-writer:oc-fe-test-writer`) with a prompt that includes the resolved scope:

- **Changed mode:** instruct the agent to write Vitest tests for the code changed against `[BASE-BRANCH]`, passing `[BASE-BRANCH]` so it can compute the diff.
- **File mode:** instruct the agent to write Vitest tests for exactly the files in `[FILES]` (do not expand to the whole diff).

The agent will read the target code, find nearby existing specs to match style, write/update the tests following project conventions (`__tests__/`, `FormWrapper`, `renderWithApp`, MSW, accessible queries), and run Vitest to verify them.

### Step 4: Present the Report

Relay the agent's report to the user, including:

- The source files covered
- The test files created/updated and how many tests each has
- The Vitest run result (passed/failed)
- Any flags the agent raised (untestable changes skipped, or a potential defect surfaced in the code under test)

If the agent surfaced a real defect rather than a test bug, highlight it so the user can decide how to proceed.

### Step 5: Mark the Ticket as Tested by the Frontend AI Test Writer

After the tests are written and verified, set the JIRA **AI field** (`customfield_10613`) to `frontend_test` to record that the frontend AI test writer added coverage.

**Resolve the ticket id first:**

- This skill takes no ticket argument (it can run outside the Jira flow), so derive the ticket id from the current branch name: match the `XXX-NNNNN` pattern in the output of `git rev-parse --abbrev-ref HEAD` (e.g. `bugfix/INTRD-36922-...` → `INTRD-36922`).
- If no ticket id can be resolved from the branch, skip this step and note it.

**Skip conditions:**

- Skip if the agent reported no meaningfully testable change (no tests were written).
- Skip if no ticket id could be resolved from the branch.

**Append the tag** `frontend_test` — **never overwrite `customfield_10613`.** It is a **multi-value labels field (an array of strings)** shared with the other AI commands (`ai_code_review_Front`, `ai_code_review_back`, `ai_Dev_back`, `ai_test_back_dev`, …). Sending a single-select `{ "value": … }` object, a bare string, or a one-element array **replaces the whole field and destroys the other tags**.

1. **Read first** — `getJiraIssue` (official `atlassian` plugin) with `fields: ["customfield_10613"]`. Store the existing array as `[CURRENT-TAGS]` (treat `null` / missing as `[]`).
2. If `frontend_test` is already in `[CURRENT-TAGS]`, skip the write and note "already tagged".
3. Otherwise call `editJiraIssue` with **every** existing value plus the new one:
   - `issueIdOrKey`: [TICKET-NUMBER]
   - `fields`: `{ "customfield_10613": ["frontend_test", <...CURRENT-TAGS>] }`

   Expand `<...CURRENT-TAGS>` into the actual strings you read — every one of them must survive, including tags you don't recognise. Never drop or rename a tag you did not add.
4. **If the read fails, do not write** — a blind write would clobber the field. Warn the user and skip the tagging.
5. If the update fails, warn the user but continue.

## Examples

```bash
# Write tests for everything changed on the current branch vs dev (default)
/oc-fe-write-tests

# Write tests for changes vs a specific base branch
/oc-fe-write-tests master

# Write tests for one specific file
/oc-fe-write-tests src/srcProject/widgets/b2b/contracts/Form.tsx

# Write tests for several specific files
/oc-fe-write-tests src/srcProject/widgets/b2b/contracts/Form.tsx src/srcProject/widgets/b2b/contracts/mappers.ts
```
