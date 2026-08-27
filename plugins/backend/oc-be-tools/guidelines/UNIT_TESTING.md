# Opencell Project - Unit Testing Guidelines

> **Note**: This document contains **unit-testing** guidelines for the Opencell project. For **Postman / integration-testing** guidelines, see [POSTMAN_TESTING.md](./POSTMAN_TESTING.md). For general development guidelines (entities, services, API, etc.), see [CLAUDE.md](./CLAUDE.md).

> **Development Environment**: See **[DEVELOPMENT_SETUP.md](./DEVELOPMENT_SETUP.md)** for Java/Maven execution commands on this machine.

This guide covers:
- Unit test patterns and best practices
- Service layer testing with EntityManager mocking
- API layer testing with ArgumentCaptor

---

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

