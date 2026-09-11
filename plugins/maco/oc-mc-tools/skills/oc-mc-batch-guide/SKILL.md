---
name: oc-mc-batch-guide
description: >
  TRIGGER when user asks to create or modify a Spring Batch job, step, ItemReader, ItemProcessor,
  ItemWriter, Tasklet, Partitioner or listener in opencell-maco-project (maco-batch-processing module).
  Also trigger on chunk sizing, job parameters, StepExecution counters, batch thread-safety or
  job launching. Loads the MACO Spring Batch guidelines.
---

# MACO Spring Batch Guidelines

Before touching `maco-batch-processing`, read and follow:

1. **Batch patterns**: `${CLAUDE_PLUGIN_ROOT}/guidelines/BATCH_GUIDELINES.md` — job/step configuration, @StepScope, thread-safe readers, counters, partitioning
2. **Job services**: `${CLAUDE_PLUGIN_ROOT}/guidelines/SERVICE_GUIDELINES.md` — how a job is launched and how its results are read back
3. **Critical rules**: `${CLAUDE_PLUGIN_ROOT}/guidelines/CRITICAL_RULES.md`
4. **Performance**: `${CLAUDE_PLUGIN_ROOT}/guidelines/CODE_QUALITY.md` — no unbounded findAll, no query per item, EAGER relation traps
5. **Tests**: `${CLAUDE_PLUGIN_ROOT}/guidelines/TESTING_GUIDELINES.md`

Two mistakes dominate review here: a **reader that is not thread-safe** while its step uses a
`taskExecutor`, and **state not reset in `@BeforeStep`**. Bean names are a runtime contract with the
job service's `@Qualifier`.
