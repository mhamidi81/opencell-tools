# Repo, branching, review, CI/CD, and doc discipline

> Load this when scaffolding the repo, setting branch/commit/tag conventions, defining PR review, or
> wiring CI/CD. These are Opencell house standards (Bitbucket + Jenkins + Confluence). OPH (an internal
> Opencell reference project, not bundled with this plugin) is the illustrative worked example; the
> conventions themselves are reusable across Opencell projects.

## Repository layout

- **Single mono-repo** for the product (backend + GUI + `docs/`). One clone gives whole-system
  context — a strong multiplier for a single agent.
- **Carve out code that belongs to another product's lifecycle.** OPH's *gateway module* imports
  into Opencell Core, so it lives **with Core**, on Core's build/release cadence — not in the OPH
  repo. Apply the same test to any cross-product artifact.
- **Doc tree:** `docs/{decisions,functional,technical,process,research}/`. `PLAN.md`, `README.md`,
  `DECISIONS.md`, and the project `CLAUDE.md` sit at the root. (Scaffold from `templates/`.)

### Where the design artifacts live — by tier

The mono-repo above is the **standalone-product** case. Match the work to a tier:

| Work | Design home |
|---|---|
| **Standalone product / service** (own codebase + release lifecycle, e.g. Payment Hub) | its **own repo** (the mono-repo above) |
| **Big feature / multi-Epic initiative** on an existing product | a **self-contained folder in a shared design repo** (a repo dedicated to design-only artifacts) — *or* a `docs/<feature>/` subtree of the product's repo if that repo is a suitable design home |
| **Routine Story / Enabler / Bug** | no design repo — straight to `oc-fn-func-design` |

The discriminator is *standalone-deliverable-vs-not*, **not** size — a multi-Epic initiative still
belongs in the shared design repo as long as it ships inside an existing product rather than as its
own service.

**Why a shared design repo rather than a subtree of the implementation repo:** when the code lands in
a large, shared, or open-source repo (e.g. `opencell-core`), that repo is a poor home for design
markdown — it adds noise and couples the design lifecycle to the code's release cadence. A shared
design repo keeps design-only artifacts together, **one self-contained folder per initiative**
(`PLAN.md`, project `CLAUDE.md`, `DECISIONS.md`, `docs/` tree), without spinning up **a repo per
feature**. It is itself design-only: no application code. Its root `CLAUDE.md` carries the
cross-initiative conventions; each folder's `CLAUDE.md` is more specific and wins.

**Consequences inside a shared design repo** (these do *not* apply to a single-product mono-repo):
- **Gate tags are namespaced per initiative** — `<initiative>/phase-N` (e.g. `e-reporting/phase-2`),
  because git's tag namespace is flat across the repo and an un-prefixed `phase-2` would collide
  between initiatives.
- **ADR / DR numbering is folder-scoped** — each initiative folder owns its own ADR series; no
  cross-initiative uniqueness is implied.

## Branching

- **Trunk-based on a protected `main`**: the single long-lived branch; no direct pushes; required
  green pipeline + required approvals before merge.
- **Short-lived feature branches** cut from `main`, **squash-merged** back via PR (one logical change
  = one commit; linear, readable history).
- **No long-lived `release/*` branches** pre-1.0. If hotfix-on-old-release pressure ever appears,
  introduce one *then* via a superseding ADR — don't pre-build the ceremony.

## Interop with the marketplace common flow

If the marketplace common-flow plugins are installed (`/oc-fe-fix-bug` → `/oc-commit` →
`/oc-pull-request`, etc.), reconcile this methodology's trunk-based model with their defaults:

- **Branch naming must embed the base as the 3rd segment** — `{author}/{type}/{base}/{KEY-NN}-{desc}`
  — because `/oc-pull-request` parses the PR target from that segment. Under this methodology the base
  is always `main` (e.g. `jdoe/feature/main/INTRD-42-add-retry`).
- **`/oc-fe-fix-bug` defaults to a `dev` integration branch** (the GitFlow convention on existing
  Opencell repos like `opencell-portal`/`opencell-core`). On a repo run under THIS methodology there is
  no `dev` — pass the trunk explicitly: `/oc-fe-fix-bug INTRD-NN main`, so the fix branch is cut from
  `main`. Likewise, when `/oc-pull-request` prompts for the base, answer `main` so the PR targets the
  trunk. Keep their `dev`/`master` defaults only on the existing repos that actually use them.
- **`/oc-commit` and `/oc-pull-request` are Jira-ticket-bound** — they read `.claude/cache/jira-tickets.json`
  and **stop** if the ticket is absent, so cache it first via `/oc-cache-jira`. Consequently: **Phase 0–3
  design commits use a plain `git commit`** (no Jira key exists yet, by design — these commands don't
  apply); **from Phase 4**, once the Story/Enabler exists and is cached, the `KEY-NN: <summary>` subject
  this skill prescribes is exactly what `/oc-commit` produces, so the commands drop in cleanly.

## Commits & branch naming

- **Pre-Phase-4 (no Jira keys yet):** plain **imperative subject** (`Add ADR for branching model`).
  No issue-key prefix exists yet — this is a Bitbucket/Jira repo, so keys appear only from Phase 4
  (`KEY-NN:`).
