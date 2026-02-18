---
name: jira-tickets
description: Search, read, create, and update Jira tickets via Atlassian MCP
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Glob, Grep, mcp__atlassian__*
argument-hint: "<ticket-key-or-query>"
---

Use the Atlassian MCP server to work with Jira tickets based on $ARGUMENTS.

The argument can be:
- A Jira ticket key (e.g. `OC-1234`) to fetch and display a specific ticket
- A JQL query or natural language search to find relevant tickets
- A description of a new ticket to create

## Workflow

1. **Fetch ticket context**: Use Atlassian MCP tools to search or retrieve Jira issues matching the request.
2. **Present the information**: Summarize ticket details including status, assignee, priority, description, and comments.
3. **Take action if requested**: Create, update, or comment on tickets as instructed.

## Guidelines

- When fetching a single ticket, include its full context: summary, description, status, assignee, priority, labels, and recent comments
- When searching, present results as a concise table with key, summary, status, and assignee
- For ticket creation, ensure required fields (project, summary, issue type) are provided before creating
- For updates, confirm the changes before applying them
- Use JQL for precise queries when the user provides structured search criteria
- Always reference tickets by their key (e.g. `OC-1234`) in output

## Output

Provide:
1. Ticket details or search results in a readable format
2. Any actions taken (created, updated, commented) with confirmation
3. Relevant links to the tickets in Jira
