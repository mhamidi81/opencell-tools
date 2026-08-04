# Opencell Project - Testing Guidelines

> **Note**: This document contains testing-specific guidelines for the Opencell project. For general development guidelines (entities, services, API, etc.), see [CLAUDE.md](./CLAUDE.md).

> **Development Environment**: See **[DEVELOPMENT_SETUP.md](./DEVELOPMENT_SETUP.md)** for Java/Maven execution commands on this machine.

This guide covers:
- Unit test patterns and best practices
- Service layer testing with EntityManager mocking
- API layer testing with ArgumentCaptor
- Integration testing with Postman

---

# Unit Test Guidelines

## Test Coverage Target

**Aim for 80% code coverage** as a minimum quality standard:
- Focus on critical business logic and complex methods
- Cover main scenarios, edge cases, and error conditions

## General Structure

### Test Method Naming

- Use descriptive names following the pattern: `test_methodName_scenario_expectedResult`
    - Example: `test_calculatePrice_withDiscount_returnsDiscountedPrice`

### AAA Pattern

- **Arrange**: Set up test data and preconditions
- **Act**: Call the method being tested
- **Assert**: Verify the expected outcome


### Test Independence

- Each test should be independent and not rely on other tests
- Reset any shared state between tests


### Test Edge Cases
- Null values
- Empty collections
- Boundary values
- Error conditions


### Test Data

**Write tests with real scenarios in mind** - use meaningful test data that represents actual usage:
- Use helper methods for creating test objects
- Consider using test data builders for complex objects
- Use meaningful values that relate to the test scenario
- Model test data after real-world use cases

### Date Handling in Tests

**CRITICAL: Use dates relative to `LocalDate.now()` so tests remain valid over time**

Never hardcode absolute dates (e.g., `LocalDate.of(2026, 4, 16)`) in tests. If acceptance criteria specify hardcoded dates (e.g., "CSD = May 15, 2026"), translate them into relative offsets from today.

```java
// ❌ WRONG - will fail in 6 months
LocalDate fiscalStart = LocalDate.of(2026, 1, 1);
LocalDate fiscalEnd = LocalDate.of(2026, 12, 31);

// ✅ CORRECT - always valid
LocalDate today = LocalDate.now();
LocalDate fiscalStart = today.minusMonths(6).withDayOfMonth(1);
LocalDate fiscalEnd = fiscalStart.plusMonths(12).minusDays(1);
```

**Exceptions**: Use absolute dates only when testing entities that are guaranteed to always be in the past (e.g., `LocalDate.of(1900, 1, 1)`) or always in the future (e.g., `today.plusYears(10)`).

### Independence from Ambient State

**Keep tests independent of ambient state — the clock, timezone, locale, and randomness.** A test must produce the same result on any machine, in any timezone, on any day. Two safe strategies:

- **Assert derived results, not the ambient value.** If the code falls back to "today" when no date is given, assert *the effect* (the query ran, a value was resolved) or compute the same fallback in the test — never hardcode a specific date and hope the run lands on it.
- **Read the ambient value at run time** and derive the expectation from it: `int expectedYear = Calendar.getInstance().get(Calendar.YEAR);` rather than `2026`.

```java
// ❌ WRONG - depends on the wall clock; breaks on Jan 1 or in another timezone
assertThat(resolved.getYear()).isEqualTo(2026);

// ✅ CORRECT - derive the expectation from the same ambient value production uses
int expectedYear = LocalDate.now().getYear();
assertThat(resolved.getYear()).isEqualTo(expectedYear);
```

Locale/timezone-sensitive formatting, `Math.random()`, and `UUID.randomUUID()` are the other common offenders — inject or stub the source, or assert a shape/constraint rather than an exact value.

### A Deliberate Behavior Change Obligates a Test Sweep

**When you intentionally change existing behavior, you own every test that asserted the old behavior.** Adding tests for the new behavior is not enough — find and update the existing tests that encoded the old contract, and run the **whole affected suite**, not just your new tests.

