# Critical Rules — opencell-maco-project

These rules apply to ALL code in the MACO project, regardless of module.

> **MACO is NOT opencell-core.** It is a standalone **Spring Boot 2.3 / Java 11** application.
> Several `oc-be-tools` rules are **inverted** here. Never apply Opencell Core backend
> guidelines to this repository — see the comparison table below.

1. **Always use `javax.*` packages, NEVER `jakarta.*`** (Java 11 / Spring Boot 2.3)
   - `javax.persistence.*`, `javax.validation.*`, `javax.xml.bind.annotation.*`
   - The codebase contains **zero** `jakarta.*` imports. Introducing one breaks the build.
2. **Java 11 language level.** No records, no sealed types, no pattern matching for `instanceof`,
   no text blocks. `var` is allowed by the language but **not used** — always declare explicit types.
3. **No Lombok.** The project has zero Lombok usage. Write explicit getters, setters and
   constructors. Do not add the dependency.
4. **No license header.** Files start directly with `package …;` — unlike opencell-core, MACO
   files carry no AGPL header. Do not add one.
5. **All public methods and all entity fields must have Javadoc.** Entity fields use the
   `/** Column {description} **/` form (see ENTITY_GUIDELINES).
6. **All REST endpoints must carry Swagger 2 annotations** — `io.swagger.annotations.*`
   (`@Api`, `@ApiOperation`, `@ApiParam`, `@ApiResponses`). This is Swagger 2 / springfox,
   **not** OpenAPI 3 / `io.swagger.v3.*`.
7. **Never assume entity fields, table columns or business rules. Stop work and ask.**
   MACO models the French energy market (Enedis/GRDF flows: C12, C15, F15, R15, R17, R50, R64,
   ADIF, ELD). Field semantics are regulatory — guessing produces plausible, wrong code.
8. **Always verify the REST specification from the Jira ticket before implementing.**
   MACO tickets live in the **`MACRD`** project. Opencell stories store content in
   **custom fields**, NOT the (usually empty) standard `description`. Fetch with
   `fields: ["*all"]` and read `customfield_10134` (Requirement), `customfield_10135`
   (Functional design), `customfield_10136` (Acceptance), `customfield_10137`
   (Technical design). Check sub-tasks and comments too.
9. **Verify all referenced entities, repositories and Flyway versions exist before implementing.**
10. **Do not create methods without a specific requirement.**
11. **Respect the module dependency direction** (see ARCHITECTURE.md). A lower module must never
    import from a higher one — notably `maco-repository` depends only on `maco-model`, never on
    `maco-batch-processing`.
12. **Never edit an already-applied Flyway migration.** Add a new versioned script instead
    (see DATABASE_GUIDELINES).

---

## MACO vs Opencell Core — do not mix

| Concern | opencell-core (`oc-be-tools`) | **opencell-maco-project (this plugin)** |
|---------|-------------------------------|------------------------------------------|
| Stack | JEE / Wildfly, CDI, JAX-RS | **Spring Boot 2.3**, Spring MVC, Spring Batch |
| Java | 21 | **11** |
| Namespace | `jakarta.*` **mandatory** | **`javax.*` mandatory** |
| Persistence | Entity base classes, CFs | **Plain JPA + Spring Data `JpaRepository`** |
| Migrations | Liquibase changesets | **Flyway** `V{version}__{name}.sql` |
| API layer | `IBaseRs` / `BaseRs` / `BaseApi` | **`@RestController`** + `ResponseDto` / `FiltersDto` |
| Injection | `@Inject` (CDI) | **`@Autowired`** (Spring) |
| Swagger | OpenAPI 3 | **Swagger 2** (`io.swagger.annotations`) |
| Tests | Arquillian + Postman | **Spring Boot `@SpringBootTest` + MockMvc, JUnit 4** |
| Jira project | `INTRD` | **`MACRD`** |
