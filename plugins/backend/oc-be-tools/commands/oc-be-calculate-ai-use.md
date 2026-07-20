---
description: Estimate how much of the current work came from AI (Claude Code) and how much of the AI's suggestions survived, using this session's transcript, the oc-be-implement sub-agent manifests, and file-history vs. the last commit (or uncommitted changes). Breaks the numbers down by artifact category and by first-pass-vs-fix provenance, and — for planning-heavy tickets with little code — reports the AI's planning/analysis effort as a separate band. Also counts unit tests added/modified and Postman assertion-vs-setup requests. Lets the developer adjust, then posts the result as a comment on the branch's JIRA ticket and tags it (customfield_10613) as ai_Dev_back for code and ai_test_back_dev for newly added tests.
argument-hint: "[--working | --commit <ref>] [--run <RUN_ID>]"
---

# Calculate AI Use (`calculateAIUse`)

You estimate how much of the current piece of work came from AI (Claude Code) and record it on the JIRA ticket. Everything needed is already in the environment — **do not ask the developer for a ticket number, a session, or a scope**; derive them:

- **Ticket** → from the current git branch name.
- **AI-suggested code** → from three complementary sources (see Task 3):
  1. **Sub-agent manifests** written by `/oc-be-implement`'s builder agents — the only reliable record of code written *inside* a sub-agent (their `Write`/`Edit` calls are **not** in the session transcript).
  2. **This session's transcript** — every `Write`/`Edit`/`MultiEdit` the assistant performed in the main context (your post-review fixes and the orchestrator's own edits).
  3. **File-history** (`~/.claude/file-history/<session>/`) — full versioned snapshots of tracked files; a backstop that also captures sub-agent edits to *existing* files.
- **Final code** → the **last commit** by default, or the **uncommitted working tree** if that is what is being measured.
- **Planning / analysis effort** (non-code) → from the `/oc-be-implement` planning manifest (`.claude/cache/ai-stats/<RUN_ID>/_planning.json`) if present, otherwise reconstructed from the transcript. Reported as an effort band, never a percentage (see Metrics).

## Metrics

| Metric | Definition | Formula |
|--------|------------|---------|
| **AI contribution** | Of the code lines added in the final code, the percentage that originated from AI (sub-agents **and** main-context edits). | `ai_added_lines / added_lines` |
| **AI retention** | Of the code lines AI proposed (across all drafts), the percentage still present in the final code. | `preserved_ai_lines / ai_suggested_lines` |

Both are reported **overall and per artifact category** (production code, DB migration, tests, Postman, docs/other), and are **rounded to the nearest 5%** and clamped to `0–100`.

The analyzer also reports **provenance** of the added lines:

| Provenance | Meaning |
|------------|---------|
| **agent (first pass)** | Written by an `oc-be-implement` builder sub-agent (or captured only in file-history). |
| **fix (main context)** | Written/edited by the assistant in the main session — your post-review fixes. |
| **human** | Present in the final commit but in *no* AI source — hand-typed in the IDE. |

The **fix burden** = `fix / (agent + fix)` — how much post-review steering the first pass needed.

### Planning / analysis effort (non-code axis)

Some tickets are mostly planning and discussion — the `/oc-be-implement` requirements-gathering and architecture-plan phases and the back-and-forth to approve the plan — with little committed code. That effort never lands in Jira/Confluence and is invisible to a line-based metric, so it is measured as **effort, not a percentage** (there is no artifact to take a percentage *of*):

| Signal | Meaning |
|--------|---------|
| **revision rounds** | how many approve/revise cycles the plan went through with the developer (the strongest depth signal) |
| **analysis tool calls** | Read/Grep/Glob/Bash/web/Jira lookups during planning |
| **plan size** | word count of the approved architecture plan |
| **duration** | wall-clock minutes in the planning window |
| **assistant turns** | planning-phase assistant messages |

These roll up to an **effort band — Low / Medium / High** (thresholds are seed values in `planning_band()`, meant to be tuned against your real runs). Preferred source is the planning manifest written by `/oc-be-implement` at plan approval; if absent, the analyzer **reconstructs** the window from the transcript — everything before the first code-producing action (first `Write`/`Edit` to a repo file, or the first builder sub-agent dispatch), scoped to the current branch via `gitBranch`. When fewer than `MEANINGFUL_CODE_MIN` (20) lines were added, the ticket is flagged **`planning-dominant`** and the effort band — not the code % — becomes the headline.

### Artifact counts & test-vs-setup

Alongside line counts, the analyzer reports concrete test counts (independent of AI attribution — computed from the commit itself):

- **Unit tests** — `@Test` methods in changed `src/test` `.java` files, split into **added** (method not in the base version) and **modified** (present before, body changed), plus `methods_total` in the final files.
- **Postman** — every request in changed `*.postman_collection.json`, split into **assertion requests** (a `test` script containing `pm.test` / `pm.expect` / `pm.response.to` / `tests[...]` — the actual tests) and **setup/cleanup requests** (no assertions — data prep/teardown). Also `added_requests` / `added_assertion_requests` vs the base collection, so you see what this commit introduced rather than the whole collection.

### Tags applied to `customfield_10613`

Two tags, either or both:

- **`ai_Dev_back`** — code changes excluding unit tests (added lines in production / migration / other source).
- **`ai_test_back_dev`** — newly added unit tests and/or Postman requests (`tests.added > 0` or `postman.added_requests > 0`).

