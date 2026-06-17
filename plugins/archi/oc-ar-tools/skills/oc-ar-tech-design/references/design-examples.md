# Design Examples — Validated Patterns

Reference patterns from validated technical designs in this conversation.
Use these as anchors for consistency.

---

## Pattern 1 — Extending an existing method (INTRD-35926)

When a story asks to extend existing behaviour rather than add new:

```java
// ALWAYS read the existing method from related sibling stories first.
// Then show CURRENT vs FIXED clearly.

// CURRENT — BUG: only handles full matching
if (isValidAo.get() && isPaidToDateMode() && ...) {
    createVatTransferEntries(...);
}

// FIXED — extend condition to also handle partial matching
boolean isFullMatch    = isValidAo.get();
boolean isPartialMatch = MatchingStatusEnum.P.equals(
        accountOperation.getMatchingStatus()); // NEW

if (isPaidToDateMode()
        && (isFullMatch || isPartialMatch)
        && ...) {
    createVatTransferEntries(paymentAo, matchedInvoice, vatAmount);
}
```

**Key rule**: `isValidAo` controls matching code stamping — never modify that block.
`isPartialMatch` is added ONLY for the VAT transfer block.

---

## Pattern 2 — Bug fix via isVirtual flag (INTRD-41717)

When a bug is caused by charges being instantiated when they shouldn't:

```java
// CURRENT — instantiates ALL one-shot charge types, creating WOs
oneShotChargeInstanceService.oneShotChargeInstanciation(
    serviceInstance, serviceCharge, serviceChargeTemplate,
    subscriptionAmount, null, true,
    isVirtual || (oneShotChargeTemplateType == OTHER)
);

// FIXED — INVOICING_PLAN charges are now virtual at activation time
// They are billed exclusively by the OrderAdvancementScript
oneShotChargeInstanceService.oneShotChargeInstanciation(
    serviceInstance, serviceCharge, serviceChargeTemplate,
    subscriptionAmount, null, true,
    isVirtual
        || (oneShotChargeTemplateType == OTHER)
        || (oneShotChargeTemplateType == INVOICING_PLAN)  // FIX
);
```

**Why this works**: `isVirtual=true` → charge instance computed, no WO persisted to DB.
No WO → no double billing from billing run.

---

## Pattern 3 — Fix start date origin (INTRD-35784)

When a method uses `now()` where it should use the entity's own date:

```java
// CURRENT — BUG: uses now() when no sub-periods exist yet
LocalDateTime startDateTime = maxDate == null
    ? LocalDateTime.now()  // ← BUG
    : maxDate.toInstant()...plusMonths(1)...toLocalDateTime();

// FIXED — use fiscal year start date
LocalDateTime startDateTime = maxDate == null
    ? ap.getStartDate().toInstant()
          .atZone(ZoneId.systemDefault()).toLocalDateTime()
    : maxDate.toInstant()...plusMonths(1)...toLocalDateTime();
```

---

## Pattern 4 — Initializing a field after entity creation (INTRD-42263)

When a field must be overridden right after an entity is created:

```java
// After invoiceService.createAdjustment() returns, override the copied value:
adjInvoice.setDueDate(new Date()); // today, not copied from source invoice
invoiceService.update(adjInvoice); // persist before further processing
```

**Important**: the `update()` call is mandatory to persist before any rerate block executes.

---

## Pattern 5 — Backend validation guard (INTRD-42263)

For date/status validation at the service layer:

```java
if (invoice.getDueDate() != null && invoice.getInvoiceDate() != null) {
    LocalDate dueDate     = invoice.getDueDate().toInstant()
            .atZone(ZoneId.systemDefault()).toLocalDate();
    LocalDate invoiceDate = invoice.getInvoiceDate().toInstant()
            .atZone(ZoneId.systemDefault()).toLocalDate();
    if (dueDate.isBefore(invoiceDate)) {
        throw new BusinessException(
            "invoice.creditNote.dueDate.beforeInvoiceDate");
    }
}
```

**Rule from comments**: `dueDate < today` → frontend WARNING only, not a backend error.
`dueDate < invoiceDate` → both frontend AND backend error. Always read story comments for these
nuances — they often override the initial functional design text.

---

## Pattern 6 — Closeout strategy for financial rounding (INTRD-35926)

When a proportional calculation must produce an exact total with no residual:

```java
BigDecimal lineVat;
if (isFinalPayment) {
    // Closeout: transfer EXACTLY what remains to guarantee zero residual in 44580
    // regardless of accumulated rounding from prior partial payments
    BigDecimal alreadyTransferred = getAlreadyTransferredVat(invoice, collectedAcc);
    lineVat = taxAgr.getAmountTax().subtract(alreadyTransferred);
} else {
    // Intermediate: proportional share
    lineVat = computeLineVatAmount(taxAgr, vatAmount, matchedInvoice);
}
```

---

## Pattern 7 — Reading sibling stories before designing

For series like INTRD-35925 → INTRD-35926 → INTRD-42015:

1. Fetch all stories in the series via JQL: `issuelinks` or parent epic
2. Read `customfield_10137` (technical design) of each sibling
3. Extract: class names, method names, error codes, field names
4. Use them verbatim in the new design — no invention

Example JQL to find siblings:
```
key in (INTRD-35925, INTRD-27746) ORDER BY key ASC
```

---

## Pattern 8 — NO IMPACT sections

Use concise, informative NO IMPACT panels:

```
"NO MODEL CHANGES — Reuses Tax fields from INTRD-27746 (Tax.pendingVatAccountingCode,
Tax.collectedVatOnReceiptAccountingCode) and journal entry infrastructure from INTRD-35925.
No new entity fields or DB columns required."

"NO MIGRATION SCRIPT — All schema changes delivered in INTRD-27746."

"NO GUI CHANGES — VAT transfer entries are generated automatically by the batch job.
The resulting 44580/44574 journal entry lines are visible on the existing JournalEntry
list view against the Payment AO."
```

Never just write "NO IMPACT" alone — always explain why.

---

## Common Opencell class references

| Class | Package | Role |
|---|---|---|
| `JournalEntryService` | `org.meveo.service.accountingscheme` | Journal entry creation & matching |
| `InvoiceApiService` | `org.meveo.apiv2.billing.service` | Invoice API layer |
| `InvoiceService` | `org.meveo.service.billing.impl` | Invoice business logic |
| `ServiceInstanceService` | `org.meveo.service.billing.impl` | Service instance & charge instantiation |
| `OneShotChargeInstanceService` | `org.meveo.service.billing.impl` | One-shot charge instantiation |
| `RatedTransactionService` | `org.meveo.service.billing.impl` | WO → RT conversion |
| `SubAccountingPeriodService` | `org.meveo.service.billing.impl` | Fiscal sub-period generation |
| `AccountingPeriodService` | `org.meveo.service.billing.impl` | Fiscal year management |
| `CommercialOrderApi` | `org.meveo.api.cpq` | Order advancement & invoicing |
| `BillingRunApiImpl` | `org.meveo.apiv2.billing` | Billing run API |
