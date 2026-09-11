# MACO — Module Architecture

`opencell-maco-project` is a Maven multi-module **Spring Boot 2.3** application
(`com.opencell.maco`, Java 11) exposing the MACO REST API for the French energy market.

## Modules

| Module | Role | Depends on |
|--------|------|------------|
| `maco-exception` | Business exception hierarchy | — |
| `maco-model` | JPA entities, enums, builders, flat projection DTOs | `maco-exception` |
| `maco-dto` | Transport DTOs (`ResponseDto`, `FiltersDto`, JAXB/XML flow DTOs) | `maco-model` |
| `maco-repository` | Spring Data JPA repositories | `maco-model` |
| `maco-service` | Business services, job orchestration | `maco-repository`, `maco-dto` |
| `maco-batch-processing` | Spring Batch jobs (readers/processors/writers) | `maco-service` |
| `maco-spring-config` | Shared Spring configuration | — |
| `maco-db-sql-scripts` | **Flyway** migrations (`db/postgres`, `db/oracle`) | — |
| `maco-rest-api` | `@RestController` layer, security, app entry point, tests | all of the above |
| `maco-talend-jars` | Vendored Talend jars installed as Maven deps | — |
| `maco-env-config` | Postman environments, Keycloak client setup | — |

## Dependency direction — non-negotiable

```
exception → model → {dto, repository} → service → batch-processing → rest-api
```

**A lower module must never import from a higher one.** Two consequences that come up in review:

- `maco-repository` depends only on `maco-model`. A JPQL `select new …` projection used by a
  batch reader therefore lives in **`maco-model`** (e.g. `model/dto/BillableConsumptionCdrDto`),
  **not** in `maco-batch-processing` — otherwise the repository could not reference it.
- Entities never reference DTOs; DTOs map from entities.

## Package layout

Inside every module the root package is `com.opencell.maco`, then:

- `model` — entities; `model.dto` — flat JPQL projections; `builder` — entity builders
- `dto` — transport DTOs; `repository` — repositories; `service` — services
- `controller` — REST controllers (sub-packages allowed, e.g. `controller.jobs`)
- `config`, `readers`, `processors`, `writers`, `listeners`, `tasklet`, `partition`,
  `collectors` — Spring Batch (see BATCH_GUIDELINES)

## Runtime

- **Two database profiles**: PostgreSQL (default) and Oracle (`-Dspring.profiles.active=oracle`),
  each with its own Flyway script directory. A schema change must be written for **both**.
- **Security**: Keycloak adapter, `@Secured({"ROLE_…"})` on protected endpoints; the current
  username is read from the `KeycloakAuthenticationToken` principal.
- **Build**: Talend jars must be installed first
  (`maco-talend-jars/install/install-talend-jars-as-maven-dependencies.sh`), then `mvn clean package`;
  the runnable artifact is `maco-rest-api/target/maco-api.jar`.

## Business domain

MACO ingests and produces French energy-market flows (Enedis / GRDF / ELD): **C12, C15, F15,
R15, R17, R50, R64, R64B, ADIF**, plus meter readings, billable consumption/fees, CDR generation,
price calculation and estimation. Flow codes and field semantics are **regulatory** — never invent
them; take them from the ticket or an existing implementation of the same flow.
