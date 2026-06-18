---
name: oc-be-entity-guide
description: >
  TRIGGER when user asks to create, modify, or refactor JPA entity classes,
  enum types, or @Embeddable classes in the opencell-model module.
  Also trigger when working with entity field types, relationships, or base classes.
  Also trigger when user gives review feedback on entity code and you are about to edit entity files.
  Loads entity and database guidelines for proper Opencell patterns.
---

# Entity Development Guidelines

Before making any entity changes, read and follow the guidelines in these files:

1. **Entity patterns**: Read `${CLAUDE_PLUGIN_ROOT}/guidelines/ENTITY_GUIDELINES.md` for base classes, field types, relationships, naming conventions
2. **Database changes**: Read `${CLAUDE_PLUGIN_ROOT}/guidelines/DATABASE_GUIDELINES.md` for Liquibase changeset patterns
3. **Code quality**: Read `${CLAUDE_PLUGIN_ROOT}/guidelines/CODE_QUALITY.md` for exception handling, resource management, formatting
4. **Critical rules**: Read `${CLAUDE_PLUGIN_ROOT}/guidelines/CRITICAL_RULES.md` for rules that apply to all code

Apply these guidelines when generating or modifying entity code.
