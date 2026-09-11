# MACO — Service Guidelines (`maco-service`)

## Declaration

```java
package com.opencell.maco.service.calculation;

import com.opencell.maco.exception.BusinessException;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

/**
 * The consumption calculation job service.
 *
 * @author {Author}
 */
@Service
public class MacoCalculConsumptionService extends MacoCommonService {

    private final Logger log = LogManager.getLogger(MacoCalculConsumptionService.class);

    @Autowired
    private MacoPodMacoRepository macoPodMacoRepository;
}
```

- **`@Service`** on every business service (98 of them; `@Component` is not used here).
- **`@Autowired` field injection** is the established house style. Constructor injection is
  acceptable for new classes but do **not** refactor existing services to it as a side effect.
- Sub-package by domain: `service.calculation`, `service.execution`, `service.treatment`, …

## Logging — Log4j2, not SLF4J

```java
private final Logger log = LogManager.getLogger(Xxx.class);   // org.apache.logging.log4j.*
```

Never `org.slf4j.Logger` and never `System.out`. Use parameterised messages (`log.info("… {}", v)`).
Log at `ERROR` with the exception object (`log.error(msg, e)`), never just `e.getMessage()`.

## Transactions — read this carefully

**`maco-service` contains zero `@Transactional` annotations.** Transaction boundaries in MACO come from:

- **`maco-repository`** — `@Transactional` is declared there (~41 usages), on the repository methods
  that need it, notably `@Modifying` bulk operations;
- **Spring Batch** — each chunk-oriented step commits per chunk under the step's
  `PlatformTransactionManager` (see BATCH_GUIDELINES).

So: **do not scatter `@Transactional` across services** to "be safe" — it is not the local pattern and
changes the commit semantics batch steps rely on. If a new service genuinely needs its own atomic
unit of work, annotate that one method, and say why in Javadoc and in the PR description.

## Exceptions

Throw the typed exceptions from `maco-exception`, never a bare `RuntimeException`:

| Exception | Use for |
|-----------|---------|
| `BusinessException` | checked base for business failures |
| `ValidationException` | invalid input/state |
| `MissingParamException` | a required job/request parameter is absent |
| `ResourceNotFoundException` | entity lookup failed (also drives the 404 in controllers) |
| `EntityNotFoundException`, `PodNotFoundException` | specific lookup failures |
| `SearchKeysNotFoundException` | unknown search key in a `/list` filter |
| `JobIsAlreadyRunningException` | a job launch is rejected because one is in flight |
| `IgnoredException` | a record is deliberately skipped by a flow treatment |
| `ConsumptionDateIsNullException`, `ProfileCalendarChangedException`, `ResourceNotEqualsException` | flow-specific business rules |

`BusinessException` extends `Exception` (**checked**) — propagate it rather than wrapping it in a
runtime exception. Add a new exception type to `maco-exception` only when an existing one does not fit.

## Job services

Services that launch a Spring Batch job follow a fixed shape (see `MacoCalculConsumptionService`):

1. `setParams(params)` then reject an empty map with `MissingParamException`.
2. Reset counters/report state (`setNbOk`, `setNbError`, `setReport`).
3. Resolve the caller: `setUser(ofNullable(getParams().get(USER_KEY)).orElse("no-user-found"))`.
4. Validate business parameters (e.g. `checkJobTreatmentDate`).
5. Build `JobParameters` via `JobParametersBuilder`, then `jobLauncher.run(job, params)`.
6. Read results back from the `StepExecution` `ExecutionContext` keys the writer published
   (e.g. `CALC_CONS_OK`, `CALC_CONS_KO`, `CALC_CONS_COUNT`), and build the `JobResponse`.

Inject the job by qualifier — `@Autowired @Qualifier("calculConsumptionJob") Job job;` — matching the
`@Bean(name = …)` in the batch configuration. Declare the shared context keys as `public static final`
constants on the service so the writer and the service cannot drift apart.

## `MacoCommonService`

Most services extend `MacoCommonService`, which centralises parameter handling, the counters/report,
the `EntityManager`, MACO logging (`MacoLogBuilder`) and reference-data lookups. **Look there before
writing a helper** — duplicating one of its lookups is a common review finding.

## General

- Keep services stateless apart from the inherited job counters; never cache mutable business state
  in a field.
- Public methods need Javadoc: purpose, `@param`, `@return`, `@throws`.
- No business logic in controllers and none in repositories — it belongs here.
