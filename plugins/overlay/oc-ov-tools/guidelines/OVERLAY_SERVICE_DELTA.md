# Overlay service layer

> LAYERS OVER: oc-be-tools/guidelines/SERVICE_GUIDELINES.md
> CORE BASELINE: oc-be-tools 1.17.0
> PRECEDENCE: every core section applies unchanged unless marked REPLACES below.

The core service guidelines apply in full — conventions, business-rule placement, validation,
exception handling, logging, configuration, concurrency, performance. They are not restated here.

There are three distinct situations. Pick the right one before writing anything.

---

## 1. A new overlay service

Identical to core. `@Stateless class XService extends BusinessService<X>` in the overlay's ejb module,
injecting core services with plain `@Inject` (they are `provided`-scope EJBs in the same deployment).
Nothing in the core guideline changes. Use the reused `oc-be-service-builder` agent.

## 2. Changing the behaviour of a core service — `@Specializes` — PREFERRED

Do **not** copy a core service and edit it. Extend it and override only the methods you need:

```java
@Stateless(name = "OverlayBillingAccountService")
@Specializes
public class BillingAccountService extends org.meveo.service.billing.impl.BillingAccountService {

    @Override
    public BillingAccount update(BillingAccount entity) throws BusinessException {
        // vertical-specific rule
        return super.update(entity);
    }
}
```

Rules:

- **Extend the core bean class directly.** CDI specialization only applies to the immediate superclass;
  an intermediate class breaks it.
- **Same bean kind and scope.** A `@Stateless` bean specializes a `@Stateless` bean.
- **Give it a distinct EJB name.** `@Stateless(name = "OverlayXxxService")`. In a war, core's jars and
  the overlay's jars form a single EJB module, so two beans with the same unqualified class name clash.
- **Override the minimum, and call `super`** wherever the core behaviour should still run.
- The specializing bean **inherits the parent's bean types and qualifiers**, and the parent CDI bean is
  disabled — so every `@Inject`ed `BillingAccountService` in core now resolves to yours.
- **Re-verify every overridden signature on each core upgrade.** A changed core signature turns your
  override into an unrelated overload that is never called, silently.
- Record the specialization in the repo `CLAUDE.md` override register.

### The blast radius is application-wide

Core has ~400 `@Stateless` services. Specializing one changes behaviour for **every** core caller, not
just overlay code. Confirm that is what the ticket actually asks for. If only overlay code needs the
new behaviour, add a new service instead.

### `@Specializes` does NOT reach scripts — know this before you rely on it

`@Specializes` is a **CDI** mechanism: it redirects `@Inject`-by-type. Scripts do not use CDI. They
call:

```java
SomeService s = (SomeService) getServiceInterface("SomeService");
```

which resolves through `EjbUtils.getServiceInterface` to a **JNDI lookup by EJB bean name**:

```
java:global/${opencell.moduleName:-opencell}/<serviceInterfaceName>
```

Specialization does not unbind the core EJB from JNDI, so `getServiceInterface("BillingAccountService")`
still returns **core's** bean. Consequences:

- A specialization changes `@Inject` call sites but **not** the ~400+ script call sites.
- If a script must get the specialized behaviour, it has to ask for it by name:
  `getServiceInterface("OverlayBillingAccountService")`.
- When a ticket says "change how X behaves everywhere", `@Specializes` alone does not deliver that.
  Say so, and agree the approach before implementing.

## 3. Full replacement (FQN shadowing) — discouraged, last resort

Putting a class with a core FQN into the overlay war module shadows core's copy (`WEB-INF/classes`
precedes `WEB-INF/lib`). Only justified when the method you must change is `private`/`final`, or the
class is not proxyable.

The cost is extreme: you inherit the entire file, and every future core change to it is invisible until
something breaks at runtime. If you do it: register it in the repo `CLAUDE.md` override register, note
the core version it was forked from, and diff it against core on every upgrade.

---

## Startup singletons

`@Startup @Singleton` beans (typically `com.oc.startup`) must be **idempotent** and must never throw
out of `@PostConstruct` — a failure there fails the whole deployment. If one rewrites a file on disk,
it is a runtime override: register it.

## Not applicable

Core's partitioning and archiving sections describe core infrastructure and have no overlay counterpart.
