# Opencell Project - Database Guidelines

> **Note**: This document contains database and Liquibase guidelines. For general project guidelines, see [CLAUDE.md](./CLAUDE.md).

## Table of Contents
- [Liquibase Changesets](#liquibase-changesets)
- [File Structure](#file-structure)
- [Column Type Mappings](#column-type-mappings)
- [Index Best Practices](#index-best-practices)
- [Multitenancy Support](#multitenancy-support)
- [Example Patterns](#example-patterns)

---

## Liquibase Changesets

All changes to database require Liquibase changesets.

### Changeset Conventions

- **Changeset ID**: Should consist of ticket number and a date
  - Example: `#INTRD-12668-20231002`
- **Author**: Use your name as author
- **Constraints**: Add applicable constraints:
  - Primary keys
  - Foreign keys
  - Unique constraints (but NOT on UUID fields)
- **Primary key naming**: Table name plus `_pkey` suffix
  - Example: `cat_price_update_pkey`

---

## File Structure

### current/structure.xml

- Contains the complete changeset with all database changes
- Changes are applied incrementally to existing databases
- Location: `opencell-model/src/main/resources/db_resources/changelog/current/structure.xml`

### rebuild/structure.xml

Contains database structure organized by sections. Used for rebuilding database from scratch.

**Must include:**

1. **Sequences section** (before `<!-- end sequence -->`)
   - Add `<createSequence>` statements

2. **Tables section** (before `<!-- end tables -->`)
   - Add `<createTable>` statements with all columns

3. **Foreign Keys section** (before `<!-- end fk -->`)
   - Add `<addForeignKeyConstraint>` statements

4. **Reference changeset** (before `<!-- liquibase_update_old_data_to_structure -->`)
   - Add empty changeset reference: `<changeSet id="#TICKET-DATE" author="yourname" />`

Location: `opencell-model/src/main/resources/db_resources/changelog/rebuild/structure.xml`

---

## Column Type Mappings

Use these type mappings for consistency:

| Java Type | Liquibase Type | Notes |
|-----------|----------------|-------|
| Boolean | `${type.boolean}` | For boolean columns |
| JSON/JSONB | `${type.json}` | For JSON/JSONB columns |
| BigDecimal | `numeric(23,12)` | Provides 23 total digits with 12 decimal places |
| Auto-increment ID | `${id.auto}` | For auto-increment ID columns |
| String | `varchar(255)` | Or other appropriate length |
| Long/Integer | `bigint` or `integer` | Depending on size requirements |
| Date/Timestamp | `timestamp` or `date` | Depending on precision needed |

### Choosing a Column Type — Match Semantics and the Nearest Analogous Column

**CRITICAL: Pick a column type from the field's *meaning* and its JPA mapping, mirroring the nearest *semantically* analogous existing column — not one that merely looks similar.**

- `date` vs `timestamp` is a semantic choice, not a stylistic one: a calendar-date value (`@Temporal(TemporalType.DATE)` — e.g. a per-index target *calendar date*) maps to `date`; a moment-in-time business/audit timestamp maps to `timestamp`. A calendar-date audit column is **not** the same as a run-level business timestamp — do not copy the latter's type onto the former.
- Before adding a column, find the closest existing column that plays the **same role** in a sibling entity and mirror its type, length, nullability and mapping. "Superficially similar name" (any `*_date`) is not "semantically analogous".
- The Liquibase type must agree with the entity mapping: `@Temporal(TemporalType.DATE)` ↔ `date`, `@Temporal(TemporalType.TIMESTAMP)` ↔ `timestamp`, `BigDecimal` money/factor ↔ `numeric(23,12)`, boolean ↔ `${type.boolean}`.

---

## Index Best Practices

### Lowercase Indexes for Case-Insensitive Search

**Indexes on string fields for case-insensitive search must be lowercase:**

```xml
<sql>CREATE INDEX flat_file_orig_name_index ON ${db.schema.adapted}flat_file (lower(file_original_name))</sql>
```

This allows queries using `lower()` function to use the index:

```sql
SELECT * FROM flat_file WHERE lower(file_original_name) = lower(:fileName)
```

### Don't Abuse Indexes

**Remember:** Inserting, updating, and deleting requires index and FK update/check.

- Only create indexes that will actually be used in queries
- Too many indexes slow down write operations
- Balance between read performance and write performance

### Foreign Keys to Massive Tables

**CRITICAL: There should be no foreign keys to massive and especially partitioned tables**

Examples of massive tables:
- `wallet_operation`
- `rated_transaction`

**Why?**
- Foreign key checks significantly slow down inserts
- Partitioned tables have special constraints
- Massive tables typically have millions/billions of records
- FK check on such tables is expensive

**Alternative approaches:**
- Use application-level referential integrity checks
- Document the relationship in code comments
- Validate references before inserting

---

## Multitenancy Support

Opencell supports multitenancy in the form of a separate schema per tenant.

### In structure.xml Files

**Use `${db.schema.adapted}` prefix in front of table names** in SQL update statements:

```xml
<sql>ALTER TABLE ${db.schema.adapted}ar_account_operation RENAME COLUMN occ_code TO code;</sql>
```

### In Native Queries (Java Code)

**Use `{h-schema}` prefix in front of table names** in native queries:

```sql
UPDATE {h-schema}billing_rated_transaction rt
SET status='BILLED',
    updated=now(),
    aggregate_id_f=pending.aggregate_id_f
FROM {h-schema}billing_rated_transaction_pending pending
WHERE status='OPEN' AND rt.id=pending.id
```

### Database Compatibility

Opencell supports **PostgreSQL and Oracle** databases.

SQL/JPA queries that use non-standard functions must provide a version for both databases.

**Use `dbms` attribute when needed:**

```xml
<changeSet id="#INTRD-12345-20231001" author="andrius" dbms="postgresql">
    <!-- PostgreSQL-specific SQL -->
</changeSet>

<changeSet id="#INTRD-12345-20231001" author="andrius" dbms="oracle">
    <!-- Oracle-specific SQL -->
</changeSet>
```

---

## Example Patterns

### Example: Complete Changeset Pattern

```xml
<!-- In current/structure.xml -->
<changeSet id="#INTRD-34243-20251010" author="andrius">
    <createSequence sequenceName="cpq_indexation_seq" />
    <createTable tableName="cpq_indexation">
        <column name="id" type="bigint" autoIncrement="${id.auto}">
            <constraints nullable="false" primaryKey="true" primaryKeyName="cpq_indexation_pkey" />
        </column>
        <column name="code" type="varchar(255)">
            <constraints nullable="false" />
        </column>
        <column name="description" type="varchar(2000)" />
        <column name="value" type="numeric(23,12)" />
        <column name="disabled" type="${type.boolean}">
            <constraints nullable="false" />
        </column>
        <column name="metadata" type="${type.json}" />
        <!-- other columns -->
    </createTable>
    <addForeignKeyConstraint
        constraintName="fk_indexation_parent"
        baseTableName="cpq_indexation"
        baseColumnNames="parent_id"
        referencedTableName="parent_table"
        referencedColumnNames="id" />
</changeSet>
```

### Example: Rebuild Structure Pattern

```xml
<!-- In rebuild/structure.xml -->

<!-- 1. Add to sequence section (before <!-- end sequence -->) -->
<changeSet id="#INTRD-34243-20251010-seq" author="andrius">
    <createSequence sequenceName="cpq_indexation_seq" startValue="1" />
</changeSet>

<!-- 2. Add to tables section (before <!-- end tables -->) -->
<changeSet id="#INTRD-34243-20251010-tbl" author="andrius">
    <createTable tableName="cpq_indexation">
        <column name="id" type="bigint" autoIncrement="${id.auto}">
            <constraints nullable="false" primaryKey="true" primaryKeyName="cpq_indexation_pkey" />
        </column>
        <column name="code" type="varchar(255)">
            <constraints nullable="false" />
        </column>
        <!-- same structure as in current/structure.xml -->
    </createTable>
</changeSet>

<!-- 3. Add to FK section (before <!-- end fk -->) -->
<changeSet id="#INTRD-34243-20251010-fk" author="andrius">
    <addForeignKeyConstraint
        constraintName="fk_indexation_parent"
        baseTableName="cpq_indexation"
        baseColumnNames="parent_id"
        referencedTableName="parent_table"
        referencedColumnNames="id" />
</changeSet>

<!-- 4. Add reference at end (before <!-- liquibase_update_old_data_to_structure -->) -->
<changeSet id="#INTRD-34243-20251010" author="andrius" />
```

---

## Best Practices

1. **Always create both changesets**: One in `current/structure.xml` and corresponding ones in `rebuild/structure.xml`
2. **Test changesets**: Verify they run cleanly on a fresh database
3. **Use consistent naming**: Follow table and constraint naming conventions
4. **Document complex changes**: Add comments for non-obvious migrations
5. **Avoid data loss**: Use appropriate column types and constraints to prevent data loss
6. **Version control**: Always commit changeset files with related entity changes