- Grep for callers and for tests referencing the changed method/message/field before declaring done.
- A previously-passing test that now fails is a signal to reconcile (update the assertion *or* reconsider the change), never to skip or delete without understanding why.
- Example: making a mandatory field optional (a nullable batch date) invalidates every test that assumed it was always present — those must be revisited, not left red or ignored.

## Mocking

### When to Mock

- Mock external dependencies (services, repositories, etc.)
- **CRITICAL: Don't mock the class under test**
- **CRITICAL: Never mock methods in the class you're testing** - always let the real logic execute
  - Mock external dependencies only (other services, repositories, EntityManager)
  - Example: When testing `ContractItemService.update()`, don't mock `update()` itself - mock EntityManager instead

### Mockito Best Practices

- Use `@Mock` for dependencies
- Use `@InjectMocks` for the class under test
- Use `ArgumentCaptor` to verify complex arguments
- For varargs, use `captor.getAllValues()` to get all captured values
- Prefer using `@Spy` with `@InjectMocks` annotations over manual spy creation
  - Injects all mocked dependencies automatically
  - Supports partial mocking while maintaining dependency injection

### Build Expected Stub Values the Way Production Builds Them

**CRITICAL: When a mock is stubbed with `eq(value)` for something the code computes internally, construct the expected value identically to production — or match only the meaningful fields with `argThat(...)`.**

Normalized dates (time-of-day zeroed), trimmed/upper-cased strings, and scaled `BigDecimal`s are the usual traps. If the argument the code actually passes differs from your `eq(...)` by even a millisecond or a trailing scale digit, Mockito does **not** match, the stub returns `null`/`0`/default, and the real assertion silently passes against garbage — a green test that proves nothing.

```java
// Production zeroes the time before querying:
//   Date target = setTimeToZero(batch.getTargetDate());
//   indexationValueService.findValueAtDate(index, target);

// ❌ WRONG - raw date won't equal the zeroed date the code passes → stub returns null
when(indexationValueService.findValueAtDate(eq(index), eq(someDate))).thenReturn(value);

// ✅ CORRECT - build the expected value exactly as production does
Date expected = setTimeToZero(someDate);
when(indexationValueService.findValueAtDate(eq(index), eq(expected))).thenReturn(value);

// ✅ ALSO CORRECT - match only the field(s) that matter
when(indexationValueService.findValueAtDate(eq(index),
        argThat(d -> DateUtils.isSameDay(d, someDate)))).thenReturn(value);
```

### Ordering of Overlapping Mock Matchers

**With overlapping matchers on the same mock method, the LAST-defined stub wins.** Define the broad catch-all (`any(...)`) **first**, then the specific cases (`eq(...)`), so the specific stub is not shadowed by the general one.

```java
// ✅ CORRECT - broad first, specific last (specific wins for INDEX_A)
doReturn(defaultValue).when(service).resolve(any());
doReturn(specialValue).when(service).resolve(eq("INDEX_A"));

// ❌ WRONG - the any() defined last overrides the specific stub; INDEX_A gets defaultValue
doReturn(specialValue).when(service).resolve(eq("INDEX_A"));
doReturn(defaultValue).when(service).resolve(any());
```

### Stubbing Patterns for Spied Objects

**CRITICAL: Use `doReturn().when()` pattern for spied objects, NOT `when().thenReturn()`**

When stubbing methods on spied objects (`@Spy` with `@InjectMocks`):
- **ALWAYS use**: `doReturn(value).when(spy).method(args)` for methods returning values
- **ALWAYS use**: `doNothing().when(spy).method(args)` for void methods
- **ALWAYS use**: `doAnswer(invocation -> {...}).when(spy).method(args)` for complex stubbing
- **NEVER use**: `when(spy.method(args)).thenReturn(value)` or `when(spy.method(args)).thenAnswer(...)`

**Reason**: The `when().thenReturn()` pattern calls the real method during stubbing setup, which will fail if the method has null dependencies or side effects.

**Examples:**

