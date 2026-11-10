#!/usr/bin/env python3
"""oc-be-tools hooks: make sure /oc-be-calculate-ai-use is not forgotten.

Ad-hoc work (a bug or an enabler analysed in conversation, no /oc-be-implement) must end up with the
same three outcomes as an /oc-be-implement run: all analysis and code accounted for, the guidelines
applied, and the deliverables met. The hooks below get there; all of them skip sub-agents, which
load their own guidelines.

Before the code (PreToolUse on Edit/Write/MultiEdit, --pre-edit):
- the first code edit for a ticket in a session is held once until Claude writes an *analysis
  checkpoint* (.claude/cache/ai-stats/<TICKET>-<ts>/_planning.json: the agreed approach, acceptance
  points and deliverables) and shows the developer the "Agreed scope" — the planning record for the
  AI-usage metrics and the checklist /oc-be-review checks the code against;
- the first edit of each layer in opencell-core is held once until its guideline file was read
  (entity, DB, service, API, unit-test, Postman).

While coding (PreToolUse/PostToolUse on Bash/PowerShell, --pre-script / --post-script): a command
that can write files (python, node, sed -i, Set-Content, redirection, ...) is bracketed by a snapshot
of the dirty files, and the lines it added are appended to a per-session sidecar
(~/.claude/oc-be-tools/script-edits/<repo-slug>/<session>.jsonl), so script edits — e.g. a Postman
collection rewritten by a Python script — count as AI lines instead of hand-written ones. A file the
command changed whose guideline was not read gets a follow-up reminder.

At the milestone, the intended order is *review, record AI usage, commit*:
- SessionStart (--session-start): a standing rule — whenever Claude suggests committing, it suggests
  /oc-be-review and recording first.
- Stop, milestone: tests passed (mvn test/verify/install, newman run) after Claude's latest code edit
  in this session, and the changes are uncommitted and not yet recorded -> remind once per change set.
- PreToolUse (--pre-commit): Claude is about to run `git commit` on changes this session edited that
  are not recorded -> the commit is held back once so the developer can choose to review/record first.
- Stop, commits: a commit already made (by Claude, the IDE or a terminal) is offered afterwards.

Developers commit from Claude, from the IDE or from a terminal, and open PRs outside Claude, so
the trigger is anchored to the *commit*, not to a command: HEAD's reflog records every commit
made in this clone (``commit:`` / ``commit (amend):``) whatever tool made it, and tells them apart
from cherry-picks (backports), merges and pulls, which are not new work.

For commits, at the end of every Claude turn in a backend repository (opencell-core or an overlay) the Stop hook:

1. reads the commits made locally in the last WINDOW_DAYS days and groups them by ticket
   (commit-message prefix ``INTRD-123:``, else the ticket in the branch the commit was made on);
2. drops the tickets the ledger already settles (recorded for that tip, declined, or already
   offered in this session);
3. keeps only the tickets whose files were edited (Edit/Write/MultiEdit) by a Claude session,
   main or sub-agent transcript — work done without Claude is not nagged about;
4. blocks the stop once with an instruction to offer the measurement to the developer.

A ticket recorded before its commit is not offered again once committed: the --working mark stores
the measured diff's `git patch-id`, and a commit with the same patch-id is taken as already recorded.
A commit that differs (changed after measuring) is offered again; that run replaces the working-tree
measurement, using the record as it was before it (also kept in the ledger).

The same script is the ledger writer and reader for /oc-be-calculate-ai-use:

    python ai_use_watch.py --mark <repo> <TICKET> <ref> recorded|declined|snoozed [--working [--prior <record.json>]]
    python ai_use_watch.py --show <repo> <TICKET>

The ledger lives outside the repository (~/.claude/oc-be-tools/ai-use-ledger/<repo-slug>.json),
so it can never be committed and survives branch switches. Any failure exits 0 silently: a broken
reminder must never get in the way of the session.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

WINDOW_DAYS = 7          # commits older than this are not offered automatically
TRANSCRIPT_SLACK_DAYS = 21  # transcripts last written this long before the ticket's first commit are skipped
REFLOG_DEPTH = 400
BACKEND_REPOS = ("opencell-core", "opencell-vertical-", "opencell-ext-", "opencell-elec-")
TICKET_AT_START = re.compile(r"^\s*([A-Z][A-Z0-9]+-\d+)")
TICKET_ANYWHERE = re.compile(r"([A-Z][A-Z0-9]+-\d+)")
EDIT_CALL = re.compile(rb'"name":"(?:Edit|Write|MultiEdit)","input":\{[^{}]*?"file_path":"((?:[^"\\]|\\.)*)"')
COMMAND = "oc-be-tools:oc-be-calculate-ai-use"
GIT_COMMIT = re.compile(r"\bgit\b(?:\s+-[cC]\s+\S+)*\s+commit\b")
SESSION_KEEP_DAYS = 30
WRITE_CAPABLE = re.compile(r"\b(python3?|py|node|perl|ruby)\b|\bsed\s+(-\S*\s+)*-i|\bawk\b.*-i\s+inplace|"
                           r"(?<![0-9&-])>{1,2}\s*[^&\s>]|\btee\b|\b(Set|Add|Out)-(Content|File)\b|\bOut-File\b|"
                           r"\b(Copy|Move)-Item\b|(^|[;&|]\s*)(cp|mv)\s", re.I)
SNAPSHOT_MAX_BYTES = 5 * 1024 * 1024
GUIDELINES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guidelines")
# (applies to repo-relative path, guideline files to read, skill that reads them) — opencell-core layout
GUIDE_RULES = [
    (lambda r: r.startswith("opencell-model/") and "/src/main/" in r and r.endswith(".java"),
     ["ENTITY_GUIDELINES.md", "CRITICAL_RULES.md", "CODE_QUALITY.md"], "oc-be-tools:oc-be-entity-guide"),
    (lambda r: "/db_resources/changelog/" in r and r.endswith(".xml"),
     ["DATABASE_GUIDELINES.md"], "oc-be-tools:oc-be-db-guide"),
    (lambda r: r.startswith("opencell-admin/ejbs/") and "/src/main/" in r and r.endswith(".java"),
     ["SERVICE_GUIDELINES.md", "CRITICAL_RULES.md", "CODE_QUALITY.md"], "oc-be-tools:oc-be-service-guide"),
    (lambda r: r.startswith(("opencell-api/", "opencell-api-dto/")) and "/src/main/" in r and r.endswith(".java"),
     ["API_GUIDELINES.md", "CRITICAL_RULES.md", "CODE_QUALITY.md"], "oc-be-tools:oc-be-api-guide"),
    (lambda r: "/src/test/" in r and r.endswith(".java"), ["UNIT_TESTING.md"], None),
    (lambda r: r.endswith(".postman_collection.json"), ["POSTMAN_TESTING.md"], None),
]
LAYERS = ["entity", "db", "service", "api", "unittest", "postman"]   # GUIDE_RULES order; edit_gate.sh uses the same


def layer_key(rel):
    """The edit-gate layer of a repo-relative path — must match the case table in edit_gate.sh."""
    r = rel.lower()
    for (applies, _, _), name in zip(GUIDE_RULES, LAYERS):
        if applies(r):
            return name
    return "other"


def gate_dir(session):
    return os.path.join(os.path.expanduser("~"), ".claude", "oc-be-tools", "gate", session)


def mark_gate(session, *parts):
    """Leave the marker edit_gate.sh answers from: <session>/skip, or <session>/<ticket|none>/<layer>."""
    if not session:
        return
    path = os.path.join(gate_dir(session), *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").close()


def is_test_command(command):
    """A test run: Maven with a test phase (not skipping tests) or a Newman collection run."""
    c = command.lower()
    if re.search(r"\bnewman\s+run\b", c):
        return True
    return bool(re.search(r"\bmvnw?(\.cmd)?\b", c) and re.search(r"\b(test|verify|install)\b|-dtest=", c)
                and "-dskiptests" not in c and "maven.test.skip" not in c)


def git(repo, *args):
    """Run git in repo; return stdout ('' on any failure)."""
    try:
        res = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=15)
        return res.stdout if res.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def repo_slug(top):
    """Claude Code's project slug: every non-alphanumeric character becomes '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", top)


