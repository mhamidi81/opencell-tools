---
name: oc-fn-project-management
version: 1.9.0
updated: 2026-07-03T07:50:10+02:00
author: Stéphane Chambrin
description: >
  How to run an Opencell project from kickoff to release: the design-first phased
  delivery model with hard gates, ADR/decision discipline, staged stakeholder
  engagement, and repo/branch/CI/doc conventions. Load this skill when starting a
  NEW Opencell project or product, or a BIG feature / Epic that warrants design-first
  delivery — and whenever the user mentions project kickoff, phased delivery, phase
  gates, "ways of working", the Decision Register, ADR setup, DECISIONS.md, SteerCo
  approval, scaffolding a project, or "how we run this project". Opencell projects are
  Bitbucket/Jira/Jenkins/Confluence-hosted. This skill orchestrates the *process*; it
  defers issue authoring to `oc-fn-func-design` and Confluence to
  `oc-fn-documentation`. Do NOT load it for a single routine Story, Enabler, or
  Bug — that is `oc-fn-func-design`'s job.
---

# Running an Opencell project — phased delivery, decisions, engagement

This skill is the **process playbook** for kicking off and running an Opencell project or
large Epic: *what to do in what order, why, and what each gate requires*. It is the
methodology distilled from the way the **Opencell Payment Hub (OPH)** project was run.
OPH (and OER) are **internal Opencell reference projects — not bundled with this plugin**;
they appear throughout only as illustrative worked examples.

## 1. When this skill applies

Load it when the work is **big enough to need design before build**:

- **A new Opencell product / project** — greenfield or a standalone subsystem. Use the full
  model (all phases, formal approval, dedicated docs tree).
- **A big feature / Epic** inside an existing product — significant enough that decisions
  must be recorded and design must precede a backlog. Use the **scaled-down** model (§5).

**Do not** load it for routine, already-scoped work — a single Story, Enabler, or Bug.
That is `oc-fn-func-design`'s job. When unsure whether something is "big enough," §5's
test decides; when still unsure, ask.

Opencell projects are **Bitbucket** (source + PRs) / **Jira** (planning) / **Jenkins** (CI/CD)
/ **Confluence** (doc mirror) — use Opencell/Jira conventions (Bitbucket source/PRs, Jira planning,
Jira Smart Commits); confirm with `git remote -v` if the host is ever ambiguous.

## 2. How this fits with the other skills

This skill **orchestrates**; it does not duplicate. It sits *above* the two authoring skills
and *defers* to them at the relevant gate:

| Layer | Owns | Loaded |
|---|---|---|
| **`oc-fn-project-management`** (this) | the *when / why / what-order* of the whole project | at kickoff, and at each phase gate |
| **`oc-fn-func-design`** | the *how* of Jira authoring — Epics, Stories, Enablers, ADF, custom fields, and a Story's **functional** sections (Requirement, Functional Design, Acceptance); creates the empty Technical-design scaffold but does **not** author it | at the backlog gate (Phase 4) and for every issue after |
| **`oc-ar-tech-design`** (marketplace `oc-ar-tools`, where available) | the *how* of a Story's **Technical design** section (`customfield_10137`), authored from the Phase-5 technical artifacts | at the technical-design gate (Phase 5) |
| **`oc-fn-documentation`** | the *how* of Confluence pages | at the docs/release gate (Phase 7) |
| **`oc-fn-decks`** | the *how* of a branded slide deck — Marp theme, authoring, rendering, overflow, locale rule | at the Phase-2 framing/approval deck (and any standalone deck) |

**Process layer vs execution layer.** This skill is the **process** layer — the phased model and
its gates. On an `oc-fn-tools` + common-plugins setup, the per-ticket implementation in **Phase 6**
runs through the marketplace common flow (the **execution** layer): `/oc-cache-jira` → implement
(`/oc-fe-fix-bug` or `/oc-fe-create-ui` for frontend; `oc-be-tools` `/oc-be-implement` for backend)
→ `/oc-commit` → `/oc-pull-request` → `/oc-review-pr` — subject to the reconciliations in
`repo-and-ci.md`. The two layers meet at the **Phase 5 → 6 gate** (see `phases.md` Phase 6).

**Versioning, tagging, and publishing rules this skill leans on** (inline, so the skill stands alone;
if your environment defines global conventions they apply, otherwise follow these):

- **Versioning** — **Major** only on explicit instruction; **Minor** on a feature or core-logic
  change; **Patch** on fixes.
- **Annotated tag on every version bump** — Opencell form `X.Y.Z` (**no `v` prefix**); message is the
  `git log --oneline --no-merges <prev_tag>..` range since the previous tag.
