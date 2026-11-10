import argparse
import importlib.util
import json
import pathlib

PLUGIN = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "skills" / "oc-fe-fix-evidence" / "scripts"
REPO = PLUGIN.parents[2]

spec = importlib.util.spec_from_file_location("jira_evidence", SCRIPTS / "jira_evidence.py")
je = importlib.util.module_from_spec(spec)
spec.loader.exec_module(je)

MANIFEST = {
    "ok": True, "backendVerified": True, "backendRequests": 12,
    "server": "https://dev.example.eu", "finishedAt": "2026-11-10T10:00:00Z",
    "steps": ["Open the customer", "Save"],
    "screenshots": [{"file": "01-after-save.png", "label": "After save"}],
    "video": "recording.webm",
}


class FakeJira:
    def __init__(self, comments=()):
        self._comments, self.attached, self.posted = list(comments), [], []

    def comments(self, ticket):
        return self._comments

    def attach(self, ticket, name, content):
        self.attached.append(name)

    def comment(self, ticket, body):
        self.posted.append(body)


def args():
    return argparse.Namespace(ticket="INTRD-1", state="abc1234+9f8e7d6c",
                              branch="fix/INTRD-1", summary="Total is right", uncommitted=True)


def write_files(tmp_path):
    for name in ("01-after-save.png", "recording.webm"):
        (tmp_path / name).write_bytes(b"x")


def test_comment_embeds_attachments_by_their_uploaded_names():
    body = je.build_comment("INTRD-1", "abc1234", MANIFEST, "fix/INTRD-1", "Total", False)
    assert "!INTRD-1-evidence-abc1234-01-after-save.png|width=900!" in body
    assert "[^INTRD-1-evidence-abc1234-recording.webm]" in body
    assert "https://dev.example.eu" in body and "no mocks" in body
    assert je.marker("abc1234") in body


def test_comment_says_when_the_fix_is_uncommitted():
    body = je.build_comment("INTRD-1", "abc1234+9f8e7d6c", MANIFEST, "b", "s", True)
    assert "{{abc1234}} plus the uncommitted fix" in body


def test_user_text_cannot_break_the_markup():
    assert je.escape("a {code} [x] !y! |z") == "a \\{code\\} \\[x\\] \\!y\\! \\|z"


def test_post_uploads_then_comments(tmp_path):
    write_files(tmp_path)
    jira = FakeJira()
    assert je.post(jira, args(), MANIFEST, str(tmp_path), log=lambda *_: None) == 0
    assert len(jira.attached) == 2 and len(jira.posted) == 1


def test_post_is_skipped_when_the_marker_exists(tmp_path):
    jira = FakeJira([{"body": "x " + je.marker("abc1234+9f8e7d6c")}])
    assert je.post(jira, args(), MANIFEST, str(tmp_path), log=lambda *_: None) == 0
    assert jira.attached == [] and jira.posted == []


def test_a_different_state_is_not_a_duplicate():
    assert not je.has_marker([{"body": je.marker("other")}], "abc1234")


def test_failed_or_mocked_runs_are_refused(tmp_path):
    for bad in ({"ok": False, "error": "boom"}, {"backendVerified": False, "backendRequests": 0}):
        jira = FakeJira()
        assert je.post(jira, args(), {**MANIFEST, **bad}, str(tmp_path), log=lambda *_: None) == 3
        assert jira.attached == [] and jira.posted == []


def test_an_unrestored_user_setting_blocks_the_post(tmp_path):
    jira = FakeJira()
    bad = {**MANIFEST, "restored": False, "restoreError": "flag not found"}
    assert je.post(jira, args(), bad, str(tmp_path), log=lambda *_: None) == 3
    assert jira.attached == [] and jira.posted == []
    assert je.check_manifest({**MANIFEST, "restored": True}) is None


def test_multipart_carries_name_and_type():
    data, boundary = je.encode_multipart("a.webm", b"VID", boundary="B")
    assert data.startswith(b"--B\r\n") and data.endswith(b"\r\n--B--\r\n")
    assert b'filename="a.webm"' in data and b"video/webm" in data and b"VID" in data


def test_credentials_are_both_required():
    for env in ({}, {"JIRA_API_TOKEN": "t"}, {"JIRA_EMAIL": "e"}):
        try:
            je.auth_header(env)
        except je.EvidenceError:
            continue
        raise AssertionError(env)


def test_packaging():
    plugin = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == "oc-fe-fix-evidence"
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    assert any(p["name"] == "oc-fe-fix-evidence"
               and p["source"] == "./plugins/frontend/oc-fe-fix-evidence"
               for p in market["plugins"])
    skill = (PLUGIN / "skills" / "oc-fe-fix-evidence" / "SKILL.md").read_text()
    # The recording must never reuse the mocked regression harness.
    assert "app-boot.ts" in skill and "must not" in skill.lower()
    # The checkout is chosen before anything is recorded or posted.
    assert skill.index("portal_checkout.py select") < skill.index("jira_evidence.py check") \
        < skill.index("evidence_run.mjs run") < skill.index("jira_evidence.py post")
    runner = (SCRIPTS / "evidence_run.mjs").read_text()
    assert "restoreSettings" in runner and "markVisible" in runner
    fix_bug = (REPO / "plugins/frontend/oc-fe-fix-bug/skills/oc-fe-fix-bug/SKILL.md").read_text()
    assert fix_bug.index("Step 6b") < fix_bug.index("/oc-fe-fix-evidence") < fix_bug.index("### Step 7")
