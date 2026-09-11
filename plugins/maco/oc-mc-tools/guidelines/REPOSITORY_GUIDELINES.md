# MACO — Repository Guidelines (`maco-repository`)

Spring Data JPA. One repository interface per aggregate entity.

## Declaration

```java
package com.opencell.maco.repository;

import com.opencell.maco.model.MacoAdjustedCoef;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.stereotype.Repository;

/**
 * maco_d_adjusted_profiles_gaz repository
 *
 * @author {Author}
 */
@Repository
public interface MacoAdjustedCoefRepository
        extends JpaRepository<MacoAdjustedCoef, Long>, JpaSpecificationExecutor<MacoAdjustedCoef> {
}
```

Rules:

- Always `@Repository`, always an **interface** — never a class, never an `@Autowired`
  `EntityManager` wrapper unless a native/dynamic query genuinely requires it.
- Extend **both** `JpaRepository<T, ID>` and `JpaSpecificationExecutor<T>`. The specification
  executor is what the generic `/list` search endpoint needs (see API_GUIDELINES); omitting it
  breaks the standard controller template.
- The `ID` type parameter must match the entity's actual key — `Long` for sequence-generated
  entities, **`String`** for natural-code reference tables.
- Repositories depend **only** on `maco-model`. Never import a DTO from `maco-dto`, a service, or
  anything from `maco-batch-processing`.

## Query methods

Prefer, in this order:

1. **Derived query methods** when the name stays readable:
   `findFirstByApgDateBetweenAndApgProfileCodeOrderByApgValidFromDesc(...)`.
   Past ~4 criteria the name becomes unreadable — switch to `@Query`.
2. **`@Query` JPQL** with **named parameters** bound by `@Param`:

```java
@Query("SELECT adj FROM MacoAdjustedCoef adj WHERE adj.apgDate = :date "
        + "AND adj.apgProfileCode = :profile "
        + "AND adj.apgZoneCode = :zoneCode")
List<MacoAdjustedCoef> findByDateAndProfileAndZoneCode(@Param("date") Date date,
        @Param("profile") String profile, @Param("zoneCode") String zoneCode);
```

3. **Native queries** (`nativeQuery = true`) only when JPQL cannot express it; state why in Javadoc.

Conventions:

- Return **`Optional<T>`** for at-most-one results, never a bare nullable entity.
- Return `List<T>` for many; return `Page<T>` when the caller paginates.
- **Never return an unbounded `List` on a batch path.** Use `Page`/`Slice`, a projection, or a
  streaming reader (see BATCH_GUIDELINES).
- For read-heavy batch reads, declare a `select new com.opencell.maco.model.dto.XxxDto(...)`
  projection query rather than loading managed entities with EAGER relations.
- Write operations that touch many rows (`@Modifying @Query`) must be annotated
  `@Modifying(clearAutomatically = true)` when the caller continues to use the persistence context,
  and must run inside a transaction owned by the **service** layer.
- Javadoc every non-obvious query method, especially the business meaning of its criteria.
