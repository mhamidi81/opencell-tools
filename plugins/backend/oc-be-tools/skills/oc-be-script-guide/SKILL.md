---
name: oc-be-script-guide
description: >
  TRIGGER when user asks to write, generate, modify or review an Opencell script (a ScriptInstance,
  a class extending org.meveo.service.script.Script or a core script base class such as TaxScript,
  PaymentScript, DateRangeScript, AccountOperationFilterScript), to pick the hook point a script
  plugs into, or to choose between a JAVA and a JAVA_CLASS script.
  Also trigger when reading, analysing or planning a Jira ticket whose need is a script (a "standard
  script", an invoice validation rule, a hook point, a ScriptInstance, a script parameter, a custom
  action, a scripting job), before proposing any plan for it, even when no code is written yet; and when
  a builder agent writes scripts.
  Loads the Opencell script library (hook point contracts, starters, business templates, JAVA vs
  JAVA_CLASS rule, transaction rules) and, in an overlay repository, the overlay script rules.
---

# Opencell script guide

The knowledge lives in the **Opencell script library** (`opencellsoft/opencell-script-library`):
39 hook point contracts mapped from the core, 36 starters (two hook points reuse the starter of a
neighbour with the same contract, and the mediation reader has none on purpose), and business templates
generalized from customer projects. This skill locates it and says in which order to apply it. It does
**not** restate the library: the rules below are a summary, and the library explains each of them.

## 1. Resolve the library

```bash
LIB=""
# 1. an explicit location (a developer's own working clone)
[ -n "$OC_SCRIPT_LIBRARY" ] && [ -d "$OC_SCRIPT_LIBRARY/src/main/java/org/meveo/service/script" ] && LIB="$OC_SCRIPT_LIBRARY"
# 2. the clone managed by oc-be-tools, kept on main
MANAGED="$HOME/.claude/oc-be-tools/opencell-script-library"
URL="git@ssh.bitbucket.org:opencellsoft/opencell-script-library.git"   # Bitbucket SSH host since 12 Nov 2026
if [ -z "$LIB" ]; then
  if [ -d "$MANAGED/.git" ]; then
    git -C "$MANAGED" remote set-url origin "$URL"   # a clone made on bitbucket.org before the move
    git -C "$MANAGED" pull -q --ff-only || echo "WARN: could not update $MANAGED, using it as is"
  else
    mkdir -p "$(dirname "$MANAGED")" && git clone -q "$URL" "$MANAGED" || echo "ERROR: could not clone. If the message says 'Host key verification failed', accept the Bitbucket SSH host once with: ssh -T git@ssh.bitbucket.org"
  fi
  [ -d "$MANAGED/src/main/java/org/meveo/service/script" ] && LIB="$MANAGED"
fi
echo "$LIB"
```

- Never `pull` the developer's own clone (`OC_SCRIPT_LIBRARY`): it may hold work in progress. If it is
  behind `origin/main`, say so.
- If `LIB` is empty (no access to the repository), **stop** and say so: generating a script without the
  hook point contracts produces code that compiles and fails at run time.

## 2. Read, in this order

1. `$LIB/README.md`: **Two kinds of scripts** (the `JAVA` / `JAVA_CLASS` table, *Which one to choose*,
   the cases table, *What the source type does not change*, *Transaction boundaries in a `JAVA`
   script*), **Template metadata**, **Readiness checklist**, **Checking that a script compiles**.
2. The root README **Structure** table, to find the category of the need.
3. `$LIB/src/main/java/org/meveo/service/script/<category>/README.md`: the contract of the hook point
   (called by, base class, context in and out, configuration, pitfalls) and the category's services,
   business objects and common patterns.
4. The starter of the hook point (`<category>/starters/*StarterScript.java`) and the closest business
   template (`<category>/templates/*TemplateScript.java`), if any.

A hook point that is not in the library: say so, read the core class that calls the script, and
treat the result as unverified.

## 3. Overlay repositories

An overlay repository (modules `opencell-elec-*` or `opencell-ext-*`, or a `## Overlay profile` block in
its `CLAUDE.md`) has its own script rules, owned by `oc-ov-tools`. **Read them, do not restate them.**

```bash
OV=""
# 1. the marketplace checkout (opencell-tools first, then any marketplace)
[ -d ~/.claude/plugins/marketplaces/opencell-tools/plugins/overlay/oc-ov-tools/guidelines ] \
  && OV=~/.claude/plugins/marketplaces/opencell-tools/plugins/overlay/oc-ov-tools/guidelines
[ -z "$OV" ] && OV=$(find ~/.claude/plugins/marketplaces -maxdepth 5 -type d -path '*/plugins/overlay/oc-ov-tools/guidelines' 2>/dev/null | head -1)
# 2. the versioned plugin cache, highest version wins
[ -z "$OV" ] && OV=$(find ~/.claude/plugins/cache -maxdepth 4 -type d -path '*/oc-ov-tools/*/guidelines' 2>/dev/null | sort -V | tail -1)
# 3. a source checkout of the marketplace repository next to the project
[ -z "$OV" ] && [ -d ../ccode-marketplace/plugins/overlay/oc-ov-tools/guidelines ] && OV=../ccode-marketplace/plugins/overlay/oc-ov-tools/guidelines
echo "$OV"
```

