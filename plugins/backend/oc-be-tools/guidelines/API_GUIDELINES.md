# Opencell Project - API Development Guidelines

> **Note**: This document contains API, REST, and DTO guidelines. For general project guidelines, see [CLAUDE.md](./CLAUDE.md).

## Table of Contents
- [Scope Annotations](#scope-annotations)
- [REST API Guidelines](#rest-api-guidelines)
- [DTO Guidelines](#dto-guidelines)
- [API Implementation](#api-implementation)
- [Mapper Methods](#mapper-methods)
- [Documentation](#documentation)

---

## Scope Annotations

**CRITICAL: Use correct scope annotations for each layer:**

- **REST resource implementation classes** (implementing JAX-RS interfaces) → `@RequestScoped`
  - Example: `IndexationResourceImpl`, `IndexationValueResourceImpl`
- **API classes** (service layer extending `BaseCrudApi` or similar) → `@Stateless`
  - Example: `IndexationApi`, `IndexationValueApi`

---

## REST API Guidelines

### REST API Specification Verification

**CRITICAL: Always verify exact API specifications from requirements/Jira tickets before implementing REST endpoints**

Before implementing any REST API:

1. **Check requirements/Jira ticket** for exact URL specifications
2. **Verify all API details**:
   - Base path and resource paths (e.g., `/v2/indexation/batches` not `/v2/cpq/indexationBatches`)
   - Parameter types (`{id}` vs `{code}`)
   - Resource naming (`/priceIndexations` not `/lines`)
   - Action endpoint names (`/validate` vs `/validation`)
   - HTTP methods (POST, PUT, GET, DELETE)
3. **Don't assume URL patterns** based on conventions alone - specifications take precedence
4. **Document deviation reasons** if you must deviate from ticket specifications

**Example of specification-following errors:**
- ❌ Assumed: `/v2/cpq/indexationBatches/{code}` based on conventions
- ✅ Specified: `/v2/indexation/batches/{id}` in Jira ticket

**The ticket specification always takes precedence over general patterns.**

### Postman Collection URL Verification

**CRITICAL: When creating or updating Postman collection tests, always verify URLs against the actual `@Path` annotations in the REST resource interfaces.**

Never guess or assume API URLs. Before writing any Postman request:

1. **Read the REST resource interface** to get the exact `@Path` value
2. **Check parameter types** — some endpoints use `{id}`, others use `{code}`. Read the `@PathParam` annotations
3. **Check HTTP methods** — action endpoints may use `@POST` not `@PUT`
4. **Check action paths** — publish/close may use `{code}` not `{id}`

### REST Endpoint Naming

- Use nouns, not verbs for resources
- Use plural forms for collection resources
- Follow the pattern: `/v2/{domain}/{resource}`
  - **GOOD**: `/v2/catalog/priceManagement/priceUpdates`
  - **BAD**: `/v2/catalog/getPriceUpdate`

### Standard CRUD Operations

Implement standard operations with consistent naming:

1. **Create**: `POST /v2/{domain}/{resource}`
2. **Read**: `GET /v2/{domain}/{resource}/{id}`
3. **Update**: `PUT /v2/{domain}/{resource}/{id}`
4. **Delete**: `DELETE /v2/{domain}/{resource}/{id}`
5. **List**: `GET /v2/{domain}/{resource}`
6. **CreateOrUpdate**: `POST /v2/{domain}/{resource}/createOrUpdate`

### Custom Operations

- Use descriptive endpoint names:
- **Status changes**: `POST /v2/{domain}/{resource}/{id}/close`, `/publish`, `/enable`, `/disable`
- **Actions**: `POST /v2/{domain}/{resource}/{id}/{action}`

### REST Endpoint Response

- All endpoints return `jakarta.ws.rs.core.Response`
- Set HTTP response status when applicable

**HTTP Status Codes:**
- **201 Created**: For successful POST create operations
- **200 OK**: For successful GET, PUT operations and custom operations that return data
- **204 No Content**: For successful DELETE, enable, disable operations and other void operations that don't return data
- **400 Bad Request**: For validation errors, invalid parameters
- **404 Not Found**: When requested entity does not exist
- **409 Conflict**: When operation conflicts with current state

**CRITICAL**: Match HTTP response codes with API method return types:
- Methods returning DTO/data → use 200 OK (or 201 Created for POST)
- Methods returning void → use 204 No Content

### Hypermedia Links and Response Building (v3)

**CRITICAL: v3 REST resources extend `org.meveo.apiv3.base.RestResource<R>` and build every response through its helpers — do not assemble `Response` with ad-hoc `Response.ok(...)`/`Response.created(...)` calls in the endpoint.**

`RestResource<R extends Resource>` centralises ETag/Cache-Control handling, the entity→URL construction, and HATEOAS link attachment. The concrete resource only implements `copyWithLinks(R dto, Link... links)` (because the Immutables-generated `copyOf`/`withLinks` live on the concrete immutable type, e.g. `ImmutableInvoiceDto`, and cannot be reached through a generic type parameter):

```java
@Override
protected InvoiceDto copyWithLinks(InvoiceDto dto, Link... links) {
    return ImmutableInvoiceDto.copyOf(dto).withLinks(links);
}
```

**Two complementary link layers** — every write endpoint expresses the affected resource both ways:

| Layer | Built by | Goes to | Purpose |
|---|---|---|---|
| `Location` header | `LinkGenerator.getUriBuilderFromResource(this.getClass(), id)` | HTTP header | Canonical URL of the affected resource |
| Body `links[]` | `toResourceWithLink(dto)` → `copyWithLinks` → `SelfLinkGenerator` | inside the DTO | `self` link + allowed actions |

**Use the matching base helper for each operation:**

| Operation | Helper | Status | Body | Location header |
|---|---|---|---|---|
| Read one | `buildGetResponse(request, dto)` | 200 | self-linked DTO | — |
| Read list | `buildSearchResponse(request, genericSearchResponse)` | 200 | each item self-linked + pagination links on the wrapper | — |
| Create | `buildCreatedResponse(dto)` | 201 | self-linked DTO | ✓ |
| Mutate (update/validate/reject/rebuild/cancel/setRate…) | `buildUpdatedResponse(dto)` | 200 | self-linked DTO | ✓ |
| Deferred mutation (recalculate) | `buildAcceptedResponse(dto)` | 202 | self-linked DTO | ✓ |

**CRITICAL: Action endpoints must return the updated, self-linked resource — not an empty body.** The action's API-service method must **return the updated DTO** (it already holds the loaded, mutated entity — convert it with `toDto(...)`); do NOT leave the service method `void` and re-read the entity in the resource (that causes a wasteful second DB load):

```java
// API service — return the DTO from the already-loaded entity (no re-fetch)
public InvoiceDto validate(Long id) {
    Invoice invoice = findInvoiceEligibleToUpdate(id);
    invoiceService.validateInvoice(invoice, true);
    return toDto(invoice, entityToDtoConverter.getCustomFieldsDTO(invoice, CustomFieldInheritanceEnum.INHERIT_NO_MERGE));
}

// REST resource — pass the returned DTO straight to the helper
public Response validate(@PathParam("id") Long id) {
    return buildUpdatedResponse(invoiceApiService.validate(id));   // 200 + Location + self-linked invoice
}
```

```java
// ❌ WRONG — void service method forces the resource to re-load the entity
public void validate(Long id) { ... }                       // discards the entity it just updated
return buildUpdatedResponse(invoiceApiService.find(id));    // second DB load
```

This works because the on-entity service operations run in the caller's transaction, so the managed entity reflects the change in memory — `toDto(invoice, ...)` is correct without a refresh. (If an operation instead commits in a separate `@TransactionAttribute(REQUIRES_NEW)` transaction, refresh the entity before converting.)

**Do NOT put the resource URL in the response body** (e.g. `Response.ok(uri)` / `Response.accepted(uri)`). The URL belongs in the `Location` header (set by the helpers); the body is always the self-linked DTO.

**Exceptions** — endpoints whose result is operation-specific data rather than the resource keep returning that data as-is (do not force them through the helpers): bulk filter operations (`*ByFilter`), `sendByEmail` (sent flag), `refreshRate` (status message), `generate` (generation results), file/PDF downloads.

**Paginated list links:** `GenericSearchResponse<T>` exposes a `links` field; `buildSearchResponse` self-links each item and attaches `next`/`previous` pagination links (built from the response's `paging` offset/limit/total) on the wrapper.

### Error Handling

#### Exception Types

- `ValidationException`: For validation errors in service layer (invalid status transitions, constraint violations, invalid field values, overlapping periods)
- `BusinessException`: For other business logic errors (general business rule violations, state conflicts)
- `EntityDoesNotExistException`: When entity not found (API layer)
- `EntityAlreadyExistsException`: When entity is not expected, but was found (API layer)
- `InvalidParameterException`: For missing or invalid parameters (API layer)
- `MissingParameterException`: For missing required parameters (API layer)

#### REST Resource Implementation Exception Handling

**CRITICAL: Do NOT catch exceptions in REST resource methods**

REST resource methods must **not** use try-catch blocks. Let exceptions propagate to the global JAX-RS `ExceptionMapper` providers registered in `JaxRsActivatorApiV2`, which automatically map exceptions to correct HTTP status codes and JSON error responses:

| Exception | ExceptionMapper | HTTP Status |
|---|---|---|
| `EntityDoesNotExistsException` | `EntityDoesNotExistsExceptionMapper` | 404 Not Found |
| `BusinessException` | `BusinessExceptionMapper` | 400 Bad Request |
| `ValidationException` | `ValidationExceptionMapper` | 400 Bad Request |
| `MeveoApiException` | `MeveoExceptionMapper` | 400 Bad Request |
| `InvalidParameterException` | `MeveoExceptionMapper` | 400 Bad Request |
| Unhandled exceptions | `UnhandledExceptionMapper` | 500 Internal Server Error |

```java
// ✅ CORRECT - No try-catch, let exceptions propagate to ExceptionMapper
public Response create(EntityDto dto) {
    EntityDto result = apiService.create(dto);
    return Response.status(Response.Status.CREATED).entity(result).build();
}

public Response findById(Long id) {
    EntityDto result = apiService.find(id);
    return Response.ok(result).build();
}
```

```java
// ❌ WRONG - Do NOT catch exceptions in REST resource methods
public Response create(EntityDto dto) {
    try {
        EntityDto result = apiService.create(dto);
        return Response.status(Response.Status.CREATED).entity(result).build();
    } catch (MeveoApiException | BusinessException e) {
        return Response.status(Response.Status.BAD_REQUEST).entity(e.getMessage()).build();
    }
}
```

**Important:**
- Do NOT add try-catch blocks in REST resource methods
- Do NOT add logging in resource implementations (interceptors handle it)
- Keep resource implementations thin - delegate all logic to API service layer
- Input validation that throws exceptions (e.g., `throw new InvalidParameterException(...)`) is fine - that is throwing, not catching

#### REST Response Messages via Resource Bundle

**CRITICAL: User-facing messages in REST responses must be resolved from `messages_en.properties` / `messages_fr.properties`**

Inject `ResourceBundle` into the REST resource and use `getString()` with parameters:

```java
@Inject
private ResourceBundle resourceMessages;

String message = resourceMessages.getString("indexationBatch.importCandidates.success", linesAdded, id);
return Response.ok(message).build();
```

- Message keys use dot-separated naming: `{entity}.{operation}.{outcome}`
- Parameters use `{0}`, `{1}`, etc. in the properties files
- Both EN and FR translations must be added to:
  - `opencell-admin/web/src/main/resources/messages_en.properties`
  - `opencell-admin/web/src/main/resources/messages_fr.properties`

**CRITICAL: A message/label/config key is not "done" until code actually emits or references it.** Adding a key to `messages_en.properties`/`messages_fr.properties` (or a config property) is only half the work — if no Java (or `.xhtml`) code resolves and returns/logs/displays it, the requirement is **unmet**, not complete. A defined-but-unused key silently satisfies a keyword search while the behaviour it was meant to produce never happens.

- When a requirement says "an informational/error message is shown", wire the key into the code path that produces it (`resourceMessages.getString(key, ...)` returned in the `Response`, logged, or thrown via a `ValidationException` message key) — do not stop at defining the string.
- Verify by grepping for the key across `*.java` / `*.xhtml`, not just in the `.properties` files. Zero code references = incomplete.

#### REST Resource Update Pattern

**CRITICAL: For entities without code field (extending AuditableCFEntity), set ID from path parameter**

When the entity extends `AuditableCFEntity` (id only, no code field), the REST resource implementation must copy the DTO and set the id from the path parameter before passing it to the API service:

```java
public Response update(Long id, EntityDto dto) {
    // Copy DTO and set id from path parameter
    IndexationBatchDto dtoWithId = ImmutableIndexationBatchDto.copyOf(dto).withId(id);
    IndexationBatchDto result = apiService.update(dtoWithId);
    return Response.ok(result).build();
}
```

**Why this pattern:**
- API service `update()` method expects DTO with id populated
- REST endpoint receives id in path (`/v2/resource/{id}`) separately from body
- Must merge path parameter id into DTO before calling API service
- Use `.copyOf(dto).withId(id)` to create immutable DTO with id set

#### REST Resource Registration

**CRITICAL: Register all REST resource implementations in JaxRsActivatorApiV2**

- Add import for the resource implementation class
- Add the class to the resources set in the `getClasses()` method
- Location: `opencell-api/src/main/java/org/meveo/apiv2/JaxRsActivatorApiV2.java`

---

## DTO Guidelines

### DTO Class Conventions

- DTO class names should end with `Dto` suffix (Example: `CustomerDto`)
- Implement DTO classes as immutable `@Value.Immutable` extending `org.meveo.apiv2.models.Resource` interface
- Do not mark any fields in DTO as required even when the field is mandatory in entity model (same DTO is used in create and update API)
- Do not create DTO classes for embeddable entities
- Do not set default values for fields
- Use Boolean instead of boolean, Integer instead of integer, and Long instead of long as field types
- Use `@JsonInclude(JsonInclude.Include.NON_NULL)` to exclude null fields from JSON
- **Date fields must be annotated with `@JsonSerialize(using = CustomDateSerializer.class)`** to ensure consistent ISO 8601 format (yyyy-MM-dd'T'HH:mm:ssXXX) in JSON responses
- **CRITICAL: Verify DTO has all entity fields** - After creating a DTO, compare it against the entity to ensure all fields are represented (exclude only parent references that are part of URL path context)

### DTO Field Types

**Use wrapper types (Boolean, Integer, Long) instead of primitives in DTOs:**

This is critical because DTOs are used for both create and update operations, and wrapper types allow distinguishing between:
- `null` - Field not provided in request (don't update)
- `false`/`0` - Field provided with false/zero value (update to false/zero)

```java
// ✅ CORRECT - Wrapper allows null (not provided), true, or false
public interface EntityDto extends Resource {
    @Nullable Boolean getEnabled();
    @Nullable Integer getCount();
}

// ❌ WRONG - Primitive boolean can't represent "not provided"
public interface EntityDto extends Resource {
    boolean getEnabled(); // Always has a value (true or false)
}
```

### Resource Interface Fields

**CRITICAL: Do NOT redeclare `getId()` or `getCode()` in DTO interfaces**

- Resource interface already provides these methods
- Only declare entity-specific fields in the DTO
- **In mapper methods (toDto/fromDto), only map fields that actually exist in the entity**:
  - If entity extends **AuditableCFEntity**: It has NO code field - don't map code in toDto/fromDto
  - If entity extends **EnableBusinessCFEntity**: It HAS code field - map code normally
  - Always map `id` via `.id(entity.getId())` in toDto() - all entities have id

**Example:**

```java
// ✅ CORRECT - Entity extends AuditableCFEntity (no code field)
@Value.Immutable
public interface IndexationBatchDto extends Resource {
    // DON'T declare getId() or getCode() - inherited from Resource
    @Nullable String getDescription();
    // ... other entity-specific fields
}

// In toDto():
return ImmutableIndexationBatchDto.builder()
    .id(entity.getId())        // ✅ Always map id
    // DON'T map code - entity doesn't have it
    .description(entity.getDescription())
    .build();

// ✅ CORRECT - Entity extends EnableBusinessCFEntity (has code field)
@Value.Immutable
public interface IndexationDto extends Resource {
    // DON'T declare getId() or getCode() - inherited from Resource
    @Nullable String getDescription();
    // ... other entity-specific fields
}

// In toDto():
return ImmutableIndexationDto.builder()
    .id(entity.getId())        // ✅ Always map id
    .code(entity.getCode())    // ✅ Map code - entity has it
    .description(entity.getDescription())
    .build();
```

### Collections of References

**CRITICAL: Use Set of reference DTOs for one-to-many relationships, not collections of IDs or codes**

When a parent entity has a collection of child entities (e.g., Indexation has IndexationValues), represent this relationship in the DTO as a Set of minimal reference DTOs.

**DTO Declaration:**

```java
// ❌ WRONG: Using List of IDs
@Nullable
List<Long> getIndexationValueIds();

// ❌ WRONG: Using List of codes
@Nullable
List<String> getIndexationValueCodes();

// ✅ CORRECT: Using Set of reference DTOs
@Nullable
Set<IndexationValueDto> getIndexationValues();
```

**Reference DTO Content:**

Include only essential identifying and status fields in reference DTOs:
- **Always include**: `id` (required for lookups)
- **Include if available**: Key business fields like `code`, `status`, `value`, `name`
- **Exclude**: Large fields, nested collections, custom fields, descriptions

**Why Set instead of List:**
- Prevents duplicate references
- Order is typically not significant for reference collections
- Matches JPA `@OneToMany` relationship patterns

### DTO Validation

- DTOs should not contain business logic
- Validation happens in API layer, not DTO
- Keep DTOs simple and focused on data transfer
- Don't add computed fields unless explicitly required

---

## API Implementation

### API Service Classes

**CRITICAL: All API service classes MUST extend BaseCrudApi**

- **Always extend** `org.meveo.apiv3.base.BaseCrudApi<EntityType, DtoType>` for all API services
- **Required implementations**:
  - `getPersistenceService()` - return the service instance
  - `getEntityToDtoFunction()` - return method reference to toDto (e.g., `this::toDto`)
- Keep API implementations thin - delegate to service layer
- **CRITICAL: Do NOT add logging in API layer** - logging should be done in the service layer only
- Use consistent response building pattern
- Create, update and find methods in API class return a DTO object. No extra wrapper class is needed.
- List method in API class return `GenericSearchResponse<T>` type object where `<T>` is a DTO class
- In List method in API class, `count()` should be executed first and only if number of items is greater than one, a search should be executed

### BaseCrudApi Method Naming

**CRITICAL: Use correct method names from BaseCrudApi**

When extending BaseCrudApi, use the inherited method names correctly:

| Operation | BaseCrudApi Method | ❌ WRONG | ✅ CORRECT |
|-----------|-------------------|----------|-----------|
| Find by code | `find(String code)` | `findByCode(code)` | `find(code)` |
| Find by ID | `find(Long id)` | `findById(id)` | `find(id)` |
| Delete by code | `remove(String code)` | `delete(code)` | `remove(code)` |
| Delete by ID | `remove(Long id)` | `delete(id)` | `remove(id)` |
| Enable | `enableOrDisable(String code, boolean enable)` | `enable(code)` | `enableOrDisable(code, true)` |
| Disable | `enableOrDisable(String code, boolean enable)` | `disable(code)` | `enableOrDisable(code, false)` |

### Parameter Validation

- **Standard CRUD operations** (create, update, find by code/id): Validate required parameters at the beginning of the method and throw `MissingParameterException`
  - Example: `if (StringUtils.isBlank(dtoData.getCode())) { throw new MissingParameterException("code"); }`
- **Custom business operations** (close, publish, etc.): Validate required parameters and throw `MissingParameterException`
  - Example: `if (id == null) { throw new MissingParameterException("id"); }`
- **Always validate all required parameters** before proceeding with business logic
- Use `StringUtils.isBlank()` for string parameters
- Use `== null` check for object parameters

### Field Validation Rules

**CRITICAL: Status and Disabled Fields**

- **Status field**: Must never be accepted in create() or update() methods
  - Status changes must go through dedicated lifecycle action APIs (publish, close, etc.)
  - Validation: Check if `dtoData.getStatus() != null` and throw `InvalidParameterException`

- **Disabled field**: Can be set in create(), but must NOT be accepted in update() methods
  - Enable/disable operations after creation must go through dedicated enable/disable action APIs
  - Validation in update(): Check if `dtoData.getDisabled() != null` and throw `InvalidParameterException`
  - fromDto(): Set disabled field normally - validation in update() prevents it from being called for updates

**Multilingual Field Format**

- **Language codes**: Use 3-letter uppercase ISO 639-2 format in examples and documentation. No validation required.
  - Examples: ENG, FRA, DEU, SPA
  - Use in DTO @Schema examples and Postman collections

### Validation and Business Logic

- **Lookup reference entities by ID or code**:
  - If **ID provided**: Lookup by ID first, then verify code matches if code was also provided
  - If **only code provided**: Lookup by code
  - Never lookup by code first when ID is available (ID is the primary identifier)
  ```java
  ContractItem contractItem;
  if (contractItemId != null) {
      // Lookup by ID first
      contractItem = contractItemService.findById(contractItemId);
      if (contractItem == null) {
          throw new EntityDoesNotExistsException("ContractItem with id " + contractItemId + " not found");
      }
      // If code also provided, verify it matches
      if (StringUtils.isNotBlank(contractItemCode) && !contractItemCode.equals(contractItem.getCode())) {
          throw new InvalidParameterException("ContractItem code " + contractItemCode + " does not match ID " + contractItemId + " (actual code: " + contractItem.getCode() + ")");
      }
  } else {
      // Lookup by code (only when ID not provided)
      contractItem = contractItemService.findByCode(contractItemCode);
      if (contractItem == null) {
          throw new EntityDoesNotExistsException("ContractItem with code " + contractItemCode + " not found");
      }
  }
  ```
- Delegate business logic to service classes unless business logic requires field value comparison to a current (old) field value
- **CRITICAL: When calling service methods that return updated entity, capture and use the returned entity**
  - Pattern: `entity = serviceMethod(entity);`
  - Example: `formula = indexationFormulaService.publish(formula);`
  - Always reassign the returned entity to ensure you have the latest state

---

## Mapper Methods

### Mapper Pattern

**CRITICAL: Always use fromDto() method** to map DTO fields to entity in create() and update() operations

**CRITICAL: Always use toDto() method with customFields parameter** when returning DTOs for entities that extend CustomFieldEntity

Use consistent mapper pattern for converting between DTOs and entities:
- `protected DtoClass toDto(EntityClass entity, CustomFieldsDto customFieldsDto)` - for entities with custom fields
- `protected void fromDto(DtoClass dtoData, EntityClass entity)` - to populate entity from DTO

### The fromDto() Method

**CRITICAL: Distinguish between null (not provided) and empty (provided but empty)**

- If DTO field is **null**: Field was not provided in request - ignore and don't update entity
- If DTO field is **empty string/blank**: Field was provided but empty - set entity field to null
- If DTO field has **value**: Update entity field with the value

The fromDto() method should:
- Handle custom fields using `populateCustomFields(dtoData.getCustomFields(), entity, entity.getId() == null)`
- Be called in both create() and update() methods
- Update only the modified fields sent by the API

Handle entity references properly in mappers:
- String fields: `null` = not provided (ignore), empty = clear field
- Entity references: `null` = not provided, blank = clear reference, value = lookup and set
- Custom fields: Use `populateCustomFields(dtoData.getCustomFields(), entity, entity.getId() == null)`

### Handling Embedded Objects

**CRITICAL: Always access embedded object fields through the object, not as flat fields**

- Use `dtoData.getValidity().getFrom()` not `dtoData.getValidFrom()`
- Initialize embedded object if null: `entity.setValidity(new DatePeriod())`
- Check each nested field individually when mapping

### Handling Resource References in DTOs

**CRITICAL: Build proper Resource DTO objects for entity references**

- Build nested DTO objects with minimal fields (id, code)
- Access via nested object: `dto.getIndexation().getCode()` not `dto.getIndexationCode()`

### Custom Fields Handling

Adapt toDto() and fromDto() functions to handle custom fields if applicable:

```java
@Override
protected BiFunction<Endpoint, CustomFieldsDto, EndpointDto> getEntityToDtoFunction() {
    return (entity, customFieldInstances) -> toDto(entity);
}

@Override
protected BiFunction<Endpoint, CustomFieldsDto, EndpointDto> getEntityToDtoFunction() {
    return (entity, customFieldInstances) -> toDto(entity, customFieldInstances);
}
```

---

## Documentation

### Javadoc

- Add Javadoc documentation to all API classes and methods
- Document parameters, return values, and exceptions

#### Document Non-Obvious Side Effects

**CRITICAL: Document non-obvious side effects — silent drops, filtering, normalization, reordering — in the endpoint/method Javadoc (and `@Operation` description), so callers rely on the RETURNED state rather than assuming their input was applied verbatim.**

When a write endpoint does not persist exactly what the caller sent — e.g. it silently drops entries that are not valid in context, filters or de-duplicates a collection, or normalizes values — the caller cannot know unless it is documented and the response reflects the actual persisted state.

- State the rule explicitly: *"Entries whose index is not a component of the assigned formula are silently dropped."*
- Ensure the method **returns the resulting state** (the effective, post-filter collection), so callers read what was actually stored instead of trusting their request body.
- Prefer this over a silent contract that only a maintainer reading the implementation would discover.

### Swagger Annotations

In addition to Javadoc, add Swagger annotations to REST interface definition and DTO classes.

#### REST Interface Swagger Annotations

- **Class level**: Add `@Tag` annotation with name and description
- **Method level**: Add `@Operation` with summary, tags, description, examples, and all possible response codes
- **Parameters**: Use `@Parameter` annotation with description and required status

#### Tag Naming

Group related endpoints under a consistent, hierarchical tag name, using ` - ` as the separator from broadest to narrowest:

`<Domain>[ - <Subdomain>] - <Entity>`

- All endpoints for one entity share a single tag; sibling entities share the `<Domain>[ - <Subdomain>]` prefix so Swagger UI clusters them together.
- Use a singular, human-readable entity name (e.g. `Batch`, `Index value`) — not the Java class or URL path segment.
- Do **not** leave standalone/ungrouped tags (e.g. `IndexationBatch`, `PriceIndexation`), and avoid redundant repetition (e.g. `... - Indexation - Indexation`).
- Example — the indexation domain:
  - `Charging and rating - Indexation - Index`
  - `Charging and rating - Indexation - Index value`
  - `Charging and rating - Indexation - Indexation formula`
  - `Charging and rating - Indexation - Batch`
  - `Charging and rating - Indexation - Price indexation`

#### DTO Swagger Annotations

- Always use `@Schema` annotations on DTO fields
- Include description, example values, and required status
- Do not mark field as required in swagger if field is not marked as required in DTO

#### Examples

Every operation shows two examples, and they answer different questions. **Captured** is a call
that really happened, recorded against a running instance. **Generated** is assembled in the
documentation page from the field examples each time it loads, and shows every field the endpoint
accepts in that direction. Neither replaces the other: a recorded call is short and true, a
generated one is complete and hypothetical.

**Where a recorded example belongs**

- A **find or a list** is documented by the record it returns, so the payload goes on the DTO as
  a class-level `@Schema(example = ...)`. One record, one example, however many endpoints return
  it.
- **The wrapper a list returns carries no example.** A find answers with the record itself, a
  list answers with it inside a search response or a plural holder - `GenericSearchResponseXxx`,
  `XxxsDto` - and those exist only to carry the record and its paging. Put the example on the
  record; the documentation page assembles the envelope around it.
- A **create, update or action** keeps its payload on the operation, in `@RequestBody` or the 2xx
  `@ApiResponse`, because there the response is the result of doing something.
- Name it `@ExampleObject(name = "Captured", summary = "<collection> / <folder>", ...)` so a
  reader can find the call that produced it.
- Never store a payload that shows no record — a list captured while the table was empty documents
  nothing, and a reader reads it as "this endpoint returns nothing".
- Never let a response envelope (`actionStatus`, `paging`) into a record's own example.
- **Never put a real person's name, address or mailbox in an example.** Recordings come from test
  collections that people fill in with their own details; scrub them before they ship.

**When a field needs a seed**

A seed is a refinement, not an obligation: every field appears in the generated example anyway,
valued by its seed, else its type's default, else a placeholder shaped like the type. Add one
where the placeholder would mislead, or where the value teaches something:

- an expression or a format a reader could not guess — `"#{ op.quantity }"`, an EL filter, a
  code that must match another record
- **amounts that have to agree** — with-tax, without-tax and the tax itself
- **dates that bound a range or share a timeline** — `validFrom`/`validTo`, an invoice date and
  the due date that follows it
- **a configured default** that documents behaviour — `dueDateDelay`, `periodLength`
- **a reference field**, to show the reference rather than the whole related record:
  `@Schema(example = "[{\"id\": 1, \"code\": \"DP_GLOBAL_10PERC\"}]")`

Do **not** seed a plain boolean, number, enum or date. `"false"` on a flag and one constant of an
enumeration say nothing the type does not, and the generated example supplies them - an enum shows
its first constant. Names that describe a switch or an instruction (`disabled`, `displayXxx`,
`returnXxx`, `generateXxx`, `everyXxx`, `failOnXxx`) never need one.

**Inherited fields**

`code`, `description` and `id` are declared on a base class, so Java cannot seed them per subtype.
They come from the type's identity instead:

```java
@Schema(description = "...", extensions = @Extension(name = "identity", properties = {
        @ExtensionProperty(name = "code", value = "CPI_2024"),
        @ExtensionProperty(name = "description", value = "Consumer Price Index") }))
```

**Direction**

`readOnly` keeps a field out of requests, `writeOnly` out of responses, and both are how a
generated example stays honest about what a caller may send. A record's own `id` is shown in
responses only. Mutually exclusive fields cannot be expressed this way at all — say so in the
field description, because no assembled example can know it.

**When no recording exists**

Every stored example is normally a payload recorded against a running instance, and the
documentation page says so beneath it: *"Captured - recorded from a real find or list against a
running instance"*. Occasionally there is nothing to record - the entity has no rows in any
environment, so no call can return one. Write the example from the schema then, and mark it as
written, or the page will present your sentence as a recording.

The marker is an extension on the **class-level** `@Schema`, beside `description` and `example`.
Where the type already declares an `identity`, both go in one `extensions` array:

```java
@Schema(description = "A contact person, with their address and contact details",
        extensions = {
            @Extension(name = "identity", properties = {
                @ExtensionProperty(name = "code", value = "CONTACT_0001") }),
            @Extension(name = "example-source", properties = {
                @ExtensionProperty(name = "kind", value = "authored") }) },
        example = "{\"code\": \"CONTACT_0001\", \"company\": \"Example SA\"}")
public class ContactDto extends BusinessEntityDto {
```

The page then prints *"Written from the schema - no recorded call exists for this record"* in
place of the recording note. Remove the marker as soon as a real payload can be captured.

#### Documenting the Response

- **Always declare the success response.** An `@Operation` that lists `responses` replaces the
  response Swagger would infer from the return type, so an operation naming only its `400` and
  `409` documents no success at all — no schema, no example, nowhere for a payload to go.
  ```java
  @Operation(operationId = "createPaymentTerm", summary = "Create a payment term", responses = {
      @ApiResponse(responseCode = "200", description = "The payment term was created",
              content = @Content(schema = @Schema(implementation = ActionStatus.class))),
      @ApiResponse(responseCode = "400", description = "Invalid input or a required parameter is missing",
              content = @Content(schema = @Schema(implementation = ApiException.class))) })
  ```
- **Never declare the same status code twice on one operation.** A responses object is keyed by
  status: Swagger keeps one entry and discards the rest without warning, and the one it keeps may
  be the one carrying no schema. In review, treat a repeated `responseCode` as a defect.
- **Describe the outcome, not the type.** `description = "The SMS template successfully updated"`
  — not `"A list of SMS templates"`. The type is named by the schema beside it; the description is
  the only place the operation's own result is stated.
- **Do not return a bare `Response`.** A JAX-RS `Response` carries no type, so the payload exists
  only in the implementation and cannot be documented. Return the DTO. Where `Response` is
  unavoidable, declare the schema on the `@ApiResponse`.
- **Do not assemble a payload by hand.** `Response.ok(map)`, `Collections.singletonMap("id", id)`
  and string concatenation leave the endpoint with no type to document and no name to reference.
  Return a DTO, even a two-field one.

#### Making a DTO Visible to the Generator

- **Give every documented field an accessor.** Swagger resolves properties from getters. A field
  serialised by Jackson through field access but lacking a getter is returned by the API and
  missing from the schema — the reader is told the response has four fields when it has five.
- **Do not give two DTOs the same simple name within one document.** Each document - V0, V1/V2,
  V3 - keys its schemas by simple name, so two classes of that name reaching the same document
  leave one describing the other's fields, and every example built from it is wrong. Sharing a
  name *across* documents is harmless and already happens: `LanguageDto` and `CounterInstanceDto`
  each exist twice, one per document, with different fields. Before adding a DTO, check whether
  the name is already taken **in the document your endpoint publishes to**; if it is, name yours
  for what distinguishes it rather than for the entity alone.
- **The declared property name must be the name on the wire.** Where JAXB or Jackson renames an
  element — a plural property serialised in the singular, `paymentMethod` emitted as
  `methodOfPayment` — the schema and the payload disagree and every example built from either is
  wrong. Annotate the property so the two match.
- **An inline `@Schema(type = "object")` with no properties is discarded.** A schema needs a type
  to point at; if there is nothing to point at, that is a signal the endpoint needs a DTO.

#### Stating What the Schema Cannot

- **Document required combinations in the operation or DTO description.** Where a call needs
  several fields together — a counter instance needs its counter template, product, subscription
  and charge instance, plus the one account code matching the template's level — no `required`
  list expresses it, and the caller learns it from a 400.
- **Document mutually exclusive fields in the field description.** No generated example can know
  that two fields are alternatives; it will show both.
- **Treat `@Produces` and `@Consumes` as documentation.** They decide the media types the document
  advertises. Declaring `APPLICATION_XML` is a promise to accept and return XML.

#### Review Checklist

Before approving an API change, confirm:

1. every operation declares a `2xx` with a schema, and no status is declared twice;
2. each response description says what that operation returns;
3. no new endpoint returns a bare `Response` or a hand-built map;
4. every new DTO field has an accessor, and its name matches the wire format;
5. no new DTO repeats the simple name of another in the same document (V0, V1/V2 or V3);
6. field seeds follow the rules above — references seeded, primitives not;
7. any required combination or mutual exclusion is written in a description;
8. no example contains a real person, and none shows an empty envelope;
9. every DTO an operation sends or returns has a class-level example;
10. every create, update and action operation has both a request and a response example;
11. no find or list operation has an example of its own.
