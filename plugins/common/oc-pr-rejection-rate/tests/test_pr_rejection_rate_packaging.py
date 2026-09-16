"""The plugin must be discoverable and follow the marketplace naming convention.

Cheap guards against the two mistakes that make a plugin silently absent: a missing
marketplace entry, and a directory name that disagrees with the plugin name.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PLUGIN_DIR = REPO / "plugins" / "common" / "oc-pr-rejection-rate"
NAME = "oc-pr-rejection-rate"


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
    hint = re.search(r'argument-hint: "(.+)"', text).group(1)
    advertised = set(re.findall(r"--[a-z-]+", hint))
    documented = set(re.findall(r"^\| `(--[a-z-]+)`", text, re.M))
    assert advertised - documented == set(), "advertised but undocumented"
    assert documented - advertised == set(), "documented but not advertised"


def test_every_script_the_skill_invokes_exists():
    for name in set(re.findall(r"scripts/([a-z_]+\.py)", skill_text())):
        assert (SCRIPTS / name).is_file(), name


def test_skill_only_passes_flags_the_scripts_accept():
    """Catches the commonest rot: a renamed CLI flag the skill still calls."""
    for name in sorted(set(re.findall(r"scripts/([a-z_]+\.py)", skill_text()))):
        helptext = subprocess.run(
            [sys.executable, str(SCRIPTS / name), "--help"],
            capture_output=True, text=True, check=True).stdout
        for block in re.findall(r"```bash\n(.*?)```", skill_text(), re.S):
            if f"scripts/{name}" not in block:
                continue
            for flag in re.findall(r"--[a-z-]+", block):
                assert flag in helptext, f"{name} does not accept {flag}"


def test_skill_states_the_basic_auth_rule():
    """The Bearer trap costs an hour every time someone rediscovers it."""
    text = skill_text()
    assert "BITBUCKET_EMAIL" in text and "BITBUCKET_ACCESS_TOKEN" in text
    assert "Bearer" in text


def test_skill_is_documented_as_read_only():
    assert "read-only" in skill_text().lower()
