"""The taxonomy is the contract between the classifier and the report. Renaming a
category breaks period-over-period comparison, so the exact list is pinned here: a
change to it must be a deliberate edit of this test too."""
import re
from pathlib import Path

TAXONOMY = (Path(__file__).resolve().parents[1] / "skills" / "oc-bug-root-causes"
            / "references" / "dev-root-causes.md")

AGREED = [
    "incomplete-change-propagation", "null-handling", "edge-case-boundary",
    "dto-payload-mapping", "update-overwrites-state", "persistence-transaction",
    "query-construction", "api-contract", "frontend-state-effects", "missing-wiring",
    "business-rule-logic", "numeric-date-precision", "concurrency-lifecycle",
    "ui-cosmetic", "insufficient-evidence",
]


def categories():
    return re.findall(r"^## ([a-z0-9-]+)\s*$", TAXONOMY.read_text(), re.M)


def test_taxonomy_is_exactly_the_agreed_vocabulary():
    assert categories() == AGREED


def test_every_category_has_a_definition_and_examples():
    blocks = re.split(r"^## ", TAXONOMY.read_text(), flags=re.M)[1:]
    for block in blocks:
        name, _, body = block.partition("\n")
        paragraphs = [p.strip() for p in body.strip().split("\n\n") if p.strip()]
        assert paragraphs and not paragraphs[0].startswith("Examples:"), name
        assert any(p.startswith("Examples: INTRD-") for p in paragraphs), name


def test_regression_is_not_a_category():
    assert not any("regression" in c for c in categories())
