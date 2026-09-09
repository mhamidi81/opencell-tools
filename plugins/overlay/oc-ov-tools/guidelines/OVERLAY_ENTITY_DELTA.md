# Overlay entities

> LAYERS OVER: oc-be-tools/guidelines/ENTITY_GUIDELINES.md
> CORE BASELINE: oc-be-tools 1.17.0
> PRECEDENCE: every core section applies unchanged unless marked REPLACES below.

Core's field types, default values, relationships, `@OneToMany` performance rules and documentation
requirements apply verbatim. Only the following differ.

## Base class — REPLACES core "Base Classes" (vertical-energy profile)

The house pattern is `BusinessCFEntity` with custom-field and observability support:

```java
@Entity
@ObservableEntity
@Cacheable
@CustomFieldEntity(cftCodePrefix = "PointOfDelivery")
@Table(name = "point_of_delivery")
@GenericGenerator(name = "ID_GENERATOR", strategy = "org.hibernate.id.enhanced.SequenceStyleGenerator",
    parameters = { @Parameter(name = "sequence_name", value = "point_of_delivery_seq"),
                   @Parameter(name = "increment_size", value = "1") })
public class PointOfDelivery extends BusinessCFEntity {
```

Core's `EnableBusinessCFEntity` / `AuditableCFEntity` / `BaseEntity` remain legal but are unused here —
match the neighbouring entity rather than the core guideline's default.

## ID generator form

This repo uses the **string** form `strategy = "org.hibernate.id.enhanced.SequenceStyleGenerator"`,
not core's `type = SequenceStyleGenerator.class`. Match the surrounding files.

## Table naming — REPLACES core

Profile-driven, and this is a common mistake:

- `vertical-energy`: **no prefix** — `point_of_delivery`, `home_info`.
- `template`: `ext_` prefix — `ext_person`.

Sequence naming is unchanged from core: `{table_name}_seq`.

## Inheritance

`SINGLE_TABLE` with a `@DiscriminatorColumn` is the established pattern for entity families
(e.g. an abstract base with per-energy-type subclasses). Follow it rather than introducing
`JOINED` for a new family.

## Where entities live, and the registration you must not forget

Entities go in the overlay model module. Whatever jar they end up in **must be listed as a
`<jar-file>` in the overlay `persistence.xml`** or Hibernate never scans them and the entity is
silently unmapped. Adding the first entity to a *new* module means editing `persistence.xml` in the
same change — see `OVERLAY_ARCHITECTURE.md`.

The package is conventionally `org.meveo.model`, the same package as core's entities. That is a split
package: it is why these classes compile without importing `@ObservableEntity`. Never rely on
package-private access to core members.

## Custom-field references carry the FQN

Custom-field values stored as JSON reference entities by fully-qualified class name
(`"classname": "org.meveo.model.PointOfDelivery"`). **Moving or renaming an entity class breaks stored
data**, not just code. A rename needs a data migration changeset alongside it.

## Every entity needs its Liquibase pair

An entity is not done until both `current/overlay.xml` and `rebuild/overlay.xml` are updated per
`OVERLAY_DATABASE_DELTA.md`, and `LiquibaseFileTest` passes.

## Known defects — do not replicate

- `HomeInfo` mixes `javax.validation.constraints.NotNull` with `jakarta.persistence.*`. The constraint
  is **inert** — see `OVERLAY_CRITICAL_RULES.md` OV-4.
- `serialVersionUID = 1L` appears in places. Core requires a unique value; use one.
