# Overlay profiles

Overlay repositories do not share one set of conventions. Two exist today and they differ on almost
every axis. **Neither is wrong** — a reviewer that treats `vertical-energy`'s apiv0 style as a defect
produces nothing but noise. Rules are therefore profile-scoped; only the genuinely universal ones
(in `OVERLAY_ARCHITECTURE.md`, `OVERLAY_SCRIPTS.md`, `OVERLAY_SERVICE_DELTA.md`) are written
profile-free.

## Selecting the profile

1. The repo's own `CLAUDE.md` `## Overlay profile` block. **Authoritative** — always prefer it.
2. Fallback by module prefix: `opencell-elec-*` → `vertical-energy`; `opencell-ext-*` → `template`.
3. Neither matches → stop and ask. Do not guess.

## Axis table

| Axis | `vertical-energy` | `template` |
|---|---|---|
| Module prefix | `opencell-elec-*` | `opencell-ext-*` |
| Package roots | `org.meveo.*` (core-discovered) / `com.oc.*` | `com.opencell.ext.*` |
| Table prefix | **none** (`point_of_delivery`) | `ext_` (`ext_person`) |
| Entity base | `org.meveo.model.BusinessCFEntity` | `BusinessEntity` |
| API style | **apiv0** | apiv2-style `BaseCrudApi` |
| REST interface base | `org.meveo.apiv0.base.rest.IBaseRs` | JAX-RS resource interface |
| REST impl base | `org.meveo.apiv0.base.rest.BaseRs` | `@RequestScoped` resource impl |
| API bean base | `org.meveo.api.base.BaseApi` | `org.meveo.apiv3.base.BaseCrudApi<E,D>` |
| REST base path | `/ve/…` | `/api/rest/ext/…` |
| REST registration | **none** — Reflections scan (see `OVERLAY_API_DELTA.md`) | `ExtRestActivator.getClasses()` |
| DTO style | plain mutable POJO | `@Value.Immutable` + `ResourceWithUpdatableCode` |
| Liquibase | `db_resources/{current,rebuild}/overlay.xml` | `db_resources/changelog/{current,rebuild}/overlay.xml` |
| Script package | `com.oc.**` | `com.opencell.ext.service.script` |
| Postman dir | `opencell-elec-postman/` | `opencell-ext-postman/` |
| Test framework | JUnit 5 (+ JUnit 4 for `LiquibaseFileTest`) | — |

## Rule

**The repo's profile is authoritative.** Never "modernise" `vertical-energy` toward the template, or
retrofit template repos to apiv0, as a side effect of an unrelated ticket. A profile migration is its
own decision, its own ticket, and its own review.
