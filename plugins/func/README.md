# func factory

Functional / product-design plugins, on the `oc-fn-<name>` naming convention.

## oc-fn-tools

Bundle plugin (`plugins/func/oc-fn-tools`) with four skills:

- **oc-fn-func-design** — author Jira INTRD issues (Epic / User Story / Enabler / Bug / Feature): templates, ADF custom fields, acceptance criteria. Functional lane; defers Technical-design authoring to `oc-ar-tech-design`.
- **oc-fn-documentation** — create/update Confluence pages in the Opencell docs space (Concepts + User Manuals).
- **oc-fn-portal** — drive the Opencell Portal via Playwright for design/docs screenshots (not testing). Ships the headless `oc-fn-playwright` MCP server.
- **oc-fn-project-management** — the design-first phased delivery methodology (gates, ADRs, repo/CI conventions).

**Requires** the Atlassian (Rovo) connector for the Jira/Confluence skills — it is not bundled here; enable it in claude.ai.
