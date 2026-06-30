# Jira INTRD — User Story acceptance tests

Reference rules for filling the **Acceptance** field (`customfield_10136`) on
User Story issues. Read together with `stories.md` whenever the user asks
Claude to write, refine, or review acceptance tests.

The Acceptance field has two sub-sections — *Dataset* and *Test cases*. Both
are mandatory.

## Hard precondition — Functional design must be solid

Acceptance tests derive almost entirely from `customfield_10135`
*Functional design* (and, secondarily, from the *Requirement* field and the
*Technical design § Limits & volumes* section). Before writing a single test
row, verify that the Functional design:

- follows the Story template structure — sections *User journey & Process
  flow*, *Information requirements*, *Business rules & Permissions*,
  *User-Facing messages & Edge cases*, *Function transition*, *GUI*;
- has every mandatory table filled with concrete content — no placeholder
  rows, no "TBD", no panels still containing the template hint text;
- describes business rules with enough specificity that each row maps to a
  verifiable outcome (no "system should behave correctly", no rules without
  conditions or impacted roles);
- lists user-facing messages with both their trigger condition and exact
  wording in **en** and **fr** (the FD table mandates both languages).

**If the Functional design has gross holes — missing sections, empty
mandatory tables, vague rules without conditions, missing or single-language
messages — refuse to write the tests.** Reply to the user with the explicit
list of holes and ask the Product Owner to complete the FD first. Do not
invent business rules, fabricate trigger conditions, or translate missing
messages to "fill" gaps; doing so turns acceptance authoring into
specification work and silently locks ambiguity into the contract.

The only acceptable partial case is when the user explicitly asks Claude to
draft tests on top of a known-incomplete FD as a working draft. Even then,
flag every test row that depends on assumed (rather than specified)
behaviour, and recap the assumptions at the top of the reply so they get
back to the PO.

## Where each test row comes from

Every row in the *Test cases* table must trace back to one or more elements
of the Story:

| Source in the Story                                                | Tests it implies                                                              |
|--------------------------------------------------------------------|-------------------------------------------------------------------------------|
| FD — *Business rules & Permissions* table, each row                | ≥ 1 `Happy Path`; plus a `Business Rule` test per threshold / branch / role   |
| FD — *User-Facing messages & Edge cases* table, each row           | ≥ 1 test exercising the trigger, quoting the message verbatim in *Then*       |
| FD — *Information requirements* table, each validation constraint  | ≥ 1 `Negative` test (mandatory field, format, range, …)                       |
| FD — *Function transition* section                                 | ≥ 1 `Business Rule` test on the existing-data path                            |
| Technical design — *Limits & volumes*, each non-N/A item           | ≥ 1 boundary test (cap, page-size limit, p95 latency point, degradation path) |

Conversely, every test row must reduce to at least one source above. A test
row that has no traceable source is either over-specification or evidence
that the FD is incomplete — in the latter case, fix the FD, not the tests.

## Test cases table — how to write each cell

The template's *Test cases* table has four columns: **Type**, **Context
(given)**, **Actions (when)**, **Expected outcome (then)**. Stay strictly
inside this BDD shape — do not introduce extra columns.

### Type (column 1) — closed list

Only these four values, written exactly as below:

- `Happy Path` — main expected behaviour. **Mandatory** (at least one per
  Story).
- `Business Rule` — non-obvious thresholds, status conditions, branches,
  role-dependent behaviour. **Mandatory when the rule has them.**
- `Negative` — what must not happen; required input rejected; permission
  denied. **Mandatory when financial integrity, data integrity, or security
  is at risk.**
- `Edge Case` — realistic AND previously known to cause bugs. **Default
  count is zero.** Do not invent edge cases for the sake of completeness.

### Context — Given (column 2)

State the preconditions factually:

- **Reference Dataset rows by stable IDs** (e.g. *Customer C1*, *Offer O1*,
  *Subscription S1*). Do not inline data — the *Dataset* section is the
  single source of truth for fixtures.
