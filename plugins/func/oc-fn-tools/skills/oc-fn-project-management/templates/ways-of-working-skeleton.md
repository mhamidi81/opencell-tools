<!-- TEMPLATE — copy to docs/process/ways-of-working.md. Replace <placeholders>; delete guidance
     comments. This is authoritative for PROCESS; PLAN.md remains authoritative for vision,
     requirements and open decisions. Keep the "Current phase" line (§2) up to date.

     It states what is TRUE OF THIS PROJECT and points at the methodology for everything else.
     Do not paste the phase table, the ADR conventions, the branching rules or the CI pipeline in
     here: they live in the `oc-fn-project-management` skill, and a second copy only drifts. -->

# Ways of Working — <Project Name> (<ACRONYM>)

> How we run this project. Authoritative for *process*; `PLAN.md` is the source for *vision,
> requirements and open decisions*. The methodology itself is the **`oc-fn-project-management`**
> skill — load it at kickoff and at each gate. **Last updated:** <YYYY-MM-DD>.

## 1. This project's own rules

The methodology's non-negotiables apply unchanged. These are the ones **specific to this project**:

1. **<Domain invariant>** — <the correctness law this project adds; not a preference>.
2. **Stable seams:** <which boundaries are swappable ports/adapters here>.
3. <any further project-specific law, or delete>

<!-- Deviations from the methodology go in an ADR, not here. Name them: "ADR-00NN amends ADR-0003". -->

## 2. Current phase

**Phase <N> — <Name>.** <one line: what is done, what this phase produces, what its gate needs.>

Eight phases with hard gates, `.md` + ADRs until Jira opens at the 3 → 4 gate — full table,
deliverables and exit criteria in the skill's `phases.md`. Each gate's merge commit is tagged
`<annotated tag form used here>`.

## 3. Where things live

- **Repo:** <mono-repo | folder in the shared design repo> — <url>.
- **Doc tree:** `docs/{decisions,functional,technical,process,research}/`.
- **Jira:** <project key(s)>, decided <date> — see `docs/decisions/ADR-00NN`.
- **Confluence:** <space / parent page>, one-way mirror of the repo `.md`.
- **ADR numbering:** <repo-scoped | folder-scoped>; index in `DECISIONS.md`.

## 4. Conventions — the deltas only

Branching, commits, PR review tiers, CI/CD and versioning follow the skill's `repo-and-ci.md`.
Record here **only what differs for this project**:

- **Sensitive seams needing non-waivable human sign-off:** <list them — this is the one entry
  almost every project must fill, because the list is project-specific by definition>.
- **Version source:** <manifest path, once the stack is chosen in Phase 5>.
- <other deviation, with its ADR reference, or delete>

## 5. Who's involved when

<!-- One line; staged-engagement detail is in the skill's engagement.md. -->
Solo/lightweight early → feasibility read from <architect>/<infra> → approval gate (Phase 2) →
<domain PO> (Phases 3–4) → <architect>/<infra> (Phase 5).
