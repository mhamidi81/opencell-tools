---
name: oc-mc-repository-guide
description: >
  TRIGGER when user asks to create or modify a Spring Data JPA repository, a derived query method,
  a @Query JPQL/native query or a Specification in opencell-maco-project (maco-repository module).
  Loads the MACO repository guidelines.
---

# MACO Repository Guidelines

Before touching `maco-repository`, read and follow:

1. **Repository patterns**: `${CLAUDE_PLUGIN_ROOT}/guidelines/REPOSITORY_GUIDELINES.md` — JpaRepository + JpaSpecificationExecutor, query styles, Optional returns
2. **Entity/projection rules**: `${CLAUDE_PLUGIN_ROOT}/guidelines/ENTITY_GUIDELINES.md`
3. **Module boundaries**: `${CLAUDE_PLUGIN_ROOT}/guidelines/ARCHITECTURE.md` — repositories depend on `maco-model` only
4. **Code quality**: `${CLAUDE_PLUGIN_ROOT}/guidelines/CODE_QUALITY.md`

Every repository must extend **both** `JpaRepository<T, ID>` and `JpaSpecificationExecutor<T>` —
the standard `/list` search endpoint depends on it.
