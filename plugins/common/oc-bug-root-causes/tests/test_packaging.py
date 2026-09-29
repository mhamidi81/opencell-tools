"""The plugin must be discoverable, follow the naming convention, and keep its copied
transport identical to the originals it was copied from.

Copies, not imports: ${CLAUDE_PLUGIN_ROOT} resolves to this plugin's own versioned
install directory, so a path into oc-bug-clusters or oc-pr-rejection-rate does not exist
once installed. The identity test is what stops the copies from drifting silently.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
PLUGIN_DIR = REPO / "plugins" / "common" / "oc-bug-root-causes"
NAME = "oc-bug-root-causes"
SCRIPTS = PLUGIN_DIR / "skills" / NAME / "scripts"


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


@pytest.mark.parametrize("name,origin", [
    ("jira_client.py", "oc-bug-clusters/skills/oc-bug-clusters/scripts"),
    ("bug_fetch.py", "oc-bug-clusters/skills/oc-bug-clusters/scripts"),
    ("bitbucket_client.py", "oc-pr-rejection-rate/skills/oc-pr-rejection-rate/scripts"),
])
def test_copied_transport_is_byte_identical(name, origin):
    original = REPO / "plugins" / "common" / origin / name
    assert (SCRIPTS / name).read_bytes() == original.read_bytes(), (
        f"{name} drifted from {origin}/{name}: change the original, then re-copy it here")
