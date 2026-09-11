# oc-mc-tools — MACO development toolkit

Claude Code toolkit for **`opencell-maco-project`**, the MACO REST API for the French energy market.

## Why this is a standalone plugin, not a delta over `oc-be-tools`

`oc-ov-tools` (overlay) is a thin *delta* over the backend guidelines because overlay repositories
layer on top of the Opencell Core war and inherit its conventions. **MACO does not.** It is a
separate Spring Boot application whose rules are not a superset of core's — several are the exact
inverse:

| Concern | opencell-core (`oc-be-tools`) | **opencell-maco-project (`oc-mc-tools`)** |
|---------|-------------------------------|--------------------------------------------|
| Stack | JEE / Wildfly, CDI, JAX-RS | **Spring Boot 2.3**, Spring MVC, Spring Batch |
| Java | 21 | **11** |
| Namespace | `jakarta.*` **mandatory** | **`javax.*` mandatory** (zero `jakarta.*` imports) |
| Persistence | Entity base classes, custom fields | **Plain JPA + Spring Data `JpaRepository`** |
| Migrations | Liquibase changesets | **Flyway** `V{x.y.z}__{name}.sql` |
| API layer | `IBaseRs` / `BaseRs` / `BaseApi` | **`@RestController`** + `ResponseDto` / `FiltersDto` |
| Injection | `@Inject` (CDI) | **`@Autowired`** (Spring) |
| Swagger | OpenAPI 3 | **Swagger 2** (`io.swagger.annotations`) |
| Tests | Arquillian + Postman | **`@SpringBootTest` + MockMvc, JUnit 4** |
| License header | AGPL header required | **none** |
| Lombok | — | **not used** |
| Jira project | `INTRD` | **`MACRD`** |

A delta layer that said "REPLACES core §X" for nearly every section would be harder to read and
easier to get wrong than a self-contained set. So `oc-mc-tools` carries its own guidelines and has
**no dependency on `oc-be-tools`** — with one deliberate exception, below.

## The one thing that is shared: AI-usage measurement

`/oc-mc-calculate-ai-use` is a **thin alias** over `/oc-be-tools:oc-be-calculate-ai-use`. The
analyzer, the four measurement sources and the cross-team record contract are **not forked** — one
reporting tool reads every team's data from one Jira field (`customfield_10745`), so the schema, the
record-key layout and the `domain` value must stay identical. MACO work is recorded as
`domain: backend` with the ordinary `ai_Dev_back` / `ai_test_back_dev` / `ai_code_review_back` tags;
only the artifact categories differ (`bat` for Spring Batch, `mig` matching Flyway `.sql`).

Running `/oc-mc-calculate-ai-use` therefore requires **`oc-be-tools`** to be installed.

## Contents

**Guidelines** (`guidelines/`) — the single source of truth, read by every skill and agent:

| File | Covers |
|------|--------|
| `CRITICAL_RULES.md` | the rules that invert vs core, plus the comparison table |
| `ARCHITECTURE.md` | module map, dependency direction, runtime, business domain |
| `ENTITY_GUIDELINES.md` | id strategies, field types, projections, builders |
| `REPOSITORY_GUIDELINES.md` | `JpaRepository` + `JpaSpecificationExecutor`, query styles |
| `SERVICE_GUIDELINES.md` | `@Service`, Log4j2, the no-`@Transactional` convention, job services |
| `API_GUIDELINES.md` | `/api/rest/v3`, the five standard endpoints, `@Secured`, Swagger 2 |
| `BATCH_GUIDELINES.md` | job/step config, `@StepScope`, thread-safe readers, counters |
| `DATABASE_GUIDELINES.md` | Flyway naming, versioning, the never-edit-an-applied-script rule |
| `CODE_QUALITY.md` | exceptions, logging, `BigDecimal`, resources, performance |
| `TESTING_GUIDELINES.md` | JUnit 4, the two base classes, the context-caching rule |

**Skills** (`skills/`) — load the right guidelines on demand:
`/oc-mc-entity-guide`, `/oc-mc-db-guide`, `/oc-mc-repository-guide`, `/oc-mc-service-guide`,
`/oc-mc-api-guide`, `/oc-mc-batch-guide`, `/oc-mc-test-guide`

**Agents** (`agents/`):
`oc-mc-entity-builder` (entities + Flyway), `oc-mc-service-builder` (repositories + services),
`oc-mc-batch-builder` (Spring Batch), `oc-mc-api-builder` (REST), `oc-mc-test-generator` (JUnit 4),
`oc-mc-pr-reviewer` (guideline review with a scoring rubric)

**Commands** (`commands/`):

| Command | Does |
|---------|------|
| `/oc-mc-implement` | orchestrates a full MACO ticket across the builder agents, with blocking checkpoints |
| `/oc-mc-review` | two-axis review (guidelines + JIRA acceptance criteria), posts to the Bitbucket PR, tags the ticket |
| `/oc-mc-calculate-ai-use` | thin alias supplying the MACO repo profile to the shared analyzer |

## Notes for maintainers

- **Never apply a core rule to MACO code.** The reviewer is explicitly instructed not to flag
  `javax.*`, a missing AGPL header, or a missing Liquibase changeset — all three would be wrong here.
- **Keep the AI-usage alias thin.** If measurement logic starts appearing in
  `oc-mc-calculate-ai-use.md`, it has been forked and the cross-team report will drift.
- **Bitbucket uses Basic auth**, not Bearer: `BITBUCKET_ACCESS_TOKEN` holds an Atlassian API token
  (`ATATT…`) used as `-u "${BITBUCKET_EMAIL}:${BITBUCKET_ACCESS_TOKEN}"`. The diff endpoints answer
  302 — always `curl -sL`.
- MACO tickets are in **`MACRD`**, shared with overlay work, so the ticket key does not identify the
  codebase; the repository does.
