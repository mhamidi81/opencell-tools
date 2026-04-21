# Opencell Project - Entity Development Guidelines

> **Note**: This document contains entity-specific guidelines. For general project guidelines, see [CLAUDE.md](./CLAUDE.md).

## Table of Contents
- [Base Classes](#base-classes)
- [Enum Classes](#enum-classes)
- [Entity Classes](#entity-classes)
- [Field Types](#field-types)
- [Default Values](#default-values)
- [Relationships](#relationships)

---

## Base Classes

Choose the appropriate base class based on entity requirements:

- **EnableBusinessCFEntity**: code, description, enable/disable, custom fields
- **AuditableCFEntity**: audit trail, custom fields (ID only, no code)
- **BaseEntity**: ID and version only

---

## Enum Classes

### Conventions

- Enum class names should end with `Enum` suffix (e.g., `IndexationStatusEnum`)
- Use UPPER_CASE for enum values
- Add Javadoc to describe each enum value's purpose
- Add getLabel method:

```java
public String getLabel() {
    return this.getClass().getSimpleName() + "." + this.name();
}
```

---

## Entity Classes

### Conventions

- **Table names**: lowercase_with_underscores (e.g., `cpq_indexation`)
- **Sequences**: Sequence name should follow pattern: `{table_name}_seq`
  - Add sequence generator to entity class:
  ```java
  @GenericGenerator(
      name = "ID_GENERATOR",
      type = SequenceStyleGenerator.class,
      parameters = {
          @Parameter(name = "sequence_name", value = "table_name_seq"),
          @Parameter(name = "increment_size", value = "1")
      }
  )
  ```
- **Unique serialVersionUID** (not `1L`)
- Do not make entities @Cacheable unless requested
- Include JPA annotations: `@Entity`, `@Table`, `@Column`
- **CRITICAL: Check actual `@Column` names in `@Embedded` classes** (e.g., `DatePeriod` uses `start_date/end_date`)

---

## Field Types

### Type Mappings

- **@Type is not valid in Java v21** - use alternatives below
- **JSON**: `@JdbcTypeCode(SqlTypes.JSON)`, `columnDefinition = "jsonb"`
- **Boolean**: `@Convert(converter = NumericBooleanConverter.class)`
- **Money**: `BigDecimal` with `NB_PRECISION` and `NB_DECIMALS`
  - These constants are already defined in BaseEntity, do not redeclare them
- **Enums**: `@Enumerated(EnumType.STRING)`
- **Multilingual**: `Map<String, String>` with JSON type
- **Map fields**: Use JSON type instead of a separate table

### Primitives vs Objects

**Use boolean primitive** when you clearly have only two values with no "undecided" option:

```java
// ✅ CORRECT - Only true or false, no middle ground
private boolean isVirtual;
private boolean enabled;
```

**Rule of thumb for entities:**
- Use boolean primitive when field has clear true/false semantics
- Use Boolean wrapper only when null has specific business meaning (e.g., "not yet decided")
- For method parameters, use boolean primitive when you clearly have only two options

### Validation Annotations

Use validation annotations where appropriate:
- `@NotNull` - for required fields
- `@Size` - for string length constraints
- Other Jakarta validation annotations as needed

### Embedded Fields

**CRITICAL: For `@Embedded` fields, always check the actual `@Column` names in the embeddable class**

Do not assume column names match field names.

**Example:**
```java
// DatePeriod embeddable class uses:
@Column(name = "start_date")  // NOT "from"
private Date from;

@Column(name = "end_date")    // NOT "to"
private Date to;
```

---

## Default Values

Set default values directly in the entity model using field initializers for simple, static defaults. Use service layer for complex defaults requiring business logic or user context.

### Model Layer (Entity)

Use for simple, static defaults:

```java
@Entity
public class IndexationBatch extends AuditableCFEntity {
    @Enumerated(EnumType.STRING)
    @NotNull
    private IndexationBatchStatusEnum status = IndexationBatchStatusEnum.DRAFT;

    private Date scheduledExecutionDate = new Date();

    private boolean enabled = true;

    private int priority = 0;

    private List<Child> children = new ArrayList<>();
}
```

### Service Layer (create method)

Use for complex defaults requiring:
- User context: `"Created by " + currentUser.getUserName()`
- Dependent field values: `appliedFactor = computedFactor`
- External lookups or calculations
- Business logic evaluation

```java
@Override
public void create(IndexationBatch batch) throws BusinessException {
    // Set description default that requires user context
    if (StringUtils.isBlank(batch.getDescription())) {
        batch.setDescription("Created by " + currentUser.getUserName() + " on " + new Date());
    }
    super.create(batch);
}
```

### Important Notes

- Model defaults are set during object construction
- Service defaults are set during persistence
- Model defaults take precedence (service only fills if null)
- Use model defaults when possible for cleaner code

---

## Relationships

### JPA Entity Relationships

When implementing JPA entity relationships (`@OneToMany`, `@OneToOne`, `@ManyToOne`):

**Fetch Strategy:**
- **ALWAYS specify `fetch = FetchType.LAZY` explicitly** unless related entities are absolutely necessary to be fetched together with main data
- Use `orphanRemoval = true` for parent-child relationships
- **Note:** In `@ManyToOne` and `@OneToOne`, eager fetching is the default - always override with LAZY
- **Note:** In `@OneToMany`, lazy loading is the default

```java
// ✅ CORRECT - Explicit LAZY fetching
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

// ❌ WRONG - Default is EAGER for @ManyToOne
@ManyToOne
private Customer customer; // Will eagerly fetch customer!
```

**Cascade Types:**
- **Prioritize CascadeType.REMOVE**: For parent-child relationships where deleting the parent must also delete its children
- **CRITICAL: Avoid CascadeType.ALL**: Can cause unintended side effects by cascading every operation. Use only when explicitly asked.
- **Use other types explicitly**: Only add other CascadeType values (like PERSIST or MERGE) if the business logic explicitly requires cascading those specific operations

**Caching:**
- Make associations of entities Cacheable only if entity is Cacheable

**Example:**

```java
@OneToMany(
    mappedBy = "parent",
    cascade = CascadeType.REMOVE,
    fetch = FetchType.LAZY,
    orphanRemoval = true
)
private List<Child> children;
```

### @OneToMany Performance Considerations

**CRITICAL: @OneToMany access leads to additional DB lookups unless fetched together**

Accessing `@OneToMany` collections triggers additional database queries:

```java
// ❌ WRONG - Will trigger additional query
List<CustomerAccount> accounts = customer.getCustomerAccounts();
```

**Unless fetched together with the main data:**

```java
// ✅ CORRECT - Single query with join fetch
SELECT c FROM Customer c JOIN FETCH c.customerAccounts WHERE c.id = :id
```

**For large related entity sets:**
- **Don't use @OneToMany** - it might retrieve more data than needed
- **Use custom queries** with filtering and paging in the database
- This allows you to filter in DB before loading into memory

```java
// ✅ CORRECT - Filter in database, not in memory
List<CustomerAccount> activeAccounts = customerAccountService
    .findByCustomerAndStatus(customerId, Status.ACTIVE, pageable);

// ❌ WRONG - Load all, then filter in memory
List<CustomerAccount> allAccounts = customer.getCustomerAccounts();
List<CustomerAccount> activeAccounts = allAccounts.stream()
    .filter(a -> a.getStatus() == Status.ACTIVE)
    .collect(Collectors.toList());
```

---

## Documentation

- Add Javadoc documentation to all entity classes
- For setter and getter methods, use field description in Javadoc
- Document business rules and constraints
- Include examples for complex field types (JSON, multilingual)
