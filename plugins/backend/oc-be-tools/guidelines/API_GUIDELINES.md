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

### Swagger Annotations

In addition to Javadoc, add Swagger annotations to REST interface definition and DTO classes.

#### REST Interface Swagger Annotations

- **Class level**: Add `@Tag` annotation with name and description
- **Method level**: Add `@Operation` with summary, tags, description, and all possible response codes
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
