# Overlay architecture and the core-override mechanism

> LAYERS OVER: nothing — this is new material with no core equivalent.
> CORE BASELINE: oc-be-tools 1.17.0

## What a war overlay is

An overlay repo is a standalone Maven aggregator (no `<parent>`). It declares core artifacts as
`provided` dependencies and core's web application as a `war`-typed **runtime** dependency:

```xml
<dependency>
  <groupId>com.opencellsoft</groupId><artifactId>opencell-admin-web</artifactId>
  <version>${opencell.version}</version><type>war</type><scope>runtime</scope>
</dependency>
```

`maven-war-plugin` unpacks core's war, then lays this module's files on top. The result is
`<overlay-module>/target/opencell.war`.

## Override precedence — what wins

1. A file at the same path in the overlay module's `src/main/webapp` or `src/main/resources`
   **replaces** core's copy. This is the normal, supported override.
2. `WEB-INF/classes` precedes `WEB-INF/lib/*.jar` on the war classloader, so a class compiled into
   the overlay war module **shadows** a same-FQN class from a core jar. This is the escape hatch.
3. Jars contributed by the overlay's own modules land in `WEB-INF/lib` alongside core's.

## Prefer extension over replacement

Ranked, best first:

1. **Add** a new class — no coupling to core internals.
2. **`@Specializes`** an existing core service and override only the methods you need — see
   `OVERLAY_SERVICE_DELTA.md`. This is the preferred way to change core behaviour.
3. **Replace a resource file** (xhtml, properties, config) via the war overlay — acceptable, but every
   entry must be registered in the repo `CLAUDE.md` override register and re-checked on core upgrade.
4. **Shadow a class by FQN** — last resort only. Maintenance cost is extreme: you inherit the whole
   file, and a core change to it is invisible to you until something breaks at runtime.

## The override register

The repo's `CLAUDE.md` carries the authoritative list of everything this overlay overrides. Adding an
entry is a reviewed decision, not an implementation detail. Three kinds exist:

- **File overrides** — same-path replacement via the war overlay.
- **Class FQN shadowing** — a class in the war module whose FQN matches a core class. Must be
  re-verified on every core upgrade.
- **Runtime overrides** — code that rewrites a core-shipped file on disk at boot (e.g. a
  `@Startup @Singleton` that overwrites a versions/config file). No static check catches these, which
  is exactly why they must be listed.

## `persistence.xml`

The overlay's `META-INF/persistence.xml` overrides core's, and normally exists for **one** reason: to
add the overlay model jar so Hibernate scans it for entities.

```xml
<jar-file>lib/opencell-model-${opencell.version}.jar</jar-file>
<jar-file>lib/opencell-elec-model-${project.version}.jar</jar-file>
```

**Any new jar containing `@Entity` classes must be added here**, or its entities are silently unmapped.
Because this file is an override, it must also be reconciled against core's version on every upgrade —
a persistence unit or property added in core is lost otherwise.

## Liquibase reaches the database through core's jar

Core ships **empty placeholder** changelogs inside `opencell-model.jar` at
`db_resources/changelog/{current,rebuild}/overlay.xml`, and core's master changelogs already
`<include>` them. The overlay module's build unzips that core jar, overwrites those two entries with
its own files, and re-jars the result into `WEB-INF/lib`.

Consequence: **the names and paths are fixed by core.** Renaming either file, or adding a third,
silently drops every migration with no build error. See `OVERLAY_DATABASE_DELTA.md`.

## Split package warning

Overlay entities commonly sit in `org.meveo.model` — the *same package* as core's, which is why they
compile without importing `@ObservableEntity` or `@CustomFieldEntity`. This works in a flat war
classloader, but it means:

- never rely on package-private access to core members;
- a core rename fails at **runtime**, not compile time;
- it will not survive any move to modular classloading.

Document it; do not try to fix it as a side effect of a feature ticket.

## Build pipeline

1. **Core must be built and installed first** — the overlay depends on `provided`/`war` core artifacts
   at the exact `opencell.version`. See `OVERLAY_WORKFLOW.md`.
2. `mvn clean package` from the repo root. Use the **full reactor** — not `-pl` — because the war
   overlay needs every module's jar.
3. Output: `<overlay-module>/target/opencell.war`.
4. Liquibase runs at application startup.

## Modules that are not in the reactor

Overlay repos typically carry folders that are **not** Maven modules — Postman collections, Jasper
reports, environment config, docker files, Keycloak realm exports. Nothing in the build validates
them. Treat a change there as unverified until manually exercised, and check whether a folder that has
a `pom.xml` is actually listed in `<modules>` before assuming the build covers it.
