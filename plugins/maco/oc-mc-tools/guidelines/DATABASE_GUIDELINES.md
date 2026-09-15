# MACO — Database Guidelines (Flyway)

> MACO uses **Flyway**, not Liquibase. There are no changesets, no `db_resources/*.xml`.

## Location and configuration

```
maco-db-sql-scripts/src/main/resources/db/
  postgres/   # the ONLY Flyway location — spring.flyway.locations=classpath:db/postgres/
  manual/     # NOT executed by Flyway — DBA/ops scripts run by hand
```

`spring.flyway.enabled=true` and `spring.flyway.locations=classpath:db/postgres/`.
Migrations run automatically at application startup **and** before each integration-test class
(`DatabaseCleanupTestExecutionListener` drops and re-migrates the schema).

> An Oracle profile exists at the application level (`application-oracle.properties`), but there is
> **no `db/oracle` migration directory**. Write PostgreSQL DDL only, unless the ticket explicitly
> introduces Oracle migrations.

## Naming

**Versioned** — applied once, in version order:

```
V{major}.{minor}[.{patch}]__{snake_case_description}.sql
```

Examples: `V2.4.6__horodate_without_time_zone.sql`,
`V1.3.5__add_table_elec_service_facturable.sql`.

**Repeatable** — re-applied whenever the file's checksum changes, after all versioned ones:

```
R__{kebab-or-snake-description}.sql
```

Only for idempotent maintenance (e.g. `R__fix-sequence-for-all-maco-tables.sql`,
`R__force_null_boolean_to_false.sql`). Never put a schema change in an `R__` script.

## Rules

1. **Never modify a migration that has been applied.** Flyway validates checksums; editing an
   applied script breaks every existing environment. Add a **new** versioned script instead.
2. **Pick the next free version number** — list the directory sorted by version (`sort -V`) and take
   the next patch. Verify no teammate's branch already claims it.
3. **One concern per script**, with a leading SQL comment stating what and why (comments are
   written in French in this repository — match the surrounding style).
4. **Every new table needs its sequence**, named `{table}_id_seq`, matching the entity's
   `@SequenceGenerator`. Creating the table without the sequence makes the entity fail at runtime,
   not at build time.
5. **Additive by default.** Prefer `ADD COLUMN` with a sensible default over destructive changes.
   A `DROP COLUMN` / `DROP TABLE` needs an explicit statement in the ticket.
6. **Data migrations** (`V…__init_data`, `…_add_error_code_…`) must be idempotent-safe where
   possible — guard inserts against duplicate keys.
7. **Entity and migration land in the same commit.** A migration without its entity change (or the
   reverse) breaks startup or the test suite.
8. `db/manual/` scripts are **not** run by Flyway. Anything placed there must also be communicated
   to ops — do not use it to sneak a schema change past the migration history.

## Checklist before committing a schema change

- [ ] Version number is free and greater than every applied one
- [ ] Sequence created for a new table, name matches `@SequenceGenerator`
- [ ] Entity fields ↔ columns match exactly (name, nullability, type)
- [ ] Existing applied scripts untouched
- [ ] Integration tests pass (they re-run the full migration chain from scratch)