def ledger_path(top):
    return os.path.join(os.path.expanduser("~"), ".claude", "oc-be-tools", "ai-use-ledger",
                        repo_slug(top) + ".json")


def load_ledger(top):
    try:
        with open(ledger_path(top), encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_ledger(top, data):
    path = ledger_path(top)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)


def repo_top(start):
    """The work tree root containing `start`, found on disk (spawning git costs ~0.1 s per call on Windows,
    and these hooks run on every edit and shell command); git itself for anything unusual."""
    path = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(path, ".git")):
            return path.replace("\\", "/")
        if os.path.exists(os.path.join(path, ".git")):          # worktree/submodule: .git is a file
            return git(start, "rev-parse", "--show-toplevel").strip()
        parent = os.path.dirname(path)
        if parent == path:
            return ""
        path = parent


def origin_url(top):
    try:
        with open(os.path.join(top, ".git", "config"), encoding="utf-8", errors="replace") as fh:
            m = re.search(r'\[remote "origin"\][^\[]*?\burl\s*=\s*(\S+)', fh.read())
            return m.group(1).lower() if m else ""
    except OSError:
        return git(top, "remote", "get-url", "origin").strip().lower()


def is_backend_repo(top):
    name = origin_url(top) or os.path.basename(top).lower()
    return any(marker in name for marker in BACKEND_REPOS)


