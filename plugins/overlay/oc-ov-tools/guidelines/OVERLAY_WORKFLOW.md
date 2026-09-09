# Overlay workflow: core sync, branches, build, release

> LAYERS OVER: oc-be-tools/guidelines/CODE_QUALITY.md §Version Control
> CORE BASELINE: oc-be-tools 1.17.0
> PRECEDENCE: branch and commit conventions REPLACE core's.

## The core repository

Overlay code is written against core's classes, so core must be **on disk and readable**: to check base
classes, to read the method signatures of a service being `@Specializes`-ed, and to detect FQN
collisions before any shadowing.

Resolution order:

1. The `## Core project` block in the repo's `CLAUDE.md`.
2. The sibling convention `../opencell-core`.
3. A path remembered from a previous session.
4. **Ask the user**, then remember the answer.

### Version and branch correspondence

`opencell.version` in the overlay root pom must equal the core version being built against.

For the **branch**, compare *base* branches, not branch names: either side may sit on a feature branch,
so a name match is the wrong test. Determine each side's base (`dev`, `18.1.X`, `18.X`, `16.5.X`,
`15.X`), report both, and **ask the user to confirm they correspond**. Warn and continue — do not block.

Core must be built and installed before the overlay:

```bash
sh docker-files/fetch-and-compile-new-core-version.sh   # checks out the matching core branch and mvn installs it
```

That script assumes core is the sibling `../opencell-core`, and for a SNAPSHOT version it checks out
`origin/<current-overlay-branch>` — which only works when the overlay is on a target branch, not a
feature branch. On a feature branch, check core out to the **target** branch manually.

## Branch naming — REPLACES core

```
[<type>/]<KEY>-<number>[-<slug>]<sep><targetBranch>
```

where `<sep>` is `-` or `_`. **The target-branch suffix is mandatory.** There is no `{username}/`
prefix (core's convention). Real examples:

```
bugfix/MACRD-1905-wfa-blocked-at-step-activatio-dev
feature/MACRD-587-dev
MACRD-1884_dev
bugfix/MACRD-1811-regression-on-usagescharge_165x
```

| Target branch | Suffix |
|---|---|
| `dev` (default) | `-dev` / `_dev` |
| `18.1.X` | `-181x` |
| `18.X` | `-18x` |
| `16.5.X` | `-165x` |
| `15.X` | `-15x` |

**Ask which target branch(es) before creating a branch.** A fix that must land on several release lines
gets one branch and one pull request **per target** — never one branch for several.

## Commit messages — REPLACES core

`KEY-1234 short description` — a space, usually no colon. French descriptions are normal and fine.
Core's rule against a `Co-Authored-By:` trailer carries over.

## Before opening a pull request

1. Core built and installed at the matching version.
2. `mvn clean package` from the repo root — full reactor, not `-pl`; produces the overlay war.
3. If Liquibase changed: `cd <overlay-module> && mvn test -Dtest=LiquibaseFileTest`.
4. If scripts changed: deploy them and exercise at least one (see `OVERLAY_SCRIPTS.md`).
5. If a `.jrxml` changed: confirm the regenerated `.jasper` is committed (see `OVERLAY_JASPER.md`).

## Release

The repo's `release-new-version.sh` bumps the aggregate version. `opencell.version` moves in lock-step
with the core release line.
