# Jira INTRD — PO review of a delivered Story

Reference rules for the **PO review lane**: judging a Story QA has delivered — validating it,
rejecting it, or parking it. Loads when a Story sits in **`To Review by PO`**, the end of Phase 6
(QA) in `stories.md` § *Workflow*, which stays the source of truth for the phase model and the side
states. Read together with the main `SKILL.md`.

## Before judging — confirm the build under test

**A verdict on the wrong build is worthless.** The mechanics — confirming each build, getting a
token, replaying the failing call — live in the **`oc-fn-portal`** skill, file **`api-replay.md`**;
load it rather than re-deriving them. What a PO has to judge:

- **Core and Portal deploy from separate builds and drift independently** — confirm each on its
  own. A matching Core commit says nothing about the front end.
- **The Portal build comes from the version panel** at the bottom-left of the left menu — **never
  from grepping the served JavaScript**. That method has already produced a false "stale front end"
  claim that reached a ticket and had to be retracted publicly.
- **Judge the gap by what it touches, not by its size.** A build days behind is irrelevant if
  nothing in between went near the Story's code.

**A symptom you have not reproduced yourself on a confirmed build is a report, not a finding.** If
the build cannot be confirmed, the Story is not testable yet — that is `PO can't test yet` below,
which is a *non-verdict*.

## Reading a failure — two traps that make server bugs look like client errors

Two Opencell-specific behaviours systematically mis-route a defect to the wrong side. The mechanism
and the code paths are documented in the **`oc-fn-portal`** skill's API-replay lane
(**`api-replay.md`**); what a reviewer needs is the consequence.

- **A `400` from apiv2 is not proof of bad input.** apiv2 wraps an internal fault as **`400`, never
  `500`**. When the response `details` carries a JDK helpful-NPE (`Cannot invoke "X.y()" because … is
  null`) or a stack trace, it is a **server bug**, not a malformed request. Do not let the status
  code push the analysis toward "the client sent something wrong".
- **"The UI showed no error message" is never evidence the server sent none.** The Portal discards
  apiv2 error bodies and renders **"Server communication error"** in their place. The server's real
  message exists only in the raw response.
- **Therefore: a user-reported HTTP status and message are second-hand.** Replay the call and read
  the raw response **before** writing any analysis into a ticket.

## Rejecting a Story — file the Sub-bug(s) first

**File the defect(s) as `Sub-bug`s under the Story before rejecting it.** This is an **Opencell
convention, not a Jira constraint**, and the non-enforcement is the verified half: `Rejected by PO`
carries no transition screen and no required fields, so the API accepts a bare rejection with no
defect attached and nothing flags it. Follow it anyway: the rejection reason has to be a readable,
assignable, trackable defect, not a comment.

- **One `Sub-bug` per distinct defect.** Rejecting for three problems means three `Sub-bug`s, not one
  carrying a list.
- `bugs.md` carries the `Sub-bug` authoring rules — issue type, parent, required fields at creation,
  which template applies — and the rule for **when a defect belongs under the Story as a `Sub-bug`
  versus as a standalone `Bug`** (a generic, out-of-scope problem the Story merely exposed).
- **Before filing anything, search closed issues for the same symptom** — see `bugs.md`
  § *Before filing — regression archaeology*. A defect that reproduces an already-closed Bug is a
  different finding, with a different owner, from a fresh one.

## The verdict transitions

**Transition names do not match the status they land in.** Three of the eight transitions available
from `To Review by PO` end in a status with a different name — including **both verdicts** — and that
mismatch is exactly what makes the right transition hard to find. Never pick a transition by guessing
which one is named after the target status.

| id | Transition name | Resulting status |
|---|---|---|
| 141 | On Hold | On Hold |
| 261 | Released | Released |
| 271 | Ready for Sprint Review | Ready for Sprint Review |
| 321 | Ready For Design | Ready For Design |
| 411 | Invalid | Invalid |
| 421 | **Validated by PO** | **Ready for Sprint Review** |
| 431 | **Rejected by PO** | **Waiting for fixing** |
| 521 | **PO can't test yet** | **Test Blocked** |

**Ids are workflow-specific — resolve them at use time** with `jira transitions KEY` (or
`getTransitionsForJiraIssue`) and apply the id from *that* listing. The **name** is the stable
handle; the ids above were observed on one INTRD Story in `To Review by PO` and may differ on another
workflow.

## When each verdict applies

| Transition | Use when | Lands in |
|---|---|---|
| **Validated by PO** | The delivered behaviour matches the Story's *Functional design* and *Acceptance*. A pass. | `Ready for Sprint Review` — Phase 7 |
| **Rejected by PO** | Defects found. **File the `Sub-bug`(s) first** (above). | `Waiting for fixing` — back to Phase 5, Development |
| **Invalid** | The **Story itself should not exist** — not reproducible, superseded, abandoned. A scope verdict, **not** a defect verdict: never use it for work that was delivered but broken. | `Invalid` — side state, `stories.md` § *Side states* |
| **PO can't test yet** | Blocked from testing — environment down, wrong build deployed, missing data or dependency. **No verdict is given.** | `Test Blocked` — back inside Phase 6, QA |
| **On Hold** | The review is paused for reasons outside the Story's quality. The reason **must** be written in a comment (`stories.md` § *Side states*). | `On Hold` |

## After a rejection — the dev loop

From `Waiting for fixing`, the Story leaves through one of:

| id | Transition name | Resulting status | Meaning |
|---|---|---|---|
| 341 | Fix provided | Ready for Test | Fixed; back through QA (Phase 6). |
| 471 | Send to PO | To Review by PO | Straight back to this lane, skipping QA. |
| 591 | Need additional tech design | To Design - Tech | The defect needs Phase-3 rework by the Tech Lead. |

The standing side transitions (`On Hold`, `Released`, `Ready for Sprint Review`, `Ready For Design`,
`Invalid`) are offered here too, with the same ids as in the table above. Same caveat: resolve ids
live.

## Review checklist

1. **Confirm the build** — Core and Portal separately (above). An unconfirmed build is
   `PO can't test yet`, not a verdict.
2. **Reproduce** the reported symptom yourself, on that build.
3. **Replay the API call before analysing** — read the raw response, not the UI's rendering of it
   (**`oc-fn-portal`** skill, `api-replay.md`).
4. **Search closed issues for the same symptom** before filing anything (`bugs.md` § *Before
   filing — regression archaeology*).
5. **File one `Sub-bug` per defect** under the Story (`bugs.md`).
6. **Then transition** — resolve the id live, and pick it by transition *name*.
