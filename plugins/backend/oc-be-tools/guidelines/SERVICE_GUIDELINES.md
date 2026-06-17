# Opencell Project - Service Layer Guidelines

> **Note**: This document contains service layer guidelines. For general project guidelines, see [CLAUDE.md](./CLAUDE.md).

## Table of Contents
- [Service Conventions](#service-conventions)
- [Business Rules Implementation](#business-rules-implementation)
- [Validation Method Placement](#validation-method-placement)
- [Exception Handling](#exception-handling)
- [Application Configuration](#application-configuration)
- [Concurrency](#concurrency)
- [Performance Considerations](#performance-considerations)

---

## Service Conventions

### Basic Structure

1. **Extends**: Service classes should extend `BusinessService<EntityType>` or `PersistenceService<EntityType>`
2. **Annotations**: Use `@Stateless` for EJB services
3. **Injection**: Use `@Inject` for dependency injection
4. **Transactions**: Methods are transactional by default; use `@TransactionAttribute` only to override

### Exception Guidelines

**CRITICAL - Service layer must throw `BusinessException` or its subclasses only**

Never throw API layer exceptions like `BusinessApiException`, `MeveoApiException`, or `EntityDoesNotExistsException` from service classes.

**Use these exception types:**
- **`ValidationException`**: For validation errors (invalid status transitions, constraint violations, invalid field values)
- **`BusinessException`**: For other business logic errors (entity not found internally, state conflicts)
- Note: `ValidationException` extends `BusinessException`, so both are acceptable service layer exceptions

---

## Business Rules Implementation

### Field Value Comparison - API Layer vs Service Layer

**API Layer** - Use when comparing field values to decide IF or WHAT to update:
- "Only update description if it changed"
- "Don't allow change to this field if status is X"
- "Prevent update if no actual changes detected"

**Service Layer** - Use when comparing field values to handle side effects or maintain referential integrity:
- "When formula changes, update lifecycle status of old and new formulas"
- "When parent entity changes, update children accordingly"
- "When relationship is removed, clean up orphaned references"

### Pattern for Detecting Field Changes

**CRITICAL: Use `isFieldDirty()` from `PersistenceService` to detect field changes**

The `PersistenceService` base class provides `isFieldDirty(IEntity entity, String fieldName)` which compares the entity's current in-memory value against Hibernate's loaded state snapshot (the original DB value stored in the persistence context). No extra DB query needed.

```java
@Override
public Indexation update(Indexation entity) throws BusinessException {
    // Simple dirty check — no DB query needed
    if (entity.getStatus() != IndexationStatusEnum.DRAFT && isFieldDirty(entity, "code")) {
        throw new InvalidParameterException(
            "Indexation code can only be modified in DRAFT status",
            "indexation.code.editableOnlyInDraft"
        );
    }
    return super.update(entity);
}
```

**Why use `isFieldDirty()`:**
- No extra DB query — uses Hibernate persistence context snapshot
- Available in all services extending `PersistenceService`
- Easy to mock in unit tests: `doReturn(true).when(service).isFieldDirty(entity, "fieldName")`

### Retrieving the Original Field Value

When you need the **actual old value** (not just whether it changed), use `getOldFieldValue()` from `PersistenceService`. It returns the original DB-loaded value from Hibernate's persistence context snapshot.

```java
@Override
public Indexation update(Indexation entity) throws BusinessException {
    if (isFieldDirty(entity, "status")) {
        IndexationStatusEnum oldStatus = getOldFieldValue(entity, "status");
        validateStatusTransition(entity.getCode(), oldStatus, entity.getStatus());
    }
    return super.update(entity);
}
```

**Notes:**
- Returns `null` if the entity is not managed (detached) or has no loaded state
- Uses generic return type — no casting needed: `String oldCode = getOldFieldValue(entity, "code")`
- Easy to mock in unit tests: `doReturn("OLD_CODE").when(service).getOldFieldValue(entity, "code")`

---

## Validation Method Placement

**CRITICAL: Place validation methods in the service that owns the business rule**

- If `ContractItem` has a rule about which formulas it can use → validation goes in `ContractItemService`
- If `IndexationFormula` has a rule about its own status transitions → validation goes in `IndexationFormulaService`
- Don't put ContractItem-specific validation in IndexationFormulaService

### Example - Correct Placement

```java
// ✅ CORRECT - In ContractItemService
public void validateFormulaStatusForContractItem(IndexationFormula formula) throws ValidationException {
    if (formula != null &&
        formula.getStatus() != IndexationFormulaStatusEnum.PUBLISHED &&
        formula.getStatus() != IndexationFormulaStatusEnum.IN_USE) {
        throw new ValidationException(
            "Contract item can only reference formula in status PUBLISHED or IN_USE. " +
            "Formula '" + formula.getCode() + "' has status " + formula.getStatus()
        );
    }
}

// ✅ CORRECT - In IndexationFormulaService
public void validateStatusTransition(String code, IndexationFormulaStatusEnum current,
                                     IndexationFormulaStatusEnum newStatus) throws ValidationException {
    // Validates formula's own status transition rules
}
```

### Example - Incorrect Placement

```java
// ❌ WRONG - Contract-specific validation in IndexationFormulaService
// This creates coupling and unclear responsibility
public void validateFormulaStatusForContractItem(IndexationFormula formula) {
    // Don't put this in IndexationFormulaService!
}
```

---

## Exception Handling

### General Business Rule Guidelines

- Implement state transition validation logic in service class. It can be used from both service and API layer.
- Validate state transitions before applying
- Return meaningful error messages with proper exception types

**CRITICAL: All exception messages MUST include context information (entity code or ID)** to help identify which entity caused the error:
- **Good**: `"Cannot delete indexation '" + indexation.getCode() + "' with status IN_USE"`
- **Bad**: `"Cannot delete indexation with status IN_USE"`

**CRITICAL: Validation methods that are called from API layer should receive primitive parameters (code, ID) instead of entity objects** to avoid unnecessary entity loading:
- **Good**: `validateStatusTransition(String code, Status current, Status new)`
- **Bad**: `validateStatusTransition(Entity entity, Status current, Status new)`

**CRITICAL: Validation methods that validate related entities/collections should receive parent entity identifier for error context**:
- When validating child entities or components, include parent entity code/ID as parameter
- Error messages must include BOTH parent and child entity identifiers
- **Good**: `validateIndexations(String formulaCode, Set<Component> components)`
  - Error: `"Formula 'FORM_001' uses disabled indexation 'IDX_002'"`
- **Bad**: `validateIndexations(Set<Component> components)`
  - Error: `"Indexation is disabled"` (no context about which formula or which indexation)

**CRITICAL: Service methods that call `update()` must return the updated entity**:
- Change return type from `void` to entity type
- Return the result of `update()` call: `return update(entity);`
- For conditional updates, return the entity even if not updated

### Message Keys in Exceptions

**CRITICAL: ValidationException must use message keys resolved from `messages_en.properties` / `messages_fr.properties`**

Use the constructor with message key and parameters so the API layer can resolve localized messages automatically via `ExceptionSerializer`:

```java
throw new ValidationException(
    "Indexation batch [id=" + batch.getId() + "] is not in DRAFT status",
    "indexationBatch.importCandidates.notInDraft",
    String.valueOf(batch.getId()), batch.getStatus().name());
```

- **Message keys** use dot-separated naming: `{entity}.{operation}.{outcome}` (e.g., `indexationBatch.importCandidates.notInDraft`)
- **Parameters** use `{0}`, `{1}`, etc. in the properties files
- **Both EN and FR** translations must be added:
  - `opencell-admin/web/src/main/resources/messages_en.properties`
  - `opencell-admin/web/src/main/resources/messages_fr.properties`
- **French strings** must escape single quotes as `''` and use `\uXXXX` for accented characters

### Business Rule Implementation

- Implement all business rules from requirements explicitly in service methods
- Create dedicated methods for complex business operations (e.g., `close()`, `publish()`, `markAsInUse()`)
- Keep business logic in service layer, not scattered across API and REST layers

---

## Logging Standards

- Use SLF4J for logging: `@Slf4j` annotation or `private static final Logger log = LoggerFactory.getLogger(ClassName.class)`
- **Log levels**:
  - **ERROR**: Exceptions and critical failures
  - **WARN**: Recoverable issues or deprecated usage
  - **INFO**: Important business events (entity created, status changed)
  - **DEBUG**: Detailed flow information
  - **TRACE**: Very detailed diagnostic information
- Include context in log messages (entity ID, code)
- Don't log sensitive data (passwords, tokens, PII)
- Use parameterized logging: `log.info("Processing entity: {}", entityCode)`

---

## Application Configuration

### ParamBean Configuration Lookups

**CRITICAL: Don't lookup configuration values inside loops**

ParamBean reads application configuration values from `opencell-admin.properties` file.

```java
// ❌ WRONG - Lookup inside loop (performance issue)
for (Item item : items) {
    boolean useCache = Boolean.parseBoolean(paramBean.getProperty("cache.enabled", "true"));
    processItem(item, useCache);
}

// ✅ CORRECT - Lookup outside loop
boolean useCache = Boolean.parseBoolean(paramBean.getProperty("cache.enabled", "true"));
for (Item item : items) {
    processItem(item, useCache);
}
```

**Pass configuration value to other methods that are called from the loop.**

### Static Configuration Loading

For parameters that are unlikely to change or require a server restart, load them as a static EJB constructor:

```java
private static boolean usePrepaidBalanceCache = true;

static {
    ParamBean tmpParamBean = ParamBeanFactory.getAppScopeInstance();
    usePrepaidBalanceCache = Boolean.parseBoolean(tmpParamBean.getProperty("cache.cachePrepaidBalance", "true"));
}
```

**Use this pattern only for:**
- Configuration that never changes at runtime
- Configuration that requires server restart to take effect
- Frequently accessed configuration values

---

## Concurrency

### @Synchronized on Stateless/Stateful Beans

**@Synchronized on a method in a stateless/stateful bean has no use** as every thread will have its own instance of a bean.

```java
// ❌ WRONG - No effect on stateless beans
@Stateless
public class MyService {
    public synchronized void processData() {
        // Each thread gets own instance, so no synchronization!
    }
}
```

### Use @ConcurrencyLock Annotation

Use `@ConcurrencyLock` annotation on a method to make it accessible in a synchronized fashion:

```java
@ConcurrencyLock
public void createCounterPeriodIfMissing(CounterInstance counterInstance, Date date,
                                         Date initDate, ChargeInstance chargeInstance)
                                         throws CounterInstantiationException {
    methodCallingUtils.callMethodInNewTx(() ->
        createCounterPeriodIfMissing_noLock(counterInstance, date, initDate, chargeInstance));
}
```

**Note:** This still does not solve the cluster situation.

### Don't Mix @ConcurrencyLock and TX=REQUIRES_NEW

Don't mix `@ConcurrencyLock` and `TX=REQUIRES_NEW` annotations on same method, as Transaction interceptor is the last to run and any changes made while others wait for synchronized call to finish won't be visible by the next thread when it gets access to the method.

**Solution:** Call method in new TX from inside the concurrency locked method (as shown in example above).

---

## Performance Considerations

### Size of Data

**Always ask specification author for number of items and their size to process.**

This has an impact on:
- Memory footprint
- DB queries
- Usability
- File size

**Consider typical numbers:**
- Number of Customers: 200K
- Number of Billing accounts per Customer: 1K
- Number of subscriptions per Billing account: 1K
- Number of Rated transactions per Billing account per invoice: 15M
- Total number of Subscriptions: 2M
- Total number of Rated transactions per invoice: 70M

### Memory Considerations

Looping over hundreds of thousands of items is very quick. However, whatever you loop over has to be:
- Retrieved from the database/file
- Loaded into memory

**Consider:**
- How many items the list contains
- What their combined size is
- What is the size of what is being produced

**Best practices:**
- Consider doing filtering in DB instead of looping in code
- Use scrollable resultsets to retrieve and process a page of data at a time
- Don't load all data into memory at once

### DB Query Optimization

#### Limit Retrieved Items

Limit the number of items retrieved to minimize memory footprint.

```java
// Use scrollable resultsets for large datasets
StatelessSession statelessSession = emWrapper.getEntityManager()
    .unwrap(Session.class)
    .getSessionFactory()
    .openStatelessSession();

ScrollableResults scrollableResults = statelessSession
    .createNamedQuery("WalletOperation.listConvertToRTs")
    .setParameter("maxId", maxId)
    .setReadOnly(true)
    .setCacheable(false)
    .setMaxResults(processNrInJobRun)
    .setFetchSize(fetchSize)
    .scroll(ScrollMode.FORWARD_ONLY);
```

#### Query Performance Verification

- **Verify query performance** via EXPLAIN (in PostgreSQL)
- **Adjust indexes as needed**
- Don't abuse indexes - inserting/updating/deleting requires index and FK update/check
- Check what indexes exist already

#### Case-Insensitive Search

`PersistenceService.list()` with `PaginationConfiguration` uses case-insensitive search for String type fields. Behind the scenes it applies `lower(dbField)` function.

**Use `lower(dbField)` in custom queries to use existing index:**

```sql
SELECT e FROM Entity e WHERE lower(e.name) = lower(:searchName)
```

#### Query Optimization Patterns

**Use queries with parameters** (more efficient than dynamically built queries):

```sql
SELECT r FROM RatedTransaction r WHERE r.billingAccount.id=:billingAccountId
```

**Use named queries when possible** - validated at application startup:

```java
@NamedQuery(name = "Entity.findByCode", query = "SELECT e FROM Entity e WHERE e.code = :code")
```

**Use lowercase for case-insensitive search:**

```sql
SELECT e FROM Entity e WHERE lower(e.code) = lower(:code)
```

#### Query Hints

**readOnly hint** - Skip dirty checking for entities you don't plan to modify:

```java
getEntityManager()
    .createNamedQuery("WalletOperation.getOpenByWallet", WalletOperation.class)
    .setHint("org.hibernate.readOnly", true)
```

**cacheable hint** - Cache frequently used query results:

```java
@NamedQuery(name = "SecuredEntity.listByUserName",
            query = "SELECT s FROM SecuredEntity s WHERE lower(s.userName)=:userName",
            hints = {@QueryHint(name = "org.hibernate.cacheable", value = "TRUE")})
```

### Write vs Update Performance

**Write to DB is fast, update is slow.**

```java
// ❌ WRONG - Insert then immediately update
Customer customer = new Customer();
customer.setCode("test");
customerService.create(customer);
customer.setDescription("test customer"); // Update triggered

// ✅ CORRECT - Set all values before create
Customer customer = new Customer();
customer.setCode("test");
customer.setDescription("test customer");
customerService.create(customer); // Single write
```

**For massive updates:** Instead of passing update parameters, use an intermediate table. Insert data to update into intermediate table, then do update with join:

```sql
UPDATE {h-schema}billing_rated_transaction rt
SET status='BILLED',
    updated=now(),
    aggregate_id_f=pending.aggregate_id_f,
    billing_run_id=pending.billing_run_id,
    invoice_id=pending.invoice_id
FROM {h-schema}billing_rated_transaction_pending pending
WHERE status='OPEN' AND rt.id=pending.id
```

### JPA Entity Traversing

**JPA hides any interaction with DB from the developer.** With `@ManyToOne` and `@OneToMany` relationships, related entities can be accessed without explicitly thinking about database queries.

**Enable SQL logging or check in Glowroot** to see what queries are being executed.

#### Detect 1+N Query Pattern

If you see a 1+N type of data fetching (e.g., customer list with their customer accounts), change to fetch related records as part of the main query:

```java
// ❌ WRONG - 1+N queries (one for customers, N for accounts)
List<Customer> customers = customerService.list();
for (Customer customer : customers) {
    List<CustomerAccount> accounts = customer.getCustomerAccounts(); // N queries!
}

// ✅ CORRECT - Single query with join fetch
SELECT c FROM Customer c JOIN FETCH c.customerAccounts
```

#### @OneToMany Performance

**Preferably do not access data via `@OneToMany` relationship.** It might retrieve more data than you need and you will end up filtering it anyway.

For large sets of related data, use a query with filtering and paging:

```java
// ❌ WRONG - Loads all related entities
List<CustomerAccount> allAccounts = customer.getCustomerAccounts();
List<CustomerAccount> activeAccounts = allAccounts.stream()
    .filter(a -> a.getStatus() == Status.ACTIVE)
    .collect(Collectors.toList());

// ✅ CORRECT - Filter in database
List<CustomerAccount> activeAccounts = customerAccountService
    .findByCustomerAndStatus(customer.getId(), Status.ACTIVE);
```

### File Size Considerations

**Ask:** What is a maximum file size, or number of lines to process?

**Consider:**
- Can you load it all or must process one line at a time?
- Same question when writing it out
- XML file processing/creation:
  - **DOM parser/writer**: Keeps all document in memory
  - **SAX parser**: Works with events, much smaller memory footprint
- Flush file writers periodically

### Partitioning

For large datasets, consider using partition by some interesting field. When status change is important, consider using partitions by status.

**Example:** WalletOperation has partition for status OPEN and another one for the remaining statuses.

### Archiving

For very large datasets, data can be archived periodically to reduce the set of data to a manageable size.
