# Error Code Conventions & Bilingual Message Examples

## Naming convention

Error codes follow the pattern: `entity.context.rule`

Examples:
- `billing.run.advanceStatus.invalidStatus`
- `billing.run.notFound`
- `invoice.creditNote.dueDate.beforeInvoiceDate`
- `VAT_TRANSFER_ENTRY_GENERATION_FAILED`
- `PENDING_VAT_ACCOUNTING_CODE_MISSING`
- `COLLECTED_VAT_ACCOUNTING_CODE_MISSING`
- `SETUP_FEE_WO_RT_TRANSFORMATION_FAILED`

## HTTP status codes

| Code | When |
|---|---|
| 400 | Bad request, validation error, missing parameter |
| 404 | Entity not found |
| 409 | Conflict (e.g. invalid status transition) |
| 403 | Forbidden (permission, feature flag) |
| 500 | Unexpected server error |

## Bilingual message examples

| Code | EN | FR |
|---|---|---|
| `billing.run.advanceStatus.invalidStatus` | Billing run status must be one of {allowed} | Le statut du billing run doit être l'un de {allowed} |
| `billing.run.notFound` | Billing run {id} not found | Le billing run {id} est introuvable |
| `invoice.creditNote.dueDate.beforeInvoiceDate` | Due date cannot be before invoice date. | La date d'échéance ne peut pas être antérieure à la date de facture. |
| `COLLECTED_VAT_ACCOUNTING_CODE_MISSING` | Collected VAT on receipt accounting code (44574) is not configured on Tax {code} while VAT recognition mode is 432. | Le compte TVA collectée (44574) n'est pas configuré sur la taxe {code} alors que le mode de reconnaissance TVA est 432. |
| `PENDING_VAT_ACCOUNTING_CODE_MISSING` | Pending VAT accounting code (44580) is not configured on Tax {code} while VAT recognition mode is 432. | Le code TVA en attente (44580) n'est pas configuré sur la taxe {code} alors que le mode de reconnaissance est 432. |
| `VAT_TRANSFER_ENTRY_GENERATION_FAILED` | Failed to generate VAT transfer journal entries for AccountOperation id={id}: {reason} | Echec de génération des écritures de transfert TVA pour l'opération comptable id={id}: {raison} |
| `SETUP_FEE_WO_RT_TRANSFORMATION_FAILED` | An error occurred while processing the setup fee charge for this order. Please contact your administrator. | Une erreur est survenue lors du traitement des frais de mise en service. Veuillez contacter votre administrateur. |

## Java throw pattern

```java
// Always use message key, never hardcoded string
throw new BusinessException("entity.context.rule", param1, param2);

// For API layer (400)
throw new BadRequestException("entity.context.rule");

// For missing entities (404)
throw new EntityDoesNotExistsException(Entity.class, code);

// For forbidden operations (403)
throw new ForbiddenException(resourceMessages.getString("error.action.forbidden"));
```

## Rules

- Never hardcode error message text in Java source
- Always provide both EN and FR in the technical design error table
- Use `{param}` placeholders for dynamic values
- Message keys go in the i18n properties file — note this in the design if new keys are added
