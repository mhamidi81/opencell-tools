# Overlay critical rules

> LAYERS OVER: oc-be-tools/guidelines/CRITICAL_RULES.md
> CORE BASELINE: oc-be-tools 1.17.0
> PRECEDENCE: every core rule applies unchanged unless marked REPLACES below.

Core rules 1–10 all apply. They are **not** restated here — read them from the core file.

---

## OV-1 No AGPL license header — REPLACES core rule 2

Overlay repositories hold vertical/client code, not AGPL core code. Do **not** add an AGPL header to
overlay source files, and do not flag a missing one in review.

*Verified:* 2 of 258 `.java` files under `opencell-elec-*` carry one, versus 561 of 844 in core's
`opencell-model`. The two that do are strays.

## OV-2 Package root is decided by who must discover the class

This is the single most consequential overlay rule, because every failure mode is **silent** — the
code compiles, deploys, and simply never runs.

| What | Required placement | Discovery mechanism | Failure if misplaced |
|---|---|---|---|
| JAX-RS resource impl | under `org.meveo.apiv0.rest.*` **and** `extends BaseRs` | core's `JaxRsActivatorApiV0123` runs `new Reflections("org.meveo.apiv0.rest").getSubTypesOf(BaseRs.class)` | endpoint does not exist; no error |
| JPA entity | any package, but **inside a jar listed in the overlay `persistence.xml`** | Hibernate scans the listed `<jar-file>`s | entity not mapped; runtime failure on first use |
| Service / job / startup bean | any package | CDI/EJB discovery by type | — |
| ScriptInstance | `com.oc.**` | deployed by REST, compiled at runtime | — |

Convention on top of the mechanism: use `org.meveo.*` when core must discover or reference the class
(entities, entity services, apiv0 REST, jobs that extend a core job), and `com.oc.*` for everything
vertical-specific (scripts, script helpers, POD jobs, startup singletons).

## OV-3 Never edit core from the overlay repo

A change needed in `opencell-core` belongs in that repo, followed by an `opencell.version` bump here.
Editing core from an overlay checkout produces a build that only works on your machine.
See `OVERLAY_WORKFLOW.md` for the core-repo location and branch-correspondence rules.

## OV-4 `javax` vs `jakarta` — clarifies core rule 1

Core rule 1 stands for **Jakarta EE** packages: `jakarta.persistence`, `jakarta.ejb`, `jakarta.inject`,
`jakarta.ws.rs`, `jakarta.validation`.

It does **not** apply to `javax.xml.*` (`javax.xml.parsers`, `javax.xml.transform`,
`javax.xml.validation`) — those are **JDK** APIs, are correct, and must not be "fixed". 11 of the 13
overlay files importing `javax.*` are exactly this case.

`HomeInfo`'s `javax.validation.constraints.NotNull` **is** a real defect, and a serious one: a
jakarta-namespace validator never sees a `javax`-namespace annotation, so the constraint is **inert**.
Treat it as a bug to fix, not a pattern to copy.

## OV-5 Jira

Primary project key **MACRD** (also `INTOP` for ops/infra and `INTRD` for core-driven work). Story
content lives in the same four custom fields as core — see core CRITICAL_RULES rule 8; the IDs are not
repeated here.

## OV-6 Version lock-step

`opencell.version` in the root pom must equal the core release the overlay is built against. Changing
it is a deliberate upgrade with its own verification pass, never an incidental edit.
