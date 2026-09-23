--[[ oc-artifact.lua — Pandoc Lua filter for the oc-fn-briefs ARTIFACT lane only.

  Runs after oc-brief.lua when rendering a brief as a claude.ai Artifact. It adds no
  vocabulary: the same `.md` renders to the A4 PDF and to the Artifact unchanged.

  An Artifact is read at phone width, where the page body must never scroll sideways; only a
  table may, inside its own box. Pandoc emits bare <table>s, so each one is wrapped in a
  `div.tscroll` (styled by theme/artifact.css). The print lane doesn't load this filter,
  so the PDF layout is untouched.
]]

function Table(el)
  return pandoc.Div({ el }, pandoc.Attr("", { "tscroll" }))
end
