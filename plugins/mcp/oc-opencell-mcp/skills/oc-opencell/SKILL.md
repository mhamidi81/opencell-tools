---
name: oc-opencell
description: Interact with the Opencell billing system — query entities, manage invoices, payments, quotes, customers, dunning, and all billing operations
disable-model-invocation: true
allowed-tools: Read, Glob, Grep, mcp__opencell__*
argument-hint: "<action-or-query>"
---

Use the Opencell MCP server to interact with the billing system based on $ARGUMENTS.

The argument can be:
- A natural language query about billing data (e.g., "list all draft invoices", "find customer OPENSOFT-01")
- A billing action to perform (e.g., "cancel invoice 123", "retry payment 456")
- An entity discovery request (e.g., "what entities are available?", "describe the Invoice entity")

## Available Tools

### Discovery Tools
- **list_entities** — Discover all queryable entity names (423+ entities)
- **describe_entity** — Get field names, types, and relationships for any entity
- **opencell_version** — Get Opencell system version
- **help** — Show all available tools and usage guide

### Generic CRUD Tools (work with ANY entity)
- **generic_list** — Search/filter any entity with pagination and sorting
- **generic_get** — Get a single entity by name and ID
- **generic_create** — Create a new entity
- **generic_update** — Update an existing entity
- **generic_delete** — Delete an entity

### Domain Action Tools
- **invoice_actions** — Cancel, validate, reject, rebuild, get PDF, generate, duplicate invoices
- **invoicing_actions** — Manage billing runs (create, advance, cancel, enable/disable)
- **payment_actions** — Process card/SEPA payments, manage rejection codes, retry payments
- **dunning_actions** — Manage collection plans (switch, pause, resume, stop, mass operations)
- **account_actions** — Transfer subscriptions, move accounts, apply charges
- **order_actions** — Find and manage orders
- **cpq_actions** — CPQ quotes and contract billing rules
- **catalog_actions** — Price plans, price lists, discount plans
- **mediation_actions** — CDR management
- **indexation_actions** — Price indexation batches
- **document_actions** — Document file management with versioning
- **reporting_actions** — Execute report queries, export aged receivables

## Workflow

1. **Discover**: Use `list_entities` to see what's available, then `describe_entity` to learn fields
2. **Query**: Use `generic_list` with filters and field selection to find data
3. **Inspect**: Use `generic_get` to retrieve full entity details
4. **Act**: Use domain action tools for business operations (cancel invoice, process payment, etc.)
5. **Modify**: Use `generic_create`/`generic_update`/`generic_delete` for data changes

## Key Entity Names
Common entities: Invoice, Customer, CustomerAccount, BillingAccount, UserAccount, CpqQuote, CommercialOrder, Subscription, InvoiceLine, AccountOperation, DunningCollectionPlan, PricePlanMatrix, DiscountPlan, AccountingArticle

## Guidelines

- Always use `describe_entity` before creating/updating to understand required fields
- Use field selection in `generic_list` to keep responses concise (e.g., `fields: ["id", "code", "status"]`)
- Use pagination (offset/limit) for large result sets
- Filter with exact field values: `filters: {"status": "ACTIVE"}`
- Sort with `sortBy` and `sortOrder` (ASCENDING/DESCENDING)
- For invoice operations, use `invoice_actions` instead of generic CRUD
- For payment processing, use `payment_actions`

## Output

Provide:
1. The data or result of the operation in a clear, readable format
2. Relevant counts and pagination info for list queries
3. Confirmation of actions performed with entity IDs
4. Any errors with actionable guidance on how to fix them
