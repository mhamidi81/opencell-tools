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


import subprocess
import sys

import bug_enabler  # conftest already puts scripts/ on sys.path

SKILL = PLUGIN_DIR / "skills" / NAME / "SKILL.md"
SCRIPTS = PLUGIN_DIR / "skills" / NAME / "scripts"


def skill_text():
    return SKILL.read_text()


def test_skill_frontmatter_name_matches_the_plugin():
    head = skill_text().split("---")[1]
    assert f"name: {NAME}" in head
    assert "description:" in head and "argument-hint:" in head


def test_skill_documents_every_flag_it_advertises():
    """The argument-hint and the argument table must not drift apart."""
    text = skill_text()
    hint = re.search(r"argument-hint: \"(.+)\"", text).group(1)
    advertised = set(re.findall(r"--[a-z-]+", hint))
    documented = set(re.findall(r"^\| `(--[a-z-]+)`", text, re.M))
    assert advertised - documented == set(), "advertised but undocumented"
    assert documented - advertised == set(), "documented but not advertised"


def test_skill_pins_both_default_assignee_account_ids():
    text = skill_text()
    assert "5ef5c13914f60e0ac1c9b049" in text     # Mohamed Hamidi, Frontend
    assert "63369fa788ed2ebef97cddfb" in text     # Adil El Jaouhari, Backend
    # The literals above only prove SKILL.md mentions SOME ids matching this
    # comment's claims. Compare the full set against the code so the two can
    # never quietly drift -- a stale id here would still get used by a direct
    # script run, since DEFAULT_ASSIGNEE is what actually ships.
    ids_in_skill = set(re.findall(r"\b[0-9a-f]{24}\b", text))
    assert ids_in_skill == set(bug_enabler.DEFAULT_ASSIGNEE.values())


def test_every_script_the_skill_invokes_exists():
    for name in set(re.findall(r"scripts/([a-z_]+\.py)", skill_text())):
        assert (SCRIPTS / name).is_file(), name


def test_skill_only_passes_flags_the_scripts_accept():
    """Catches the commonest rot: a renamed CLI flag the skill still calls."""
    for name in sorted(set(re.findall(r"scripts/([a-z_]+\.py)", skill_text()))):
        helptext = subprocess.run(
            [sys.executable, str(SCRIPTS / name), "--help"],
            capture_output=True, text=True, check=True).stdout
        # Scan each whole fenced block that invokes the script: the commands are
        # backslash-continued across lines, so a line-bounded regex would miss most
        # of the flags — the exact drift this test exists to catch.
        for block in re.findall(r"```bash\n(.*?)```", skill_text(), re.S):
            if f"scripts/{name}" not in block:
                continue
            for flag in re.findall(r"--[a-z-]+", block):
                assert flag in helptext, f"{name} does not accept {flag}"


def test_skill_forbids_the_atlassian_mcp_for_the_fetch():
    assert "Do not use the Atlassian MCP" in skill_text()
