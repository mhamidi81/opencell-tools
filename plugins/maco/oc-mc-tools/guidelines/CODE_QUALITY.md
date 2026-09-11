# MACO — Code Quality Guidelines

Applies to every module. Read CRITICAL_RULES.md first.

## Formatting

- **Tabs** for indentation in most of the codebase (some files use 4 spaces — **match the file you
  are editing**, never reformat a file you touch).
- Long lines are tolerated (the codebase runs well past 80 columns); do not rewrap existing code.
- Imports: no wildcard imports **except** `javax.persistence.*` in entities, which is the
  established style there. Static imports are used for assertions and `Optional.ofNullable`.
- **Never reformat code you did not functionally change.** A diff full of whitespace hides the real
  change and is a review rejection.

## Javadoc

Mandatory on:
- every class (with `@author` where the surrounding files carry one),
- every public method — purpose, `@param`, `@return`, `@throws`,
- every entity field, in the `/** Column {description} **/` form.

Javadoc and comments are written in **French in some modules and English in others** — match the
file. Explain **why**, not what the code obviously does. Non-obvious performance choices (a
projection instead of an entity, a chunk size, a native query) must say why.

## Null handling

- Return **`Optional<T>`** from lookups; never return `null` to signal "not found".
- `Optional.ofNullable(x).orElse(default)` is the house idiom for defaulting
  (`ofNullable(getParams().get(USER_KEY)).orElse("no-user-found")`).
- Guard method parameters that can legitimately be null (e.g. the Keycloak `principal`).
- `org.apache.commons.lang3.StringUtils` — `isBlank` / `isNotBlank` — for string checks, never
  `s != null && !s.isEmpty()`.

## Exceptions

- Throw the typed `maco-exception` classes (see SERVICE_GUIDELINES); never a bare
  `RuntimeException` or `Exception`.
- **Never swallow an exception.** `catch (Exception e) { }` and `catch` + `log.error(e.getMessage())`
  (losing the stack trace) are both review rejections — log with the exception object: `log.error(msg, e)`.
- Do not catch an exception just to rethrow it unchanged.
- Do not use exceptions for control flow, with the one sanctioned exception of `IgnoredException`
  marking a deliberately skipped flow record.

## Logging

- **Log4j2** only: `private final Logger log = LogManager.getLogger(Xxx.class);`
  (`org.apache.logging.log4j.*`). Never SLF4J, never `System.out`/`printStackTrace`.
- Parameterised messages: `log.info("Processed {} rows for {}", count, prm)` — never string
  concatenation.
- Levels: `error` for failures needing attention, `warn` for recoverable anomalies, `info` for job
  milestones, `debug`/`trace` for per-item detail. **Never log at `info` inside a per-item batch
  loop** — MACO jobs process very large volumes.
- Never log secrets, tokens, or full personal data. PRM/PDL identifiers are business keys and may be
  logged.

## Numbers and dates

- **`BigDecimal`** for every monetary value, quantity, price and coefficient — never `double`/`float`.
  Compare with `compareTo`, never `equals`. Always pass an explicit `RoundingMode` when rounding
  (`setScale(n, RoundingMode.HALF_UP)`).
- Dates: prefer `java.time` (`LocalDate`, `LocalDateTime`) in new code; keep `java.util.Date` where
  the surrounding entity uses it. Be explicit about timezone semantics on `DATE` columns — this is a
  known MACO defect class, and it must be covered by a test.

## Resources

- **try-with-resources** for every `Closeable` (files, streams, JDBC). MACO reads and writes many
  flow files; a leaked handle surfaces only under production volume.
- Use `java.nio.file.Files` / `Path` for file work.

## Performance — the MACO-specific ones

- **No unbounded `findAll()`** into a `List` on a batch path — page, project, or stream.
- **Watch EAGER `@ManyToOne`**: loading entities in a high-volume read path triggers JOIN/N+1
  blow-ups. Use a flat projection DTO (ENTITY_GUIDELINES).
- **No query inside a per-item loop.** Pre-load a keyed `Map` in `@BeforeStep` instead.
- Batch writes with `saveAll`, never `save()` per item.

## Dead code and scope

- Do not add speculative configuration, abstractions, or "flexibility" that the ticket did not ask for.
- Remove imports/fields your own change orphaned; leave unrelated dead code alone (mention it in the PR).
- **`@SuppressWarnings("ALL")` appears in some legacy batch configs — do not copy it into new code.**