```java
// ✅ CORRECT - for methods returning a value
doReturn(entity).when(spiedService).update(entity);
doReturn(entity).when(spiedService).findByCode("TEST");

// ✅ CORRECT - for void methods
doNothing().when(spiedService).remove(entity);
doNothing().when(spiedService).validateStatusTransition(anyString(), any(), any());

// ✅ CORRECT - for void methods with complex logic (e.g., create)
doAnswer(invocation -> {
    Entity e = invocation.getArgument(0);
    e.setId(1L);
    return null;
}).when(spiedService).create(any());

// ❌ WRONG - calls real method during setup!
when(spiedService.update(entity)).thenReturn(entity);

// ❌ WRONG - calls real method during setup!
when(spiedService.create(any())).thenAnswer(invocation -> { ... });
```

**Rule of thumb**:
- For regular mocks (`@Mock`): Either pattern works, `when().thenReturn()` is more common
- For spied objects (`@Spy`): **ALWAYS** use `do*().when()` pattern to avoid calling real methods during setup

**CRITICAL: This applies to ALL methods on spied objects, including inherited methods like `findById()`, `update()`, `create()`, etc.**

```java
// ✅ CORRECT - stubbing spied service methods
doReturn(entity).when(spiedService).findById(1L);
doReturn(entity).when(spiedService).findByCode("CODE");
doReturn(entity).when(spiedService).update(any());

// ❌ WRONG - will call real method during setup!
when(spiedService.findById(1L)).thenReturn(entity);
when(spiedService.update(any())).thenReturn(entity);
```

### EntityManager Mocking Patterns

**CRITICAL: When testing service CRUD methods (create, update, remove), mock EntityManager operations instead of mocking the service methods themselves**

This allows the real business logic and validation to execute while avoiding actual database operations.

**Pattern for create() tests:**

```java
@Test
public void test_create_withValidData_validatesAndPersists() throws Exception {
    // Arrange
    ContractItem contractItem = new ContractItem();
    contractItem.setCode("ITEM_001");

    // Mock EntityManager.persist() to set ID without database
    doReturn(entityManager).when(contractItemService).getEntityManager();
    doAnswer(invocation -> {
        ContractItem item = invocation.getArgument(0);
        item.setId(1L);
        return null;
    }).when(entityManager).persist(any(ContractItem.class));

    // Act
    contractItemService.create(contractItem);

    // Assert
    assertThat(contractItem.getId()).isEqualTo(1L);
    verify(entityManager).persist(contractItem);
}
```

**Pattern for update() tests:**

```java
@Test
public void test_update_withValidData_mergesEntity() throws Exception {
    // Arrange
    ContractItem contractItem = new ContractItem();
    contractItem.setId(1L);

    // Mock EntityManager.merge() to return entity without database
    doReturn(entityManager).when(contractItemService).getEntityManager();
    when(entityManager.merge(any(ContractItem.class))).thenReturn(contractItem);

    // Act
    ContractItem result = contractItemService.update(contractItem);

    // Assert
    assertThat(result).isNotNull();
    verify(entityManager).merge(contractItem);
}
```

**Pattern for remove() tests:**

```java
@Test
public void test_remove_withValidEntity_removesFromDatabase() throws Exception {
    // Arrange
    ContractItem contractItem = new ContractItem();
    contractItem.setId(1L);

    // Mock EntityManagerWrapper and EntityManager for remove
    when(emWrapper.getEntityManager()).thenReturn(entityManager);
    when(entityManager.contains(any())).thenReturn(true);

    // Act
    contractItemService.remove(contractItem);

    // Assert
    verify(entityManager).remove(any());
}
```

**Required mocks for service tests:**

```java
@Mock
private EntityManager entityManager;

@Mock
private org.meveo.jpa.EntityManagerWrapper emWrapper;

@Mock
private org.meveo.service.base.DeletionService deletionService;
```

## Service Layer Testing

### Testing Validation Methods

**CRITICAL: Don't mock validation methods in the class being tested**

When testing business methods (create, update, etc.) that call validation methods:
- **DO**: Let the real validation execute with valid test data
- **DON'T**: Mock validation methods with `doNothing()` - this skips validation entirely
- Test validation failures separately in dedicated validation tests

