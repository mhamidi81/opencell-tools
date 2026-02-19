# opencell-tools

A collection of Claude Code plugins that streamline the OpenCell developer workflow — from Jira ticket management and UI scaffolding to automated commits, pull requests, and code review.

## Plugins

### Skills (slash commands)

| Plugin | Command | Description |
|--------|---------|-------------|
| **oc-cache-jira** | `/cache-jira` | Fetch and cache Jira ticket data locally for use by other commands |
| **oc-commit** | `/oc-commit` | Commit changes using the cached Jira ticket ID and summary with automatic code review |
| **oc-pull-request** | `/oc-pr` | Push changes and create a pull request for the current Jira ticket |
| **oc-create-ui** | `/oc-ui-creation` | Scaffold a UI page from a Jira ticket using the frontend-engineer sub-agent |
| **oc-review-front-code** | `/review-code` | Review React/Node.js code for bugs, security, performance, and best practices |

### MCP Integrations

| Plugin | Description |
|--------|-------------|
| **oc-atlassian-mcp** | Access Jira tickets, Confluence pages, and Compass services |
| **oc-bitbucket-mcp** | Create pull requests, manage repositories, and review code on Bitbucket |
| **oc-figma-mcp** | Extract design context, generate code from Figma designs, and retrieve design tokens |
| **oc-playwright-mcp** | Automate browser interactions, take screenshots, and test web applications |

### Sub-agents

| Plugin | Description |
|--------|-------------|
| **oc-frontend-engineer** | Expert React/TypeScript sub-agent for building, refactoring, and architecting frontend components |
| **oc-frontend-reviewer** | Frontend code reviewer sub-agent that validates React/TypeScript code against project standards |

## Installation

```bash
claude install-plugin opencell/opencell-tools
```
