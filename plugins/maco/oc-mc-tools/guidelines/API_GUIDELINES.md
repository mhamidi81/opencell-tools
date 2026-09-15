# MACO — REST API Guidelines (`maco-rest-api`)

Spring MVC `@RestController` + **Swagger 2** (springfox). No JAX-RS, no `BaseRs`/`BaseApi`.

## Controller declaration

```java
/**
 * Spring REST controller for 'MacoBillingFrequency' management.
 *
 * @author {Author}
 */
@RestController
@RequestMapping("/api/rest/v3/macoBillingFrequency")
@Api(tags = "MacoBillingFrequency API")
public class MacoBillingFrequencyController {

    @Autowired
    private MacoBillingFrequencyRepository macoBillingFrequencyRepository;
}
```

- **Base path**: `/api/rest/v3/{entityNameLowerCamel}`. `v3` is the current version; `v2` endpoints
  still exist — **do not add new endpoints under `v2`**. Cross-cutting controllers (jobs, cache) map
  `/api/rest/v3` and carry the resource in the method path.
- **`@Api(tags = "… API")`** on every controller — Swagger 2 annotations from
  `io.swagger.annotations.*`, **never** `io.swagger.v3.*`.
- Javadoc on the class (with `@author`) and on every endpoint (`@param`, `@return`, `@throws`).

## The five standard endpoints

MACO CRUD controllers follow one template. Reproduce it exactly unless the ticket says otherwise.

| Verb     | Path    | Purpose                                                |
|----------|---------|--------------------------------------------------------|
| `POST`   | `/list` | paginated + filtered search — returns `ResponseDto<T>` |
| `GET`    | `/{id}` | fetch one — 404 via `ResourceNotFoundException`        |
| `POST`   | `""`    | create — returns the saved entity                      |
| `PUT`    | `/{id}` | update                                                 |
| `DELETE` | `/{id}` | delete                                                 |

### The `/list` search — always this shape

```java
@PostMapping("/list")
@Secured({ "ROLE_MACOBILLINGFREQUENCY.ALL", "ROLE_MACOBILLINGFREQUENCY.GET" })
public ResponseDto<MacoBillingFrequency> getAllMacoBillingFrequency(
        @RequestBody(required = false) FiltersDto filters)
        throws ResourceNotFoundException, SearchKeysNotFoundException {

    GenericSpecificationsBuilder<MacoBillingFrequency> builder =
            new GenericSpecificationsBuilder<>(filters.getFilters());
    Specification<MacoBillingFrequency> specs = builder.build();
    Pageable pageable = new GenericPaginationBuilder(filters).build();

    Page<MacoBillingFrequency> result = repository.findAll(specs, pageable);
    if (pageable.getPageNumber() > result.getTotalPages()) {
        throw new ResourceNotFoundException("Page size " + pageable.getPageNumber()
                + " is greater than total pages " + result.getTotalPages());
    }
    return new ResponseDto<>(result);
}
```

Never hand-roll pagination or filtering: `GenericSpecificationsBuilder` + `GenericPaginationBuilder`
(`com.opencell.maco.utils`) are the only sanctioned path, and they require the repository to extend
`JpaSpecificationExecutor`.

- **`FiltersDto`** — `filters` (list of `SpecSearchCriteria`), `limit` (default 20), `offset`
  (default 0), `sortBy`, `sortOrder`.
- **`ResponseDto<T extends Serializable>`** — wraps a `Page` into `{ total, limit, offset, data }`.
  Construct it from the `Page`; do not build the envelope by hand.

### Fetch one

```java
MacoBillingFrequency entity = repository.findById(code)
        .orElseThrow(() -> new ResourceNotFoundException(MacoBillingFrequency.class, code));
return ResponseEntity.ok().body(entity);
```

## Security

- **`@Secured({ "ROLE_{ENTITY_UPPERCASE}.ALL", "ROLE_{ENTITY_UPPERCASE}.{ACTION}" })`** on every
  protected endpoint, where `{ACTION}` is `GET` for reads and `UPDATE` for writes. The `.ALL` role is
  always listed first.
- Job/report endpoints use functional roles instead (e.g. `ROLE_PRICE_CALCULATION`).
- **Roles come from the ticket** — do not invent a role name; an unknown role silently locks the
  endpoint for everyone.
- The authenticated user is read from the Keycloak principal:

```java
KeycloakAuthenticationToken kp = (KeycloakAuthenticationToken) principal;
SimpleKeycloakAccount account = (SimpleKeycloakAccount) kp.getDetails();
return account.getKeycloakSecurityContext().getToken().getPreferredUsername();
```

Null-check `principal` first. When a job endpoint needs the caller, pass it down with
`params.putIfAbsent(USER_KEY, currentUsername)`.

## Return types

- `ResponseDto<T>` for `/list`.
- `ResponseEntity<T>` elsewhere — `ResponseEntity.ok().body(…)`.
- File downloads: `ByteArrayResource` + explicit `Content-Disposition`, `Cache-Control: no-cache,
  no-store, must-revalidate`, `Pragma: no-cache`, `Expires: 0`,
  `MediaType.APPLICATION_OCTET_STREAM`.

## Swagger documentation

```java
@ApiOperation(value = "…", response = Xxx.class)
@ApiResponses({ @ApiResponse(code = 200, message = "…"),
                @ApiResponse(code = 500, message = "Internal server error") })
@ApiParam(name = "prmId", type = "String", value = "Numéro de PRM", required = true)
```

Document every query/path parameter with `@ApiParam` including `required`. The API is consumed by
external integrators through the Swagger UI — an undocumented parameter is a defect.

## Do not

- Put business logic in a controller. Trivial CRUD may call the repository directly (that is the
  house template); anything with rules goes through a `@Service`.
- Return an entity graph with EAGER relations on a high-volume endpoint — use a projection.
- Add an endpoint under `/api/rest/v2`.
- Catch an exception just to return 500 — let the exception type drive the status.
