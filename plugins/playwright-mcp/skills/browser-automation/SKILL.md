---
name: browser-automation
description: Automate browser interactions, take screenshots, and test web pages using Playwright
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Glob, Grep, mcp__playwright__*
argument-hint: "<url-or-action>"
---

Use the Playwright MCP server to automate browser interactions based on $ARGUMENTS.

The argument can be:
- A URL to navigate to and interact with
- A description of a browser automation task to perform
- A test scenario to execute against a web application

## Workflow

1. **Navigate**: Open the target URL or page in the browser.
2. **Interact**: Perform the requested actions such as clicking, typing, scrolling, or taking screenshots.
3. **Report**: Summarize what was found or accomplished, including any screenshots taken.

## Guidelines

- Always start by navigating to the target URL before performing interactions
- Use screenshots to verify the current state of the page when needed
- Wait for page elements to be ready before interacting with them
- When testing, report pass/fail status clearly for each check
- For form interactions, fill fields in a logical order
- If an action fails, capture a screenshot to help diagnose the issue

## Output

Provide:
1. A summary of the actions performed
2. Screenshots or page content as evidence of the result
3. Any errors or issues encountered during the automation