**Correct Pattern:**

```java
@Test
public void test_update_withValidFormula_executesRealValidation() throws Exception {
    // Arrange
    IndexationFormula formula = new IndexationFormula();
    formula.setStatus(IndexationFormulaStatusEnum.PUBLISHED); // Valid status

    ContractItem item = new ContractItem();
    item.setFormula(formula);

    // Mock EntityManager, but NOT validation methods
    doReturn(entityManager).when(contractItemService).getEntityManager();
    when(entityManager.merge(any())).thenReturn(item);

    // Act - real validation will execute and pass
    contractItemService.update(item);

    // Assert
    verify(contractItemService).validateFormulaStatusForContractItem(formula);
}

@Test
public void test_validateFormulaStatus_withInvalidStatus_throwsException() {
    // Test validation failures separately with invalid data
    IndexationFormula formula = new IndexationFormula();
    formula.setStatus(IndexationFormulaStatusEnum.DRAFT); // Invalid status

    assertThatExceptionOfType(ValidationException.class)
        .isThrownBy(() -> contractItemService.validateFormulaStatusForContractItem(formula))
        .withMessageContaining("PUBLISHED or IN_USE");
}
```

**Incorrect Pattern (DO NOT USE):**

```java
// BAD - Mocking validation skips the logic entirely
doNothing().when(contractItemService).validateFormulaStatusForContractItem(any());

// Act
contractItemService.update(item); // Validation never actually runs!

// This test is meaningless - it only tests that the mocked method was called
verify(contractItemService).validateFormulaStatusForContractItem(any());
```

**Why this matters:**
- Mocking validation methods creates false test coverage
- You're only testing that the method was called, not that validation works
- Bugs in validation logic won't be caught by these tests
- Use valid test data and let real validation execute to test the full integration

## API Layer Testing

### Testing CRUD Methods (create, update)

**CRITICAL: Use ArgumentCaptor to capture and verify entity mapping**

Pattern: Capture argument → Return captured object with ID → Verify captured fields → Verify returned DTO

**Correct Pattern:**

```java
@Test
public void test_create_withValidData_capturesCorrectEntityFields() throws Exception {
    // Arrange
    IndexationDto dto = ImmutableIndexationDto.builder()
            .code("CPI_2024")
            .description("CPI 2024")
            .status(IndexationStatusEnum.DRAFT)
            .build();

    when(indexationService.findByCode("CPI_2024")).thenReturn(null);
    when(entityToDtoConverter.getCustomFieldsDTO(...)).thenReturn(null);

    // Capture the argument and return the same object with ID set
    ArgumentCaptor<Indexation> entityCaptor = ArgumentCaptor.forClass(Indexation.class);
    when(indexationService.create(entityCaptor.capture())).thenAnswer(invocation -> {
        Indexation entity = invocation.getArgument(0);
        entity.setId(1L);
        return entity;
    });

    // Act
    IndexationDto result = indexationApi.create(dto);

    // Assert - verify the captured entity has correct field values from DTO
    Indexation capturedEntity = entityCaptor.getValue();
    assertThat(capturedEntity.getCode()).isEqualTo("CPI_2024");
    assertThat(capturedEntity.getDescription()).isEqualTo("CPI 2024");
    assertThat(capturedEntity.getStatus()).isEqualTo(IndexationStatusEnum.DRAFT);

    // Verify returned DTO has all correct field values
    assertThat(result).isNotNull();
    assertThat(result.getId()).isEqualTo(1L);
    assertThat(result.getCode()).isEqualTo("CPI_2024");
    assertThat(result.getDescription()).isEqualTo("CPI 2024");
    assertThat(result.getStatus()).isEqualTo(IndexationStatusEnum.DRAFT);
}
```

**Incorrect Pattern (DO NOT USE):**

```java
// BAD - Mocking service return separately
when(indexationService.create(any())).thenReturn(mockedEntity);
// Then verifying the mocked entity fields - this doesn't test actual mapping!
```

