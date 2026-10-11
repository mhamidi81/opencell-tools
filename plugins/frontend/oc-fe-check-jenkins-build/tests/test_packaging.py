"""The plugin must be discoverable, and the SKILL must keep its fail-closed order.

Fully automatic means nothing human stands between an AI fix and a deployed branch,
so the order local-build → PR → merge → rebuild is pinned here.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
NAME = "oc-fe-check-jenkins-build"
PLUGIN_DIR = REPO / "plugins" / "frontend" / NAME
SKILL = PLUGIN_DIR / "skills" / NAME / "SKILL.md"
SCRIPTS = PLUGIN_DIR / "skills" / NAME / "scripts"


def text():
    return SKILL.read_text()


def test_plugin_json_name_matches_directory():
    meta = json.loads((PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text())
    assert meta["name"] == NAME == PLUGIN_DIR.name
    assert re.fullmatch(r"\d+\.\d+\.\d+", meta["version"])
    assert meta["description"].strip()


def test_marketplace_registers_the_plugin():
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    entries = [p for p in market["plugins"] if p["name"] == NAME]
    assert len(entries) == 1
    assert entries[0]["source"] == f"./plugins/frontend/{NAME}"


def test_skill_frontmatter():
    head = text().split("---")[1]
    assert f"name: {NAME}" in head
    assert "description:" in head and "argument-hint:" in head


def test_every_script_the_skill_invokes_exists():
    names = set(re.findall(r"scripts/([a-z_]+\.py)", text()))
    assert names == {"jenkins_status.py", "jenkins_log.py", "jenkins_rebuild.py"}
    for name in names:
        assert (SCRIPTS / name).is_file(), name


def test_skill_only_passes_flags_the_scripts_accept():
    for name in sorted(set(re.findall(r"scripts/([a-z_]+\.py)", text()))):
        helptext = subprocess.run([sys.executable, str(SCRIPTS / name), "--help"],
                                  capture_output=True, text=True, check=True).stdout
        for block in re.findall(r"```bash\n(.*?)```", text(), re.S):
            if f"scripts/{name}" not in block:
                continue
            for flag in re.findall(r"--[a-z-]+", block):
                assert flag in helptext, f"{name} does not accept {flag}"


def test_fail_closed_order():
    t = text()
    s6, s7, s8 = t.index("## Step 6"), t.index("## Step 7"), t.index("## Step 8")
    assert s6 < s7 < s8
    assert "run build" in t[s6:s7], "the local build must be verified in Step 6"
    assert t.index('"$BB/pullrequests" -d @') > s7, "PR creation belongs to Step 7"
    merge = t.index("pullrequests/[PR_ID]/merge")
    assert s7 < merge < s8, "merge belongs to Step 7, before the rebuild"
    assert t.index("scripts/jenkins_rebuild.py") > s8, "nothing rebuilds before Step 8"


def test_one_fix_attempt_and_no_shortcuts():
    t = text()
    assert "one fix attempt per run" in t.lower()
    for forbidden in ("@ts-ignore", "@ts-expect-error", "eslint-disable"):
        assert forbidden in t


def test_ticket_jira_field_and_auth_conventions():
    t = text()
    assert "INTRD-22890" in t and "fix/INTRD-22890-build-[N]" in t
    assert t.index("getJiraIssue") < t.index("editJiraIssue")
    assert "customfield_10613" in t and "ai_Dev_Front" in t
    assert "ATCTT" in t and "ATATT" in t and "Bearer" in t
    assert "Co-Authored-By" not in t
