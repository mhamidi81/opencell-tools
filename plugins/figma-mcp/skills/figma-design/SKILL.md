---
name: figma-design
description: Extract design context from Figma and generate matching code
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Glob, Grep, mcp__figma__*
argument-hint: "<figma-url>"
---

Use the Figma MCP server to extract design context from the provided Figma URL and generate or update code to match the design.

The user will provide a Figma frame or layer URL as $ARGUMENTS.

## Workflow

1. **Extract design context**: Use the Figma MCP tools to retrieve design data from the provided URL, including layout, styles, components, and design tokens.
2. **Analyze the design**: Identify the structure, spacing, colors, typography, and component hierarchy.
3. **Generate or update code**: Produce code that accurately reflects the design, reusing existing components from the codebase where possible.

## Guidelines

- Always fetch the latest design data from Figma before generating code
- Preserve existing code structure and patterns in the project
- Reuse existing components and design system tokens when available
- Match spacing, colors, typography, and layout as closely as possible to the Figma design
- Use semantic HTML and follow accessibility best practices
- If the design references components, check Code Connect mappings first

## Output

Provide:
1. A summary of the design elements extracted
2. The generated or updated code files
3. Any design tokens or variables that were used or need to be added
