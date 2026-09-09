# Overlay REST API (apiv0)

> LAYERS OVER: oc-be-tools/guidelines/API_GUIDELINES.md
> CORE BASELINE: oc-be-tools 1.17.0
> PRECEDENCE: this is the largest delta. Core's apiv2/apiv3 model does NOT apply to the
> `vertical-energy` profile — read the REPLACES sections carefully.

## The API style is apiv0 — REPLACES core's `BaseCrudApi` / Immutables model

| Artifact | Package | Annotations | Base type |
|---|---|---|---|
| REST interface | `org.meveo.apiv0.rest` | `@Path("/ve/…")`, `@Consumes`, `@Produces`, `@PermitAll` | `org.meveo.apiv0.base.rest.IBaseRs` |
| REST impl | `org.meveo.apiv0.rest.impl` | `@RequestScoped` | `org.meveo.apiv0.base.rest.BaseRs` |
| API bean | `org.meveo.api` | *(none — see below)* | `org.meveo.api.base.BaseApi` |
| DTO | overlay dto module | — | plain POJO |

Core's *Hypermedia Links*, *Response Building (v3)* and *Standard CRUD URL shapes* sections do not
apply. Return `ActionStatus` or a `*ResponseDto`.

## Registration — there is none, and getting the package wrong fails silently

**Do not look for an activator to edit.** Core's `JaxRsActivatorApiV0123` (`@ApplicationPath("/api/rest")`)
discovers resources at runtime with:

```java
new Reflections("org.meveo.apiv0.rest").getSubTypesOf(BaseRs.class)
```

So a resource is registered if and only if it **both**:

1. lives under `org.meveo.apiv0.rest` (or a subpackage such as `.impl`), **and**
2. extends `org.meveo.apiv0.base.rest.BaseRs`.

Miss either and the class compiles, packages and deploys — and the endpoint simply does not exist.
There is no error at build or boot. This is the single most common overlay API mistake.

Core's API_GUIDELINES step "register the resource in `JaxRsActivatorApiV2`" has **no counterpart here**.

## The API bean has no scope annotation — REPLACES core's "API classes are `@Stateless`"

Existing beans are declared as plain `public class XxxApi extends BaseApi`, picked up as `@Dependent`
via `beans.xml` (`bean-discovery-mode="all"`).

Consequence, and state it in review when it matters: the bean has **no transaction boundary of its
own**, so the whole create/update runs inside the JAX-RS request transaction. If you need
`REQUIRES_NEW` or a separate boundary, put it on the **service**, not the API bean. Do not add
`@Stateless` to an existing API bean as a drive-by change — it alters transactional behaviour.

## DTOs — REPLACES core "DTO Guidelines"

Plain, mutable POJOs in the overlay dto module. **No** `@Value.Immutable`, no `ImmutableXxx` builders,
no `Resource`/`ResourceWithUpdatableCode`, no Immutables annotation processor.

These core DTO rules **do** survive: the `Dto` suffix; wrapper types (`Integer`, not `int`); no default
values; `@JsonInclude(NON_NULL)`; nothing implicitly required; the standard date serializer; and the
mandatory step of verifying every field against the actual entity before writing the DTO.

## URL namespace

Interface `@Path` values start with `/ve/` (e.g. `/ve/homeInfo`, `/ve/pod`) under the `/api/rest` root.
**Verify the deployed URL against an existing request in the Postman collections before writing tests**
rather than deriving it — the effective prefix comes from core's JAX-RS application.

## Impl naming

Both `XxxRsImpl` and `XxxImplRs` exist, plus one bare `XxxImpl`. **New code uses `XxxRsImpl`.** Do not
mass-rename existing classes as a side effect of a feature ticket.

## Swagger

Core rule 4 (Swagger on all endpoints and DTOs) applies to new code. Most existing interfaces lack
`@Operation`/`@Tag`; add them on what you touch, do not retrofit the module.

*Known defect:* the swagger maven plugin in the api module scans `org.meveo.api.rest`, a package with
zero classes, so the generated `openapi-vertical.json` is empty. The correct package is
`org.meveo.apiv0.rest`.

## Template profile

The `template` profile uses `BaseCrudApi<E,D>`, `@Value.Immutable` DTOs extending
`ResourceWithUpdatableCode`, base path `/api/rest/ext/`, and explicit registration in
`ExtRestActivator.getClasses()`. In that profile core's API_GUIDELINES apply almost unchanged.