def local_commits(top):
    """Commits made in this clone within the window, newest first: (sha, unix_time, subject, branch).

    The reflog is walked newest -> oldest; a 'checkout: moving from A to B' entry means everything
    older than it happened on A, which is how a commit without a ticket prefix gets its branch."""
    out = git(top, "reflog", "--date=unix", "-n", str(REFLOG_DEPTH), "--format=%H%x09%gd%x09%gs")
    branch = git(top, "branch", "--show-current").strip()
    cutoff = time.time() - WINDOW_DAYS * 86400
    commits = []
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        sha, selector, subject = parts
        m = re.search(r"\{(\d+)\}", selector)
        when = int(m.group(1)) if m else 0
        if subject.startswith("checkout: moving from "):
            branch = subject[len("checkout: moving from "):].split(" to ")[0]
            continue
        if when < cutoff:
            break
        if subject.startswith(("commit: ", "commit (amend): ", "commit (initial): ")):
            commits.append((sha, when, subject.split(": ", 1)[1], branch))
    return commits


def group_by_ticket(commits):
    """{ticket: {'sha': newest sha, 'subject': ..., 'shas': [...], 'first': oldest time}}."""
    tickets = {}
    for sha, when, subject, branch in commits:   # newest first
        m = TICKET_AT_START.match(subject) or TICKET_ANYWHERE.search(branch or "")
        if not m:
            continue
        t = tickets.setdefault(m.group(1), {"sha": sha, "subject": subject, "shas": [], "first": when})
        t["shas"].append(sha)
        t["first"] = min(t["first"], when)
    return tickets


def settled(entry, sha, session):
    """True when the ledger says this ticket needs no reminder now."""
    if not entry:
        return False
    status = entry.get("status")
    if status == "declined":
        return True                                   # 'never for this ticket'
    if status == "recorded":
        return entry.get("sha") == sha                # a newer commit re-opens the ticket
    if status in ("snoozed", "offered"):
        return entry.get("sha") == sha and entry.get("session") == session  # ask again next session
    return False


def ticket_files(top, shas):
    files = set()
    for sha in shas:
        for p in git(top, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha).splitlines():
            if p.strip():
                files.add(p.strip().replace("\\", "/").lower())
    return files


def patch_id(top, *diff_args):
    """`git patch-id --stable` of `git diff <diff_args>` ('' when there is no diff)."""
    try:
        diff = subprocess.run(["git", "-C", top, "diff", *diff_args], capture_output=True, timeout=30).stdout
        if not diff.strip():
            return ""
        out = subprocess.run(["git", "-C", top, "patch-id", "--stable"], input=diff,
                             capture_output=True, timeout=30).stdout.split()
        return out[0].decode() if out else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def committed_as_measured(top, working, sha):
    """True if the commits from the working-tree measurement's base to `sha` are exactly what was measured."""
    base = working.get("base", "")
    try:
        is_ancestor = subprocess.run(["git", "-C", top, "merge-base", "--is-ancestor", base, sha],
                                     capture_output=True, timeout=15).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
    return is_ancestor and bool(working.get("patch_id")) and patch_id(top, base, sha) == working["patch_id"]


def claude_edited(top, files, transcripts_dir, current_transcript, since):
    """True if a main or sub-agent transcript has an Edit/Write/MultiEdit on one of `files`."""
    if not files or not transcripts_dir or not os.path.isdir(transcripts_dir):
        return False
    candidates = glob.glob(os.path.join(transcripts_dir, "*.jsonl")) + \
        glob.glob(os.path.join(transcripts_dir, "*", "subagents", "*.jsonl"))
    recent = []
    for path in candidates:
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime >= since:
            recent.append((path != current_transcript, -mtime, path))   # current session first
    prefix = top.replace("\\", "/").lower().rstrip("/") + "/"
    for _, _, path in sorted(recent):
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            continue
        for m in EDIT_CALL.finditer(data):
            try:
                edited = json.loads(b'"' + m.group(1) + b'"').replace("\\", "/").lower()
            except ValueError:
                continue
            if edited.startswith(prefix) and edited[len(prefix):] in files:
                return True
    return False


def reminder(top, pending):
    script = os.path.abspath(__file__).replace("\\", "/")
    python = (sys.executable or "python").replace("\\", "/")
    lines = ["[oc-be-tools] AI usage is not recorded yet for work committed in this repository:"]
    for key, t in pending:
        lines.append(f"- {key}: {len(t['shas'])} local commit(s) in the last {WINDOW_DAYS} days, "
                     f"latest {t['sha'][:10]} \"{t['subject'][:80]}\"")
    key, t = pending[0]
    lines += [
        "",
        f"Before you finish, ask the developer with AskUserQuestion whether to record {key} now. Options:",
        "- \"Record now (Recommended)\" -> invoke the Skill "
        f"`{COMMAND}` with args `--ticket {key} --commit {t['sha'][:10]}`.",
        f"- \"Later\" (ask again next session) -> run: \"{python}\" \"{script}\" --mark \"{top}\" {key} {t['sha']} snoozed",
        f"- \"Never for this ticket\" -> run: \"{python}\" \"{script}\" --mark \"{top}\" {key} {t['sha']} declined",
        "Handle one ticket per reminder; the others are offered at the end of the next turn. "
        "Keep it short and do not repeat the previous answer.",
    ]
    return "\n".join(lines)


