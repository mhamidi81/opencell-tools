<!-- TEMPLATE — copy to README.md at the repo root. Replace <placeholders>; delete guidance
     comments. Keep this updated in the SAME commit as any change to what it documents. -->

# <Project Name> (<ACRONYM>)

<One-paragraph statement of what this is and the problem it solves.>

> **Status:** <Phase N — Name>. Source of truth for process is [`PLAN.md`](./PLAN.md) until the Jira
> backlog opens (Phase 4). Read it first on every resume.

## What this is

<2–4 bullets: the product/feature, what makes it distinct, the key constraints.>

## Documentation map

| Where | What |
|---|---|
| [`PLAN.md`](./PLAN.md) | Vision, requirements, candidate architecture, phased plan, Decision Register |
| [`DECISIONS.md`](./DECISIONS.md) | ADR index (the decision log) |
| [`docs/process/ways-of-working.md`](./docs/process/ways-of-working.md) | How we run the project (phases, gates, conventions) |
| [`docs/decisions/`](./docs/decisions/) | The ADRs themselves |
| [`docs/functional/`](./docs/functional/) | Scope, glossary, personas, use-cases, NFRs, specs *(Phase 1+)* |
| [`docs/technical/`](./docs/technical/) | Architecture, stack, security, data model, API, deployment *(Phase 5+)* |

## Building & running

<TBD until the stack is chosen (Phase 5). Fill in build/run/test commands then, and keep them
current in the same commit as any change.>

## Contributing

Trunk-based on protected `main`; short-lived branches; squash-merge. See
[`docs/process/ways-of-working.md`](./docs/process/ways-of-working.md) for branch/commit/review
conventions and the phase gates.
