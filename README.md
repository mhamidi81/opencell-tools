# opencell-tools

A collection of Claude Code plugins that streamline the OpenCell developer workflow — from Jira ticket management and UI scaffolding to automated commits, pull requests, and code review.

## Installation

1. Add the marketplace:

```bash
claude
/install-plugin marketplace https://bitbucket.org/opencellsoft/ccode-marketplace.git
```

2. Install the plugins you need — every plugin in the tables below installs the same way, with `/plugin install <plugin>@opencell-tools`. For example, the frontend set:

```bash
/plugin install oc-fe-engineer@opencell-tools
/plugin install oc-fe-designer@opencell-tools
/plugin install oc-fe-reviewer@opencell-tools
/plugin install oc-fe-test-writer@opencell-tools
/plugin install oc-fe-create-ui@opencell-tools
/plugin install oc-fe-fix-bug@opencell-tools
/plugin install oc-fe-fix-pr@opencell-tools
```

## Plugins

### Skills (slash commands)

| Plugin | Command | Description |
|--------|---------|-------------|
| **oc-cache-jira** | `/oc-cache-jira` | Fetch and cache Jira ticket data locally for use by other commands |
| **oc-commit** | `/oc-commit` | Commit changes using the cached Jira ticket ID and summary, with automatic code review |
| **oc-pull-request** | `/oc-pull-request` | Push changes and create a pull request for the current Jira ticket (auto-detects Bitbucket vs GitHub) |
| **oc-review-pr** | `/oc-review-pr` | Review a pull request linked to a Jira ticket — fetch the PR, select the appropriate reviewer agent, and generate a detailed report |
| **oc-fe-create-ui** | `/oc-fe-create-ui` | Scaffold a UI page from a Jira ticket using the `oc-fe-engineer` sub-agent |
| **oc-fe-fix-bug** | `/oc-fe-fix-bug` | Fix a bug from a Jira ticket — update status to In Progress, create a fix branch, and start fixing |
| **oc-fe-fix-pr** | `/oc-fe-fix-pr` | Fix a pull request's review remarks — read its unresolved Bitbucket comments, fix them on the PR branch via `oc-fe-engineer`, write tests, then reply, resolve, and push |
| **oc-fe-test-writer** | `/oc-fe-write-tests` | Write Vitest tests for changed code (git diff) or specific files via the `oc-fe-test-writer` sub-agent |
| **oc-fe-create-e2e-test** | `/oc-fe-create-e2e-test` | Create Playwright E2E tests from Jira ticket requirements via the `oc-fe-e2e-expert` sub-agent |
| **oc-ar-tools** | `/oc-ar-tech-design` | Analyze a user story and produce a technical design for Opencell Core |
| **oc-ar-ai-tools** | `/oc-ar-ai-tech-design` | Technical design tailored for AI-assisted (Claude) development |

### Backend toolkit (oc-be-tools)

`oc-be-tools` is a complete backend development toolkit for Opencell Core. It bundles slash commands, builder/reviewer sub-agents, and guideline-loading skills that all share one source of truth: the guideline files under `plugins/backend/oc-be-tools/guidelines/` (CRITICAL_RULES, ENTITY, SERVICE, API, DATABASE, CODE_QUALITY, TESTING).

| Type | Provides | Description |
|------|----------|-------------|
| Commands | `/oc-be-implement` | Orchestrate the full implementation of a Jira ticket across entities, database, services, API, tests, and Postman collections |
| Commands | `/oc-be-review` | Evaluate backend changes against the guidelines — reviews uncommitted code or a specific Bitbucket PR (with approve/request-changes) |
| Sub-agents | `oc-be-entity-builder`, `oc-be-service-builder`, `oc-be-api-builder`, `oc-be-test-generator`, `oc-be-postman-generator` | Builder agents that scaffold each layer following the guidelines |
| Sub-agents | `oc-be-pr-reviewer` | Backend code reviewer validating Java/EJB/JPA/Liquibase code against the guidelines, with a score and file:line suggestions |
| Skills | `/oc-be-entity-guide`, `/oc-be-service-guide`, `/oc-be-api-guide`, `/oc-be-db-guide` | Skills that load the relevant guidelines when working on each layer |

### Functional toolkit (oc-fn-tools)

`oc-fn-tools` (func factory) bundles the functional / product-design skills for Opencell. These are **auto-loading** skills — no slash command; each triggers from context — covering Jira authoring, Confluence docs, portal capture, and the design-first delivery methodology.

| Type | Provides | Description |
|------|----------|-------------|
| Skills | `oc-fn-func-design` | Author Jira INTRD issues (Epic / User Story / Enabler / Bug / Feature) — templates, ADF custom fields, acceptance criteria. Functional lane; defers Technical-design authoring to `oc-ar-tech-design`. |
| Skills | `oc-fn-documentation` | Create / update Confluence pages in the Opencell docs space (Concepts + User Manuals) |
| Skills | `oc-fn-portal` | Drive the Opencell Portal via Playwright for design/docs screenshots (not testing); ships the headless `oc-fn-playwright` MCP server |
| Skills | `oc-fn-project-management` | Design-first phased delivery methodology — phase gates, ADRs, repo/CI conventions |

Requires the Atlassian (Rovo) connector for the Jira/Confluence skills (not bundled).

### Sub-agents (frontend)

| Plugin | Description |
|--------|-------------|
| **oc-fe-engineer** | Expert React/TypeScript sub-agent for building, refactoring, and architecting frontend components |
| **oc-fe-designer** | Frontend designer sub-agent for translating Figma designs into implementation-ready React/MUI components with design tokens and styling |
| **oc-fe-reviewer** | Frontend code reviewer sub-agent that validates React/TypeScript code against project standards |
| **oc-fe-test-writer** | Frontend test writer sub-agent that writes Vitest tests for changed React/TypeScript code |
| **oc-fe-cypress-expert** | Cypress testing expert sub-agent for end-to-end testing, test automation, and flaky test resolution |
| **oc-fe-e2e-expert** | Playwright E2E expert sub-agent for authoring browser end-to-end tests |

### MCP Integrations

| Plugin | Command | Description |
|--------|---------|-------------|
| **oc-bitbucket-mcp** | `/oc-bitbucket` | Create pull requests, manage repositories, and review code on Bitbucket |
| **oc-figma-mcp** | `/oc-figma` | Extract design context, generate code from Figma designs, and retrieve design tokens |
| **oc-playwright-mcp** | `/oc-playwright` | Automate browser interactions, take screenshots, and test web applications |
| **oc-opencell-mcp** | `/oc-opencell` | Query and manage the Opencell billing system — invoices, quotes, customers, payments, subscriptions, and more |
| **oc-sonar-mcp** | — | Access SonarQube code quality metrics, issues, and analysis results |
| **oc-postgres-mcp** | — | Database health analysis, index tuning, query optimization, and safe SQL execution via PostgreSQL |
