# Jira INTRD — User Story acceptance tests

Reference rules for filling the **Acceptance** field (`customfield_10136`) on
User Story issues. Read together with `stories.md` — in particular § *Story
structure — light format*, whose *write each fact once* rule governs this
field too — whenever the user asks Claude to write, refine, or review
acceptance tests.

The Acceptance field has two sub-sections: *Test cases* (mandatory) and
*Dataset* (optional — only when tests share data).

## Hard precondition — Functional design must be solid

Acceptance tests derive almost entirely from `customfield_10135`
*Functional design* (and, secondarily, from the *Requirement* field and the
*Technical design § Limits & volumes* section). Before writing a single test
row, verify that the Functional design:

- has its mandatory sections — *Business rules*, *GUI* (content or
  `N/A — <reason>`) and *Impact on existing data* (a line, or `None`);
- has a *Business rules* table filled with concrete rows — no placeholder
  rows, no "TBD", no template hint text left in place;
- states each rule with a condition (*When*, including who may act) and an
  observable outcome (*Then*) specific enough to verify — no "the system
  behaves correctly";
- gives every message in *Messages* in both **EN** and **FR**, keyed to the
  rule that triggers it.

**If the Functional design has gross holes — a missing mandatory section, an
empty *Business rules* table, rules without a condition or an outcome, a
message without both languages — refuse to write the tests.** Reply to the
user with the explicit list of holes and ask the Product Owner to complete
the FD first. Do not invent business rules, fabricate trigger conditions, or
translate missing messages to "fill" gaps; doing so turns acceptance
authoring into specification work and silently locks ambiguity into the
contract.

The only acceptable partial case is when the user explicitly asks Claude to
draft tests on top of a known-incomplete FD as a working draft. Even then,
flag every test row that depends on assumed (rather than specified)
behaviour, and recap the assumptions at the top of the reply so they get
back to the PO.

## Where each test row comes from

Every row in the *Test cases* table must trace back to one or more elements
of the Story, and its *Rule* cell names that element:

| Source in the Story                                         | Tests it implies                                                    | *Rule* cell        |
|-------------------------------------------------------------|---------------------------------------------------------------------|--------------------|
| FD — *Business rules*, each row                             | ≥ 1 test per rule; more when the rule has thresholds, branches or role-dependent behaviour | `BR-n`             |
| FD — *Messages*, each row                                   | the test of its rule asserts that the message is shown              | `BR-n`             |
| FD — *Data*, each validation constraint                     | ≥ 1 negative test (mandatory field, format, range, …)               | `Data — <information>` |
| FD — *Impact on existing data*, when it is not `None`       | ≥ 1 test on the existing-data path                                  | `Existing data`    |
| Technical design — *Limits & volumes*, each non-N/A item    | ≥ 1 boundary test (cap, page-size limit, p95 latency point, degradation path) | `Limit — <item>`   |

Conversely, every test row must reduce to at least one source above. A test
row that has no traceable source is either over-specification or evidence
that the FD is incomplete — in the latter case, fix the FD, not the tests.

## Test cases table — how to write each cell

The template's *Test cases* table has four columns: **Rule**, **Given**,
**When**, **Then**. Stay strictly inside this BDD shape — do not introduce
extra columns.

### Rule (column 1)

The source the test verifies, in one of the forms in the table above —
usually a business-rule number (`BR-2`). Several rules may share a test
(`BR-1, BR-2`) when one scenario genuinely verifies both. Every rule in the
FD must appear in this column at least once: that is the coverage check,
visible at a glance.

Which tests to write — the judgement the old `Type` column used to carry:

- **The main expected behaviour** of the Story is always tested.
- **Thresholds, status conditions, branches and role-dependent behaviour**
  get a test each.
- **Negative tests** — what must not happen, rejected input, denied
  permission — are **mandatory when financial integrity, data integrity, or
  security is at risk**.
- **Edge cases** must be realistic AND previously known to cause bugs. **The
  default count is zero**; do not invent edge cases for completeness.

### Given (column 2)

State the preconditions factually:

- **Reference Dataset rows by their IDs** (e.g. *Customer C1*, *Offer O1*)
  when there is a *Dataset*. A fixture used by a single test may be
  described inline instead.