The paths are tested with `find` and `[ -d ]` rather than shell globs, so the block works in bash and
zsh alike (zsh aborts a command whose glob matches nothing).

Read `$OV/OVERLAY_PROFILES.md` (the profile gives the script package) and `$OV/OVERLAY_SCRIPTS.md`
(script and utility modules, base classes, deployment). In an overlay, these rules win over the
library's package convention. If `OV` is empty in an overlay repository, **stop** and ask the
developer to install `oc-ov-tools` (`/plugin install oc-ov-tools@opencell-tools`).

## 4. Rules that are easy to get wrong

The library explains each of them; check them on every script.

| Rule | Why |
|---|---|
| Pick the hook point from its contract, and extend the base class it requires | A wrong base class fails at run time with a `ClassCastException`, or the script is silently ignored |
| Set the mandatory output keys of the hook point (`RESULT_VALUE`, `InvoiceValidation.STATUS`...) with the type the core expects | The core reads them with a cast; a wrong type fails or is ignored |
| `JAVA`: services through `getServiceInterface("XxxService")`, checked for `null`, in `private final transient` fields; never `@Inject` | A `JAVA` script is created with `newInstance()`: annotations are ignored and the field stays `null` |
| Choose `JAVA` or `JAVA_CLASS` **for each script**, and say why | Simple, hot-deployed logic is `JAVA`; complex logic needing injection, own transactions or unit tests is `JAVA_CLASS`; the mediation reader and parser are always `JAVA_CLASS` |
| State the transaction strategy: `REQUIRED` services for an atomic flow, no core method in `REQUIRES_NEW` inside it (for example `SubscriptionApi.subscribeAndActivateServices`), `runRunnableWithNewTransaction` to isolate an item | The script type does not change the transactions the core opens; `RatingException` does not roll back |
| Import explicitly every class provided by the application server, even one that only appears in a `throws` clause | The core compiles a `JAVA` script against the war plus the jars of the imported classes only |
| No state in instance fields when the hook point runs the script from a pool | The same instance serves several calls, possibly on several threads |
| Never assume a business rule, an entity field or a service method: check it in the library or in the core | A plausible method that does not exist compiles in no instance |
| When the script bypasses a core method (for example it creates a `DiscountPlanInstance` itself instead of calling `SubscriptionService.instantiateDiscountPlan`), read that method and keep its side effects: filters it checks (`applicationFilterEL`), status changes (plan `ACTIVE` → `IN_USE`), counters it updates | The core method does more than its name says; skipping it silently drops business rules and statistics |
| "Operations already rated" are the `WalletOperation`s in status `OPEN` **and** `TREATED` whose rated transaction is not `BILLED`; leave out invoiced ones and the discount operations themselves | `RT_Job` turns `OPEN` operations into rated transactions (`TREATED`) at night: a script that only reads `OPEN` misses the part of the period already processed |
| When the core shows several conventions for the same thing, follow the most recent one (check the `git log` of the sibling scripts), and never replace a choice the developer made explicitly: point out the difference instead. Standard core scripts are now `JAVA_CLASS`, with the fully qualified class name as ScriptInstance code; a `JAVA` source that only extends the war class is the older pattern | Older code stays in the core next to newer code; copying the first example found reproduces an abandoned convention |
| A filter parameter (offers, sellers...) restricts where the rule applies: when it leaves nothing to check, the rule does not apply and passes | Rejecting an invoice that the rule does not concern blocks billing for every customer outside the filter |
| A case the ticket does not settle (empty parameter, no data to check) is a question for the developer, never a default rejection or acceptance chosen by the agent | A default chosen silently is an invented business rule |
| Never deploy or enable a script on an instance; the compile check only saves a temporary, **disabled** copy and removes it | Deployment is the developer's decision |

## 5. Check that it compiles

- `JAVA`: `python3 "$LIB/tools/compile_on_instance.py" <file.java...> --base-url <instance>/opencell/api/rest`
  with `OC_USER` / `OC_PASS` in the environment, against a **development** instance only. The tool saves
  a temporary, disabled copy of the draft, reads its compilation errors, then removes the copy: the script
  stays in the developer's checkout and nothing is left on the instance.
- `JAVA_CLASS`: compile it with the module that ships it (overlay or project module), or with `javac`
  against the `WEB-INF/lib` of the war (see the library README).