### Testing Mapper Methods (fromDto, toDto)

**Test scenarios:**
- **fromDto()**: All fields provided, null values (not updated), empty strings (cleared), individual field updates
- **toDto()**: All fields populated, null entity, nested resources

```java
@Test
public void test_fromDto_withNullValues_doesNotUpdateFields() throws Exception {
    // Arrange - Setup entity with all fields populated
    Indexation entity = new Indexation();
    entity.setCode("ORIGINAL_CODE");
    entity.setDescription("Original description");
    entity.setStatus(IndexationStatusEnum.PUBLISHED);

    // DTO with only code set, all other fields null
    IndexationDto dto = ImmutableIndexationDto.builder()
            .code("NEW_CODE")
            .build();

    // Act
    indexationApi.fromDto(dto, entity);

    // Assert - only code should be updated, all other fields remain unchanged
    assertThat(entity.getCode()).isEqualTo("NEW_CODE");
    assertThat(entity.getDescription()).isEqualTo("Original description");
    assertThat(entity.getStatus()).isEqualTo(IndexationStatusEnum.PUBLISHED);
}

@Test
public void test_fromDto_withEmptyStrings_clearsStringFields() throws Exception {
    // Arrange
    Indexation entity = new Indexation();
    entity.setCode("ORIGINAL_CODE");
    entity.setDescription("Original description");

    // IMPORTANT: Do not test clearing code field - it's immutable after entity creation
    IndexationDto dto = ImmutableIndexationDto.builder()
            .description("")
            .build();

    // Act
    indexationApi.fromDto(dto, entity);

    // Assert - empty strings should clear description field, code remains unchanged
    assertThat(entity.getCode()).isEqualTo("ORIGINAL_CODE");
    assertThat(entity.getDescription()).isNull();
}
```

**CRITICAL: Code Field Testing Rules**
- **DO NOT test clearing code field with empty strings** - code is immutable after entity creation
- Only test description and other mutable string fields for empty string clearing
- Code field changes should only be tested in create operations, not in update operations

### Testing Inherited CRUD Methods

**CRITICAL: Test all inherited methods from BaseCrudApi:**

- `find(String code)` - with valid, missing, and non-existent code
- `find(Long id)` - with valid, null, and non-existent ID
- `list()` - with results and no results
- `remove(String code)` - with valid, missing, and non-existent code
- `remove(Long id)` - with valid, null, and non-existent ID
- `createOrUpdate()` - if applicable
- `enableOrDisable()` - if applicable

### Testing Custom Operations

Test all custom business operations: Valid scenarios, missing parameters, non-existent entities, business rule violations

### DTO Nested Resource Access

When DTOs have nested Resource objects, use correct access pattern:

```java
// Correct - accessing nested resource field
assertThat(result.getIndexation().getCode()).isEqualTo("CPI_2024");

// Incorrect - trying to access non-existent flat field
assertThat(result.getIndexationCode()).isEqualTo("CPI_2024"); // Method doesn't exist!
```

## Verification

- Use `verify(mock, times(n))` to check number of invocations
- For varargs methods, use `ArgumentCaptor` and `getAllValues()`:

     ```
     // For varargs methods like: void method(String arg1, Object... varargs)
     ArgumentCaptor<Object> varargCaptor = ArgumentCaptor.forClass(Object.class);
     verify(mock).method(eq("expectedArg1"), varargCaptor.capture());

     // Get all captured varargs as a List
     List<Object> capturedVarargs = varargCaptor.getAllValues();

     // Verify individual vararg elements
     assertThat(capturedVarargs.size()).isEqualTo(expectedSize);
     assertThat(capturedVarargs.get(0)).isEqualTo(expectedFirstValue);
     assertThat(capturedVarargs.get(1)).isEqualTo(expectedSecondValue);

     ```

