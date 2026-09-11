# MACO — Spring Batch Guidelines (`maco-batch-processing`)

The largest module after the DTOs (~180 classes): ~40 readers, ~47 processors, ~45 writers.
Chunk-oriented steps launched from a job service (see SERVICE_GUIDELINES → *Job services*).

## Package layout

| Package | Contents |
|---------|----------|
| `config` | `@Configuration @EnableBatchProcessing` classes declaring `Step` and `Job` beans |
| `readers` | `ItemReader` implementations, suffix `ItemReader` |
| `processors` | `ItemProcessor` implementations, suffix `ItemProcessor` |
| `writers` | `ItemWriter` implementations, suffix `ItemWriter` |
| `listeners` | step/job listeners |
| `tasklet` | `Tasklet` steps (non chunk-oriented work) |
| `partition` | `Partitioner` implementations, suffix `Partitioner` |
| `collectors` | result collection helpers |
| `dto`, `dto.builder` | batch-local transport objects |

One class per role; do not merge a reader and a processor.

## Job configuration

```java
@Configuration
@EnableBatchProcessing
public class CalculConsumptionBatchConfiguration {

    @Bean(name = "calculConsumptionStep1")
    public Step calculConsumptionStep1(JobRepository jobRepository,
            PlatformTransactionManager transactionManager, /* repositories, services … */) {
        return new StepBuilder("calculConsumptionStep1")
                .repository(jobRepository)
                .transactionManager(transactionManager)
                .<MacoPodMaco, List<MacoBillableConsumption>>chunk(100)
                .reader(new CalculConsumptionItemReader(macoPodMacoRepository))
                .processor(new CalculConsumptionItemProcessor(/* … */))
                .writer(new CalculConsumptionItemWriter(/* … */))
                .taskExecutor(new SimpleAsyncTaskExecutor())
                .build();
    }

    @Bean(name = "calculConsumptionJob")
    public Job calculConsumptionJob(JobRepository jobRepository,
            @Qualifier("calculConsumptionStep1") Step step1) {
        return new JobBuilder("calculConsumptionJob")
                .repository(jobRepository)
                .incrementer(new RunIdIncrementer())
                .flow(step1).end().build();
    }
}
```

Rules:

- **Name every bean explicitly** — `@Bean(name = "…")`. The job service injects it by
  `@Qualifier`, so the bean name is a contract: renaming it breaks the launcher at runtime, not at
  compile time.
- Bean name convention: job `{domain}Job`, steps `{domain}Step1`, `{domain}Step2`, …
- Components are **constructed by hand** in the configuration (`new XxxItemReader(repo)`) and
  receive their dependencies as **constructor parameters**, which the `@Bean` method itself receives
  by injection. Readers/processors/writers are therefore **not** `@Component` beans.
- `RunIdIncrementer()` on the job so it can be relaunched with identical business parameters.
- `.taskExecutor(new SimpleAsyncTaskExecutor())` enables multi-threaded steps — **only** with a
  thread-safe reader (see below).
- Chunk size is explicit (100 is typical). Justify a materially different size in the PR.

## Readers

```java
@StepScope
public class XxxItemReader implements ItemReader<Xxx> {

    private final Queue<Xxx> queue = new ConcurrentLinkedQueue<>();
    private final Logger log = LogManager.getLogger(XxxItemReader.class);

    public XxxItemReader(XxxRepository repository) { this.repository = repository; }

    @BeforeStep
    public void beforeStep(StepExecution stepExecution) {
        queue.clear();
        String param = stepExecution.getJobParameters().getString(MacoCommonService.CF_XXX);
        // load the working set into the queue
    }

    @Override
    public Xxx read() { return queue.poll(); }
}
```

- **`@StepScope` on every reader, processor and writer** — state must not leak between executions.
- **Thread safety is mandatory** when the step uses a `taskExecutor`: the house pattern is to load
  the working set in `@BeforeStep` into a **`ConcurrentLinkedQueue`** and `poll()` it in `read()`.
  A reader holding a plain `List` + index cursor is a race condition — it will silently skip or
  duplicate rows under a `SimpleAsyncTaskExecutor`.
- **Clear all state in `@BeforeStep`** (`queue.clear()`, counters to 0) — never rely on construction.
- Read job parameters through `stepExecution.getJobParameters()`, using the `MacoCommonService`
  constants (`CF_…`), never a hard-coded string literal.
- For large reads, prefer a **projection DTO** (`select new …`, see ENTITY_GUIDELINES) or
  `JdbcTemplate` with a `BeanPropertyRowMapper` over materialising entities with EAGER relations.

## Processors

- `ItemProcessor<I, O>`; `I` and `O` may differ (the MACO steps often map one entity to a
  `List<Other>`).
- **Returning `null` filters the item out** of the chunk — this is the sanctioned way to skip a
  record, and it must be logged.
- No persistence in a processor: it transforms, the writer saves.
- Business rules that reject a record throw the matching `maco-exception` type (e.g.
  `IgnoredException` for a deliberate skip).

## Writers

```java
@StepScope
public class XxxItemWriter implements ItemWriter<Xxx> {

    private final AtomicInteger ok = new AtomicInteger();
    private final AtomicInteger ko = new AtomicInteger();

    @BeforeStep public void beforeStep(StepExecution se) { ok.set(0); ko.set(0); }

    @AfterStep public void afterStep(StepExecution se) {
        se.setWriteCount(ok.get());
        se.setRollbackCount(ko.get());
        ok.set(0); ko.set(0);
    }

    @Override public void write(List<? extends Xxx> list) throws Exception {
        repository.saveAll(/* the valid subset */);
    }
}
```

- Counters are **`AtomicInteger`** (steps are multi-threaded), reset in both `@BeforeStep` and
  `@AfterStep`.
- Publish results through the `StepExecution` — `setWriteCount` / `setRollbackCount`, or
  `ExecutionContext` keys — because that is what the job service reads back to build its
  `JobResponse`. **Keys are `public static final` constants on the job service**
  (`CALC_CONS_OK`, `CALC_CONS_KO`, `CALC_CONS_COUNT`), never inline strings on either side.
- Batch the writes (`saveAll`), never one `save()` per item.
- Never swallow a persistence exception silently: count it as KO **and** log it with the exception.

## Partitioning

Use a `Partitioner` (suffix `Partitioner`, package `partition`) to split a large working set across
threads by a business key. Each partition's `ExecutionContext` carries only the key range — never
entities.

## Review checklist

- [ ] `@StepScope` on reader/processor/writer
- [ ] All mutable state reset in `@BeforeStep`
- [ ] Reader is thread-safe if the step has a `taskExecutor`
- [ ] Counters are atomic and published to the `StepExecution`
- [ ] Context/parameter keys are shared constants, not literals
- [ ] Bean names match the `@Qualifier` used by the job service
- [ ] No unbounded `findAll()` into a `List`
- [ ] Chunk size explicit and justified
