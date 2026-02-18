---
name: bitbucket-pr
description: Create and manage Bitbucket pull requests via MCP
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, mcp__bitbucket__*
argument-hint: "<action> [details]"
---

Use the Bitbucket MCP server to manage pull requests and repositories based on $ARGUMENTS.

The argument can be:
- `create pr` — Create a new pull request from the current branch
- `list prs` — List open pull requests for the current repository
- `review <pr-id>` — Fetch and summarize a specific pull request
- A natural language description of what you need

## Workflow

1. **Identify the action**: Determine whether the user wants to create, list, review, or update a pull request.
2. **Gather context**: For PR creation, inspect the current branch, commits, and changes to draft a title and description.
3. **Execute via MCP**: Use the Bitbucket MCP tools to perform the requested action.
4. **Report results**: Provide confirmation with relevant links and details.

## Guidelines

- When creating a PR, analyze the branch diff to write a clear title and description
- Include the source and destination branches in PR creation
- For PR reviews, summarize the changes, comments, and approval status
- Always include the PR URL in the output
- Default destination branch is `main` unless the user specifies otherwise

## Output

Provide:
1. Confirmation of the action taken
2. PR URL and key details (title, source/destination branches, status)
3. Summary of changes when relevant
