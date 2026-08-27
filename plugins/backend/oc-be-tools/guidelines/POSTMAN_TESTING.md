# Opencell Project - Postman / Integration Testing Guidelines

> **Note**: This document contains **Postman / integration-testing** guidelines for the Opencell project. For **unit-testing** guidelines, see [UNIT_TESTING.md](./UNIT_TESTING.md).

## Authoring and Editing Generated / Large Collection Artifacts

Postman collections are large generated JSON artifacts. A few principles keep them correct and reviewable:

1. **Author against verified real endpoints and shapes — never invent.** Copy URLs, paths, and field names from a known-working request or from the actual route/DTO definitions. This is the same rule enforced in detail by **API Call Verification** below; treat inventing a URL or a field name as a defect, not a guess to be corrected later.

2. **Keep the collection consistently pretty-printed, and insert new content pretty-printed too — never a minified blob.** A Postman collection MUST stay one-field-per-line (`json.dumps(..., indent=2, ensure_ascii=False)`, which reproduces Postman's own export format). That is what makes it **diffable, mergeable, and line-countable** — a folder of 20+ requests collapsed onto a single line is impossible to review, impossible to merge, and defeats the AI-usage line metrics. When adding content, **serialize it with the same indentation as its neighbours and splice it in formatted**; do NOT insert a compact single-line `json.dumps(x)` blob even when doing byte-preserving surgery (that is exactly how an otherwise-formatted file ends up with unreviewable 50k-char lines). Byte-preserving splicing is still the right tool for *edits*; the constraint is that the spliced text is formatted. Re-serializing the **whole** file at the matching indent is acceptable when it reproduces the existing formatting — verify first that a load→dump of the base version is byte-identical to the base (so the only real diff is your addition). After editing, verify unrelated content is unchanged and nothing was duplicated:
   - Confirm request/item counts before vs after (only the delta you intended); confirm the set of request names *outside* your folder is unchanged.
   - Grep for the edited request's unique name/id to ensure exactly one occurrence (no accidental duplication from a copy-paste insert).
   - Confirm the file has no abnormally long lines (a quick "longest line length" check catches an accidental minified insertion).

3. **Respect the framework's assertion conventions for success vs expected-failure.** Follow how the harness marks negative tests so they are not auto-overridden into passes. In Opencell Postman collections this is the `" - fail"` naming rule (see **Error Scenario Tests**): a negative test's name must end in `" - fail"` and assert the specific error status; a name without it must assert success.

4. **Ensure data isolation and idempotency across repeated runs.** Shared environments accumulate state, so every run must use unique keys (the per-domain `iteration_nr` sequence) and fully tear down what it created. See **Test Data Variables**, **Per-folder data isolation**, and **Deletion Best Practices** below for the concrete patterns.

## Postman Collections

Provide Postman collection with:
- Examples for all CRUD operations
- Examples for custom operations
- Error scenarios
- Environment variables

**CRITICAL: Request Body Requirements**

- **Create requests**: Must include ALL entity fields in the request body
  - Include all mandatory fields with valid values
  - Include all optional fields (can be null or omitted)
  - Include all i18n fields (descriptionI18n, longDescriptionI18n) with proper language codes (ENG, FRA, etc.)
  - Include disabled field (can be set during creation)
  - DO NOT include status field (managed through lifecycle actions)

- **Update requests**: Must include all updatable entity fields
  - Include all fields that can be updated
  - Include all i18n fields with proper language codes
  - DO NOT include status field (managed through lifecycle actions)
  - DO NOT include disabled field (managed through enable/disable actions)

- This ensures comprehensive testing of field mapping and validation

## Environment Variables

**CRITICAL: Use `opencell.url` variable for all API requests**

- Variable name: `opencell.url` (not `base_url`)
- Default value: `http://localhost:8080/opencell/api/rest` (includes full path)
- The variable should include the complete path up to `/opencell/api/rest`

**Pattern:** Use `{{opencell.url}}/v2/{domain}/{resource}` in all requests

### Test Data Variables

**CRITICAL: The ONLY collection variable for building codes is a per-domain sequence number. Everything else is written literally in the request body.**

1. **Iteration number = a sequence, NOT a timestamp.** In the folder's first pre-request script, increment a stored counter:
   ```javascript
   let iterationNr = parseInt(pm.collectionVariables.get("iteration_nr") || "0", 10) + 1;
   pm.collectionVariables.set("iteration_nr", iterationNr);
   ```
   Do NOT use `Date.now()` / `{{$timestamp}}` — a readable, reproducible sequence number is required.

2. **Build codes as a descriptive literal prefix + the sequence number, written directly in the body** — do not hide them behind per-code variables:
   - ✅ `"code": "CONTRACT_TEST_SUB_FOR_CONTRACT_{{iteration_nr}}"`
   - ❌ `"code": "{{test_sub_code}}"` (forces the reader to hunt for what `test_sub_code` is)

3. **Static values are literals, never variables.** A value that never changes (an article code `ART-STD`, an invoice type `COM`, a category `CONSUMPTION`, a seller `SELLER_FR`) is written directly in the body. Do NOT do `pm.collectionVariables.set("test_accounting_article_code", "ART-STD")` and then reference `{{test_accounting_article_code}}` — it makes request bodies unreadable. Only IDs the server generates at runtime (invoice id, line id) are stored in variables and referenced back.

**Example:**

```javascript
// Pre-request: only the sequence counter
let iterationNr = parseInt(pm.collectionVariables.get("iteration_nr") || "0", 10) + 1;
pm.collectionVariables.set("iteration_nr", iterationNr);

// Request body: descriptive code + sequence, statics inline
{
    "code": "INVOICE_CRUD_BA_{{iteration_nr}}",
    "customerAccount": "INVOICE_CA_{{iteration_nr}}",
    "billingCycle": "INVOICE_BC_{{iteration_nr}}",
    "country": "FR"
}
```

### Per-folder data isolation

**Test folders must not share a data-aggregation root whose contents accumulate and make results order-dependent.** When a domain rolls data up under a parent entity — and one folder's activity would otherwise change what another folder sees on that parent — give each folder its own instance of that parent so every folder is independently reproducible regardless of which folders run or in what order. Shared, immutable reference data (sellers, articles, calendars, tax classes, etc.) can and should stay shared.

- **Invoicing** aggregates invoice lines and unbilled data per **billing account**, so each invoicing folder MUST create and use its **own billing account** — otherwise lines from one folder leak into another folder's invoices (and the invoice-create can link stray unbilled lines). Give each folder a distinct, descriptive BA code, e.g. `INVOICE_CRUD_BA_{{iteration_nr}}`, `INVOICE_STATUS_BA_{{iteration_nr}}`, `INVOICE_LINES_BA_{{iteration_nr}}`, `INVOICE_BILLING_RUN_BA_{{iteration_nr}}`.
- **Other domains** where folders only read/modify their own explicitly-created entities (no shared aggregation root) can safely reuse the same billing account / customer hierarchy.

## API Call Verification

**CRITICAL: Before creating ANY Postman request, you MUST read the actual REST resource interface and DTO source files. Never guess or assume URLs or payload fields.**

### Step 1: Build an Endpoint Map (MANDATORY)

Read the REST resource **interface** file (not the implementation) and extract every endpoint:

1. **Class-level `@Path`** — e.g., `@Path("/v2/indexation/batches")` → this is the base path
2. **Method-level `@Path`** — e.g., `@Path("/{id}")` → append to base path
3. **Full URL** — concatenate class + method paths: `/v2/indexation/batches/{id}`
4. **HTTP method** — read the annotation: `@GET`, `@POST`, `@PUT`, `@DELETE`. Do NOT assume action endpoints (publish, close, enable, disable) use PUT — many use `@POST`
5. **Path parameters** — read `@PathParam` annotations. Note the exact name AND type (`Long id` vs `String code`)
6. **Query parameters** — read `@QueryParam` annotations for optional parameters
7. **Nested vs flat paths** — verify whether resources are nested (e.g., `/batches/{batchId}/priceIndexations`) or flat

**Write out the complete endpoint map before proceeding.** Example:
```
Endpoint Map (from IndexationBatchResource.java):
POST   /v2/indexation/batches                      → create(IndexationBatchDto)
GET    /v2/indexation/batches/{id}                  → find(@PathParam("id") Long id)
GET    /v2/indexation/batches                       → list(...)
PUT    /v2/indexation/batches/{id}                  → update(@PathParam("id") Long id, ...)
DELETE /v2/indexation/batches/{id}                  → delete(@PathParam("id") Long id)
POST   /v2/indexation/batches/{code}/close          → close(@PathParam("code") String code)
```

### Step 2: Build a DTO Field Map (MANDATORY)

For each endpoint that accepts a request body, read the **DTO class file** and extract every field:

1. **Read the DTO class** — list all fields with their Java types
2. **For Immutable DTOs (v2)** — also read the `fromDto()` method in the API service to see which fields are actually mapped from the DTO to the entity
3. **Identify mandatory vs optional** — check `@NotNull` annotations and validation logic in the service layer
4. **Read nested DTOs** — if a field type is another DTO (e.g., `List<PriceIndexationDto>`), read that DTO class too
5. **Identify excluded fields** — status fields managed by lifecycle (e.g., `status`, `disabled`) should NOT be in create/update bodies
6. **JAXB annotations determine JSON field names for v0/v1 DTOs** — v0/v1 DTOs use JAXB annotations that control JSON serialization names:
   - `@XmlAttribute(name = "code")` on a field `entityCode` → JSON key is `code` (not `entityCode`)
   - `@XmlElement(name = "role")` on a field `roles` → JSON key is the JAXB name
   - `@XmlElementWrapper(name = "accessibleEntities")` + `@XmlElement(name = "accessibleEntity")` on a `List<T>` field → JSON key is the `@XmlElement` name: `"accessibleEntity": [...]` (the wrapper name is ignored in JSON)
   - If no JAXB `name` attribute is specified (e.g., `@XmlAttribute()` without name), use the Java field name
   - **Always check `@XmlAttribute`, `@XmlElement`, and `@XmlElementWrapper` annotations on DTO fields before writing JSON payloads**

**Write out the field list before proceeding.** Example:
```
IndexationBatchDto fields:
- code: String (mandatory)
- description: String (optional)
- descriptionI18n: Map<String, String> (optional, i18n)
- indexId: Long (mandatory, reference to Index)
- startDate: Date (optional)
Fields to EXCLUDE from create/update: status (lifecycle-managed)
```

### Step 3: Verify Every Postman Request (MANDATORY)

After building the collection, verify EACH request against the maps from steps 1 and 2:

- **URL**: Does this URL match the endpoint map character by character? Common mistakes:
  - ❌ Using `{code}` when the interface says `@PathParam("id") Long id`
  - ❌ Using `/{id}/action` when the interface says `/{code}/action`
  - ❌ Inventing URLs for endpoints that don't exist in the interface
  - ❌ Using wrong base path (e.g., `/v2/cpq/entity` when interface says `/v2/catalog/entity`)
- **HTTP method**: Does the method match? Common mistakes:
  - ❌ Using PUT for action endpoints that are annotated with `@POST`
  - ❌ Using POST for update endpoints that are annotated with `@PUT`
- **Request body fields**: Does the body contain ONLY fields from the DTO? Common mistakes:
  - ❌ Including fields that don't exist in the DTO class
  - ❌ Using wrong field names (e.g., `indexCode` when DTO has `indexId`)
  - ❌ Using wrong field types (e.g., string `"123"` for a `Long` field)
  - ❌ Including `status` field in create/update requests
  - ❌ Missing nested DTO structure (e.g., flat field instead of nested object)

## Authorization

**CRITICAL: Use OAuth2 at collection level (Keycloak) — never Basic Auth.**

- **Authorization Type**: OAuth2, configured at collection level so every request inherits it.
- Token endpoint `{{keycloak.token.url}}`, client `{{client.id}}` / `{{client.secret}}`, user `{{opencell.username}}` / `{{opencell.password}}`.

### Collection-level scripts (new collections)

**When creating a NEW collection file, copy the collection-level OAuth2 auth block and the collection-level pre-request and post-response (test) scripts verbatim from `US-Tests/Opencell_Setup.postman_collection.json`** (its top-level `auth` and `event` entries). They provide the shared harness the rest of these guidelines assume, and keep auth consistent with its retry logic:

- token / `access_token` handling and automatic re-auth-on-`401` retry,
- the `[SKIP]` request-name convention,
- per-run initialisation of shared variables, and
- the global success / expected-failure assertion that enforces the `" - fail"` convention (see **Error Scenario Tests**) — a request whose name does not end in `" - fail"` is asserted to have succeeded.

## Test Organization and Independence

**CRITICAL: Organize Postman tests to be independent and complete full CRUD cycles**

### Test Independence Principles

1. **Each test folder is self-contained** - Create all needed entities at the start
2. **Complete CRUD cycle** - Create → Read → Update → Custom Operations → Delete within one folder
3. **Fresh entities for each test section** - Don't reuse entities from previous test folders
4. **Clean up at the end** - Delete all created entities in reverse dependency order

### Test Structure Pattern

**Organize by entity with full CRUD cycle:**

```
Folder: Entity Tests
  ├── Create
  ├── Get by Code/ID
  ├── List
  ├── Update
  ├── Custom operations (enable, disable, close, etc.)
  └── Delete

For child entities: Create parent first, delete parent last
```

### List Test Assertions

**CRITICAL: Access search results using `jsonData.searchResults` not `jsonData.data`**

- List endpoint responses contain results in `searchResults` property
- Use `pm.expect(jsonData.searchResults).to.be.an('array');` for array validation
- Access individual items from `jsonData.searchResults[0]`

### Deletion Best Practices

- Delete each entity only once (by code OR ID, not both)
- Delete in reverse dependency order (children first, then parents)

### Error Scenario Tests

- Test error scenarios in separate requests (e.g., "Create with missing required field")
- Error tests don't need cleanup if entity wasn't created
- **A test that deliberately expects a failure/error response MUST have a name ending in `" - fail"`.** This makes negative tests obvious at a glance and greppable. Example: `"INV-DL-002 Delete validated invoice (error) - fail"`, `"Create without code - fail"`. A test whose name does NOT end in `" - fail"` must assert a success status; a test whose name DOES end in `" - fail"` must assert the specific error status (e.g. `400`/`404`), never a success code.

### Test Assertions

**CRITICAL: Use specific value assertions, not existence checks**

- **DO**: Assert exact expected values - `pm.expect(jsonData.status).to.eql("DRAFT")`
- **DON'T**: Assert field existence only - `pm.expect(jsonData.status).to.exist` or `pm.expect(jsonData.status).to.not.be.undefined`
- **NEVER use `.to.not.be.undefined` / `.to.exist` for validation.** You control the request body, so you know the exact value to expect — assert it. For server-generated values you cannot know exactly, assert the concrete shape/constraint instead (`.to.be.a("number")`, `.to.be.a("string").with.length.above(0)`), never mere existence.
- **Derive computed values from inputs.** Amounts follow from the submitted lines and the known tax rate (e.g. 3 lines 100 + 125 + 50 = 275 net; at 5% tax → `amountTax` 13.75, `amountWithTax` 288.75). Assert those exact numbers, not `to.be.above(0)`.
- **At least one create (or update) request MUST validate ALL fields** of the returned DTO against concrete expected values — every echoed scalar, every default flag, and the full aggregate/line tree — so the response contract is fully pinned by at least one test.

**Example:**

```javascript
// ✅ CORRECT - Assert specific values
pm.test("Batch status is DRAFT", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.status).to.eql("DRAFT");
});

pm.test("Response has 3 lines", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.priceIndexations.length).to.eql(3);
});

// ❌ WRONG - Only checks existence
pm.test("Response has status", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData.status).to.exist; // Could be any value!
});
```

### HTTP Status Code Assertions

**CRITICAL: Assert one exact status code per request — never a set.**

Each endpoint returns a single, deterministic status, so assert it exactly:

- Create (`POST`) → `pm.response.to.have.status(201)`
- Update / lifecycle action (`PUT`, `PATCH`) → `pm.response.to.have.status(200)`
- Get / List (`GET`) → `pm.response.to.have.status(200)`
- Error scenario → the one expected error status, e.g. `pm.response.to.have.status(400)`

**The ONLY exception is `*/createOrUpdate` endpoints**, which return `201` when they create and `200` when they update — those may legitimately use `pm.expect(pm.response.code).to.be.oneOf([200, 201])`.

```javascript
// ✅ CORRECT - a create endpoint always returns 201
pm.test("Status code is 201", function () {
    pm.response.to.have.status(201);
});

// ❌ WRONG - hedging on the status hides a wrong response code
pm.test("Status code is 200 or 201", function () {
    pm.expect(pm.response.code).to.be.oneOf([200, 201]);
});
```

### Invoice auto-validation (`isAutoValidation`)

When creating an invoice, **omitting `isAutoValidation` makes the invoice auto-validate** (status `VALIDATED`, invoice number assigned). A test that then exercises a lifecycle transition needing a non-validated invoice (validate / cancel / reject / quarantine a `DRAFT`) MUST set `"isAutoValidation": false` in the create body, otherwise the invoice is already `VALIDATED` and the transition fails.