- **Publishing is part of *done*** — push the feature branch and open a PR; the Jira issue closes on
  merge (Smart Commits). Never leave validated work unpushed.

Where global conventions and a project's own `CLAUDE.md` both speak, the project file wins; this skill
is the source those project files are generated *from*.

## 3. The non-negotiables (apply in every phase, every project size)

These never scale away, even for a single big Epic:

1. **Decide before building.** Functional → technical design precedes implementation. The
   early phases produce only `.md` + ADRs; application code comes later, behind a gate. *(This
   skill's `.md` and ADR generation is an explicit, user-invoked design **deliverable** — it
   satisfies any "only when explicitly requested" carve-out in co-loaded code-quality rules. The
   no-proactive-documentation convention some backend code skills enforce applies to implementation
   code, not to these design artifacts.)*
2. **Every significant decision is an ADR** (MADR format), not prose buried in a doc or
   tribal knowledge. See `decisions-adr.md`.
3. **Hard gates.** A phase exits only when (a) its deliverables are merged to trunk **and**
   (b) its open design questions are resolved as `Accepted` ADRs. No half-open phases.
4. **Jira opens at the functional-design→backlog gate** (Phase 4) — once functional design is
   *approved* (the Phase 3 gate is passed), and not before. Creating Epics/Stories earlier is a
   process violation — capture premature items in the relevant `.md` instead. If asked to "make a
   ticket" before the gate, flag it and record the item in `.md`. Stories open with their
   **functional** sections (Requirement, Functional Design, Acceptance); the **Technical design**
   section and **Enablers** follow in Phase 5, from the technical design.
5. **`.md` in the repo is the single source of truth; Confluence and any slide deck are
   one-way mirrors** — never hand-edit the mirror, regenerate it from the `.md`.
6. **Stable seams.** Keep architectural boundaries (connectors, engines, dispatchers) as
   clean, swappable ports/adapters; no vendor-specific leakage into the core.
7. **Define the project's own domain invariants once, early, and enforce them.** Each
   project adds correctness laws that are not preferences. *(OPH's are: money in integer
   minor units + ISO-4217, never floats; idempotent everywhere; never persist/log PAN/CVV;
   `RECONCILING` before retry. Yours will differ — name them in Phase 1 and carry them into
   the technical design and lint/arch-tests.)*

## 4. The phased delivery model

Eight phases with hard gates. **Phases 0–3 produce only `.md` + ADRs** (Phase 2 also a pitch
deck). The **3 → 4 gate is the single hard line where Jira items first appear** — Stories open with
their *functional* sections; the technical design enriches them in Phase 5. Full detail,
deliverables, and exit criteria per phase live in `phases.md` — load it when planning a phase.

| Phase | Name | Produces | Exit gate |
|---|---|---|---|
| 0 | Setup & Process | repo scaffold, bootstrap ADRs, README/CLAUDE skeletons, doc tree | repo initialized; bootstrap ADRs Accepted; Jira-project criteria recorded |
| 1 | Functional Scoping & Vision | scope, personas, glossary, use-cases, NFRs, domain invariants | scope agreed; glossary frozen; MVP boundary unambiguous |
| 2 | Framing & Approval | business case + slide deck; feasibility read | **go/no-go** (SteerCo or sponsor) — mandate, budget, stakeholders engaged |
| 3 | Functional Design | domain model, specs, API sketch, state machines | every MVP use case spec'd; state machines Accepted; API enumerated |
| 4 | Backlog Creation — Functional (**Jira opens**) | Epics (one per capability) + Stories with their functional sections (Requirement, Functional Design, Acceptance) filled from Phase-3 specs | every MVP Story exists; functional sections domain-PO-approved |
| 5 | Technical Design | C4, stack ADRs, security, contracts, OpenAPI, data model, infra; each Story's Technical design section filled (by the **architect lane** — `oc-ar-tech-design`, where available); Enablers created (by `oc-fn-func-design`) | stack ADR'd; OpenAPI validates; infra agreed; component list frozen; Technical design sections filled; Enablers created; sprint 1 selected |
| 6 | Iterative Implementation | working software, tests, docs in the same PR | story criteria met; CI green; end-to-end path proven |
| 7 | Docs & Release | finalized docs, Confluence sync, CHANGELOG, tag, runbook | tagged release; Confluence live & matching repo `.md` |

**Track the current phase** at the top of the project's `docs/process/ways-of-working.md`,
and tag each gate's merge commit with an annotated `phase-N` tag (see `repo-and-ci.md`).

**Co-authoring fast track.** When the design is co-authored with Claude — the Phase 4 functional backlog
generated from the Phase 3 specs, the Phase 5 Technical design sections + Enablers from the Phase 5
technical design — **Phases 3–5 compress from weeks to days — without waiving any gate.** The critical
path then sits on stakeholder availability, external inputs, and the build's non-compressible human floor,
*not* on authoring time. Plan those phases in days and de-risk those three items; detail in `phases.md`.