- For multiple invocations of varargs methods, use `getAllValues()` carefully:

     ```
     // If the method is called multiple times
     verify(mock, times(2)).method(any(), varargCaptor.capture());

     // getAllValues() returns all captured values across all invocations
     List<Object> allCapturedValues = varargCaptor.getAllValues();

     // To get values from specific invocations:
     // First invocation values
     Object[] firstInvocationArgs = (Object[]) allCapturedValues.get(0);

     // Second invocation values
     Object[] secondInvocationArgs = (Object[]) allCapturedValues.get(1);

     ```

- Capture arguments and compare its values
- For varargs, verify each argument separately


### Assertions

- Use AssertJ for Fluent Assertions
- Prefer `assertThat()` over traditional assertions
- Chain assertions for better readability
- Use appropriate matchers for different types
- Use `assertThatExceptionOfType(ExceptionType.class).isThrownBy(() -> { ... })` for exception testing
- Verify exception message when relevant

**Exception Testing Guidelines:**
- **Service layer tests**: Expect `ValidationException` for validation errors, `BusinessException` for other business logic errors
- **API layer tests**: Expect API-specific exceptions (`EntityDoesNotExistsException`, `MissingParameterException`, etc.)
- Always verify exception message contains relevant context (entity code, ID, field name)
  - Example: `.withMessageContaining("Invalid status transition").withMessageContaining("CPI_2024")`


## Example Test Structure

```java

@Test
public void test_methodName_scenario_expectedResult() {

    // Arrange
    // Set up test data and mocks

    // Act
    // Call the method being tested

    // Assert
    // Verify the expected outcome
}
```

# Integration test guidelines

## Authoring and Editing Generated / Large Collection Artifacts

Postman collections are large generated JSON artifacts. A few principles keep them correct and reviewable:

1. **Author against verified real endpoints and shapes — never invent.** Copy URLs, paths, and field names from a known-working request or from the actual route/DTO definitions. This is the same rule enforced in detail by **API Call Verification** below; treat inventing a URL or a field name as a defect, not a guess to be corrected later.

2. **Keep the collection consistently pretty-printed, and insert new content pretty-printed too — never a minified blob.** A Postman collection MUST stay one-field-per-line (`json.dumps(..., indent=2, ensure_ascii=False)`, which reproduces Postman's own export format). That is what makes it **diffable, mergeable, and line-countable** — a folder of 20+ requests collapsed onto a single line is impossible to review, impossible to merge, and defeats the AI-usage line metrics. When adding content, **serialize it with the same indentation as its neighbours and splice it in formatted**; do NOT insert a compact single-line `json.dumps(x)` blob even when doing byte-preserving surgery (that is exactly how an otherwise-formatted file ends up with unreviewable 50k-char lines). Byte-preserving splicing is still the right tool for *edits*; the constraint is that the spliced text is formatted. Re-serializing the **whole** file at the matching indent is acceptable when it reproduces the existing formatting — verify first that a load→dump of the base version is byte-identical to the base (so the only real diff is your addition). After editing, verify unrelated content is unchanged and nothing was duplicated:
   - Confirm request/item counts before vs after (only the delta you intended); confirm the set of request names *outside* your folder is unchanged.
   - Grep for the edited request's unique name/id to ensure exactly one occurrence (no accidental duplication from a copy-paste insert).
   - Confirm the file has no abnormally long lines (a quick "longest line length" check catches an accidental minified insertion).

3. **Respect the framework's assertion conventions for success vs expected-failure.** Follow how the harness marks negative tests so they are not auto-overridden into passes. In Opencell Postman collections this is the `" - fail"` naming rule (see **Error Scenario Tests**): a negative test's name must end in `" - fail"` and assert the specific error status; a name without it must assert success.

4. **Ensure data isolation and idempotency across repeated runs.** Shared environments accumulate state, so every run must use unique keys (the per-domain `iteration_nr` sequence) and fully tear down what it created. See **Test Data Variables**, **Per-folder data isolation**, and **Deletion Best Practices** below for the concrete patterns.

# Postman Collections

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

**CRITICAL: Set Basic Auth at collection level**

- **Authorization Type**: Basic Auth
- **Username**: `{{opencell.username}}`
- **Password**: `{{opencell.password}}`
- Configure at collection level so all requests inherit authentication

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
