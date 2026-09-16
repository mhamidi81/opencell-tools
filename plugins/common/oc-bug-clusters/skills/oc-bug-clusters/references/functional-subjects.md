# Bug subject taxonomy

The vocabulary `/oc-bug-clusters` classifies bugs onto. One subject per bug, chosen by
what the bug is **about** — the product area it lives in — never by its symptom
(`quoting`, not `blank-screen`).

Editing this file changes future runs. Adding a subject is safe; **renaming one breaks
month-over-month comparison**, so prefer adding an alias line to renaming.

## rating
Price computation, rating scripts, price plans, charge application, contract and
discount application, usage rating, recurring charge generation.

## quoting
Quotes and the CPQ funnel: quote creation, quote versions, quote offers and products,
quote lifecycle, the Quote UI screens.

## ordering
Commercial orders and order lifecycle: order creation, open orders, order validation,
order products, order status transitions.

## subscriptions
Subscriptions, services, activation, suspension, termination, renewal, subscription
lifecycle and its charges.

## catalog
Offer templates, product templates, charge templates, price plan matrixes, bundles,
attributes and their configuration screens.

## invoicing
Invoice generation, invoice lines, aggregation, invoice validation, PDF/XML production,
invoice sequences, billing runs and billing cycles.

## payments
Payments, payment methods, payment gateways, payment schedules, refunds, direct debit,
payment logs and callbacks.

## matching
Matching and unmatching of accounting entries, manual matching, automatic matching,
account operations balancing.

## dunning
Dunning policies, dunning levels, collection plans, dunning settings and actions.

## accounting
Accounting schemes, journals, accounting entries, chart of accounts, general-ledger
export, revenue recognition.

## taxation
Tax categories, tax classes, tax mapping, tax computation and exemptions.

## customers
Customer hierarchy: sellers, customers, customer accounts, billing accounts, user
accounts, contact information and their screens.

## mediation
CDR ingestion, mediation jobs, EDR processing, rejected records, usage import.

## contracts
Framework agreements, contracts, contract lines, contract rules and their application
conditions.

## reporting
Reports, dashboards, exports, Jasper outputs, KPIs and listings meant for analysis.

## jobs
Job scheduler, job instances, job execution and timers, batch processing outside
mediation and invoicing.

## api
REST endpoints, DTO serialization, Swagger/OpenAPI, GraphQL, API error codes and
generic API filtering — where the defect is in the interface itself.

## security
Authentication, Keycloak, roles and permissions, visibility rules, session handling.

## settings
Global and provider settings, custom fields, custom entities, i18n/translations,
currencies, calendars, administration screens.

## data-management
Import/export of data, file processing, attachments and documents, data migration and
purge.

## navigation
Menus, routing, breadcrumbs, page layout, global search — defects in getting to a
screen rather than in the screen's domain.

## performance
Slow pages, slow queries, timeouts, memory and volume problems, where slowness is the
defect rather than a wrong result.