def scan_session(top, transcript, state):
    """Advance through this session's transcript from the saved offset, recording (by event order) the
    latest Edit/Write/MultiEdit of a repo file and the latest successful test run."""
    if not transcript or not os.path.isfile(transcript):
        return
    offset = state.get("offset", 0)
    if offset > os.path.getsize(transcript):
        offset = 0
    seq, pending = state.get("seq", 0), set(state.get("pending_tests", []))
    prefix = top.replace("\\", "/").lower().rstrip("/") + "/"
    with open(transcript, "rb") as fh:
        fh.seek(offset)
        for raw in fh:
            if not raw.endswith(b"\n"):
                break                                # line still being written: read it next time
            offset += len(raw)
            if b'"tool_use"' not in raw and b'"tool_result"' not in raw:
                continue
            try:
                content = (json.loads(raw).get("message") or {}).get("content")
            except ValueError:
                continue
            for b in content if isinstance(content, list) else []:
                if not isinstance(b, dict):
                    continue
                inp = b.get("input") or {}
                if b.get("type") == "tool_use" and b.get("name") == "Read":
                    m = re.search(r"guidelines[\\/]+([A-Z_]+\.md)$", str(inp.get("file_path", "")))
                    if m:
                        state["guides"] = sorted(set(state.get("guides", [])) | {m.group(1)})
                elif b.get("type") == "tool_use" and b.get("name") in ("Edit", "Write", "MultiEdit"):
                    if str(inp.get("file_path", "")).replace("\\", "/").lower().startswith(prefix):
                        seq += 1
                        state["last_edit"] = seq
                elif b.get("type") == "tool_use" and b.get("name") in ("Bash", "PowerShell") \
                        and is_test_command(str(inp.get("command", ""))):
                    pending.add(b.get("id"))
                    state["last_test_command"] = str(inp.get("command", ""))[:120]
                elif b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                    pending.discard(b.get("tool_use_id"))
                    if not b.get("is_error"):
                        seq += 1
                        state["last_green"] = seq
    state.update({"offset": offset, "seq": seq, "pending_tests": sorted(p for p in pending if p),
                  "seen": time.time()})


def session_state(ledger, session):
    sessions = ledger.setdefault("sessions", {})
    cutoff = time.time() - SESSION_KEEP_DAYS * 86400
    for sid in [k for k, v in sessions.items() if v.get("seen", 0) < cutoff and k != session]:
        del sessions[sid]
        shutil.rmtree(gate_dir(sid), ignore_errors=True)
    return sessions.setdefault(session, {"created": time.time()})


def branch_ticket(top):
    m = TICKET_ANYWHERE.search(git(top, "branch", "--show-current"))
    return m.group(1) if m else None


def milestone_reminder(top, ledger, state):
    """Tests passed after Claude's latest code edit, and the changes are uncommitted and unrecorded."""
    if not (state.get("last_green", 0) > state.get("last_edit", 0) > 0):
        return None
    pid = patch_id(top, "HEAD")
    if not pid or state.get("milestone_patch") == pid:
        return None
    key = branch_ticket(top)
    entry = ledger.get("tickets", {}).get(key or "", {})
    if entry.get("status") == "declined" or (entry.get("working") or {}).get("patch_id") == pid:
        return None
    state["milestone_patch"] = pid
    ticket = f"<TICKET> (the ticket this work is for; the branch suggests {key})" if key else "<TICKET>"
    return "\n".join([
        f"[oc-be-tools] Milestone: tests passed after your latest code changes (`{state.get('last_test_command', '')}`), "
        "and the changes are not committed or recorded yet.",
        "Suggest the next steps to the developer, in this order, without running them unasked:",
        "  1. Review: /oc-be-tools:oc-be-review (guidelines + the ticket's acceptance criteria and the agreed scope)",
        f"  2. Record AI usage: /{COMMAND} --working --ticket {ticket}",
        "  3. Commit",
        "If your last message already suggested recording AI usage, do not repeat it: just end your turn.",
    ])


def run_hook():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    if payload.get("stop_hook_active"):
        return
    top = repo_top(payload.get("cwd"))
    if not top or not is_backend_repo(top):
        return
    session = payload.get("session_id", "")
    transcript = payload.get("transcript_path") or ""
    ledger = load_ledger(top)
    state = session_state(ledger, session)
    scan_session(top, transcript, state)
    reason = commit_offers(top, ledger, session, transcript) or milestone_reminder(top, ledger, state)
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))
    save_ledger(top, ledger)


