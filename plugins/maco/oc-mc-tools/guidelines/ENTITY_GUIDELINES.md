# MACO — Entity Guidelines (`maco-model`)

> Read CRITICAL_RULES.md first. `javax.persistence.*` only — **never** `jakarta.*`.

## Table of Contents
- [Conventions](#conventions)
- [Identifier strategies](#identifier-strategies)
- [Field types](#field-types)
- [Relationships](#relationships)
- [Projection DTOs](#projection-dtos)
- [Builders](#builders)

---

## Conventions

- **No base class.** MACO entities do **not** extend a framework superclass (there is no
  `BaseEntity` / `AuditableCFEntity` here). Every entity declares its own `@Id` and
  `implements Serializable`.
- **Class name**: `Maco{Domain}` for MACO-wide tables (`MacoPodMaco`, `MacoBillableConsumption`),
  or a flow-prefixed name for flow tables (`ElecAboFacturable`).
- **Table name**: `lowercase_with_underscores`, carrying the functional prefix already in use
  (`maco_d_…`, `elec_d_…`, `maco_t_…`). **Take the exact table name from the Flyway script or the
  ticket — never derive it from the class name.**
- **Javadoc is mandatory** on the class (with `@author`) and on **every field**, in the
  house form `/** Column {human description} **/`.
- Column names mirror the physical column exactly, including the functional prefix
  (`apg_profile_code` → `apgProfileCode`).

```java
package com.opencell.maco.model;

import javax.persistence.*;
import java.io.Serializable;
import java.math.BigDecimal;
import java.util.Date;

/**
 * MacoAdjustedCoef Entity
 *
 * @author {Author}
 */
@Entity
@Table(name = "maco_d_adjusted_profiles_gaz")
@SequenceGenerator(name = "maco_d_adjusted_profiles_gaz_id_seq",
        sequenceName = "maco_d_adjusted_profiles_gaz_id_seq", allocationSize = 1)
public class MacoAdjustedCoef implements Serializable {

    /** Column id **/
    @Id
    @Column(name = "id", nullable = false)
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "maco_d_adjusted_profiles_gaz_id_seq")
    private Long id;

    /** Column adjusted profile code **/
    @Column(name = "apg_profile_code")
    private String apgProfileCode;

    // getters / setters — explicit, no Lombok
}
```

---

## Identifier strategies

Two strategies coexist; pick the one the table actually uses:

1. **Sequence-generated `Long`** — the default for transactional tables.
   `@SequenceGenerator(name = "{table}_id_seq", sequenceName = "{table}_id_seq", allocationSize = 1)`
   plus `@GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "{table}_id_seq")`.
   The generator `name` and `sequenceName` are **identical** and match the physical sequence.
2. **Natural `String` key** — used by reference/lookup tables (`MacoBillingFrequency`,
   status and code tables), keyed by `code`. These have **no** sequence generator, and their
   repository is `JpaRepository<T, String>`.

`allocationSize = 1` is the house setting — do not raise it without a stated reason.

---

## Field types

| Data | Type |
|------|------|
| Identifier | `Long` (sequence) or `String` (natural code) |
| Monetary / quantity / coefficient | **`BigDecimal`** — never `double`/`float` |
| Legacy date column | `java.util.Date` + `@Temporal(TemporalType.DATE|TIMESTAMP)` |
| New business date/time | **`LocalDate` / `LocalDateTime`** |
| Boolean | `Boolean` (wrapper, nullable) |
| Enumerated | see below |

**Dates are migrating.** Newer work uses `java.time` (`LocalDate`, `LocalDateTime`); older columns
still use `java.util.Date` with `@Temporal`. **Match the surrounding entity** — do not opportunistically
convert existing fields, and be aware that a `DATE` column persisted through `java.util.Date` is
timezone-sensitive (there is a regression test guarding exactly this).

Enums are persisted as their code via a dedicated reference entity or
`@Enumerated(EnumType.STRING)` — **never** `EnumType.ORDINAL`.

---

## Relationships

- `@ManyToOne` is the dominant association; specify `@JoinColumn(name = "…")` explicitly.
- **Beware EAGER `@ManyToOne`.** Several MACO entities carry EAGER associations that cause
  JOIN/N+1 blow-ups on batch volumes. When a batch step only needs scalars, do **not** load the
  entity — use a projection DTO (below).
- Use `fetch = FetchType.LAZY` for any association you add, unless the ticket requires otherwise.
- Collections: `@OneToMany(mappedBy = …)`, and never cascade `REMOVE` onto reference data.

---

## Projection DTOs

For read-heavy paths (notably CDR generation) MACO uses **flat immutable projections** loaded by a
JPQL `select new …` query, instead of managed entities:

- They live in **`maco-model`**, package `com.opencell.maco.model.dto` — because the query sits in
  `maco-repository`, which depends only on `maco-model` (see ARCHITECTURE.md).
- All fields `private final`, set by a single all-args constructor, getters only, no setters.
- Contain the scalars **plus the values derived from EAGER relations** (e.g. `idOperationTraitement`,
  `operationTypeCode`), which is what removes the JOINs.
- Javadoc must state **why** the projection exists (which relations it avoids materialising).

Reach for one when a step reads many rows and writes none of them back.

---

## Builders

Entities with many optional fields have a companion builder in `com.opencell.maco.builder`
(e.g. `MacoLogBuilder`): private fields, fluent `setX()` returning `this`, and a terminal
`build()`. Use the existing builder when one exists rather than a long constructor call.
