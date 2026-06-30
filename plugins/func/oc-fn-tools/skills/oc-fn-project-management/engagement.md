# Stakeholder engagement — who's involved, when

> Load this when planning engagement, preparing the approval/SteerCo gate, or deciding who to bring
> in. The principle: **engage people in stages, lightest first.** OPH (an internal Opencell reference
> project, not bundled with this plugin) is the illustrative worked example.

## The principle: staged engagement

Start lightweight and largely **solo** (sponsor/lead + Claude) to build a credible story → take an
**informal feasibility read** from the architect and infra owner → **pitch for approval** → on a
"go", **formally engage** the specialists. Two reasons this ordering matters:

1. **Don't spend others' time (or political capital) on an unproven idea.** A credible scope and a
   sharp business case earn the meeting; a vague one wastes it.
2. **Don't sink heavy design effort before a mandate** — the Phase-2 gate (`phases.md`) exists
   precisely to prevent that sunk cost.

**The sponsor controls exactly who is brought in when.** The sequence below is the default, not a
constraint.

## Roles (generalized)

| Role | Brought in | Contributes |
|---|---|---|
| **Sponsor / lead** | from the start | owns the project; writes the scope, business case, and pitch; drives design with Claude |
| **Approvers** (steering committee — e.g. CEO/CFO/CRO) | Phase 2 | the **go/no-go**: mandate, budget, commercial/ROI case |
| **Architect** | informal read pre-pitch → formal in Phase 5 | feasibility sanity-check; technical-design & architecture review |
| **Infra owner** | informal read pre-pitch → formal in Phase 5 | CI/CD + deployment topology; validates infra constraints |
| **Domain PO** | Phases 3–4 (on approval) | domain validation & functional design (3); functional backlog — Stories' functional sections (4) |
| **Implementer** (Claude) | Phase 6 | authors code under human review |

Worked example (roles only): sponsor = the VP Product; SteerCo = CEO / CFO / CRO; plus an architect,
an infra owner, and a domain PO brought in per the table above.

## The approval gate (Phase 2)

The single gate that converts a shadow/solo effort into an official, resourced one.

- **Full product → Steering Committee go/no-go.** Deliver a business case (problem, value/ROI, rough
  cost/effort/timeline, risks) and high-level slideware. The **"ask"** must be explicit: official
  mandate **and** the specialists' time (architect, infra, domain PO) as part of the approval.
- **Big feature/Epic → sponsor/lead sign-off.** A one-page brief and a decision from someone with
  authority and a real resourcing commitment. Same *intent*, lighter ceremony.

A "go" without secured stakeholder time is a half-go — name the resourcing explicitly in the ask so
Phases 3–5 aren't blocked waiting on people who were never committed.

## After approval

Engage the **domain PO** for Phases 3–4 (functional design, then the functional backlog) and the
**architect + infra owner** for Phase 5 (technical design & infra). Until then, keep the circle small —
the early phases are deliberately solo so the story is tight before more people spend time on it.
