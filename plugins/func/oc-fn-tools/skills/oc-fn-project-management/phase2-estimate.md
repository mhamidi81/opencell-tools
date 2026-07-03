# Phase-2 estimate — what the framing/approval deck must quantify

> Load this when preparing the **Phase-2 framing/approval** ask (business case + deck). It covers
> *what to quantify and how* when the build is **Claude-authored**. The deck **mechanics** (theme,
> authoring, rendering, overflow, locale rule) live in the **`oc-fn-decks`** skill — this file is only
> about the numbers.

## What a Phase-2 deck quantifies (Claude-authored builds)

When the build is **Claude-authored** (Claude Code writes the specs, code, tests, docs; humans review +
QA), the quantified ask is **delay** and **effort in man-days** — **not euros**.

- **Why not euros.** Authoring runs on a flat-rate Claude subscription (~€0 marginal), so the € build cost
  ≈ the human-review/QA floor anyway — and **pricing / ROI / the P&L is Finance's job, built later**. A
  Phase-2 deck shows **effort + delay + the ask**, not a cost line. Don't put a € figure or a P&L on a
  slide; if asked, defer it explicitly to Finance.
- **Estimate model — authoring + human floor.** Size each work item as two terms:
  - **Authoring** (Claude, working days) — review-ready drafts incl. local build/test iteration. The term
    that compresses; ~€0, but carries a *fraction* of a man-day of human guidance per authoring-day.
  - **Human floor** (working days) — review, CI, integration/debug, migrations, QA. **Non-compressible**;
    scale by **novelty** (mechanical → low; new subsystem → high) and **review style** (AI-assisted light
    < normal < heavy). This is the binding term.
  - **External path** (not in the blocks) — stakeholder decisions, external inputs, release cadence.
    **Dominates calendar**; Claude can't compress it. (See the co-authoring fast-track in `phases.md`.)
- **How to combine — put the right number on each slide:**

  | Slide figure | Formula |
  |---|---|
  | **Delay** | external path + **max**(authoring, floor) + ~25% latency. **Don't sum** authoring + floor — they pipeline. |
  | **Effort (man-days)** | **combine**: (driver-fraction ≈ 0.3–0.5 × authoring) + floor; or authoring + floor as a conservative ceiling. Distinct labor, not pipelined. |
  | **Euros** | out of scope — Finance builds the P&L later. |

- **Relative comparison travels well.** Claude accelerates authoring across options proportionally, so an
  "Option A ≈ 1×, Option B ≈ 2×" framing is robust even when the absolute numbers are soft (±~50% at
  Phase 2). Lead the deck with the recommendation and the relative multiple.

*(Worked example: a Phase-2 deck paired with a macro-estimate note.)*
