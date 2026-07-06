# func factory

Functional / product-design plugins, on the `oc-fn-<name>` naming convention.

## oc-fn-tools

Bundle plugin (`plugins/func/oc-fn-tools`) with six skills:

- **oc-fn-func-design** — author Jira INTRD issues (Epic / User Story / Enabler / Bug / Feature): templates, ADF custom fields, acceptance criteria. Functional lane; defers Technical-design authoring to `oc-ar-tech-design`.
- **oc-fn-documentation** — create/update Confluence pages in the Opencell docs space (Concepts + User Manuals).
- **oc-fn-portal** — drive the Opencell Portal via Playwright for design/docs screenshots (not testing). Ships the headless `oc-fn-playwright` MCP server.
- **oc-fn-project-management** — the design-first phased delivery methodology (gates, ADRs, repo/CI conventions).
- **oc-fn-decks** — author & render Opencell-branded slide decks with the Marp theme (Charte Graphique 2023): theme, authoring conventions, `marp-cli` rendering, overflow + locale checks.
- **oc-fn-gui-design** — design GUI-impacting Stories against the Opencell Figma design system (MUI v6): read components/tokens, produce a grounded screen spec (+ optional mockup), optionally author editable Figma frames in a sandbox. Feeds the Story's GUI section.

**Requires** the Atlassian (Rovo) connector for the Jira/Confluence skills, and the Figma connector for `oc-fn-gui-design` — neither is bundled here; enable them in claude.ai.