> **These are best-effort estimates, not ground truth.** Contribution is complete when sub-agent manifests exist (they record sub-agent-created files that are otherwise invisible). Retention is content-based: a line AI wrote and later reworked — by AI *or* by the developer — will not match the final and counts as *not preserved*; that churn is expected and is the usual reason retention is well below 100% even when contribution is 100%. For files with no captured content (a sub-agent-created file present only in a manifest, never edited in the main context and not in file-history), contribution is counted but retention cannot be — this is reported as a warning. **The developer review step (Task 6) is the source of truth: the numbers can always be corrected before posting.**

---

## Argument Parsing

Parse `$ARGUMENTS` (all optional):

- `--working` → measure the **uncommitted working tree** (`git diff HEAD`) instead of the last commit.
- `--commit <ref>` → measure the given commit instead of `HEAD`.
- `--run <RUN_ID>` → use the manifests in `.claude/cache/ai-stats/<RUN_ID>/`. If omitted, use the **most recently modified** `RUN_ID` directory (and warn if none is found).
- No mode arguments → **auto**: if the working tree is dirty, ask whether to measure the *last commit* (default) or the *uncommitted changes*; if clean, measure the last commit.

There is intentionally **no ticket argument** — see Task 2.

---

## Task 1 — Determine what to measure (scope)

1. `git status --short` — is the working tree dirty? (Untracked report/scratch files alone do **not** count as meaningful dirtiness — `git diff HEAD` ignores them.)
2. Resolve the mode:
   - `--commit <ref>` → **commit mode** against `<ref>`.
   - `--working` → **working mode**.
   - Otherwise, if there are tracked uncommitted changes → ask the developer: "Measure the last commit (HEAD) or the uncommitted changes?" (default: last commit). If clean → **commit mode** against `HEAD`.
3. Record `[MODE]` (`commit`/`working`) and `[COMMIT-REF]` (for commit mode, default `HEAD`).
4. Confirm there is something to measure (commit mode: `git show --stat [COMMIT-REF]`; working mode: `git diff --stat HEAD`). If nothing, tell the developer and stop.

---

## Task 2 — Resolve the JIRA ticket (from the branch — do not ask)

1. `git branch --show-current` → `[CURRENT-BRANCH]`.
2. Extract the **first** `[A-Z]+-\d+` match anywhere in the branch name as `[TICKET-NUMBER]`
   (e.g. `andrius/INTRD-44654-api-restfulness` → `INTRD-44654`).
3. Only if no match is found, ask the developer for the ticket number.
4. Optionally read `.claude/cache/jira-tickets.json` for the ticket `summary` (display only; not required).

---

## Task 3 — Locate the AI sources

**Slug & session.** Claude Code stores per-session transcripts as JSONL at `~/.claude/projects/<PROJECT-SLUG>/<session-id>.jsonl`, where `<PROJECT-SLUG>` is the absolute repo path with `:`, `/`, `\` each replaced by `-`. For this repo (`C:\andrius\projektai\opencell\opencell-core`) that is `C--andrius-projektai-opencell-opencell-core`. The current session id is the folder name segment just before `scratchpad` in your scratchpad path (or `$CLAUDE_SESSION_ID` if set).

Collect these paths for the analyzer (each is optional — pass what exists):

1. **Manifests** — `.claude/cache/ai-stats/<RUN_ID>/` (resolve `<RUN_ID>` per Argument Parsing). These carry the sub-agent authorship (`*.json` with a `files` list) **and** the planning effort (`_planning.json`, `type: "planning"`). If the directory is missing (work not done via `/oc-be-implement`, or an older run), warn and continue with the other sources — planning effort will be reconstructed from the transcript instead.
2. **Transcripts** — pass the whole `~/.claude/projects/<PROJECT-SLUG>/` directory. The analyzer keeps only tool calls whose `file_path` is inside the repo, so unrelated sessions are naturally excluded, and post-review fixes from any of this ticket's sessions are captured.
3. **File-history root** — `~/.claude/file-history/`. The analyzer maps each session's `file-history-snapshot` entries (found in the transcripts) to the backup blobs here.

---

## Task 4 — Run the analyzer

Write the analyzer below to your session scratchpad as `ai_use_analyzer.py`, then run it (Python 3 is available as `python`).

```bash
python "<SCRATCHPAD>/ai_use_analyzer.py" \
  --repo "C:/andrius/projektai/opencell/opencell-core" \
  --transcripts "<PROJECT-SLUG directory OR a single .jsonl file>" \
  --manifests   "<.claude/cache/ai-stats/RUN_ID directory>" \
  --file-history-root "C:/Users/<you>/.claude/file-history" \
  --branch "<current branch from git branch --show-current>" \
  --mode commit --commit HEAD          # or: --mode working
```

Every source flag except `--repo` is optional. `--branch` scopes planning reconstruction to sessions on the current branch (pass `git branch --show-current`); omit it in working mode if unsure. It prints a JSON object with `work_type`, `planning`, `overall`, `by_category`, `provenance`, `artifacts`, `suggested_tags`, `sources`, and `warnings`. Percentages are rounded to the nearest 5% (`round(x/5)*5`, clamped 0–100). A percentage is `null` when its denominator is 0 — treat it as "unknown".

- `work_type` is `code`, `planning-dominant` (< 20 lines added but planning effort detected), or `minimal-change`.
- `planning` carries `detected`, `source` (`manifest`/`transcript`), `effort_band` (Low/Medium/High), `revision_rounds`, `analysis_tool_calls`, `plan_word_count`, `duration_minutes`, `assistant_turns`.
- `by_category[c].added` is the added **line count** per artifact category (production/migration/tests/postman/docs/other).
- `artifacts.tests` = `{files, methods_total, added, modified}` (unit-test methods, via `@Test` method-body diff of base-vs-final). `artifacts.postman` = `{files, requests_total, assertion_requests, setup_requests, added_requests, added_assertion_requests}` — `assertion_requests` are real tests (a `test` script with `pm.test`/`pm.expect`/`pm.response.to`/`tests[...]`); `setup_requests` are non-asserting data setup/cleanup calls.
- `suggested_tags` ⊆ `{ai_Dev_back, ai_test_back_dev}` — see Task 6b.

### `ai_use_analyzer.py`

```python
#!/usr/bin/env python3
"""Estimate AI contribution/retention for the current work from sub-agent manifests,
the session transcript, and file-history, vs. the final code."""
import argparse, glob, json, os, re, subprocess
from datetime import datetime