- Include the **actor** (persona from the *Requirement* field) and the
  **starting system state** (entity status, configuration flag, feature
  toggle) when the rule depends on them.
- One precondition cluster per row. If two tests need materially different
  preconditions, they are different rows.

### When (column 3)

A **single user action or system trigger**. One verb. If you find yourself
writing "the user does X and then Y", split into two rows or move the first
step into *Given*.

For API-bearing Stories, the action is one HTTP call — verb + path + body
shape — referring back to the API in *Technical design* rather than
re-specifying it.

### Then (column 4)

A **single observable, verifiable outcome**:

- **For a user-facing message, name it by its rule** — *"The BR-3 warning is
  shown"* — rather than quoting it. The *Messages* table is the single home
  of the wording, in both languages; a quoted copy is a second source that
  drifts. Quote the text only where the wording itself is what the test
  verifies (e.g. a regulatory label).
- For API responses, state HTTP status + error code (from the *Technical
  design* *Error dictionary*) on
  negative paths; reference the response shape on positive paths.
- **No implementation leakage** — no Java class names, no SQL, no internal
  exception types, no audit-log structure unless those are part of the
  documented public contract. Public REST contract elements (HTTP status,
  error code, response field names) *are* user-visible and belong here.
- **Atomicity** — if a test must verify two distinct outcomes, write two
  rows. "Then" never contains an *and* that joins independent assertions.

## Dataset section

**Optional.** Use it when **two or more tests share data**: lift each shared
object into one row and reference it by ID in *Given*. A Story whose tests
each need their own small fixture can describe it inline and omit the
section — an empty *Dataset* heading is not acceptable (`stories.md`
§ *Story structure — light format*).

| ID | Object       | Key attributes (only those a test depends on)       |
|----|--------------|-----------------------------------------------------|
| C1 | Customer     | Status: Active; Country: FR; Payment method: SEPA   |
| O1 | Offer        | Price: 10 €/month; Currency: EUR                    |
| S1 | Subscription | Customer: C1; Offer: O1; Status: Active             |

Do not document attributes no test touches — the *Dataset* is fixture
documentation, not an entity dump. Conversely, if a test row references an
ID that is not in the *Dataset*, that is a defect in the acceptance section —
add the row, do not delete the test.

## Coverage check — run it before submitting

Walk through the FD and the Limits & volumes checklist and tick each against
the *Rule* column:

- Every *Business rules* row → at least one test naming it? If not, either
  the rule is dead text (raise with the PO) or the tests are incomplete.
- Every *Messages* row → its rule's test asserts the message is shown?
  Untested messages are usually a smell.
- Every *Data* validation constraint → at least one negative test? Skip this
  only when the constraint is purely cosmetic (e.g. label truncation), and
  flag the skip explicitly.
- An *Impact on existing data* other than `None` → at least one test?
- Every non-N/A *Limits & volumes* item → at least one boundary test? An
  unverified limit is an unverifiable promise.

Report uncovered rows back to the user — never silently extrapolate.

## Language

The Acceptance content is written in **English** (per `SKILL.md` general
rules). French appears only where a test verifies a French wording itself,
quoted verbatim.

## Anti-patterns to avoid

- **Tautological tests** — "When the user creates a customer, then a
  customer is created" adds nothing. *Then* must describe the *check* a
  tester can perform (specific status, specific message, specific field
  value, specific HTTP code).
- **Compound tests** — multiple actions in *When* or multiple independent
  assertions in *Then*. Split.
- **Speculative edge cases** — tests added because "we should probably test
  the empty list" without prior evidence the empty list misbehaves. The
  default count is zero.
- **Test-driven specification** — inventing business rules in tests that
  are not in the FD. The FD is the source; tests verify it. Flag the gap,
  do not paper over it.
- **Restating the FD** — copying a rule's wording or a message's text into
  *Then*. Name the rule; the FD holds the wording.
- **Schema-leak tests** — assertions on database columns, internal
  services, or implementation details that are not part of the documented
  public contract.
- **Repeated fixtures** — the same object described inline in several
  *Given* cells. Once it is shared, lift it into the *Dataset*.
