# Opencell Project - Code Quality Guidelines

> **Note**: This document contains code quality, version control, and review guidelines. For general project guidelines, see [CLAUDE.md](./CLAUDE.md).

## Table of Contents
- [Code Readability](#code-readability)
- [Resource Management](#resource-management)
- [Variable Best Practices](#variable-best-practices)
- [Exception Handling](#exception-handling)
- [Dependency Management](#dependency-management)
- [Return Values](#return-values)
- [Version Control](#version-control)
- [Code Review Checklist](#code-review-checklist)
- [Documentation Standards](#documentation-standards)
- [Important Reminders](#important-reminders)

---

## Code Readability

### Format Code Consistently

- Format code, XML and other files to the width of **220 characters**
- Use consistent indentation and spacing
- Keep methods short and focused on single responsibility

### Use Curly Braces for Single-Line IF

Always use `{ }` for single-line IF statements for better readability and maintainability:

```java
// ✅ CORRECT
if (field != null) {
    return A;
}

// ❌ WRONG
if (field != null)
    return A;
```

### Split Long Method Chains

Split long method chains into readable multi-line format instead of writing them as single-line expressions:

```java
// ❌ WRONG - Hard to read
return Optional.ofNullable(field.tableName()).map(tableName -> customEntityInstanceService.listByCet(field.tableName()).stream().map(customEntityInstanceService::customEntityInstanceAsMap).map(x -> new CustomTableRecordDto(x, tableName)).collect(Collectors.toList())).orElse(loadFromBusinessEntity(field));

// ✅ CORRECT - Much more readable
if (field.tableName() != null) {
    return customEntityInstanceService.listByCet(field.tableName()).stream()
        .map(customEntityInstanceService::customEntityInstanceAsMap)
        .map(x -> new CustomTableRecordDto(x, tableName))
        .collect(Collectors.toList());
} else {
    return loadFromBusinessEntity(field);
}
```

---

## Resource Management

### Clean Up Resources Properly

Always clean up resources like database connections, network connections, or IO streams using try-with-resources or finally blocks.

**Preferred approach - try-with-resources:**

```java
try (BufferedReader br = new BufferedReader(new FileReader("abc.txt"))) {
    // Use the resource
}
// Resource automatically closed
```

**Alternative approach - finally block:**

```java
BufferedReader br = new BufferedReader(new FileReader("abc.txt"));
try {
    // Use the resource
} finally {
    if (br != null) {
        try {
            br.close();
        } catch (Exception e) {
            log.error("Failed to close file abc.txt reader", e);
        }
    }
}
```

---

## Variable Best Practices

### Variable Declaration in Loops

**Warning:** If a variable is declared outside the loop but gets its value set inside the loop, verify it gets set in every iteration to avoid using values from previous iterations.

```java
// ❌ WRONG - newStatus might contain value from previous iteration
String newStatus = null;
for (Order order : orders) {
    if (order.status == PENDING) {
        newStatus = FINISHED;
    }

    if (newStatus == ...) // newStatus might be from previous iteration!
}

// ✅ CORRECT - Declare inside loop or ensure it's set every iteration
for (Order order : orders) {
    String newStatus = null;
    if (order.status == PENDING) {
        newStatus = FINISHED;
    }
    // Use newStatus
}
```

### Static Fields Warning

**Static fields are never garbage collected.**

When using static fields:
- Document how they are populated
- Document if they are ever cleaned up
- Consider if the data really needs to be static
- Be aware of memory implications in long-running applications

---

## Exception Handling

### Be Specific with Exception Types

Use specific exception types in catch blocks instead of generic `Exception`:

```java
// ✅ CORRECT - Specific exception types
} catch (IllegalArgumentException | ParseException e) {
    // Handle specific exceptions
}

// ❌ WRONG - Too generic
} catch (Exception e) {
    // What kind of exception is this?
}
```

### Don't Use Empty Catch Blocks

Never ignore exceptions with empty catch blocks or by only printing stack trace:


### Don't Lose the Original Exception

When constructing a new exception from inside a catch block, always pass the original exception as a parameter:

```java
// ✅ CORRECT - Original exception preserved
} catch (NoAllOperationUnmatchedException | UnbalanceAmountException e) {
    throw new BusinessException(e);
}

// ❌ WRONG - Original exception lost (NPE has empty message!)
} catch (NoAllOperationUnmatchedException | UnbalanceAmountException e) {
    throw new BusinessException(e.getMessage());
}
```

### Log and Throw Anti-Pattern

**Logging and throwing exception within catch block is an anti-pattern** that leads to duplicate log entries.

```java
// ❌ WRONG - Log and throw anti-pattern
} catch (Exception e) {
    log.error("Failed to process", e);
    throw e; // Will be logged again where finally caught!
}

// ✅ CORRECT - Only log where finally caught (GUI, API, Jobs)
} catch (Exception e) {
    throw new BusinessException("Failed to process order", e);
}
```

**Rule:** Log error messages only once - where the exception is finally caught (GUI layer, API layer, Jobs).

### Don't Use Exceptions for Flow Control

Don't throw exceptions instead of returning null. This can cause unintended transaction rollbacks:

```java
// ❌ WRONG - Using exception for flow control
public Tax findByTaxPercent(BigDecimal percent) {
    Tax tax = // lookup logic
    if (tax == null) {
        throw new TaxNotFoundException(); // Might cause transaction rollback!
    }
    return tax;
}

// ✅ CORRECT - Return null and let caller handle it
public Tax findByTaxPercent(BigDecimal percent) {
    Tax tax = // lookup logic
    return tax; // Can be null
}
```

### String Comparison - Null Safe Approach

Use null-safe string comparison by putting the known string first:

```java
// ✅ CORRECT - Null-safe approach
if ("new".equalsIgnoreCase(action)) {
    // Safe even if action is null
}

// ❌ WRONG - Potential NPE
if (action.equalsIgnoreCase("new")) {
    // Will throw NPE if action is null
}
```

---

## Dependency Management

### Check Existing Libraries First

Before adding a new dependency to pom.xml:

1. **Check if the function already exists** in an existing library
2. **Consider if it's really necessary** - maybe a simple new method is sufficient
3. **Prefer libraries distributed as modules with Wildfly**
4. **Check library dependencies and versions** to match Wildfly module versions

Adding unnecessary dependencies:
- Increases application size
- Can cause version conflicts
- May introduce security vulnerabilities
- Complicates maintenance

---

## Return Values

### Return Empty Collections Instead of Null

For methods with collection return types (List, Set, Map), return an empty collection instead of null:

```java
// ✅ CORRECT - Return empty collection
public List<Item> getItems() {
    if (items == null || items.isEmpty()) {
        return Collections.EMPTY_LIST;
    }
    return items;
}

// ❌ WRONG - Return null
public List<Item> getItems() {
    if (items == null) {
        return null; // Caller must check for null
    }
    return items;
}
```

**Use:**
- `Collections.EMPTY_LIST`
- `Collections.EMPTY_SET`
- `Collections.EMPTY_MAP`

This eliminates null checks in calling code and prevents NullPointerExceptions.

---

## Version Control

### Branch Naming

Use descriptive branch names that include username, ticket type, and number.

**Format**: `{username}/{type}/{TICKET-NUMBER}-{brief-description}`

**Types:**
- `feature/` - New features
- `bugfix/` - Bug fixes
- `hotfix/` - Urgent production fixes
- `refactor/` - Code refactoring
- `docs/` - Documentation updates

**Example:** `andrius/feature/INTRD-34243-add-indexation-entities`

**Best practices:**
- Keep names lowercase with hyphens
- Keep descriptions brief (3-5 words)
- Delete branches after merging

### Commit Messages

**Format**: `TICKET-NUMBER: Brief description`

- Use imperative mood
- Keep under 72 characters
- Be descriptive but concise

**Example:** `INTRD-34243: Add Indexation and IndexationValue entities`

### Pull Requests

- Create feature branches for new development
- Reference Jira ticket in PR title and description
- Link related tickets using `Relates to INTRD-XXXXX`
- Ensure CI/CD passes before requesting review
- Respond to review comments promptly
- Keep PRs focused and reasonably sized

---

## Code Review Checklist

Before submitting code for review, verify:

### Code Standards

- [ ] All classes have AGPL license header
- [ ] All methods have Javadoc documentation
- [ ] No compilation warnings
- [ ] No hardcoded values (use constants or configuration)
- [ ] Code follows project conventions (naming, structure)
- [ ] No use of `var` keyword (use explicit types)
- [ ] Uses `jakarta.*` packages (not `javax.*`)

### API & REST

- [ ] Swagger annotations on all REST endpoints and DTO fields
- [ ] REST endpoints match Jira ticket specifications
- [ ] Proper HTTP status codes used
- [ ] Error handling follows standard patterns
- [ ] All DTOs extend Resource interface correctly

### Service Layer

- [ ] Business rules properly validated
- [ ] Exceptions are appropriate for service layer (BusinessException, ValidationException)
- [ ] Service methods return updated entities when calling update()
- [ ] Validation methods placed in correct service

### Database

- [ ] Liquibase changesets for database changes
- [ ] Changes in both current/structure.xml and rebuild/structure.xml
- [ ] Proper column types and constraints
- [ ] Primary key naming follows convention

### Testing

- [ ] Unit tests cover main scenarios and edge cases
- [ ] Integration tests verify end-to-end functionality
- [ ] Postman collection updated (if API changes)
- [ ] Tests are independent and repeatable

### Version Control

- [ ] JIRA ticket referenced in commit message
- [ ] Branch follows naming convention
- [ ] PR description includes context and testing notes
- [ ] No unnecessary files committed (.class, .log, etc.)

### Code Quality Tools

- [ ] Sonar Cloud results reviewed for code quality and security issues

---

## Documentation Standards

### Javadoc

- Add Javadoc documentation to all classes and methods
- For setter and getter methods of entity class, use field description in Javadoc
- Document parameters, return values, and exceptions
- Include examples for complex methods

### REST and DTO Documentation

In addition to Javadoc, add Swagger annotations to REST interface definition and DTO classes.

**REST Interface Swagger Annotations:**
- **Class level**: Add `@Tag` annotation with name and description
- **Method level**: Add `@Operation` with summary, tags, description, and all possible response codes
- **Parameters**: Use `@Parameter` annotation with description and required status

**DTO Swagger Annotations:**
- Always use `@Schema` annotations on DTO fields
- Include description, example values, and required status
- Do not mark field as required in swagger if field is not marked as required in DTO

### Code Comments

- Use comments to explain "why", not "what"
- Keep comments up-to-date with code changes
- Remove commented-out code before committing
- Use TODO comments sparingly and track them properly

---

## Important Reminders

### Critical Rules

These are the most important rules that must never be violated:

1. **Never assume entity fields or business rules. Stop work and ask.**
2. **Ask for clarification if requirements or business rules are ambiguous**
3. **Always verify exact REST API specifications from requirements/Jira tickets before implementing**
4. **Always use `jakarta.*` packages, NOT `javax.*`** (JVM 21 requirement)
5. **All files need AGPL license header**
6. **Never use `var` keyword for variable declarations. Always use explicit types**

### Do What's Asked

- Do what has been asked; nothing more, nothing less
- **NEVER create files unless they're absolutely necessary for achieving your goal**
- **ALWAYS prefer editing an existing file to creating a new one**
- **NEVER proactively create documentation files (*.md) or README files**
  - Only create documentation files if explicitly requested by the user

### Code Quality Principles

- Write clean, readable, maintainable code
- Follow the Single Responsibility Principle
- Keep methods short and focused
- Use meaningful variable and method names
- Avoid duplication (DRY principle)
- Test your code thoroughly before submitting

---

## Continuous Improvement

- Learn from code review feedback
- Stay updated with project conventions
- Ask questions when uncertain
- Share knowledge with team members
- Contribute to improving these guidelines
