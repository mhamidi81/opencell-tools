---
name: db-guide
description: >
  TRIGGER when user asks to create or modify Liquibase changesets,
  database migrations, table structures, or indexes.
  Also trigger when working with current/structure.xml or rebuild/structure.xml files.
  Also trigger when user gives review feedback on database/Liquibase code and you are about to edit changeset files.
  Loads database guidelines for proper Opencell patterns.
---

# Database Guidelines

Before making any database changes, read and follow the guidelines in these files:

1. **Database patterns**: Read `${CLAUDE_PLUGIN_ROOT}/guidelines/DATABASE_GUIDELINES.md` for Liquibase changesets, column types, indexes, multitenancy
2. **Code quality**: Read `${CLAUDE_PLUGIN_ROOT}/guidelines/CODE_QUALITY.md` for exception handling, resource management, formatting
3. **Critical rules**: Read `${CLAUDE_PLUGIN_ROOT}/guidelines/CRITICAL_RULES.md` for rules that apply to all code

Apply these guidelines when generating or modifying Liquibase changesets or database-related code.
