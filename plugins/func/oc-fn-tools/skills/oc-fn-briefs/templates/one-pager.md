---
# oc-fn-briefs — Tier-1 (markdown-first) one-pager SOURCE template.
# This .md IS the source of truth (greppable, diffable). Render it to a self-contained
# branded HTML + A4 PDF with pandoc + the Chromium step — see SKILL.md § Rendering (Tier 1).
# The header band, logo, title block and CSS are fixed chrome supplied by the template;
# fill the front matter below and the body between the markers.
title: "Document title"
accent: "the sharp part, in red"          # optional — trailing red phrase after the title
tag: "Internal · confidential"            # optional — classification pill in the header band
meta: "Context line · **key date / scope** · prepared 2026-07-06"   # markdown inline OK (**bold**)
lead: "One sentence that frames why this page exists and what the reader should take away."
lang: en
---

<!-- ══ body start ══ -->

## Section heading [— optional grey hint after the title]{.hint}

Plain markdown prose. Keep it skimmable — a one-pager earns its name by what it leaves out.
Use **bold** for emphasis (renders in brand ink) and normal lists where they help.

<!-- KPI tile row — drop the whole block if the note has no headline numbers.
     The outer `kpis` div just lays out the row; each inner `kpi` is expanded by the
     oc-brief.lua filter from its n / unit / l attributes. -->
:::: kpis
::: {.kpi n="87" unit="%" l="what it measures"}
:::
::: {.kpi n="1.2" unit="M€" l="what it measures"}
:::
::: {.kpi n="6" unit="×" l="what it measures"}
:::
::: {.kpi n="40" unit="k" l="what it measures"}
:::
::::

## An inventory or comparison

Plain pipe tables render with the brand table styling. Inside a cell:
`[label]{.del}[grey supporting detail]{.why}` for a two-line row label,
`[value]{.bar pct="0-100" sub="range"}` for a magnitude bar, and `[n]{.x}` (or `[n]{.x .ink}`) for a pill badge.

| Row label | Effort | Impact | Leverage |
|:----------|-------:|:-------|---------:|
| [E-reporting mapping]{.del}[XML schema + validation]{.why} | 2 | [13]{.bar pct="40" sub="· 9–17"} | [6.5]{.x} |
| [Rating rules]{.del}[usage → charge conversion]{.why} | 12 | [48]{.bar pct="100" sub="· 38–60"} | [4.0]{.x} |
| [Invoice template]{.del}[layout + localisation]{.why} | 5 | [24]{.bar pct="55" sub="· 18–31"} | [4.8]{.x .ink} |

## Framing / takeaways

:::: cards
::: card
### Framing A
::: big
the headline
:::
Two or three sentences of supporting detail.
:::
::: card
### Framing B
::: big
the headline
:::
Two or three sentences of supporting detail.
:::
::::

::: note
**Method.** How the figures were produced. [Key term]{.k} highlighted.
**Caveats:** the important limitations, ranges, and what is / isn't in scope.
:::

<!-- ══ body end ══ -->
