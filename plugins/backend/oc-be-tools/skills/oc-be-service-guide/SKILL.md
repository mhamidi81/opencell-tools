---
name: oc-be-service-guide
description: >
  TRIGGER when user asks to create, modify, or refactor service classes
  (@Stateless beans) in the opencell-admin/ejbs module.
  Also trigger when working with business rules, validation methods, or exception handling in services.
  Also trigger when user gives review feedback on service code and you are about to edit service files.
  Loads service layer guidelines for proper Opencell patterns.
---

# Service Layer Guidelines

Before making any service layer changes, read and follow the guidelines in these files:

1. **Service patterns**: Read `${CLAUDE_PLUGIN_ROOT}/guidelines/SERVICE_GUIDELINES.md` for conventions, business rules, validation, exceptions, performance
2. **Code quality**: Read `${CLAUDE_PLUGIN_ROOT}/guidelines/CODE_QUALITY.md` for exception handling, resource management, formatting
3. **Critical rules**: Read `${CLAUDE_PLUGIN_ROOT}/guidelines/CRITICAL_RULES.md` for rules that apply to all code

Apply these guidelines when generating or modifying service code.
