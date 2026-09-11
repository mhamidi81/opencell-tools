# MACO — Testing Guidelines (`maco-rest-api/src/test`)

**JUnit 4** (`org.junit.Test`, `SpringRunner`) — *not* JUnit 5. Do not import
`org.junit.jupiter.*`; a Jupiter test is silently not collected by the surefire setup here.

All tests live in **`maco-rest-api/src/test/java`**, even when they exercise a service or a batch
step, because the Spring context is booted from `MacoApplication`.

## The two base classes — pick the right one

| Base class | Use for |
|------------|---------|
| `AbstractMacoIntegrationTest` | services, batch jobs, repositories — no HTTP security layer |
| `AbstractMacoSecuredIntegrationTest` | controller tests hitting **secured** endpoints via `MockMvc` (adds `SecurityTestConfig`, which disables Keycloak/CSRF) |

Both boot `@SpringBootTest(webEnvironment = RANDOM_PORT)`, `@ActiveProfiles("test")`,
`application-testing.properties`, `@Commit`, and the `DatabaseCleanupTestExecutionListener`.

**Never re-declare those annotations on a subclass.** The Spring context is cached across the whole
suite *only while the annotation set stays identical* — adding one annotation to one test class
forks a second context and slows the entire build.

**Do not add `@DirtiesContext`** unless the class really mutates context beans (`@MockBean`, static
state). Database isolation is already handled: `DatabaseCleanupTestExecutionListener` drops the
schema and replays the Flyway migrations **before each test class**.

## Controller test shape

```java
/**
 * Unit tests for {@link MacoPodMacoController}.
 *
 * @author {Author}
 */
@FixMethodOrder(MethodSorters.NAME_ASCENDING)
public class MacoPodMacoControllerTest extends AbstractMacoSecuredIntegrationTest {

    private static final String BASE_URL = "/api/rest/v3/macoPodMaco";

    @Autowired private MockMvc mockMvc;
    @Autowired private ObjectMapper objectMapper;

    @Test
    public void test01_createPod_shouldPersistDateWithoutTimezoneShift() throws Exception {
        MvcResult result = mockMvc.perform(post(BASE_URL)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(payload)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").exists())
                .andReturn();
    }
}
```

- **`@FixMethodOrder(MethodSorters.NAME_ASCENDING)`** plus `testNN_` prefixes when tests share
  state built up in order (the dominant style here). Prefer independent tests when you can.
- Assertions: `org.junit.Assert.*` static imports, plus MockMvc `status()`, `jsonPath()`,
  `content()`.
- Set up fixtures in `@Before`; use the repositories to seed, not raw SQL, unless the case is about
  SQL itself.

## What to test

For any production change, at minimum:

| Change | Required test |
|--------|---------------|
| New/changed endpoint | MockMvc test per status path — 200, 404 (`ResourceNotFoundException`), and the secured-role rejection where relevant |
| New/changed service rule | a test per business branch, including the exception paths |
| New/changed batch step | a job-level test asserting the `StepExecution` counters (written/skipped) and the persisted outcome |
| New entity + migration | a persistence round-trip: save → flush → reload, asserting column mapping (especially dates) |
| Bug fix | **a test that fails before the fix and passes after** |

**Date/timezone regressions are a recurring MACO defect class.** When touching a `DATE` or timestamp
column, assert the reloaded value equals the written one — there is already precedent for this
(`MacoPodMacoControllerTest`).

## Flow (`integration/`) tests

`AdifTests`, `C12Tests`, `C15Tests`, `F15Tests`, `R15Tests`, `R17Tests`, `R64Tests`, `R64BTests`, …
exercise a full market-flow import/treatment against sample files. When you change a flow
treatment, **extend its existing flow test class** rather than creating a parallel one.

## Rules

- Never `@Ignore` a test to get a build green. If a test must be disabled, the ticket must say so
  and the `@Ignore` must carry a reason.
- No `Thread.sleep` for synchronisation.
- Tests must pass from a clean database — they re-run the whole Flyway chain, so a test that depends
  on pre-existing production data will fail in CI.
- Keep the shared context: no new `@SpringBootTest` annotation set unless genuinely unavoidable.
