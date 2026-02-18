---
name: cache-jira
description: Fetch and cache JIRA ticket data locally
argument-hint: JIRA Ticket ID(s) to cache (e.g., INTRD-36922 or INTRD-36922,INTRD-36896)
---

## Purpose

This command fetches JIRA ticket data from Atlassian and stores it locally in `.claude/cache/jira-tickets.json` for use by other commands without requiring repeated API calls.

## Context

Parse the $ARGUMENTS to get:

- [TICKET-IDS]: One or more JIRA ticket IDs (comma-separated if multiple)

## Tasks

### 1. Parse Ticket IDs

- Split $ARGUMENTS by comma to get list of ticket IDs
- Trim whitespace from each ID
- Validate format (should match pattern like PROJ-12345)

### 2. Read Existing Cache

- Check if `.claude/cache/jira-tickets.json` exists
- If it exists, read and parse the JSON content
- If it doesn't exist, initialize an empty cache object:
  ```json
  {
    "lastUpdated": null,
    "tickets": {}
  }
  ```

### 3. Fetch JIRA Data

For each ticket ID:

- Connect to JIRA using the Atlassian MCP server
- Fetch the issue data including:
  - `key`: Ticket ID
  - `summary`: Ticket summary/title
  - `type`: Issue type (Story, Bug, Task, etc.)
  - `status`: Current status
  - `assignee`: Assigned user (displayName and accountId)
  - `description`: Full description
  - `labels`: Array of labels
  - `components`: Array of components
  - `fixVersions`: Target versions
  - `priority`: Priority level
  - `subtasks`: List of subtask keys and summaries

### 4. Update Cache

- Add/update each ticket in the cache with structure:
  ```json
  {
    "lastUpdated": "2024-01-31T12:00:00.000Z",
    "tickets": {
      "INTRD-36922": {
        "key": "INTRD-36922",
        "summary": "[Front] Claude Code integration on Portal",
        "type": "Task",
        "status": "In Progress",
        "assignee": {
          "displayName": "Mohamed Hamidi",
          "accountId": "5ef5c13914f60e0ac1c9b049"
        },
        "description": "...",
        "labels": ["frontend"],
        "components": ["Frontend"],
        "fixVersions": ["19.0.0"],
        "priority": "Highest",
        "subtasks": [],
        "cachedAt": "2024-01-31T12:00:00.000Z"
      }
    }
  }
  ```

### 5. Write Cache File

- Write the updated cache to `.claude/cache/jira-tickets.json`
- Use pretty-printed JSON (2-space indentation) for readability

### 6. Display Summary

Display a summary of cached tickets:

```
Cached JIRA Tickets:
--------------------
INTRD-36922: [Front] Claude Code integration on Portal (In Progress)
  Type: Task | Priority: Highest | Assignee: Mohamed Hamidi
  Cached at: 2024-01-31 12:00:00

Total: 1 ticket(s) cached
Cache location: .claude/cache/jira-tickets.json
```

## Options

If $ARGUMENTS contains:

- `--list` or `-l`: Just list currently cached tickets without fetching
- `--clear` or `-c`: Clear the cache file
- `--refresh` or `-r`: Force refresh all cached tickets

---

## JIRA Cache Utilities

This section describes how to use the JIRA cache in other commands.

### Cache File Location

```
.claude/cache/jira-tickets.json
```

### Cache Structure

```json
{
  "lastUpdated": "ISO-8601 timestamp",
  "tickets": {
    "TICKET-ID": {
      "key": "TICKET-ID",
      "summary": "Ticket summary",
      "type": "Story|Bug|Task|Sub-task",
      "status": "To Do|In Progress|Done|...",
      "assignee": {
        "displayName": "User Name",
        "accountId": "atlassian-account-id"
      },
      "description": "Full description text",
      "labels": ["label1", "label2"],
      "components": ["Component1"],
      "fixVersions": ["19.0.0"],
      "priority": "Highest|High|Medium|Low|Lowest",
      "subtasks": [{ "key": "TICKET-123", "summary": "Subtask summary" }],
      "cachedAt": "ISO-8601 timestamp"
    }
  }
}
```

### How to Use in Commands

#### Check Cache First Pattern

When your command needs JIRA data, follow this pattern:

1. **Try to read from cache first:**

   ```
   Read .claude/cache/jira-tickets.json
   Check if tickets[TICKET-ID] exists
   ```

2. **If found in cache:**

   - Check `cachedAt` timestamp
   - If less than 1 hour old, use cached data
   - If older, optionally refresh from Atlassian

3. **If not in cache:**
   - Fetch from Atlassian MCP server
   - Store in cache for future use
   - Continue with the fetched data

### Cache Expiration

- Default cache TTL: 1 hour
- Commands can force refresh with `--refresh` flag
- Use `/cache-jira --clear` to clear all cached data