- Include the **actor** (persona from the *Requirement* field) and the
  **starting system state** (entity status, configuration flag, feature
  toggle).
- One precondition cluster per row. If two tests need materially different
  preconditions, they are different rows.

### Actions — When (column 3)

A **single user action or system trigger**. One verb. If you find yourself
writing "the user does X and then Y", split into two rows or move the first
step into *Given*.

For API-bearing Stories, the action is one HTTP call — verb + path + body
shape — referring back to the API table in *Technical design* rather than
re-specifying it.

### Expected outcome — Then (column 4)

A **single observable, verifiable outcome**:

- For user-facing messages, quote the message verbatim from the FD
  *User-Facing messages & Edge cases* table in the language under test. If
  both en and fr are mandated and their wording differs meaningfully, write
  one row per language.
- For API responses, state HTTP status + error code (from the Technical
  design *Error dictionary*) on negative paths; reference the response
  shape on positive paths.
- **No implementation leakage** — no Java class names, no SQL, no internal
  exception types, no audit-log structure unless those are part of the
  documented public contract. Public REST contract elements (HTTP status,
  error code, response field names) *are* user-visible and belong here.
- **Atomicity** — if a test must verify two distinct outcomes, write two
  rows. "Then" never contains an *and* that joins independent assertions.

## Dataset section

The *Dataset* section must list **every entity referenced by any test row**
with a stable label. Suggested format:

| ID | Type        | Key attributes (only those a test depends on)       |
|----|-------------|-----------------------------------------------------|
| C1 | Customer    | Status: Active; Country: FR; Payment method: SEPA   |
| O1 | Offer       | Price: 10 €/month; Currency: EUR                    |
| S1 | Subscription| Customer: C1; Offer: O1; Status: Active             |

Do not document attributes no test touches — the *Dataset* is fixture
documentation, not an entity dump. Conversely, if a test row references an
entity not in the *Dataset*, that is a defect in the acceptance section —
add the row, do not delete the test.

## Coverage check — run it before submitting

Walk through the FD tables and the Limits & volumes checklist and tick each
item against the test list:

- Every *Business rules & Permissions* row → at least one matching test? If
  not, either the rule is dead text (raise with the PO) or the tests are
  incomplete.
- Every *User-Facing messages & Edge cases* row → at least one test
  exercising its trigger? Untested messages are usually a smell.
- Every *Information requirements* validation constraint → at least one
  `Negative` test? Skip this only when the constraint is purely cosmetic
  (e.g. label truncation), and flag the skip explicitly.
- Every non-N/A *Limits & volumes* item → at least one boundary test? An
  unverified limit is an unverifiable promise.

Report uncovered rows back to the user — never silently extrapolate.

## Language

The Acceptance content is written in **English** (per `SKILL.md` general
rules). The only French content allowed is the verbatim quote of a French
user-facing message inside a *Then* cell, when that wording is what the
test is verifying.

## Anti-patterns to avoid

- **Tautological tests** — "When the user creates a customer, then a
  customer is created" adds nothing. *Then* must describe the *check* a
  tester can perform (specific status, specific message, specific field
  value, specific HTTP code).
- **Compound tests** — multiple actions in *When* or multiple independent
  assertions in *Then*. Split.
- **Speculative edge cases** — adding `Edge Case` rows because "we should
  probably test the empty list" without prior evidence the empty list
  misbehaves. Default count is zero.
- **Test-driven specification** — inventing business rules in tests that
  are not in the FD. The FD is the source; tests verify it. Flag the gap,
  do not paper over it.
- **Schema-leak tests** — assertions on database columns, internal
  services, or implementation details that are not part of the documented
  public contract.
- **Dataset bypass** — inlining concrete data values in *Given*/*When* and
  leaving the *Dataset* section empty or partial. Always lift fixtures to
  the *Dataset*.
