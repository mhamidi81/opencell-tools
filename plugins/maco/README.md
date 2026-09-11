# maco factory

Toolkit for **`opencell-maco-project`** — the standalone MACO REST API for the French energy market
(Enedis / GRDF / ELD flows).

| Plugin | Purpose |
|--------|---------|
| [`oc-mc-tools`](./oc-mc-tools) | Guidelines, skills, builder agents, PR reviewer, implementation orchestrator and AI-usage alias for MACO |

Naming pattern: `oc-mc-<name>`.

## Why its own factory

MACO is **not** an Opencell Core overlay and **not** a delta over `oc-be-tools`. It is a separate
**Spring Boot 2.3 / Java 11** application whose conventions invert the core backend rules —
`javax.*` instead of `jakarta.*`, Flyway instead of Liquibase, `@RestController` instead of
`BaseRs`, Spring Data instead of entity base classes, JUnit 4 + MockMvc instead of Arquillian.

Applying `backend/` guidelines to this repository produces confidently wrong code, so the guidelines
live here in full. See [`oc-mc-tools/README.md`](./oc-mc-tools/README.md) for the comparison table.

The one shared piece is **AI-usage measurement**: `/oc-mc-calculate-ai-use` is a thin alias over
`/oc-be-tools:oc-be-calculate-ai-use` and must not fork it — MACO records the `backend` domain like
every other Java team.
