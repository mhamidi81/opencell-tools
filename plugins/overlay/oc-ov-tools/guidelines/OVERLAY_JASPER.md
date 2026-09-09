# Jasper reports

> LAYERS OVER: nothing — no core equivalent. Core CODE_QUALITY applies.
> CORE BASELINE: oc-be-tools 1.17.0

## Location and shape

Invoice report templates live under the jasper module's release input-files tree, as `.jrxml` sources
paired one-to-one with compiled `.jasper` files, plus image and font assets.

## The compiled artifact is committed, and the build does not produce it

**Every `.jrxml` change must ship a regenerated `.jasper` in the same commit.** Nothing in the Maven
reactor compiles them — the jasper folder is not a module — so a `.jrxml`-only commit deploys a stale
report with no error anywhere.

## Review rule

A `.jasper` is a binary: reviewing its diff is meaningless. Review the `.jrxml`, and separately assert
that a matching `.jasper` was regenerated. A changed `.jrxml` with no accompanying `.jasper` is a
blocking finding.

## Data source

Report fields come from the invoice XML produced by the XML-invoice-creation script, not directly from
entities. **Verify a field exists in that XML before adding it to a report** — a missing field renders
blank rather than failing.

## Naming

Follow the existing `invoice_<variant>{Detail|Lines}.jrxml` convention and keep the `.jasper` basename
identical.
