---
name: oc-review-front-code
description: Review React and Node.js code for bugs, security, performance, and best practices
disable-model-invocation: true
allowed-tools: Read, Grep, Glob
argument-hint: "[file-or-directory]"
---

Review the code at $ARGUMENTS (or the recent changes if no path is provided).

## React Review Checklist

- **Component design**: proper use of functional components, hooks, and composition
- **State management**: correct use of useState, useReducer, useContext; avoid unnecessary re-renders
- **Side effects**: useEffect dependencies are correct, cleanup functions are present where needed
- **Memoization**: appropriate use of useMemo and useCallback; avoid premature optimization
- **Props**: proper typing, no prop drilling, default values handled correctly
- **Keys**: stable and unique keys in lists, no use of array index as key for dynamic lists
- **Event handling**: no inline function creation in render when avoidable, proper cleanup
- **Accessibility**: semantic HTML, ARIA attributes, keyboard navigation support
- **Security**: no dangerouslySetInnerHTML with unsanitized input, no secrets in client code

## Node.js Review Checklist

- **Error handling**: async/await errors caught, no unhandled promise rejections, proper error propagation
- **Security**: input validation and sanitization, no SQL/NoSQL injection, parameterized queries
- **Authentication/Authorization**: proper middleware usage, secrets not hardcoded, token validation
- **Performance**: no blocking the event loop, efficient database queries, proper use of streams for large data
- **Dependencies**: no known vulnerable packages, minimal dependency surface
- **API design**: consistent RESTful patterns, proper HTTP status codes, request validation
- **Logging**: structured logging, no sensitive data in logs, appropriate log levels
- **Environment**: config via environment variables, no hardcoded URLs or credentials

## General Review Checklist

- **Bugs and edge cases**: null/undefined handling, off-by-one errors, race conditions
- **Code style**: consistent naming, no dead code, clear variable names
- **DRY**: no excessive duplication, but avoid premature abstraction
- **Testing**: testable code structure, edge cases considered
- **TypeScript**: proper typing, no unnecessary `any`, discriminated unions where appropriate

## Output Format

For each finding, provide:
1. **Severity**: Critical / Warning / Suggestion
2. **File and line**: exact location
3. **Issue**: concise description of the problem
4. **Fix**: actionable recommendation

Be concise and actionable. Focus on issues that matter, not style nitpicks.