ANALYSIS_TOOLS = {"Read", "Grep", "Glob", "Bash", "WebFetch", "WebSearch", "LS"}
MEANINGFUL_CODE_MIN = 20  # fewer added code lines than this => planning-dominant ticket

def norm(l): return l.strip()
def triv(l): return not any(c.isalnum() for c in l)

def to_rel(path, repo):
    """Return repo-relative forward-slash path, or None if outside the repo."""
    p = path.replace("\\", "/")
    if os.path.isabs(p) or (len(p) > 1 and p[1] == ":"):
        ap = os.path.abspath(p)
        try:
            if os.path.commonpath([ap, repo]) == repo:
                return os.path.relpath(ap, repo).replace("\\", "/")
        except ValueError:
            return None
        return None
    return p  # already repo-relative

def category(rel):
    r = rel.lower()
    if "/src/test/" in r and r.endswith(".java"): return "tests"
    if r.endswith(".postman_collection.json") or "/us-tests/" in r: return "postman"
    if "/changelog/" in r and r.endswith(".xml"): return "migration"
    if r.endswith(".java"): return "production"
    if r.endswith(".md"): return "docs"
    return "other"

# ---- source 1: sub-agent manifests -> set of repo-relative files ----
def collect_manifest_files(manifests_dir, repo):
    files = {}
    if not manifests_dir or not os.path.isdir(manifests_dir):
        return files
    for mf in glob.glob(os.path.join(manifests_dir, "*.json")):
        try:
            with open(mf, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        agent = data.get("agent") or os.path.splitext(os.path.basename(mf))[0]
        for e in data.get("files", []) or []:
            rel = to_rel(e.get("path", ""), repo)
            if rel and not rel.startswith(".."):
                files[rel] = agent
    return files

# ---- source 2: transcript -> per-file set of AI-added (main-context) lines ----
def added_from_edit(old_s, new_s):
    old = {norm(l) for l in (old_s or "").splitlines()}
    return [norm(l) for l in (new_s or "").splitlines()
            if norm(l) and not triv(norm(l)) and norm(l) not in old]

def collect_transcript_lines(transcripts, repo):
    ai = {}
    if not transcripts: return ai
    files = sorted(glob.glob(os.path.join(transcripts, "*.jsonl"))) if os.path.isdir(transcripts) else [transcripts]
    for jf in files:
        try: fh = open(jf, encoding="utf-8")
        except OSError: continue
        with fh:
            for raw in fh:
                raw = raw.strip()
                if not raw: continue
                try: o = json.loads(raw)
                except json.JSONDecodeError: continue
                if o.get("type") != "assistant": continue
                content = (o.get("message") or {}).get("content")
                if not isinstance(content, list): continue
                for c in content:
                    if not isinstance(c, dict) or c.get("type") != "tool_use": continue
                    inp = c.get("input") or {}
                    rel = to_rel(inp.get("file_path") or "", repo)
                    if not rel or rel.startswith(".."): continue
                    b = ai.setdefault(rel, set())
                    if c.get("name") == "Write":
                        b.update(norm(l) for l in (inp.get("content") or "").splitlines()
                                 if norm(l) and not triv(norm(l)))
                    elif c.get("name") == "Edit":
                        b.update(added_from_edit(inp.get("old_string"), inp.get("new_string")))
                    elif c.get("name") in ("MultiEdit", "NotebookEdit"):
                        for e in inp.get("edits", []) or []:
                            b.update(added_from_edit(e.get("old_string"), e.get("new_string") or e.get("new_source")))
    return {k: v for k, v in ai.items() if v}

# ---- source 3: file-history -> per-file union of lines across all versions ----
def collect_file_history(transcripts, fh_root, repo):
    lines = {}
    if not transcripts or not fh_root or not os.path.isdir(fh_root): return lines
    tx = sorted(glob.glob(os.path.join(transcripts, "*.jsonl"))) if os.path.isdir(transcripts) else [transcripts]
    for jf in tx:
        sid = os.path.splitext(os.path.basename(jf))[0]
        fhdir = os.path.join(fh_root, sid)
        if not os.path.isdir(fhdir): continue
        pb = {}
        try:
            with open(jf, encoding="utf-8") as fh:
                for raw in fh:
                    try: o = json.loads(raw)
                    except json.JSONDecodeError: continue
                    if o.get("type") == "file-history-snapshot":
                        for path, info in ((o.get("snapshot") or {}).get("trackedFileBackups") or {}).items():
                            bf = (info or {}).get("backupFileName")
                            if bf: pb.setdefault(path, set()).add(bf)
        except OSError: continue
        for path, bfs in pb.items():
            rel = to_rel(path, repo)
            if not rel or rel.startswith(".."): continue
            for bf in bfs:
                try:
                    with open(os.path.join(fhdir, bf), encoding="utf-8", errors="replace") as f:
                        for l in f:
                            n = norm(l)
                            if n and not triv(n): lines.setdefault(rel, set()).add(n)
                except OSError: pass
    return lines

# ---- final code ----
def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")

def added_lines_map(repo, mode, ref):
    res = git(repo, "diff", "--unified=0", "HEAD") if mode == "working" \
          else git(repo, "diff", "--unified=0", f"{ref}~1..{ref}")
    added, cur = {}, None
    for line in res.stdout.splitlines():
        if line.startswith("+++ b/"): cur = line[6:]; added.setdefault(cur, set())
        elif line.startswith(("+++", "---")): continue
        elif line.startswith("+") and cur is not None:
            n = norm(line[1:])
            if n and not triv(n): added[cur].add(n)
    return {k: v for k, v in added.items() if v}

def final_content(repo, rel, mode, ref):
    if mode == "working":
        p = os.path.join(repo, rel)
        if not os.path.isfile(p): return None
        with open(p, encoding="utf-8", errors="replace") as fh: src = fh.read()
    else:
        res = git(repo, "show", f"{ref}:{rel}")
        if res.returncode != 0: return None
        src = res.stdout
    return {norm(l) for l in src.splitlines() if norm(l) and not triv(norm(l))}

def round5(x): return max(0, min(100, int(round(x / 5.0) * 5)))
def pct(a, b): return round(100 * a / b, 1) if b else None

# ---- artifact counts: unit tests & Postman assertions ----
def changed_paths(repo, mode, ref):
    res = git(repo, "diff", "--name-only", "HEAD") if mode == "working" \
          else git(repo, "diff", "--name-only", f"{ref}~1..{ref}")
    return [p.strip().replace("\\", "/") for p in res.stdout.splitlines() if p.strip()]

def file_versions(repo, rel, mode, ref):
    """(base_src, final_src); base is '' for a newly added/unavailable file."""
    if mode == "working":
        b = git(repo, "show", f"HEAD:{rel}")
        base = b.stdout if b.returncode == 0 else ""
        p = os.path.join(repo, rel)
        final = open(p, encoding="utf-8", errors="replace").read() if os.path.isfile(p) else ""
    else:
        b = git(repo, "show", f"{ref}~1:{rel}");  base  = b.stdout if b.returncode == 0 else ""
        f = git(repo, "show", f"{ref}:{rel}");     final = f.stdout if f.returncode == 0 else ""
    return base, final

_TEST_NAME = re.compile(r'\b([A-Za-z_]\w*)\s*\(')
def extract_test_methods(src):
    """Map each @Test method name -> its normalized body. Heuristic brace matching;
    good enough to tell added-vs-modified test methods apart for an estimate."""
    methods, lines = {}, src.splitlines()
    n, i = len(lines), 0
    while i < n:
        if re.search(r'@Test\b', lines[i]):
            j = i + 1
            while j < n and j - i <= 8 and '(' not in lines[j]:  # skip further annotations/modifiers
                j += 1
            if j < n and '(' in lines[j]:
                mm = _TEST_NAME.search(lines[j])
                name = mm.group(1) if mm else f"test@{j}"
                depth, started, body, k = 0, False, [], j
                while k < n:
                    body.append(lines[k])
                    depth += lines[k].count('{') - lines[k].count('}')
                    if '{' in lines[k]: started = True
                    if started and depth <= 0: break
                    k += 1
                while name in methods: name += "_"   # de-dup overloads
                methods[name] = "\n".join(norm(x) for x in body if norm(x) and not triv(norm(x)))
                i = k + 1
                continue
        i += 1
    return methods

def java_test_stats(repo, mode, ref, changed):
    files = [p for p in changed if category(p) == "tests"]
    added = modified = total = 0
    for rel in files:
        base_src, final_src = file_versions(repo, rel, mode, ref)
        base_m, final_m = extract_test_methods(base_src), extract_test_methods(final_src)
        total += len(final_m)
        for name, body in final_m.items():
            if name not in base_m: added += 1
            elif base_m[name] != body: modified += 1
    return {"files": len(files), "methods_total": total, "added": added, "modified": modified}

_PM_ASSERT = re.compile(r'pm\.test\s*\(|pm\.expect\s*\(|pm\.response\.to\b|\btests\s*\[')
def _pm_requests(items):
    for it in items or []:
        if not isinstance(it, dict): continue
        if it.get("item") is not None:
            yield from _pm_requests(it.get("item"))
        elif it.get("request") is not None:
            yield it

def _pm_has_assertion(item):
    for ev in item.get("event", []) or []:
        if ev.get("listen") == "test":
            ex = (ev.get("script") or {}).get("exec") or []
            script = "\n".join(ex) if isinstance(ex, list) else str(ex)
            if _PM_ASSERT.search(script): return True
    return False

def postman_stats(repo, mode, ref, changed):
    files = [p for p in changed if category(p) == "postman"]
    total = assertion = added = added_assertion = 0
    for rel in files:
        base_src, final_src = file_versions(repo, rel, mode, ref)
        try: final = json.loads(final_src) if final_src else {}
        except json.JSONDecodeError: final = {}
        try: base = json.loads(base_src) if base_src else {}
        except json.JSONDecodeError: base = {}
        base_names = {r.get("name", "") for r in _pm_requests(base.get("item"))}
        for r in _pm_requests(final.get("item")):
            total += 1
            has = _pm_has_assertion(r)
            if has: assertion += 1
            if r.get("name", "") not in base_names:
                added += 1
                if has: added_assertion += 1
    return {"files": len(files), "requests_total": total, "assertion_requests": assertion,
            "setup_requests": total - assertion, "added_requests": added,
            "added_assertion_requests": added_assertion}

# ---- planning / analysis effort axis (non-code) ----
def _words(s): return len((s or "").split())

def duration_minutes(start, end):
    try:
        p = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
        if start and end:
            return max(0, round((p(end) - p(start)).total_seconds() / 60))
    except (ValueError, AttributeError, TypeError):
        pass
    return 0

def load_planning_manifest(manifests_dir):
    """A planning manifest is any *.json with type == 'planning' in the run dir."""
    if not manifests_dir or not os.path.isdir(manifests_dir): return None
    for mf in sorted(glob.glob(os.path.join(manifests_dir, "*.json"))):
        try:
            with open(mf, encoding="utf-8") as fh: d = json.load(fh)
        except (OSError, json.JSONDecodeError): continue
        if d.get("type") == "planning": return d
    return None

def _user_text(o):
    content = (o.get("message") or {}).get("content")
    if isinstance(content, str): return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text")
    return ""

def reconstruct_planning(transcripts, repo, branch):
    """Fallback when no planning manifest exists. Planning window = all activity
    before the first code-producing action (Write/Edit to a repo file, or an
    oc-be builder/generator sub-agent dispatch). Scoped to `branch` when given."""
    if not transcripts: return None
    files = sorted(glob.glob(os.path.join(transcripts, "*.jsonl"))) if os.path.isdir(transcripts) else [transcripts]
    agg = {"assistant_turns": 0, "user_turns": 0, "analysis_tool_calls": 0,
           "revision_rounds": 0, "plan_word_count": 0, "duration_minutes": 0,
           "used_plan_mode": False}
    saw = False
    for jf in files:
        events = []
        try:
            with open(jf, encoding="utf-8") as fh:
                for raw in fh:
                    try: events.append(json.loads(raw))
                    except (json.JSONDecodeError, ValueError): continue
        except OSError:
            continue
        if branch:
            gbs = {o.get("gitBranch") for o in events if o.get("gitBranch")}
            if gbs and branch not in gbs: continue   # session belongs to another branch
        # locate the first code-producing action
        first_code = None
        for o in events:
            if o.get("type") != "assistant": continue
            for c in (o.get("message") or {}).get("content") or []:
                if not isinstance(c, dict) or c.get("type") != "tool_use": continue
                nm, inp = c.get("name"), (c.get("input") or {})
                code = False
                if nm in ("Write", "Edit", "MultiEdit"):
                    rel = to_rel(inp.get("file_path") or "", repo)
                    code = bool(rel and not rel.startswith(".."))
                elif nm == "Task":
                    st = inp.get("subagent_type") or ""
                    code = ("builder" in st or "generator" in st or "oc-be" in st)
                if code: first_code = o.get("timestamp"); break
            if first_code: break
        # walk the planning window (everything before first_code); track this
        # session's own start/end so durations are summed per-session, never a
        # meaningless min..max span across many sessions on a shared branch.
        win = False
        fstart = fend = None
        for o in events:
            ts = o.get("timestamp")
            if first_code and ts and ts >= first_code: break
            t = o.get("type")
            if t == "user":
                if _user_text(o).strip():
                    agg["user_turns"] += 1; win = True
            elif t == "assistant":
                agg["assistant_turns"] += 1; win = True
                for c in (o.get("message") or {}).get("content") or []:
                    if not isinstance(c, dict) or c.get("type") != "tool_use": continue
                    if c.get("name") in ANALYSIS_TOOLS: agg["analysis_tool_calls"] += 1
                    if c.get("name") == "ExitPlanMode":
                        agg["revision_rounds"] += 1; agg["used_plan_mode"] = True
                        agg["plan_word_count"] = max(agg["plan_word_count"],
                                                     _words((c.get("input") or {}).get("plan")))
            if ts:
                if fstart is None or ts < fstart: fstart = ts
                if fend is None or ts > fend: fend = ts
        if win:
            saw = True
            agg["duration_minutes"] += duration_minutes(fstart, fend)
    return agg if saw else None

def planning_band(p):
    s = 0
    s += 2 if p["revision_rounds"] >= 3 else 1 if p["revision_rounds"] >= 1 else 0
    s += 2 if p["analysis_tool_calls"] >= 25 else 1 if p["analysis_tool_calls"] >= 8 else 0
    s += 2 if p["plan_word_count"] >= 1200 else 1 if p["plan_word_count"] >= 400 else 0
    s += 2 if p["duration_minutes"] >= 90 else 1 if p["duration_minutes"] >= 30 else 0
    s += 1 if p["assistant_turns"] >= 25 else 0
    return "High" if s >= 5 else "Medium" if s >= 2 else "Low"

def build_planning(manifest, recon):
    """Merge the planning manifest (authoritative for rounds/plan/timestamps) with
    the transcript reconstruction (authoritative for tool/turn activity)."""
    if not manifest and not recon: return {"detected": False}
    m, r = manifest or {}, recon or {}
    def pick(*vs):
        for v in vs:
            if v: return v
        return 0
    p = {
        "detected": True,
        "source": (["manifest"] if manifest else []) + (["transcript"] if recon else []),
        "revision_rounds": pick(m.get("revision_rounds"), r.get("revision_rounds")),
        "analysis_tool_calls": pick(r.get("analysis_tool_calls")),
        "assistant_turns": pick(r.get("assistant_turns")),
        "plan_word_count": pick(m.get("plan_word_count"), r.get("plan_word_count")),
        "duration_minutes": (duration_minutes(m.get("planning_started"), m.get("plan_approved"))
                             if m.get("planning_started") and m.get("plan_approved")
                             else r.get("duration_minutes", 0)),
        "used_plan_mode": bool(r.get("used_plan_mode")) or bool(manifest),
    }
    p["effort_band"] = planning_band(p)
    if m.get("notes"): p["notes"] = m["notes"]
    return p

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--transcripts")
    ap.add_argument("--manifests")
    ap.add_argument("--file-history-root", dest="fh_root")
    ap.add_argument("--mode", choices=["commit", "working"], default="commit")
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--branch")  # scopes planning reconstruction to this branch's sessions
    a = ap.parse_args()
    repo = os.path.abspath(a.repo)
    warnings = []

    manifest_files = collect_manifest_files(a.manifests, repo)
    main_lines     = collect_transcript_lines(a.transcripts, repo)
    fh_lines       = collect_file_history(a.transcripts, a.fh_root, repo)
    if not manifest_files:
        warnings.append("No sub-agent manifests found — sub-agent-created files may be undercounted. "
                        "Run future work via /oc-be-implement for complete attribution.")

    added = added_lines_map(repo, a.mode, a.commit)
    total_added = sum(len(v) for v in added.values())

    planning = build_planning(load_planning_manifest(a.manifests),
                              reconstruct_planning(a.transcripts, repo, a.branch))
    if total_added >= MEANINGFUL_CODE_MIN:
        work_type = "code"
    elif planning.get("detected"):
        work_type = "planning-dominant"
    else:
        work_type = "minimal-change"
    if work_type == "planning-dominant":
        warnings.append("Planning-dominant ticket: little code committed — the planning-effort band, "
                        "not the code contribution %, is the headline.")
    if planning.get("detected") and "manifest" not in planning.get("source", []):
        warnings.append("Planning effort reconstructed from the transcript (no _planning.json manifest). "
                        "Run planning via /oc-be-implement for a precise record.")

    cats = ["production", "migration", "tests", "postman", "docs", "other"]
    agg = {c: {"added": 0, "agent": 0, "fix": 0, "human": 0} for c in cats}
    no_retention_files = []

    # provenance of each added line
    for rel, lines in added.items():
        c = category(rel)
        for ln in lines:
            agg[c]["added"] += 1
            if ln in main_lines.get(rel, ()):        agg[c]["fix"]   += 1
            elif rel in manifest_files:              agg[c]["agent"] += 1
            elif ln in fh_lines.get(rel, ()):        agg[c]["agent"] += 1
            else:                                    agg[c]["human"] += 1
        if rel in manifest_files and not main_lines.get(rel) and not fh_lines.get(rel):
            no_retention_files.append(rel)  # counted for contribution, no content for retention

    # retention: suggested = union(main-context lines, file-history lines) per file; preserved = ∩ final
    # scoped to files that are part of the measured commit/working set
    ret = {c: {"suggested": 0, "preserved": 0} for c in cats}
    ai_files = (set(main_lines) | set(fh_lines)) & set(added)
    for rel in ai_files:
        c = category(rel)
        suggested = set(main_lines.get(rel, set())) | set(fh_lines.get(rel, set()))
        if not suggested: continue
        final = final_content(repo, rel, a.mode, a.commit)
        ret[c]["suggested"] += len(suggested)
        if final is not None:
            ret[c]["preserved"] += sum(1 for l in suggested if l in final)

    def cat_report(c):
        d, r = agg[c], ret[c]
        ai = d["agent"] + d["fix"]
        return {
            "added": d["added"], "ai_added": ai,
            "agent": d["agent"], "fix": d["fix"], "human": d["human"],
            "contribution_raw": pct(ai, d["added"]),
            "contribution_pct": round5(pct(ai, d["added"])) if d["added"] else None,
            "retention_raw": pct(r["preserved"], r["suggested"]),
            "retention_pct": round5(pct(r["preserved"], r["suggested"])) if r["suggested"] else None,
        }

    by_cat = {c: cat_report(c) for c in cats if agg[c]["added"]}
    tot_ai = sum(agg[c]["agent"] + agg[c]["fix"] for c in cats)
    tot_agent = sum(agg[c]["agent"] for c in cats)
    tot_fix = sum(agg[c]["fix"] for c in cats)
    tot_human = sum(agg[c]["human"] for c in cats)
    tot_sug = sum(ret[c]["suggested"] for c in cats)
    tot_pre = sum(ret[c]["preserved"] for c in cats)
    head = by_cat.get("production", {})

    if no_retention_files:
        warnings.append(f"{len(no_retention_files)} sub-agent file(s) counted for contribution but not "
                        f"retention (no captured line content): e.g. {no_retention_files[:3]}")

    # artifact counts (unit tests, Postman assertions) — from the commit, independent of AI attribution
    changed = changed_paths(repo, a.mode, a.commit)
    tests = java_test_stats(repo, a.mode, a.commit, changed)
    postman = postman_stats(repo, a.mode, a.commit, changed)

    # suggested tags: code work vs newly-added test work (both may apply)
    has_code = any(agg[c]["added"] for c in ("production", "migration", "other"))
    has_new_tests = tests["added"] > 0 or postman["added_requests"] > 0
    suggested_tags = (["ai_Dev_back"] if has_code else []) + (["ai_test_back_dev"] if has_new_tests else [])

    print(json.dumps({
        "mode": a.mode, "commit": a.commit,
        "work_type": work_type,
        "planning": planning,
        "headline": {"category": "production",
                     "contribution_pct": head.get("contribution_pct"),
                     "retention_pct": head.get("retention_pct")},
        "overall": {
            "added": total_added, "ai_added": tot_ai,
            "contribution_raw": pct(tot_ai, total_added),
            "contribution_pct": round5(pct(tot_ai, total_added)) if total_added else None,
            "retention_raw": pct(tot_pre, tot_sug),
            "retention_pct": round5(pct(tot_pre, tot_sug)) if tot_sug else None,
        },
        "provenance": {"agent": tot_agent, "fix": tot_fix, "human": tot_human,
                       "fix_burden_pct": round5(pct(tot_fix, tot_agent + tot_fix)) if (tot_agent + tot_fix) else None},
        "by_category": by_cat,
        "artifacts": {"tests": tests, "postman": postman},
        "suggested_tags": suggested_tags,
        "sources": {"manifest_files": len(manifest_files),
                    "transcript_files": len(main_lines),
                    "file_history_files": len(fh_lines)},
        "warnings": warnings,
    }, indent=2))

if __name__ == "__main__":
    main()
```

---

## Task 5 — Present the estimate, then let the developer adjust

Show a clear breakdown. The **headline is production code**; everything else is context.

```
AI Use Estimate — [TICKET-NUMBER]
=================================
Measured:  last commit (HEAD)        # or: uncommitted changes
Work type: code                      # or: planning-dominant / minimal-change
Sources:   manifests <n> · transcript <n> files · file-history <n> files

Planning/analysis effort: High  (source: manifest)
  6 plan iteration(s) · 38 code/ticket lookups · ~1400-word plan · ~120 min planning

Breakdown by artifact (lines · AI-contribution · retention):
  • Production code   980 lines   100%   85%     ← headline
  • DB migration      210 lines   100%   98%
  • Unit tests        340 lines   100%   95%    (17 tests added, 11 modified)
  • Postman         2,600 lines   100%    —     (56 assertion reqs added, of 80 added; 47 setup/cleanup)
  • docs/other          0 lines     —     —
  ────────────────────────────────────────────
  ALL             4,130 lines   100%   96%     (context only)

Provenance (all added lines):
  agent first-pass:   3,700
  main-context fix:      430     → fix burden 10%
  hand-written (you):     0

Suggested tags: ai_Dev_back, ai_test_back_dev

Headline → AI contribution: 100%   AI retention: 85%

Warnings:
  - <any warnings from the analyzer>
```

Pull the line counts from `by_category[c].added`; the test/postman detail from `artifacts.tests` (`added`, `modified`, `methods_total`) and `artifacts.postman` (`added_assertion_requests`, `added_requests`, `assertion_requests`, `setup_requests`). Postman retention is `—` (generated JSON, not line-matched).

Explain briefly, in one line each: contribution counts sub-agent + main-context code; retention below 100% is normal iteration churn (AI reworking its own drafts); a non-zero "hand-written" count means some final lines were in no AI source.

If a metric is `null`, show it as `unknown` and say why (no added lines / no captured AI content).

**Choose the headline by `work_type`:**
- `code` → the headline is production contribution + retention (as before).
- `planning-dominant` → the headline is the **planning effort band**; still show the code numbers but label them secondary ("<N> lines changed"). Say plainly that this ticket's AI value was in analysis/planning, not code volume.
- `minimal-change` → little code and no planning detected; report what there is and lean on the developer's judgement.

Then ask the developer to confirm or correct, using `AskUserQuestion`:
- For code tickets — the **two headline numbers** (production contribution, production retention), one question each: offer the computed value first, marked *(Recommended)*, a couple of nearby 5% steps, and a free-form override. **Re-round** to the nearest 5% and clamp `0–100`. Store as `[CONTRIBUTION]` and `[RETENTION]`. (If the developer says all code is AI, set contribution to 100% even when the automated figure is lower — the automated number is a floor.)
- Always — the **planning effort band** (`Low`/`Medium`/`High`) when planning was detected, defaulting to the computed band. Store as `[PLANNING-BAND]`. The band is a judgement call; the developer's choice wins.
- Optionally, a **1–5 "AI usefulness on this ticket"** rating — the one signal no transcript captures (e.g. AI unblocked a hard design decision in two messages). Store as `[USEFULNESS]` if given.
- The **tags** to apply (`suggested_tags`): `ai_Dev_back` when there are code changes excluding unit tests, `ai_test_back_dev` when unit tests and/or Postman requests were newly added — both may apply. Show the suggested set and let the developer add/remove. Store as `[TAGS]`.

---

## Task 6 — Post to JIRA (confirm first)

Writing to JIRA is outward-facing. **Show exactly what will be posted and set, and ask for confirmation before writing.** Present the comment body, the field change (`customfield_10613` will include the tags in `[TAGS]`), and the target ticket.

Include an artifact bullet only for categories that actually changed. Fill line counts from `by_category[c].added`, and the test/Postman counts from `artifacts`.

Comment body (**code** ticket):

```
AI usage (Claude Code) — measured on <last commit HEAD | uncommitted changes>:
- AI contribution: [CONTRIBUTION]% of the added production code originated from AI.
- AI retention: [RETENTION]% of the AI-suggested code was preserved (the remainder was superseded by AI's own iterative fixes).
- Post-review fix burden: <fix>%.

Breakdown by artifact:
- Production code: <p_lines> lines — contribution <pc>%, retention <pr>%
- DB migration: <m_lines> lines — contribution <mc>%, retention <mr>%
- Unit tests: <t_lines> lines, <t_added> test(s) added / <t_mod> modified — contribution <tc>%, retention <tr>%
- Postman: <pm_lines> lines, <pm_add_assert> assertion request(s) added (of <pm_add> added; <pm_setup> setup/cleanup, non-asserting) — contribution <pmc>%

Planning/analysis effort: [PLANNING-BAND]
- <rounds> plan iteration(s) with the developer
- <n> code/ticket lookups during planning
- ~<w>-word design plan
- ~<min> min in the planning phase
<if [USEFULNESS] given:>- Developer-rated usefulness: [USEFULNESS]/5

Method: estimated from the oc-be-implement sub-agent manifests, the Claude Code session transcript, and file-history vs. the final code, reviewed and confirmed by the developer. Values rounded to the nearest 5%.
```

Comment body (**planning-dominant** ticket — lead with effort, not code %):

```
AI usage (Claude Code) — <TICKET-NUMBER> was planning/analysis-dominant (only <N> code lines changed):
- Planning/analysis effort: [PLANNING-BAND]
  - <rounds> plan iteration(s) with the developer (times the plan was presented/refined)
  - <n> code/ticket lookups during planning
  - ~<w>-word design plan
  - ~<min> min in the planning phase
- Code contribution (of the small change): [CONTRIBUTION]%.
<if [USEFULNESS] given:>- Developer-rated usefulness: [USEFULNESS]/5.

Note: the AI value here was in requirements analysis and solution design (which is not committed to code), not in code volume. Method: planning effort from the oc-be-implement planning manifest (or reconstructed from the session transcript), reviewed and confirmed by the developer.
```

On confirmation, use the **Atlassian MCP tools** (site `opencellsoft.atlassian.net`, cloudId `648ef912-b483-4da2-91af-73ea1e3fdad8`; resolve via `getAccessibleAtlassianResources` if unknown).

### 6a. Add the comment

`addCommentToJiraIssue` with `cloudId`, `issueIdOrKey = [TICKET-NUMBER]`, and the body above.

### 6b. Set the tags on `customfield_10613`

The tag set is `[TAGS]` (from `suggested_tags`, as adjusted by the developer):
- **`ai_Dev_back`** — code changes excluding unit tests (production / migration / other source).
- **`ai_test_back_dev`** — newly added unit tests and/or Postman requests.

Both may apply (a commit with production code *and* new tests gets both); a docs-only or planning-only change may get neither.

**Do not overwrite existing values; append each tag in `[TAGS]` only if not already present.**

1. Read the current value first (`getJiraIssue` with `fields: ["customfield_10613"]`). Drop any tag from `[TAGS]` that is already present; if none remain, **skip the edit** and note it.
2. Otherwise learn the field shape (`getJiraIssueTypeMetaWithFields`: array of `option` vs array of strings vs single `option`) and build the matching `editJiraIssue` payload, merging the new tags with the existing values:
   - Multi-select (array of options): `{ "fields": { "customfield_10613": [ {"value": "ai_Dev_back"}, {"value": "ai_test_back_dev"}, <existing...> ] } }`
   - Labels-style (array of strings): `{ "fields": { "customfield_10613": ["ai_Dev_back", "ai_test_back_dev", <existing...>] } }`
   - Single-select (option): only one value is allowed — apply the primary tag (`ai_Dev_back` if present, else `ai_test_back_dev`) and warn that the field cannot hold both.
3. Call `editJiraIssue` with `cloudId`, `issueIdOrKey = [TICKET-NUMBER]`, and the payload.
   - If rejected because a tag is not an allowed option, report the error verbatim (the option may need creating in the field config) and do not retry blindly.

### 6c. Confirm

```
Posted to [TICKET-NUMBER]:
  ✓ Comment added (contribution [CONTRIBUTION]% · retention [RETENTION]% · planning [PLANNING-BAND])
  ✓ Tagged [TAGS] on customfield_10613   (or: already present — no change)
```

If the developer declines, print the comment body and intended field change so they can apply them manually, and stop without writing.

---

## Examples

```bash
# Measure the last commit; auto-pick the newest oc-be-implement run's manifests
/oc-be-tools:oc-be-calculate-ai-use

# Measure the current uncommitted changes
/oc-be-tools:oc-be-calculate-ai-use --working

# Use a specific run's manifests and a specific commit
/oc-be-tools:oc-be-calculate-ai-use --commit 3434f5767b --run INTRD-41234-20260703-101500
```

## Notes & limitations

- **Sub-agent coverage.** A sub-agent's `Write`/`Edit` calls never appear in the session transcript, and sub-agent transcripts are not persisted separately. The **manifests** are what make sub-agent (including sub-agent-*created*) files countable. Work not done through `/oc-be-implement` has no manifest — the transcript and file-history still cover main-context edits and edits to existing files, but a sub-agent-created new file from such a run cannot be attributed.
- **Contribution vs. retention.** Contribution is complete with manifests; retention is content-based and only defined for files whose line content was captured (transcript or file-history). Manifest-only files are counted for contribution and reported as retention-unknown.
- **Attribution.** A final line is `fix` if it appears in a main-context edit, else `agent` if the file is in a manifest or the line is in file-history, else `human`. Whitespace-normalized, pure-punctuation lines ignored, distinct-line based per file (heavy rewrites de-duplicated).
- **Squashed / cross-branch commits.** When many sessions/branches are squashed into one commit, file-history alone under-covers it; manifests restore coverage for the parts built via `/oc-be-implement`.
- **Artifact counts are commit-derived, not AI-attributed.** Unit-test add/modify counts come from a heuristic `@Test` method-body diff (base vs final); overloaded names and unusual formatting can be miscounted slightly. Postman assertion detection keys off `test`-event scripts; a request whose assertions live elsewhere (or a pure `console.log` test script) may be misclassified. `added_*` compares request **names** against the base collection, so a renamed request reads as added. Good enough for the ticket record; the developer can correct.
- **Tag semantics.** `ai_test_back_dev` triggers on newly *added* tests/Postman requests (not modifications). A commit that only edits existing tests gets `ai_Dev_back` (if it also touches code) but not `ai_test_back_dev` — adjust in review if that is not what you want.
- **Planning effort is effort, not a percentage.** The requirements-gathering and architecture-plan work produces no committed artifact, so it can only be quantified as activity (rounds, lookups, plan size, time) rolled into a Low/Medium/High band. The band thresholds are seed values in `planning_band()` — tune them against your real runs. Reconstruction from the transcript is a fallback; the `/oc-be-implement` planning manifest is authoritative for revision rounds and plan size.
- Always defer to the developer's adjusted numbers — the automatic figures are a starting point, not an audit.
```
