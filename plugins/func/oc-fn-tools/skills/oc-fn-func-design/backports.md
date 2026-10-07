# Jira INTRD — Backports

A **Backport** (issue type id `10087`) carries the work of bringing a Story's or an Enabler's change to
an older version. Read together with `SKILL.md` § *Cost per version — the Fix version field*: a
Backport exists so that the cost of maintaining an older version lands on that version.

## Ownership — architect-created

**Backport issues are created by the architect lane, not by the PO** (Stéphane, 2026-10-07). In
practice, 60 of the 106 Backports created in 2026 came from the product architect and 29 from the
Scrum master. The product side records the *need*: the version goes into the Story's or Enabler's
*Backport versions*, which both the PO and the architect already fill in.

- **The func/PO lane does not create Backport issues by default.** It sets *Backport versions* and
  **flags the Backport for the architect lane**: tell the user which Story, which version, and that
  the architect creates the issue.
- **It creates one only on explicit user request,** the same exception used for Enablers and the
  Story *Technical design* field. Then build it as below.
- **Everything else here applies whoever creates it:** the construction rules, the checks after
  creation, and the review and sweep.

## When one is needed

- **A Story or an Enabler carries at most one Fix version** — one once it is scheduled, never two.
  Each older version that must also receive the change is listed in the Story's or Enabler's
  **Backport versions** field (`customfield_10260`, multi-version), **and** gets its own Backport
  issue. Both, always: the field says which versions are owed, the Backport issue carries the work
  and its cost.
- **A Bug, Sub-bug, Sub-task or Task does not need one.** It may carry several Fix versions, and its
  cost is then split evenly between them.
- **Do not create Backport issues retroactively** (Stéphane, 2026-10-07). An older Story or Enabler
  that already carries several Fix versions stays as it is: report it in a review, do not split it
  after the fact.

## Field preset

```
["summary", "status", "issuetype", "parent", "components", "fixVersions", "issuelinks"]
```

On the original Story or Enabler, read `fixVersions` and `customfield_10260` as well.

## How to build one

| Field | Value |
|---|---|
| **Fix versions** | **Exactly one:** the version that receives the backport |
| **Summary** | `[Backport X.Y.Z] <original summary>`, the pattern already in use |
| **Parent** | The original's Epic |
| **Components** | The original's module(s), per the module rule, plus the layer (`Backend` / `Frontend`) |
| **Link** | `Relates` to the original |

Then add `X.Y.Z` to the original's **Backport versions**, in the same piece of work.

The create screen requires nothing beyond the summary (`jira meta 10087`, checked 2026-10-07), so
none of the rows above is enforced by Jira. That is what this file is for. On 2026-10-07, before the
backfill, 105 of the 108 Backports created or worked in 2026 carried no module and 3 carried no
version.

**REST** — create with the link in the same call, then add the version to the original:

```json
{"fields": {"project": {"key": "INTRD"}, "issuetype": {"id": "10087"},
  "summary": "[Backport 18.3.0] <original summary>", "parent": {"key": "INTRD-<epic>"},
  "fixVersions": [{"name": "18.3.0"}], "components": [{"name": "Billing"}, {"name": "Backend"}]},
 "update": {"issuelinks": [{"add": {"type": {"name": "Relates"},
  "outwardIssue": {"key": "INTRD-<original>"}}}]}}
```

```sh
jira raw PUT "/issue/INTRD-<original>" '{"update":{"customfield_10260":[{"add":{"name":"18.3.0"}}]}}'
```

**Rovo MCP** — it has no `update` verb, so it takes three calls:

1. `createJiraIssue` with `issueTypeName: "Backport"` and `additional_fields`
   `{"parent": {"key": "INTRD-<epic>"}, "fixVersions": [{"name": "18.3.0"}], "components": [{"name": "Billing"}, {"name": "Backend"}]}`.
2. `createIssueLink`, type `Relates`, between the new Backport and the original.
3. `editJiraIssue` on the original, with `fields.customfield_10260` = **the full existing list plus**
   the new version. The field is replaced, not appended.

## Verify after creating

Both sides: the Backport is complete, and its version is listed on the original.

