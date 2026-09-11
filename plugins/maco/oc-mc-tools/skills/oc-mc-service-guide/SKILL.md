---
name: oc-mc-service-guide
description: >
  TRIGGER when user asks to create, modify or refactor a business service, a job service or
  business logic in opencell-maco-project (maco-service module). Also trigger when working with
  MACO exceptions, Log4j2 logging, job launching or MacoCommonService.
  Loads the MACO service guidelines.
---

# MACO Service Guidelines

Before touching `maco-service`, read and follow:

1. **Service patterns**: `${CLAUDE_PLUGIN_ROOT}/guidelines/SERVICE_GUIDELINES.md` — @Service, Log4j2, the transaction rule, exceptions, job-service shape
2. **Critical rules**: `${CLAUDE_PLUGIN_ROOT}/guidelines/CRITICAL_RULES.md`
3. **Repositories**: `${CLAUDE_PLUGIN_ROOT}/guidelines/REPOSITORY_GUIDELINES.md`
4. **Code quality**: `${CLAUDE_PLUGIN_ROOT}/guidelines/CODE_QUALITY.md` — BigDecimal, Optional, exception handling

Note the local convention: **`maco-service` carries no `@Transactional`** — transactions come from
`maco-repository` and from Spring Batch steps. Check `MacoCommonService` before writing a helper.
