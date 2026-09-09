# ScriptInstances

> LAYERS OVER: nothing — no core equivalent. Core's CODE_QUALITY applies in full, and
> SERVICE_GUIDELINES §Exception Handling, §Logging Standards and §Performance apply.
> CORE BASELINE: oc-be-tools 1.17.0

## What a ScriptInstance is

Script source is **POSTed to a running Opencell** and compiled there at runtime. Scripts are **not**
packaged into the war. The script module exists for IDE classpath and for the deploy mojo — its
`maven-jar-plugin` (and test compilation) are deliberately skipped.

Two consequences that catch everyone:

- Nothing in `src/test/java` of the script module ever runs. Do not put tests there.
- A script compiles fine in the IDE against the full classpath and can still fail at runtime inside
  Opencell.

## Service access — the hardest rule

**`@Inject` does not work in a script.** A ScriptInstance is not a CDI bean. Injection points are never
processed, the field stays `null`, and you get an NPE in production from code that compiled cleanly.

Always:

```java
private RatedTransactionService ratedTransactionService =
        (RatedTransactionService) getServiceInterface("RatedTransactionService");
```

`getServiceInterface(name)` is a **JNDI lookup by EJB bean name**
(`java:global/${opencell.moduleName:-opencell}/<name>`). Two implications:

- The name is the **bean name**, not the CDI type. A service specialized with `@Specializes` under a
  different bean name is **not** returned here — ask for it by its own name. See
  `OVERLAY_SERVICE_DELTA.md`.
- A wrong name returns `null` rather than throwing, so the failure surfaces later as an NPE.

## Base classes

Default to core's `org.meveo.service.script.Script`. Vertical base classes live in the utility module
(e.g. an `OcValoScript extends Script` used by valuation scripts, plus import/invoice-creation bases).
Pick the one the neighbouring scripts in the same package use.

## Entry point

```java
public void execute(Map<String, Object> context) throws BusinessException
```

Read job/workflow inputs from `context`. Report progress and problems with `addReport(...)`, and
rethrow `BusinessException` for genuine failures — swallowing an exception makes a job report success.

## Serialization

Script classes are `Serializable`. Any non-serializable field (services, parsers, connections) must be
`transient`, and service handles obtained via `getServiceInterface` should be
`private final transient`.

## Shared code

Constants, DTOs and helpers shared between scripts belong in the **utility module** (`com.oc.*`),
never copy-pasted between scripts. That module *is* packaged into the war, so it is ordinary
compiled code and can use normal Java practices.

## Deployment

```bash
cd <script-module>
mvn opencell:deploy-scripts@deploy-scripts -P deploy-script            # all scripts
mvn opencell:deploy-scripts@deploy-scripts -P deploy-script -Dopencell.script.source=com/oc/valo/
mvn opencell:deploy-scripts@deploy-scripts -P deploy-script -Dopencell.url=https://energie-dev.oc-sb.eu
```

This **writes to a live Opencell instance** — confirm the target URL before running it.

The Postman collection of scripts is **generated**:

```bash
mvn opencell:create-postman@create-postman -P deploy-script
```

Never hand-edit the generated collection; regenerate it.

## Which core guidelines do not apply

Core's `@Stateless`, CDI, transaction-attribute and concurrency sections describe EJBs and have no
meaning for a ScriptInstance.
