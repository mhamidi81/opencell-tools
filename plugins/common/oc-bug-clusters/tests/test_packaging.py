"""The plugin must be discoverable and follow the marketplace naming convention.

These are cheap guards against the two mistakes that make a plugin silently absent:
a missing marketplace entry, and a directory name that disagrees with the plugin name.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PLUGIN_DIR = REPO / "plugins" / "common" / "oc-bug-clusters"
NAME = "oc-bug-clusters"


def test_plugin_json_name_matches_directory():
    meta = json.loads((PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text())
    assert meta["name"] == NAME == PLUGIN_DIR.name
    assert re.fullmatch(r"\d+\.\d+\.\d+", meta["version"])
    assert meta["description"].strip()


def test_marketplace_registers_the_plugin():
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    entries = [p for p in market["plugins"] if p["name"] == NAME]
    assert len(entries) == 1, "plugin must appear exactly once in marketplace.json"
    assert entries[0]["source"] == f"./plugins/common/{NAME}"


def test_skill_directory_name_matches_skill_name():
    assert (PLUGIN_DIR / "skills" / NAME).is_dir()


def seeded_subjects():
    text = (PLUGIN_DIR / "skills" / NAME / "references" / "subjects.md").read_text()
    return re.findall(r"^## ([a-z0-9-]+)$", text, re.M)


def test_subjects_are_lower_kebab_and_unique():
    subjects = seeded_subjects()
    assert len(subjects) >= 15, "taxonomy too thin to classify against"
    assert len(subjects) == len(set(subjects)), "duplicate subject heading"
    for s in subjects:
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s), s


def test_every_subject_has_a_description_line():
    text = (PLUGIN_DIR / "skills" / NAME / "references" / "subjects.md").read_text()
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        heading, _, body = block.partition("\n")
        assert body.strip(), f"subject '{heading}' has no description"