def commit_offers(top, ledger, session, transcript):
    """The reminder text for the first committed-but-unrecorded ticket, or None."""
    head = git(top, "reflog", "-n", "1", "--format=%H%x09%gs").strip()
    signature = f"{head}|{session}"
    if ledger.get("signature") == signature:
        return None                                  # nothing committed since the last check in this session
    tickets = ledger.setdefault("tickets", {})
    transcripts_dir = os.path.dirname(transcript)

    pending = []
    for key, t in group_by_ticket(local_commits(top)).items():
        entry = tickets.get(key)
        working = (entry or {}).get("working")
        if working and entry.get("status") == "recorded" and working.get("checked") != t["sha"]:
            working["checked"] = t["sha"]
            if committed_as_measured(top, working, t["sha"]):
                entry["sha"] = t["sha"]                  # recorded before the commit, committed as measured
                entry.pop("working")
        if settled(entry, t["sha"], session):
            continue
        if entry and entry.get("checked_sha") == t["sha"]:
            edited = entry.get("claude_edited", False)
        else:
            edited = claude_edited(top, ticket_files(top, t["shas"]), transcripts_dir, transcript,
                                   t["first"] - TRANSCRIPT_SLACK_DAYS * 86400)
            entry = tickets.setdefault(key, {})
            entry.update({"checked_sha": t["sha"], "claude_edited": edited})
        if edited:
            pending.append((key, t))

    if pending:
        key, t = pending[0]
        tickets[key].update({"status": "offered", "sha": t["sha"], "session": session,
                             "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        return reminder(top, pending)
    ledger["signature"] = signature                  # only skip re-checks once nothing is left to offer
    return None


def review_module():
    """scripts/isolated_review.py: the review ledger (which code states were reviewed, with which verdict)."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import isolated_review
    return isolated_review


def review_hold(top, command):
    """Reason to hold Claude's commit until the change set is reviewed, or None. Enforced, not once: only a
    review of exactly this change set, or the developer's explicit 'skip' / 'acknowledge', lets it through."""
    review = review_module()
    head, pid = review.code_state(top)
    if not pid:
        return None                                  # nothing uncommitted (e.g. --amend of a message only)
    entry = review.find_review(top, head, pid)
    script = os.path.join(os.path.dirname(review.__file__), "isolated_review.py").replace("\\", "/")
    python = (sys.executable or "python").replace("\\", "/")
    if entry and (entry.get("skipped") or entry.get("acknowledged") or entry.get("verdict") == "APPROVE"):
        return None
    if entry:                                        # reviewed, CHANGES_REQUESTED, not acknowledged
        return "\n".join([
            f"[oc-be-tools] The isolated review of exactly these changes requested changes (score {entry.get('score')}/10; "
            f"report: {entry.get('report', '')}). Ask the developer with AskUserQuestion:",
            "- \"Fix the findings first (Recommended)\" -> do not commit; go through the report's failed rules and "
            "missing items with the developer, then re-run /oc-be-tools:oc-be-review.",
            f"- \"Commit with known issues\" -> run: \"{python}\" \"{script}\" mark --repo \"{top}\" acknowledged, "
            "then run the same commit again.",
        ])
    return "\n".join([
        "[oc-be-tools] Review before commit: these exact changes have not been reviewed (any edit after a review "
        "needs a new one). Ask the developer with AskUserQuestion:",
        "- \"Review first (Recommended)\" -> invoke the Skill `oc-be-tools:oc-be-review` (isolated, a few minutes), "
        "then run the same commit again.",
        f"- \"Commit without review\" -> run: \"{python}\" \"{script}\" mark --repo \"{top}\" skipped, then run the "
        "same commit again (the skip is recorded).",
    ])


def run_pre_commit():
    """PreToolUse on Bash/PowerShell, on Claude's `git commit` in a backend repository:
    1. review hold (enforced) — the uncommitted change set must have an isolated review, or the developer's
       explicit skip/acknowledgement;
    2. AI-usage hold (once per change set) — changes this session edited should be recorded first.
    Record first is the intended order at the milestone: review -> record AI usage -> commit."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    command = str((payload.get("tool_input") or {}).get("command", ""))
    if not GIT_COMMIT.search(command):
        return
    top = repo_top(payload.get("cwd"))
    if not top or not is_backend_repo(top):
        return
    hold = review_hold(top, command)
    if hold:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": hold}}))
        return
    ledger = load_ledger(top)
    state = session_state(ledger, payload.get("session_id", ""))
    scan_session(top, payload.get("transcript_path") or "", state)
    m = re.search(r"([A-Z][A-Z0-9]+-\d+):", command)
    key = m.group(1) if m else branch_ticket(top)
    pids = {p for p in (patch_id(top, "HEAD"), patch_id(top, "--cached")) if p}
    entry = ledger.get("tickets", {}).get(key or "", {})
    held = set(state.get("held_patches", []))
    if (not key or not pids or not state.get("last_edit") or entry.get("status") == "declined"
            or (entry.get("working") or {}).get("patch_id") in pids or pids & held):
        save_ledger(top, ledger)
        return
    state["held_patches"] = sorted(held | pids)
    save_ledger(top, ledger)
    script = os.path.abspath(__file__).replace("\\", "/")
    python = (sys.executable or "python").replace("\\", "/")
    reason = "\n".join([
        f"[oc-be-tools] Record AI usage before this commit (record first, then commit): the changes of {key} "
        "that this session edited are not recorded yet. Ask the developer with AskUserQuestion:",
        f"- \"Record first (Recommended)\" -> invoke the Skill `{COMMAND}` with args `--working --ticket {key}`, "
        "then run the same commit again.",
        "- \"Commit without recording\" -> run the same commit again now (it will go through; the Stop hook "
        "offers the recording after the commit).",
        f"- \"Never for this ticket\" -> run: \"{python}\" \"{script}\" --mark \"{top}\" {key} HEAD declined, "
        "then run the same commit again.",
        "This hold happens once per change set.",
    ])
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


MILESTONE_RULE = (
    "[oc-be-tools] AI-usage recording: whenever you suggest committing work on a ticket (coding finished, "
    "tests green, review fixes applied, or the developer asks what is next), suggest three steps in this order: "
    "1. review: `/oc-be-tools:oc-be-review` (guidelines + the ticket's acceptance criteria and the agreed scope); "
    "2. record the AI usage on the uncommitted changes: `/" + COMMAND + " --working --ticket <TICKET>`; "
    "3. then commit. This applies whether the developer commits here or in the IDE, and whether or not "
    "/oc-be-implement was used. Suggest it once per milestone, together with the commit suggestion; do not "
    "run it unasked.")


def run_session_start():
    """SessionStart: in a backend repository, add the milestone rule to the session context."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    top = repo_top(payload.get("cwd"))
    if top and is_backend_repo(top):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": MILESTONE_RULE}}))


def is_core_repo(top):
    return "opencell-core" in (origin_url(top) or top.lower())


def required_guides(rel):
    for applies, files, skill in GUIDE_RULES:
        if applies(rel):
            return files, skill
    return [], None


def guide_instruction(missing):
    """`missing` = [(files, skill)] -> one line per layer."""
    out = []
    for files, skill in missing:
        paths = ", ".join(os.path.join(GUIDELINES, f).replace("\\", "/") for f in files)
        out.append(f"  - {skill} (Skill tool), which reads {', '.join(files)}" if skill
                   else f"  - read {paths}")
    return out


def checkpoint_exists(top, key, state):
    pattern = os.path.join(top, ".claude", "cache", "ai-stats", f"{key or '*'}-*", "_planning.json")
    since = state.get("created", 0)
    return any(os.path.getmtime(p) >= since for p in glob.glob(pattern))


def checkpoint_instruction(top, key):
    ticket = key or "<TICKET>"
    run_dir = f"{top}/.claude/cache/ai-stats/{ticket}-<yyyymmdd-HHMMSS UTC>".replace("\\", "/")
    return [
        f"Analysis checkpoint: this is the first code change for {ticket} in this session"
        + ("" if key else " (no ticket in the branch name: determine it from the conversation or ask)") + ". Before editing:",
        f"  1. Write {run_dir}/_planning.json:",
        '     {"type": "planning", "agent": "ad-hoc", "ticket": "...", "run_id": "<dir name>",',
        '      "planning_started": "<ISO UTC of the developer\'s first message about this ticket in this session>",',
        '      "plan_approved": "<ISO UTC now>", "revision_rounds": <times the approach was proposed or refined with the developer>,',
        '      "plan_word_count": <words of plan_text>, "plan_text": "<the agreed approach: cause/goal and the change>",',
        '      "acceptance": ["<what must be true when done>", ...],',
        '      "deliverables": {"unit_tests": "<required: which | not applicable: why>", "postman": "<required: which | not applicable: why>"},',
        '      "notes": "<key decisions>"}',
        "  2. Show the developer a short \"Agreed scope\" block (approach, acceptance points, deliverables). If any of it was "
        "not actually agreed in the conversation, ask before editing.",
        "  3. Then redo the edit.",
    ]


def run_pre_edit():
    """PreToolUse on Edit/Write/MultiEdit (main session only): hold the first code edit for a ticket
    until the analysis checkpoint exists, and the first edit of each layer until its guideline was read.
    Each hold happens once, so a retry always goes through."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    if payload.get("agent_id"):
        return                                       # sub-agents load their own guidelines
    path = str((payload.get("tool_input") or {}).get("file_path", ""))
    session = payload.get("session_id", "")
    top = repo_top(payload.get("cwd"))
    if not path or not top:
        return
    if not is_backend_repo(top):
        mark_gate(session, "skip")                   # the fast path stops starting Python here
        return
    norm_top = top.replace("\\", "/").rstrip("/") + "/"
    norm_path = path.replace("\\", "/")
    if not norm_path.lower().startswith(norm_top.lower()):
        return
    rel = norm_path[len(norm_top):]
    if rel.startswith((".claude/", "docs/")) or rel.endswith(".md"):
        return
    ledger = load_ledger(top)
    state = session_state(ledger, session)
    scan_session(top, payload.get("transcript_path") or "", state)
    key = branch_ticket(top)
    reason = []
    held = set(state.get("checkpoints_held", []))   # per ticket: switching branch mid-session asks again
    if (key or "none") not in held and not checkpoint_exists(top, key, state):
        state["checkpoints_held"] = sorted(held | {key or "none"})
        reason += checkpoint_instruction(top, key)
    if is_core_repo(top):
        files, skill = required_guides(rel)
        missing = [f for f in files if f not in state.get("guides", []) and f not in state.get("guides_held", [])]
        if missing:
            state["guides_held"] = sorted(set(state.get("guides_held", [])) | set(missing))
            reason += [f"Guidelines: {rel} is covered by guidelines not read in this session. Load them first:"]
            reason += guide_instruction([(missing, skill)])
            reason += ["Then redo the edit, following them."]
    save_ledger(top, ledger)
    mark_gate(session, key or "none", layer_key(rel))   # decided: every later edit of this layer is allowed
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": "[oc-be-tools] " + "\n".join(reason) + "\nThis hold happens once."}}))


def script_dir(top):
    return os.path.join(os.path.expanduser("~"), ".claude", "oc-be-tools", "script-edits", repo_slug(top))


def dirty_files(top):
    """Repo-relative paths of modified/added/untracked files (renames: the new path)."""
    out = subprocess.run(["git", "-C", top, "status", "--porcelain", "-z", "--untracked-files=all"],
                         capture_output=True, timeout=30).stdout.decode("utf-8", "replace").split("\0")
    files, i = [], 0
    while i < len(out):
        entry = out[i]
        i += 1
        if len(entry) < 4:
            continue
        if entry[0] in "RC":
            i += 1                                   # the rename source follows as its own field
        rel = entry[3:]
        if not rel.startswith(".claude/"):
            files.append(rel)
    return files


def file_lines(data):
    return {l.strip() for l in data.decode("utf-8", "replace").splitlines()
            if l.strip() and any(c.isalnum() for c in l)}


def baseline_dir(top):
    return os.path.join(script_dir(top), ".baseline")


def load_baseline(top):
    try:
        with open(os.path.join(baseline_dir(top), "index.json"), encoding="utf-8") as fh:
            base = json.load(fh)
    except (OSError, ValueError):
        base = {}
    base.setdefault("files", {})
    base.setdefault("armed", [])
    return base


def save_baseline(top, base):
    with open(os.path.join(baseline_dir(top), "index.json"), "w", encoding="utf-8") as fh:
        json.dump(base, fh)


def stat_key(full):
    st = os.stat(full)
    return [st.st_size, st.st_mtime_ns]


def refresh_baseline(top, base, rels):
    """Keep a copy of every dirty file as it is now. Only files whose size/mtime moved since their copy
    are copied again (normally none), and files no longer dirty (committed, reverted) are dropped. A change
    the developer makes in the IDE between two commands thereby becomes baseline, never an AI line."""
    os.makedirs(baseline_dir(top), exist_ok=True)
    files, dirty = base["files"], set(rels)
    for rel in [r for r in files if r not in dirty]:
        try:
            os.remove(os.path.join(baseline_dir(top), files[rel]["copy"]))
        except OSError:
            pass
        del files[rel]
    for rel in rels:
        full = os.path.join(top, rel)
        if not os.path.isfile(full) or os.path.getsize(full) > SNAPSHOT_MAX_BYTES:
            continue
        key = stat_key(full)
        entry = files.get(rel)
        if entry and entry["stat"] == key:
            continue
        copy = entry["copy"] if entry else hashlib.md5(rel.encode("utf-8")).hexdigest()
        shutil.copyfile(full, os.path.join(baseline_dir(top), copy))
        files[rel] = {"stat": key, "copy": copy}


def run_pre_script():
    """PreToolUse on Bash/PowerShell: before a command that can write files, bring the baseline of the
    dirty files up to date so --post-script can tell which lines the command added."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    command = str((payload.get("tool_input") or {}).get("command", ""))
    if not WRITE_CAPABLE.search(command) or re.match(r"\s*git\b", command):
        return
    top = repo_top(payload.get("cwd"))
    if not top or not is_backend_repo(top):
        return
    base = load_baseline(top)
    refresh_baseline(top, base, dirty_files(top))
    base["armed"] = (base["armed"] + [str(payload.get("tool_use_id") or "")])[-20:]
    save_baseline(top, base)


def run_post_script():
    """PostToolUse on Bash/PowerShell: record the lines the command added (vs. the baseline copy, or HEAD
    for a file that was clean) and remind about guidelines not read for the files it changed."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    top = repo_top(payload.get("cwd"))
    if not top or not is_backend_repo(top):
        return
    base = load_baseline(top)
    tool_use_id = str(payload.get("tool_use_id") or "")
    if tool_use_id not in base["armed"]:
        return                                       # no snapshot was taken before this command
    base["armed"].remove(tool_use_id)
    rels = dirty_files(top)
    changed = []
    for rel in rels:
        full = os.path.join(top, rel)
        if not os.path.isfile(full) or os.path.getsize(full) > SNAPSHOT_MAX_BYTES:
            continue
        entry = base["files"].get(rel)
        if entry and entry["stat"] == stat_key(full):
            continue                                 # untouched by the command
        if entry:
            with open(os.path.join(baseline_dir(top), entry["copy"]), "rb") as fh:
                before = fh.read()
        else:
            before = subprocess.run(["git", "-C", top, "show", f"HEAD:{rel}"], capture_output=True,
                                    timeout=30).stdout
        with open(full, "rb") as fh:
            after = fh.read()
        added = sorted(file_lines(after) - file_lines(before))
        if added:
            changed.append({"file": rel, "lines": added})
    refresh_baseline(top, base, rels)
    save_baseline(top, base)
    if not changed:
        return
    session = payload.get("session_id", "") or "unknown"
    os.makedirs(script_dir(top), exist_ok=True)
    with open(os.path.join(script_dir(top), session + ".jsonl"), "a", encoding="utf-8") as fh:
        for c in changed:
            fh.write(json.dumps(dict(c, at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                                     by="subagent" if payload.get("agent_id") else "main")) + "\n")
    if payload.get("agent_id") or not is_core_repo(top):
        return
    ledger = load_ledger(top)
    state = session_state(ledger, session)
    scan_session(top, payload.get("transcript_path") or "", state)
    missing = {}
    for c in changed:
        files, skill = required_guides(c["file"])
        need = [f for f in files if f not in state.get("guides", []) and f not in state.get("guides_held", [])]
        if need:
            missing[tuple(need)] = skill
    if missing:
        state["guides_held"] = sorted(set(state.get("guides_held", [])) | {f for k in missing for f in k})
        text = ["[oc-be-tools] This command changed files whose guidelines were not read in this session. "
                "Load them now and check the change against them:"]
        text += guide_instruction([(list(k), v) for k, v in missing.items()])
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                                 "additionalContext": "\n".join(text)}}))
    save_ledger(top, ledger)


def run_mark(argv):
    """--mark <repo> <TICKET> <ref> <status> [--working [--prior <file>]]: record the outcome of an
    offer or a measurement. --working: the record was measured on the uncommitted changes on top of
    <ref> (HEAD); store that diff's patch-id and the record as it was before this run (--prior)."""
    usage = ("usage: ai_use_watch.py --mark <repo> <TICKET> <ref> recorded|declined|snoozed "
             "[--working [--prior <record.json>]]")
    flags = argv[4:]
    if len(argv) < 4 or argv[3] not in ("recorded", "declined", "snoozed"):
        sys.exit(usage)
    repo, key, ref, status = argv[:4]
    top = git(repo, "rev-parse", "--show-toplevel").strip() or repo
    sha = git(top, "rev-parse", "--verify", ref + "^{commit}").strip() or ref
    ledger = load_ledger(top)
    entry = ledger.setdefault("tickets", {}).setdefault(key, {})
    previous = entry.get("working") or {}
    entry.update({"status": status, "sha": sha, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                  "session": os.environ.get("CLAUDE_SESSION_ID", entry.get("session", ""))})
    if status == "recorded" and "--working" in flags:
        prior = None
        if "--prior" in flags and flags.index("--prior") + 1 < len(flags):
            with open(flags[flags.index("--prior") + 1], encoding="utf-8") as fh:
                prior = json.load(fh)
        elif previous.get("base") == sha:
            prior = previous.get("prior")             # re-run on the same uncommitted work: same prior
        entry["working"] = {"base": sha, "patch_id": patch_id(top, "HEAD"), "prior": prior}
    elif status == "recorded":
        entry.pop("working", None)
    save_ledger(top, ledger)
    print(f"{key}: {status} at {sha[:10]}" + (" (uncommitted changes)" if entry.get("working") else ""))


def run_show(argv):
    """--show <repo> <TICKET>: print the ticket's ledger entry as JSON ({} if none)."""
    if len(argv) != 2:
        sys.exit("usage: ai_use_watch.py --show <repo> <TICKET>")
    top = git(argv[0], "rev-parse", "--show-toplevel").strip() or argv[0]
    print(json.dumps(load_ledger(top).get("tickets", {}).get(argv[1], {}), indent=2))


if __name__ == "__main__":
    if os.environ.get("OC_BE_TOOLS_ISOLATED_REVIEW"):
        sys.exit(0)                                  # inside an isolated /oc-be-review run: no reminders, no gates
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--mark":
            run_mark(sys.argv[2:])
        elif len(sys.argv) > 1 and sys.argv[1] == "--show":
            run_show(sys.argv[2:])
        elif len(sys.argv) > 1 and sys.argv[1] == "--pre-commit":
            run_pre_commit()
        elif len(sys.argv) > 1 and sys.argv[1] == "--pre-edit":
            run_pre_edit()
        elif len(sys.argv) > 1 and sys.argv[1] == "--pre-script":
            run_pre_script()
        elif len(sys.argv) > 1 and sys.argv[1] == "--post-script":
            run_post_script()
        elif len(sys.argv) > 1 and sys.argv[1] == "--session-start":
            run_session_start()
        else:
            run_hook()
    except SystemExit:
        raise
    except Exception:  # never break the session because of a reminder
        pass
