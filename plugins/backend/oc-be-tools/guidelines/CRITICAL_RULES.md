# Critical Rules

These rules apply to ALL code in the Opencell project, regardless of layer.

1. **Always use `jakarta.*` packages, NOT `javax.*`** (JVM 21 requirement)
   - `jakarta.inject.Inject`, `jakarta.ws.rs.*`, `jakarta.ejb.*`, `jakarta.persistence.*`
2. **All files need AGPL license header**
3. **All methods must have Javadoc documentation**
4. **All REST endpoints and DTOs must have Swagger annotations**
5. **Never use `var` keyword for variable declarations. Always use explicit types**
6. **Never assume entity fields or business rules. Stop work and ask.**
7. **Ask for clarification if requirements or business rules are ambiguous**
8. **Always verify exact REST API specifications from requirements/Jira tickets before implementing**
9. **Verify all referenced entities exist before implementing**
10. **Do not create methods without specific requirements**