- **From Phase 4 (Jira open):** branch `{author}/{type}/{base}/{KEY-NN}-{desc}` (the `{base}` segment
  is the PR target — `main` under this methodology — so `/oc-pull-request` can consume it; see *Interop
  with the marketplace common flow*); commit subject `KEY-NN: <description>` — **Jira Smart Commits**
  transition the issue.
- If installed, `/oc-commit` builds the `KEY-NN:` subject for you; this section is the policy it
  satisfies — without it, write the subject by hand.

## Tags — two independent kinds

1. **Version tags** — annotated, on every version bump (Opencell form: `X.Y.Z`, **no `v` prefix**). The
   version source is the backend manifest, which only exists from **Phase 5+** (once the stack is
   chosen); so version tags begin once there's a manifest. Message: the `git log --oneline --no-merges`
   range since the previous tag.
   (Bump rules: major on explicit instruction; minor on feature/core change; patch on fixes.)
2. **Phase tags** — annotated `phase-N` (`phase-0`, `phase-1`, …) on each gate's **merge commit**,
   **pushed to origin**. They mark the repo state at each gate so phase-to-phase diffs are easy to
   pull. **Independent** of version tags (which don't exist until Phase 5). Message: the phase name +
   the `git log --oneline` range it covers. **In a shared design repo, namespace them per
   initiative — `<initiative>/phase-N`** (see *Where the design artifacts live*).

## Publishing & issue close

Publishing is part of *done* — push as part of completing a work item, not as a separate ask. Because
**`main` is protected here**, "push" means **push the feature branch and open a PR** (carrying its
annotated tags, `git push --follow-tags`) — never push `main` directly. The Jira issue **closes on
merge** (Smart Commits transition it), so a resolved issue always has its work on `main`; never resolve
an issue whose PR isn't merged.

If installed, `/oc-pull-request` performs this squash + push + open-PR flow (deriving the base from the
branch's `{base}` segment — answer `main` if it prompts); this section is the policy it satisfies —
without it, do it by hand.

## PR review — two tiers

- **Tier 1 — automated gauntlet** (must be green before human eyes), run by **Jenkins**: build,
  unit/integration tests, lint/format, quality gate (SonarQube/SonarCloud), SAST/dependency scan,
  OpenAPI/contract lint.
- **Tier 2 — mandatory human sign-off, *non-waivable*** for any PR touching the project's
  high-stakes seams. For OPH that's **payments, PSP connectors, the policy engine, the gateway
  contract, auth/Keycloak, or audit**. Each project names its own non-waivable list (derive it from
  the domain invariants, non-negotiable #7). Doc-only PRs may use lighter approval.

This matters most for **AI-authored code**: the gauntlet + non-waivable human sign-off on sensitive
paths is the safety model that lets an agent author code on a high-stakes system.

## CI/CD

- **Jenkins is the pipeline** (org standard). **Bitbucket = source + PRs only; Jira = planning.**
  Don't assume Bitbucket Pipelines — if a repo carries a `bitbucket-pipelines.yml`, confirm with the
  infra owner whether it's actually used or Jenkins is sole.
- **Pipeline shape:** build/test/quality gauntlet → build & publish **Docker image** → deploy to
  **Kubernetes** per the infra owner's standard.
- **Confluence sync runs as a trunk pipeline step** (see below).

## Documentation discipline

- **`.md` in the repo is the single source of truth; Confluence is a one-way mirror** — synced on
  merge to trunk (OPH uses `kovetskiy/mark`). Every synced page carries a "generated from repo — do
  not edit" banner; Confluence edit rights are locked to prevent drift. **Never hand-edit a synced
  page.** (Confluence authoring mechanics: `oc-fn-documentation`.)
- **Same-commit doc discipline:** `README.md` is updated in the **same commit** as any change to what
  it documents — never deferred to a follow-up.
- **Slide decks follow the same rule:** the Phase-2 deck is authored as `deck.md` (one section per
  slide + speaker notes) and the `.pptx` is **rendered from it** against the branded template — a
  one-way print, never the master, never committed as a binary.
  - **Locale formatting (non-negotiable, every Marp deck):** slideshows must display **24-hour time**
    (never AM/PM) regardless of the presenting machine's browser/OS locale, and must **never** show a
    date in an ambiguous all-numeric form (`dd/mm/yyyy`, `mm/dd/yyyy`, and the like). Any all-numeric
    date uses **ISO-8601 (`YYYY-MM-DD`)**; dates written with a month name (`16 June 2026`, `Juin 2026`)
    are unambiguous and fine as-is. The bespoke presenter-view clock calls `toLocaleTimeString()` with
    no locale (so it inherits the browser locale and defaults to AM/PM on en-US), so **force it
    deck-side**: inject a `<script>` that overrides no-argument `toLocaleTimeString()` to `fr-FR` 24h,
    and render with `--html` (the flag that preserves the script). When rendering, pass the input file
    **first** and `--theme-set` **last** (it is an array flag and will otherwise consume the input path).
