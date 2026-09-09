# oc-ov-tools

Overlay development toolkit for Opencell **overlay** repositories — projects that build the final
`opencell.war` by layering their own jars and resources on top of core Opencell's war.

## Requires oc-be-tools

`oc-ov-tools` is a **delta layer**. The `oc-be-tools` guidelines stay authoritative and load first;
these files state only what differs. Install both, backend first:

```bash
/plugin install oc-be-tools@opencell-tools
/plugin install oc-ov-tools@opencell-tools
```

No configuration is needed — `guidelines/_CORE_BASE.md` locates the core guidelines automatically
(marketplace checkout → versioned plugin cache → local source checkout) and **hard-stops** if
`oc-be-tools` is missing, rather than reviewing against half a rulebook.

## Why an overlay needs its own layer

Following the core guidelines unmodified in an overlay produces wrong code and noisy reviews:

| Core says | Overlay reality |
|---|---|
| AGPL header on every file | Overlay code is vertical/client code — no header |
| Register REST resources in a JAX-RS activator | There is none; core scans `org.meveo.apiv0.rest` with Reflections |
| `BaseCrudApi` + `@Value.Immutable` DTOs | apiv0 `BaseApi` + plain POJO DTOs |
| Liquibase in `changelog/current/structure.xml` | `db_resources/{current,rebuild}/overlay.xml`, injected into core's jar |
| Services via `@Inject` | Scripts are not CDI beans — `@Inject` silently NPEs |
| *(nothing)* | Overriding core: `@Specializes`, war-overlay file replacement, FQN shadowing |

## Profiles

Two overlay conventions exist and neither is wrong. `guidelines/OVERLAY_PROFILES.md` holds the axis
table; a repo declares its own in a `## Overlay profile` block in its `CLAUDE.md`.

- **`vertical-energy`** — `opencell-elec-*`, `org.meveo.*` + `com.oc.*`, apiv0, `/ve/`, no table prefix
- **`template`** — `opencell-ext-*`, `com.opencell.ext.*`, `BaseCrudApi` + Immutables, `/api/rest/ext/`, `ext_` prefix

## What it provides

| Type | Name | Purpose |
|---|---|---|
| Command | `/oc-ov-implement` | Orchestrate a full ticket, with core-repo, branch-target and Liquibase gates |
| Command | `/oc-ov-review` | Guideline + conformance + Sonar review, plus nine overlay mechanical gates |
| Command | `/oc-ov-calculate-ai-use` | Thin alias over the shared backend AI-usage command |
| Agent | `oc-ov-entity-builder` | Entities, enums and the paired `overlay.xml` changesets |
| Agent | `oc-ov-service-builder` | Core-service extension via `@Specializes` |
| Agent | `oc-ov-api-builder` | apiv0 Rs interface + RsImpl + Api bean + POJO DTO |
| Agent | `oc-ov-script-builder` | ScriptInstances and Jobs |
| Agent | `oc-ov-pr-reviewer` | Overlay-aware reviewer (no AGPL/Immutables/activator false positives) |
| Skills | `oc-ov-{entity,service,api,db,script,test,postman,jasper,override}-guide` | Load core guidelines, then the matching delta |

Reused unchanged from `oc-be-tools`: `oc-be-service-builder` (new services), `oc-be-test-generator`,
`oc-be-postman-generator`, `oc-be-conformance-reviewer`.

## Three rules whose failure is silent

1. A REST impl must **both** extend `BaseRs` **and** live under `org.meveo.apiv0.rest.*`, or the
   endpoint does not exist. No build error.
2. Renaming or relocating either `overlay.xml` drops every migration. No build error.
3. `@Inject` in a ScriptInstance compiles and yields `null` at runtime. Use `getServiceInterface`.
