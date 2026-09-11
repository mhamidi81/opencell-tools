---
name: oc-mc-api-guide
description: >
  TRIGGER when user asks to create or modify a REST endpoint, a @RestController, a CRUD or /list
  search API, Swagger documentation, or endpoint security roles in opencell-maco-project
  (maco-rest-api module). Loads the MACO REST API guidelines.
---

# MACO REST API Guidelines

Before touching `maco-rest-api`, read and follow:

1. **API patterns**: `${CLAUDE_PLUGIN_ROOT}/guidelines/API_GUIDELINES.md` — the five standard endpoints, FiltersDto/ResponseDto, @Secured roles, Swagger 2
2. **Critical rules**: `${CLAUDE_PLUGIN_ROOT}/guidelines/CRITICAL_RULES.md`
3. **Services**: `${CLAUDE_PLUGIN_ROOT}/guidelines/SERVICE_GUIDELINES.md`
4. **Tests**: `${CLAUDE_PLUGIN_ROOT}/guidelines/TESTING_GUIDELINES.md` — every endpoint needs a MockMvc test
5. **Code quality**: `${CLAUDE_PLUGIN_ROOT}/guidelines/CODE_QUALITY.md`

New endpoints go under **`/api/rest/v3`** (never `v2`), use **Swagger 2**
(`io.swagger.annotations.*`, never `io.swagger.v3.*`), and build `/list` search with
`GenericSpecificationsBuilder` + `GenericPaginationBuilder`. Take `@Secured` role names from the
ticket — never invent one.
