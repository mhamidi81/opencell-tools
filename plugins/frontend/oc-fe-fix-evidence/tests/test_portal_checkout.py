import importlib.util
import json
import os
import pathlib
import subprocess

import pytest

PLUGIN = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN / "skills" / "oc-fe-fix-evidence" / "scripts"

spec = importlib.util.spec_from_file_location("portal_checkout", SCRIPTS / "portal_checkout.py")
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def sh(cwd, *args):
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, env=ENV)


def commit(cwd, name, message):
    (pathlib.Path(cwd) / name).write_text(message)
    sh(cwd, "git", "add", name)
    sh(cwd, "git", "commit", "-q", "-m", message)


@pytest.fixture
def portal(tmp_path):
    """origin `opencell-portal.git` with dev and 15.X, plus per-line checkouts."""
    origin = tmp_path / "remote" / "opencell-portal.git"
    origin.mkdir(parents=True)
    sh(origin, "git", "init", "-q", "--bare", "-b", "dev")
    root = tmp_path / "source"
    root.mkdir()
    main = root / "opencell-portal"
    sh(root, "git", "clone", "-q", str(origin), "opencell-portal")
    sh(main, "git", "checkout", "-q", "-b", "dev")
    (main / "package.json").write_text(json.dumps({"scripts": {"start": "vite"}}))
    sh(main, "git", "add", "package.json")
    sh(main, "git", "commit", "-q", "-m", "init")
    sh(main, "git", "push", "-q", "origin", "dev")
    sh(main, "git", "branch", "15.X")
    sh(main, "git", "push", "-q", "origin", "15.X")
    sh(main, "git", "worktree", "add", "-q", str(root / "opencell-portal-15x"), "15.X")
    sh(main, "git", "fetch", "-q", "origin")
    return root


def merge_on_origin(root, line, message):
    """Another developer merges a fix into `line` on origin."""
    other = root.parent / f"other-{line}"
    sh(root.parent, "git", "clone", "-q", "-b", line,
       str(root.parent / "remote" / "opencell-portal.git"), other.name)
    commit(other, "fix.txt", message)
    sh(other, "git", "push", "-q", "origin", line)


def test_merged_fix_uses_the_line_checkout_and_fast_forwards_it(portal):
    merge_on_origin(portal, "15.X", "INTRD-1: fix")
    got = pc.select(str(portal.parent), str(portal), "INTRD-1")
    assert got["mode"] == "line" and got["branch"] == "15.X"
    assert got["path"].endswith("opencell-portal-15x") and got["fastForwarded"] == 1
    assert (portal / "opencell-portal-15x" / "fix.txt").exists()


def test_unmerged_work_in_the_current_checkout_is_recorded_in_place(portal):
    wt = portal / "wt-fix"
    sh(portal / "opencell-portal", "git", "worktree", "add", "-q", "-b", "fix/INTRD-2", str(wt), "dev")
    commit(wt, "a.txt", "INTRD-2: wip")
    got = pc.select(str(wt), str(portal), "INTRD-2")
    assert got["mode"] == "current" and got["branch"] == "fix/INTRD-2"


def test_uncommitted_work_is_recorded_in_place_and_marked(portal):
    main = portal / "opencell-portal"
    (main / "new.ts").write_text("x")
    assert pc.select(str(main), str(portal), "INTRD-3")["mode"] == "current"
    state = pc.code_state(str(main))
    assert state["uncommitted"] and "+" in state["state"]


def test_a_claude_folder_is_not_an_uncommitted_fix(portal):
    main = portal / "opencell-portal"
    (main / ".claude").mkdir()
    (main / ".claude" / "cache.json").write_text("{}")
    state = pc.code_state(str(main))
    assert not state["uncommitted"] and "+" not in state["state"]


def test_several_lines_need_a_person_unless_a_line_is_named(portal):
    merge_on_origin(portal, "15.X", "INTRD-4: fix")
    merge_on_origin(portal, "dev", "INTRD-4: fix")
    with pytest.raises(pc.Ask, match="several lines"):
        pc.select(str(portal.parent), str(portal), "INTRD-4")
    assert pc.select(str(portal.parent), str(portal), "INTRD-4", "dev")["branch"] == "dev"


def test_a_dirty_line_checkout_is_never_touched(portal):
    merge_on_origin(portal, "15.X", "INTRD-5: fix")
    (portal / "opencell-portal-15x" / "local.txt").write_text("mine")
    with pytest.raises(pc.Ask, match="left untouched"):
        pc.select(str(portal.parent), str(portal), "INTRD-5")
    assert not (portal / "opencell-portal-15x" / "fix.txt").exists()


def test_no_checkout_on_the_line_branch_asks_instead_of_switching(portal):
    merge_on_origin(portal, "15.X", "INTRD-6: fix")
    sh(portal / "opencell-portal-15x", "git", "checkout", "-q", "-b", "bugfix/other")
    with pytest.raises(pc.Ask, match="no checkout"):
        pc.select(str(portal.parent), str(portal), "INTRD-6")
    assert pc.git(str(portal / "opencell-portal-15x"), "branch", "--show-current") == "bugfix/other"


def test_an_unknown_ticket_or_root_asks(portal):
    with pytest.raises(pc.Ask, match="no commit mentioning"):
        pc.select(str(portal.parent), str(portal), "INTRD-404")
    with pytest.raises(pc.Ask, match="OC_PORTAL_ROOT"):
        pc.select(str(portal.parent), None, "INTRD-1")


def write_pkg(tmp_path, start, nvmrc=None):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"start": start}}))
    if nvmrc:
        (tmp_path / ".nvmrc").write_text(nvmrc)
    return str(tmp_path)


VERSIONS = [((14, 21, 3), "/n/14"), ((16, 20, 2), "/n/16"), ((24, 1, 0), "/n/24")]


def test_nvmrc_wins(tmp_path):
    assert pc.pick_node(write_pkg(tmp_path, "react-app-rewired start", "14\n"), VERSIONS)[0] == "/n/14"


def test_webpack_4_lines_get_node_16_at_most(tmp_path):
    assert pc.pick_node(write_pkg(tmp_path, "react-app-rewired start"), VERSIONS)[0] == "/n/16"


def test_vite_lines_keep_the_current_node(tmp_path):
    path = write_pkg(tmp_path, "vite")
    assert pc.pick_node(path, VERSIONS)[0] is None
    assert pc.start_command(path)["kind"] == "vite"


def test_a_missing_node_is_asked_for_not_guessed(tmp_path):
    with pytest.raises(pc.Ask, match="nvm install 14"):
        pc.pick_node(write_pkg(tmp_path, "vite", "14"), [((24, 1, 0), "/n/24")])


def test_line_names():
    for good in ("dev", "15.X", "18.2.X", "15.11.X"):
        assert pc.LINE_RE.match(good)
    for bad in ("main", "bugfix/15.X/INTRD-1", "15.0.5", "hotfix/15.X"):
        assert not pc.LINE_RE.match(bad)
