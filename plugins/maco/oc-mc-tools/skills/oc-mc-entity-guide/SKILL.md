---
name: oc-mc-entity-guide
description: >
  TRIGGER when user asks to create, modify, or refactor JPA entity classes, enums,
  projection DTOs or entity builders in the opencell-maco-project maco-model module.
  Also trigger when working with MACO entity fields, sequences, @Column mappings or relationships.
  Also trigger when user gives review feedback on MACO entity code and you are about to edit entity files.
  Loads MACO entity, Flyway and architecture guidelines (Spring Boot 2.3 / Java 11 / javax.*).
---

# MACO Entity Development Guidelines

Before making any entity change in `opencell-maco-project`, read and follow:

1. **Critical rules**: `${CLAUDE_PLUGIN_ROOT}/guidelines/CRITICAL_RULES.md` — `javax.*` only, Java 11, no Lombok
2. **Entity patterns**: `${CLAUDE_PLUGIN_ROOT}/guidelines/ENTITY_GUIDELINES.md` — sequences, field types, projections, builders
3. **Database changes**: `${CLAUDE_PLUGIN_ROOT}/guidelines/DATABASE_GUIDELINES.md` — Flyway migration for every schema change
4. **Module boundaries**: `${CLAUDE_PLUGIN_ROOT}/guidelines/ARCHITECTURE.md` — where projections and entities must live
5. **Code quality**: `${CLAUDE_PLUGIN_ROOT}/guidelines/CODE_QUALITY.md`

MACO is Spring Boot 2.3 / Java 11 — **never** apply Opencell Core (`oc-be-tools`) entity rules here.
An entity change almost always needs a matching Flyway script in the same commit.