```sh
jira raw GET "/issue/$K?fields=fixVersions,components" | jq -e '(.fields.fixVersions|length)==1
  and ([.fields.components[].name] | any(. != "Backend" and . != "Frontend"))' >/dev/null \
  || echo "BACKPORT INCOMPLETE: $K"
V=$(jira raw GET "/issue/$K?fields=fixVersions" | jq -r '.fields.fixVersions[0].name')
jira raw GET "/issue/$ORIG?fields=customfield_10260" \
  | jq -e --arg v "$V" '[.fields.customfield_10260[]?.name] | index($v)' >/dev/null \
  || echo "ORIGINAL MISSING BACKPORT VERSION $V: $ORIG"
```

## Review and sweep

**Report these to the user as findings.** Old Stories and Enablers are never split, and no Backport
is created after the fact. Missing Backport data is different. A Backport's missing version or
module, and a Backport version missing from its original's *Backport versions*, are backfilled once
the user approves the list, like the module sweep in `SKILL.md`. None of these moves cost already
logged.

**Open Stories and Enablers with several Fix versions.** JQL cannot count the values of a
multi-value field, so fetch and filter. Done items are history and are not reported:

```sh
jira jql 'project = INTRD AND issuetype in (Story, Enabler) AND statusCategory != Done AND fixVersion is not EMPTY' \
  --all --fields=fixVersions --json | jq -r '.issues[]|select((.fields.fixVersions|length)>1)|.key'
```

**Backports with no Fix version, or several:**

```sh
jira jql 'project = INTRD AND issuetype = Backport' --all --fields=fixVersions --json \
  | jq -r '.issues[]|select((.fields.fixVersions|length)!=1)|.key'
```

- **No version: a backfill candidate.** Take it from the `[Backport X.Y.Z]` summary, or from the
  original's *Backport versions*, but only when that names an existing Jira version.
- **Several versions: report only.** Removing one would move cost already logged.

**Backports with no module, Done ones included.** The module sweep in `SKILL.md` skips Done items,
but Backport backfill covers history:

```sh
jira jql 'project = INTRD AND issuetype = Backport' --all --fields=components --json \
  | jq -r '.issues[]|select([.fields.components[].name]|all(. == "Backend" or . == "Frontend"))|.key'
```

**Backports and their originals' *Backport versions*, both ways.** Match through the link, not the
Epic: 29 of the 106 Backports created in 2026 have no parent, and siblings share Epics. The
recipe below was run on 2026-10-07 and found 9 reverse and 49 forward cases.

- **Reverse (a backfill candidate):** a Backport whose version is missing from a linked original's
  *Backport versions*. Adding it moves no cost.
- **Forward (report only):** a *Backport versions* entry with no linked Backport carrying it. No
  Backport issue is created after the fact.

```sh
jira jql 'project = INTRD AND issuetype = Backport' --all --fields=fixVersions,issuelinks --json > bp.json
KEYS=$(jq -r '[.issues[].fields.issuelinks[] | (.outwardIssue // .inwardIssue)
  | select(.fields.issuetype.name == "Story" or .fields.issuetype.name == "Enabler") | .key] | unique | join(",")' bp.json)
jira jql "key in ($KEYS)" --all --fields=customfield_10260 --json > orig.json
# Reverse
jq -r --slurpfile o orig.json '
  ($o[0].issues | map({key, value: [.fields.customfield_10260[]?.name]}) | from_entries) as $bv
  | .issues[] | .key as $b | [.fields.fixVersions[].name] as $fv
  | .fields.issuelinks[] | (.outwardIssue // .inwardIssue) | .key as $s | select($bv[$s] != null)
  | $fv[] | select(. as $v | $bv[$s] | index($v) | not) | "\($b) \(.) missing from \($s)"' bp.json
# Forward
jira jql 'project = INTRD AND issuetype in (Story, Enabler) AND "Backport versions" is not EMPTY' \
  --all --fields=customfield_10260,issuelinks --json > bvs.json
jq -r --slurpfile b bp.json '
  ($b[0].issues | map({key, value: [.fields.fixVersions[].name]}) | from_entries) as $fv
  | .issues[] | .key as $s
  | [.fields.issuelinks[] | (.outwardIssue // .inwardIssue) | .key | $fv[.] // empty | .[]] as $covered
  | .fields.customfield_10260[].name | select(. as $v | $covered | index($v) | not)
  | "\($s) owes \(.) with no Backport"' bvs.json
```

Write these files to the session scratchpad, not to a repo.
