---
name: oc-mc-test-guide
description: >
  TRIGGER when user asks to write, fix or review tests in opencell-maco-project — integration tests,
  MockMvc controller tests, batch job tests or market-flow tests (C12, C15, F15, R15, R17, R64, ADIF).
  Also trigger when a MACO change needs test coverage before commit or review.
  Loads the MACO testing guidelines (JUnit 4 + Spring Boot Test).
---

# MACO Testing Guidelines

Before writing or changing tests in `opencell-maco-project`, read and follow:

1. **Test patterns**: `${CLAUDE_PLUGIN_ROOT}/guidelines/TESTING_GUIDELINES.md` — the two base classes, context caching, what to test per change type
2. **Critical rules**: `${CLAUDE_PLUGIN_ROOT}/guidelines/CRITICAL_RULES.md`
3. **Code quality**: `${CLAUDE_PLUGIN_ROOT}/guidelines/CODE_QUALITY.md`

MACO uses **JUnit 4** (`org.junit.Test`, `SpringRunner`) — a JUnit 5 (`org.junit.jupiter.*`) test is
silently never collected. All tests live in `maco-rest-api/src/test/java`. Extend
`AbstractMacoIntegrationTest` or `AbstractMacoSecuredIntegrationTest` **without re-declaring their
annotations**, or you fork the shared Spring context and slow the whole suite.
