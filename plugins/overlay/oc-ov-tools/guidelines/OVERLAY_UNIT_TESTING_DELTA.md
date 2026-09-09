# Overlay unit testing

> LAYERS OVER: oc-be-tools/guidelines/UNIT_TESTING.md
> CORE BASELINE: oc-be-tools 1.17.0
> PRECEDENCE: core's structure, naming, AAA, EntityManager mocking, ArgumentCaptor, relative-date and
> stubbing rules all apply. Only the following differ.

## Framework — REPLACES core

New tests: **JUnit 5 + Mockito**, `@ExtendWith(MockitoExtension.class)` with `@Mock` / `@InjectMocks` /
`@Captor`. AssertJ where it reads better.

`LiquibaseFileTest` is **JUnit 4** — leave it alone; it is a structural check, not a unit test.

## Where tests may and may not live

Tests belong in the api, job and war-overlay modules. **The script module's `src/test/java` never
runs** — test compilation is skipped there, so anything placed there is dead weight that looks like
coverage. Script logic that needs testing should live in the utility module, which is compiled and
packaged normally.

## There is no test BOM

The root pom has no `dependencyManagement`, so JUnit/Mockito/AssertJ versions **drift per module**. Add
test dependencies to the *module* pom, matching the versions its siblings already use. Do not "fix" the
root pom as a side effect of a feature ticket — that is its own change.

## Reference patterns

- **API bean test** — mock every injected service, `@InjectMocks` the `BaseApi` bean, `@Captor` the
  entity passed to the service, assert on the captured value. Name constants for fixtures; cite the
  ticket in the class javadoc.
- **Job/parser test** — no mocks; load a fixture from `src/test/resources` via
  `getClass().getClassLoader().getResource(name).toURI()`. **Never hardcode a file path** — the
  classloader form is what keeps these tests working on Windows.

## Coverage

Core's 80% target applies to **new** code. The small number of existing tests is a gap, not a
precedent — but do not open-endedly backfill tests for untouched code inside a feature ticket.