## 5. Scaling: new product vs. big feature / Epic

One model, two intensities. The **non-negotiables (§3) hold at both**; what flexes is
formality, approval weight, and where artifacts live.

**The "big enough" test** — treat work as a project (use this skill) if **two or more** hold:
it introduces a new subsystem or external integration; it needs decisions recorded before
build; it spans multiple sprints; it needs stakeholder sign-off beyond the team. Otherwise
it's routine work → go straight to `oc-fn-func-design`.

| Aspect | New product (full) | Big feature / Epic (scaled) |
|---|---|---|
| Phase 0 Setup | new repo, full `docs/` tree, bootstrap ADRs | a self-contained folder in a shared design repo (a repo dedicated to design-only artifacts) — or a `docs/<feature>/` subtree of the product repo if it's a suitable design home; **not** a repo per feature (`repo-and-ci.md` § *Where the design artifacts live*) |
| Phase 1–2 Scoping & Approval | full scope set + business case + **SteerCo go/no-go** | a short design brief; **sponsor/lead sign-off**, not full SteerCo |
| Phase 3 Functional design | full functional design | still required, but proportionate — design-first never waived |
| Phase 4 Backlog (**Jira opens**) | new or dedicated Jira project (see `jira-project-choice.md`) | one **Epic + functional Stories** in the existing project |
| Phase 5 Technical design | full technical design + Stories' Technical design sections + Enablers | proportionate; the Epic's Stories get their Technical design + Enablers |
| ADRs | project-scoped `docs/decisions/` | feature-scoped ADRs in the existing log, or a Decision Register section |
| Engagement | staged (§ `engagement.md`) culminating in SteerCo | lighter — sponsor + relevant PO/architect |

When scaling down, **say which phases you are collapsing and why** — don't silently skip them.
A collapsed phase still has to clear its gate's *intent* (e.g. "design is agreed") even if the
artifact is a paragraph rather than a document set.

> **Repo home for a scaled feature:** match it to the tier in `repo-and-ci.md` § *Where the design
> artifacts live*. A big feature on an existing product lives as a folder in a shared design repo (a
> repo dedicated to design-only artifacts), not its own repo; there, gate tags are namespaced
> `<initiative>/phase-N` and ADR numbering is folder-scoped.

## 6. Reference files — load on demand

Keep this spine in context; pull in the file that matches the phase you're working:

| Working on… | Load |
|---|---|
| Planning/exiting a phase, gate criteria, deliverables | `phases.md` |
| Recording a decision, ADR format, Decision Register, `DECISIONS.md` | `decisions-adr.md` |
| Repo layout, branching, commits, tags, PR review tiers, CI/CD | `repo-and-ci.md` |
| Who to involve when, the approval/SteerCo gate, roles | `engagement.md` |
| Sizing the Phase-2 ask — effort/delay, no euros (Claude-authored builds) | `phase2-estimate.md` |
| Authoring/rendering a branded deck (theme, Marp, overflow, locale) | the **`oc-fn-decks`** skill |
| Choosing where the Jira backlog lives (existing vs dedicated vs hybrid) | `jira-project-choice.md` |
| Scaffolding a new project/feature from scratch | `templates/` (see §7) |

Load only what the current task needs — do not pre-read all of them.

## 7. Kicking off — the first moves

When starting fresh, scaffold from `templates/` (do not invent structure ad hoc):

1. **Repo / location.** New product → new Bitbucket mono-repo. Big feature → a `docs/<feature>/`
   subtree in the existing repo.
2. **Doc tree.** Create `docs/{decisions,functional,technical,process,research}/` from the
   template scaffold.
3. **Source-of-truth docs.** Drop in `PLAN.md` (vision, requirements, candidate architecture,
   Decision Register) and `docs/process/ways-of-working.md` from templates; set the current
   phase at the top of the latter.
4. **Decision machinery.** Add `docs/decisions/adr-template.md`, the `DECISIONS.md` index, and
   write `ADR-0001` (adopt MADR) as the first Accepted ADR.
5. **Agent rules.** Generate the project's `CLAUDE.md` from the skeleton — it points back at
   this methodology and records project-specific non-negotiables.
6. **Plan engagement.** Decide who is in from the start vs. brought in at which gate
   (`engagement.md`).

Full templates and the per-file fill-in guidance live in `templates/` — see that directory's
index. Use the `templates/` scaffolding in this skill as the reference structure. The `.md`/ADR
artifacts these moves produce are the design **deliverable** — generating them here is explicit and
user-invoked, not the proactive documentation a backend code skill would suppress.
