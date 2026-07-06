--[[ oc-brief.lua — Pandoc Lua filter for the oc-fn-briefs Tier-1 (markdown-first) path.

  Most brand components are reachable from plain markdown + Pandoc fenced divs / bracketed
  spans (they surface as `class="…"` that theme/brand.css styles). This filter exists ONLY
  for the two components markdown cannot express cleanly, so the source stays greppable
  instead of collapsing into nested colon-soup or raw HTML:

    1. KPI tile  — a fenced div with class `kpi` + attributes:
         ::: {.kpi n="87" unit="%" l="gross margin"}
         :::
       → <div class="kpi"><div class="n">87<small>%</small></div><div class="l">gross margin</div></div>
       Wrap a row of them in a bare `::: kpis` div (no filter needed — the class alone styles it).

    2. Magnitude bar — a bracketed span with class `bar` + attributes, used inside a table cell:
         [48]{.bar pct="100" sub="· 38–60"}
       → the .solo/.track/.val bar markup, filled to pct% (0–100), with an optional grey `sub` range.

  Keep this filter tiny. Anything more elaborate than these two belongs in the Tier-2
  hand-authored HTML template, NOT a new construct here (see SKILL.md § Two tiers).
]]

-- Minimal HTML-escape for author-supplied attribute text.
local function esc(s)
  if not s then return nil end
  return (s:gsub("&", "&amp;"):gsub("<", "&lt;"):gsub(">", "&gt;"))
end

-- KPI tile: Div.kpi{n, unit?, l?} → branded tile block.
function Div(el)
  if el.classes:includes("kpi") and el.attributes["n"] then
    local n    = esc(el.attributes["n"])
    local unit = esc(el.attributes["unit"])
    local l    = esc(el.attributes["l"]) or ""
    local num  = unit and (n .. "<small>" .. unit .. "</small>") or n
    local html = '<div class="kpi"><div class="n">' .. num ..
                 '</div><div class="l">' .. l .. '</div></div>'
    return pandoc.RawBlock("html", html)
  end
end

-- Magnitude bar: Span.bar{pct, sub?} → .solo/.track/.val markup. The visible value is the
-- span's own text; `sub` is an optional smaller grey suffix (e.g. a range).
function Span(el)
  if el.classes:includes("bar") and el.attributes["pct"] then
    local pct = esc(el.attributes["pct"])
    local val = pandoc.utils.stringify(el.content)
    local sub = esc(el.attributes["sub"])
    local valhtml = esc(val) .. (sub and (' <small>' .. sub .. '</small>') or '')
    local html = '<div class="solo"><span class="track"><span style="width:' .. pct ..
                 '%"></span></span><span class="val">' .. valhtml .. '</span></div>'
    return pandoc.RawInline("html", html)
  end
end
