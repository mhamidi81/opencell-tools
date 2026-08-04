---
description: Estimate how much of the current work came from AI (Claude Code) and how much of the AI's suggestions survived, using this session's transcript, the oc-be-implement sub-agent manifests, and file-history vs. the last commit (or uncommitted changes). Breaks the numbers down by artifact category and by provenance (a reviewer-rework figure), and — for planning-heavy tickets with little code — reports the AI's planning/analysis effort as a separate band. Also counts unit tests added/modified, Postman assertion-vs-setup requests and the test cases inside them, and developer↔AI interactions per session. Lets the developer adjust, then posts a human comment, tags the ticket (customfield_10613) as ai_Dev_back / ai_test_back_dev, and records a machine-readable JSON record (keyed by domain/user, latest-only) in a dedicated AI-usage field for reporting.
argument-hint: "[--working | --commit <ref>] [--run <RUN_ID>]"
---

# Calculate AI Use (`calculateAIUse`)

You estimate how much of the current piece of work came from AI (Claude Code) and record it on the JIRA ticket. Everything needed is already in the environment — **do not ask the developer for a ticket number, a session, or a scope**; derive them:

- **Ticket** → from the current git branch name.
- **AI-suggested code** → from four complementary sources (see Task 3):
  1. **Sub-agent manifests** written by `/oc-be-implement`'s builder agents — the record of *which files* a sub-agent created/modified (their `Write`/`Edit` calls are **not** in the session transcript).
  2. **Sub-agent first-pass snapshots** — `<RUN_ID>/snapshots/<phase>.diff`, a `git diff HEAD` of each builder's output captured at its finish. This preserves the sub-agent's produced **line content** (otherwise lost when its session ends), so **retention is measurable for sub-agent files** — added lines only, so it is delta-correct for modified files (e.g. an existing Postman collection) too.
  3. **This session's transcript** — every `Write`/`Edit`/`MultiEdit` the assistant performed in the main context (your post-review fixes and the orchestrator's own edits).
  4. **File-history** (`~/.claude/file-history/<session>/`) — full versioned snapshots of tracked files; a backstop that also captures sub-agent edits to *existing* files.
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

The **reviewer rework** = `fix / (agent + fix)` — of the AI-authored lines, the share written during the post-review (main-context) phase rather than the builders' first pass; i.e. how much of the AI code the review-and-fix step changed. (JSON key: `reviewer_rework_pct`.)

### Planning / analysis effort (non-code axis)

Some tickets are mostly planning and discussion — the `/oc-be-implement` requirements-gathering and architecture-plan phases and the back-and-forth to approve the plan — with little committed code. That effort never lands in Jira/Confluence and is invisible to a line-based metric, so it is measured as **effort, not a percentage** (there is no artifact to take a percentage *of*):

| Signal | Meaning |
|--------|---------|
| **revision rounds** | how many approve/revise cycles the plan went through with the developer (the strongest depth signal) |
| **analysis tool calls** | Read/Grep/Glob/Bash/web/Jira lookups during planning |
| **plan size** | word count of the approved architecture plan |
| **duration** | wall-clock minutes in the planning window |
| **assistant turns** | planning-phase assistant messages |

These roll up to an **effort band — Low / Medium / High** (thresholds are seed values in `planning_band()`, meant to be tuned against your real runs). Preferred source is the planning manifest written by `/oc-be-implement` at plan approval; if absent, the analyzer **reconstructs** the window from the transcript — everything before the first code-producing action (first `Write`/`Edit` to a repo file, or the first builder sub-agent dispatch), across the **sessions that edited this commit's files** (not by branch). When fewer than `MEANINGFUL_CODE_MIN` (20) lines were added, the ticket is flagged **`planning-dominant`** and the effort band — not the code % — becomes the headline.

### Artifact counts & test-vs-setup

Alongside line counts, the analyzer reports concrete test counts (independent of AI attribution — computed from the commit itself):

- **Unit tests** — `@Test` methods in changed `src/test` `.java` files, split into **added** (method not in the base version) and **modified** (present before, body changed), plus `methods_total` in the final files.
- **Postman** — every request in changed `*.postman_collection.json`, split into **assertion requests** (a `test` script containing `pm.test` / `pm.expect` / `pm.response.to` / `tests[...]` — the actual tests) and **setup/cleanup requests** (no assertions — data prep/teardown). Also `added_requests` / `added_assertion_requests` vs the base collection, so you see what this commit introduced rather than the whole collection. And `test_cases_total` / `added_test_cases` — the number of **individual tests** (`pm.test(...)` blocks, plus legacy `tests[...] =`) *inside* the assertion requests, since one request can hold several test cases.

### Interactions (engagement)

The analyzer also reports developer↔AI **interactions** — the count of **genuine human prompts** (messages you actually sent the AI) across the sessions that worked on this commit, plus the total and per-session average. A rough gauge of how much back-and-forth the work took, complementing the planning-effort band. (JSON: `interactions = {sessions, total_user_turns, avg_per_session, per_session[]}`.)

Two things make this count meaningful:
- **What counts as a prompt** (`is_human_prompt`): Claude Code records *many* things as `type:user` entries — tool results (the bulk), harness-injected `meta` notices, sub-agent `sidechain` turns, slash-command wrappers, and local-command output. Only genuine typed human messages are counted; all that plumbing is excluded. (In one real session, 882 `user` entries → 726 tool results, and ~130 genuine prompts, not the ~156 a naïve "user entry with text" count would give.)
- **Which sessions count**: only those that **edited one of the commit's changed files** — the same anchor the code metrics use — so it is independent of the branch and correct even on a shared branch like `dev`.

### Tags applied to `customfield_10613`

Two tags, either or both:

- **`ai_Dev_back`** — code changes excluding unit tests (added lines in production / migration / other source).
- **`ai_test_back_dev`** — newly added unit tests and/or Postman requests (`tests.added > 0` or `postman.added_requests > 0`).

> **These are best-effort estimates, not ground truth.** Contribution is complete when sub-agent manifests exist (they record sub-agent-created files that are otherwise invisible). Retention is content-based: a line AI wrote and later reworked — by AI *or* by the developer — will not match the final and counts as *not preserved*; that churn is expected and is the usual reason retention is well below 100% even when contribution is 100%. Sub-agent files get retention **only if their first-pass snapshot was captured** (`<RUN_ID>/snapshots/*.diff`); a sub-agent file with no snapshot and no main-context/file-history content is contribution-only, retention-unknown — reported as a warning. **The developer review step (Task 6) is the source of truth: the numbers can always be corrected before posting.**

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

1. **Manifests** — `.claude/cache/ai-stats/<RUN_ID>/` (resolve `<RUN_ID>` per Argument Parsing). This dir carries the sub-agent authorship (`*.json` with a `files` list), the planning effort (`_planning.json`, `type: "planning"`), **and** the sub-agent first-pass **snapshots** (`snapshots/<phase>.diff`) used for retention. Pass the dir with `--manifests`; the analyzer reads all three. If it is missing (work not done via `/oc-be-implement`, or an older run), warn and continue — planning is reconstructed from the transcript, and sub-agent files fall back to contribution-only.
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
  --mode commit --commit HEAD          # or: --mode working
```

Every source flag except `--repo` is optional. Planning reconstruction and interactions are scoped to the sessions that edited **this commit's changed files** (derived from the diff — no `--branch` needed). It prints a JSON object with `work_type`, `planning`, `overall`, `by_category`, `provenance`, `artifacts`, `interactions`, `suggested_tags`, `sources`, and `warnings`. Percentages are rounded to the nearest 5% (`round(x/5)*5`, clamped 0–100). A percentage is `null` when its denominator is 0 — treat it as "unknown".

- `work_type` is `code`, `planning-dominant` (< 20 lines added but planning effort detected), or `minimal-change`.
- `planning` carries `detected`, `source` (`manifest`/`transcript`), `effort_band` (Low/Medium/High), `revision_rounds`, `analysis_tool_calls`, `plan_word_count`, `duration_minutes`, `assistant_turns`.
- `by_category[c].added` is the added **line count** per artifact category (production/migration/tests/postman/docs/other).
- `artifacts.tests` = `{files, methods_total, added, modified}` (unit-test methods, via `@Test` method-body diff of base-vs-final). `artifacts.postman` = `{files, requests_total, assertion_requests, setup_requests, added_requests, added_assertion_requests, test_cases_total, added_test_cases}` — `assertion_requests` are real-test requests; `setup_requests` are non-asserting setup/cleanup calls; `test_cases_total`/`added_test_cases` count the individual `pm.test(...)` tests inside them.
- `interactions` = `{sessions, total_user_turns, avg_per_session, per_session[]}` — developer↔AI turns on the branch.
- `provenance.reviewer_rework_pct` — share of AI lines from the post-review phase (see Metrics).
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

# ---- source 4: sub-agent first-pass snapshots (added lines captured at agent finish) ----
def collect_snapshot_lines(manifests_dir, repo):
    """AI first-pass added lines captured at each builder's finish, from
    <RUN_ID>/snapshots/*.diff (a `git diff HEAD -- <files>` per builder). These preserve
    the sub-agent's produced line content — otherwise lost when its session ends — so
    retention is measurable for sub-agent-created/modified files. Added lines only, so it
    is delta-correct for modified files (e.g. an existing Postman collection), not just new ones."""
    lines = {}
    if not manifests_dir: return lines
    snapdir = os.path.join(manifests_dir, "snapshots")
    if not os.path.isdir(snapdir): return lines
    for df in sorted(glob.glob(os.path.join(snapdir, "*.diff"))):
        cur = None
        try: fh = open(df, encoding="utf-8", errors="replace")
        except OSError: continue
        with fh:
            for line in fh:
                if line.startswith("+++ b/"):
                    cur = to_rel(line[6:].strip(), repo)
                elif line.startswith(("+++", "---", "diff ", "index ", "@@", "new file", "deleted", "rename", "similarity")):
                    continue
                elif line.startswith("+") and cur and not cur.startswith(".."):
                    n = norm(line[1:])
                    if n and not triv(n): lines.setdefault(cur, set()).add(n)
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
_PM_TEST = re.compile(r'pm\.test\s*\(|tests\s*\[[^\]]*\]\s*=')  # individual named tests (pm.test + legacy)
def _pm_requests(items):
    for it in items or []:
        if not isinstance(it, dict): continue
        if it.get("item") is not None:
            yield from _pm_requests(it.get("item"))
        elif it.get("request") is not None:
            yield it

def _pm_scripts(item):
    for ev in item.get("event", []) or []:
        if ev.get("listen") == "test":
            ex = (ev.get("script") or {}).get("exec") or []
            yield "\n".join(ex) if isinstance(ex, list) else str(ex)

def _pm_has_assertion(item):
    return any(_PM_ASSERT.search(s) for s in _pm_scripts(item))

def _pm_test_count(item):
    """Count individual test cases (pm.test / legacy tests[...] =) in a request's test scripts."""
    return sum(len(_PM_TEST.findall(s)) for s in _pm_scripts(item))

def postman_stats(repo, mode, ref, changed):
    files = [p for p in changed if category(p) == "postman"]
    total = assertion = added = added_assertion = 0
    test_cases = added_test_cases = 0
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
            tc = _pm_test_count(r)
            if has: assertion += 1
            test_cases += tc
            if r.get("name", "") not in base_names:
                added += 1
                added_test_cases += tc
                if has: added_assertion += 1
    return {"files": len(files), "requests_total": total, "assertion_requests": assertion,
            "setup_requests": total - assertion, "added_requests": added,
            "added_assertion_requests": added_assertion,
            "test_cases_total": test_cases, "added_test_cases": added_test_cases}

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

def is_human_prompt(o):
    """A genuine human message to the AI — one 'interaction'. Excludes the many other
    things Claude Code records as type=user: tool results (no text), harness-injected
    meta, sub-agent sidechain turns, slash-command wrappers, and local-command output."""
    if o.get("type") != "user" or o.get("isMeta") or o.get("isSidechain"): return False
    t = _user_text(o).strip()
    if not t: return False                                   # tool-result-only message
    if "<command-name>" in t or "<command-message>" in t: return False   # slash-command wrapper
    if "<local-command-stdout>" in t or "local-command-caveat" in t: return False  # command output/caveat
    return True

def session_relevant(events, repo, changed):
    """True if the session worked on THIS commit — i.e. it edited one of the commit's
    changed files with a main-context Write/Edit/MultiEdit. This ties planning/interactions
    to the measured work via the same anchor the code metrics use (the commit's files),
    not the branch. Empty `changed` => treat every session as relevant."""
    if not changed: return True
    for o in events:
        if o.get("type") != "assistant": continue
        for c in (o.get("message") or {}).get("content") or []:
            if (isinstance(c, dict) and c.get("type") == "tool_use"
                    and c.get("name") in ("Write", "Edit", "MultiEdit")):
                rel = to_rel((c.get("input") or {}).get("file_path") or "", repo)
                if rel and rel in changed: return True
    return False

def reconstruct_planning(transcripts, repo, changed):
    """Fallback when no planning manifest exists. Planning window = all activity before
    the first code-producing action (Write/Edit to a repo file, or an oc-be builder/generator
    sub-agent dispatch), across the sessions that worked on this commit's files."""
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
        if not session_relevant(events, repo, changed): continue
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
        # meaningless min..max span across many sessions.
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

def count_interactions(transcripts, repo, changed):
    """Developer↔AI interactions: genuine human prompts (is_human_prompt) in the sessions
    that worked on this commit's files (see session_relevant) — branch-independent."""
    if not transcripts: return None
    files = sorted(glob.glob(os.path.join(transcripts, "*.jsonl"))) if os.path.isdir(transcripts) else [transcripts]
    per = []
    for jf in files:
        events = []
        try:
            with open(jf, encoding="utf-8") as fh:
                for raw in fh:
                    try: events.append(json.loads(raw))
                    except (json.JSONDecodeError, ValueError): continue
        except OSError:
            continue
        if not session_relevant(events, repo, changed): continue
        turns = sum(1 for o in events if is_human_prompt(o))
        if turns:
            per.append({"session": os.path.splitext(os.path.basename(jf))[0][:8], "user_turns": turns})
    if not per: return None
    total = sum(p["user_turns"] for p in per)
    sessions = len(per)
    return {"sessions": sessions, "total_user_turns": total,
            "avg_per_session": round(total / sessions, 1),
            "per_session": sorted(per, key=lambda p: -p["user_turns"])}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--transcripts")
    ap.add_argument("--manifests")
    ap.add_argument("--file-history-root", dest="fh_root")
    ap.add_argument("--mode", choices=["commit", "working"], default="commit")
    ap.add_argument("--commit", default="HEAD")
    a = ap.parse_args()
    repo = os.path.abspath(a.repo)
    warnings = []

    manifest_files = collect_manifest_files(a.manifests, repo)
    main_lines     = collect_transcript_lines(a.transcripts, repo)
    fh_lines       = collect_file_history(a.transcripts, a.fh_root, repo)
    snap_lines     = collect_snapshot_lines(a.manifests, repo)
    if not manifest_files:
        warnings.append("No sub-agent manifests found — sub-agent-created files may be undercounted. "
                        "Run future work via /oc-be-implement for complete attribution.")

    added = added_lines_map(repo, a.mode, a.commit)
    total_added = sum(len(v) for v in added.values())
    changed = changed_paths(repo, a.mode, a.commit)   # this commit's files: the scope anchor
    changed_set = set(changed)

    planning = build_planning(load_planning_manifest(a.manifests),
                              reconstruct_planning(a.transcripts, repo, changed_set))
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
            elif ln in snap_lines.get(rel, ()):      agg[c]["agent"] += 1
            elif ln in fh_lines.get(rel, ()):        agg[c]["agent"] += 1
            else:                                    agg[c]["human"] += 1
        if rel in manifest_files and not main_lines.get(rel) and not fh_lines.get(rel) and not snap_lines.get(rel):
            no_retention_files.append(rel)  # counted for contribution, no content for retention

    # retention: suggested = union(main-context, file-history, sub-agent snapshot) lines per file; preserved = ∩ final
    # scoped to files that are part of the measured commit/working set
    ret = {c: {"suggested": 0, "preserved": 0} for c in cats}
    ai_files = (set(main_lines) | set(fh_lines) | set(snap_lines)) & set(added)
    for rel in ai_files:
        c = category(rel)
        suggested = set(main_lines.get(rel, set())) | set(fh_lines.get(rel, set())) | set(snap_lines.get(rel, set()))
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
    tests = java_test_stats(repo, a.mode, a.commit, changed)
    postman = postman_stats(repo, a.mode, a.commit, changed)

    interactions = count_interactions(a.transcripts, repo, changed_set)

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
                       "reviewer_rework_pct": round5(pct(tot_fix, tot_agent + tot_fix)) if (tot_agent + tot_fix) else None},
        "by_category": by_cat,
        "artifacts": {"tests": tests, "postman": postman},
        "interactions": interactions,
        "suggested_tags": suggested_tags,
        "sources": {"manifest_files": len(manifest_files), "snapshot_files": len(snap_lines),
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
  • Postman         2,600 lines   100%    —     (80 reqs added: 56 asserting / 124 test cases; 47 setup/cleanup)
  • docs/other          0 lines     —     —
  ────────────────────────────────────────────
  ALL             4,130 lines   100%   96%     (context only)

Provenance (all added lines):
  agent first-pass:   3,700
  post-review fixes:     430     → reviewer rework 10%
  hand-written (you):     0

Interactions: 130 prompts across 3 sessions (avg 43/session)

Suggested tags: ai_Dev_back, ai_test_back_dev

Headline → AI contribution: 100%   AI retention: 85%

Warnings:
  - <any warnings from the analyzer>
```

Pull the line counts from `by_category[c].added`; the test/postman detail from `artifacts.tests` (`added`, `modified`, `methods_total`) and `artifacts.postman` (`added_requests`, `added_assertion_requests`, `added_test_cases`, `setup_requests`); the engagement line from `interactions`.

**Postman retention is always reported** (never `—`) — but treat it as **low-confidence, developer-adjustable**. Two caveats to state and then have the developer correct: (a) it is only meaningful when the collection is **pretty-printed** (one field per line — see the TESTING guideline; a minified collection makes every "line" a whole-folder blob and the number meaningless); and (b) the metric compares the AI's *captured* lines (final snapshot) to the final file, so on a collection that was **rebuilt several times** the automated figure trends toward ~100% ("matches itself") and *understates* the churn. When the Postman work went through heavy iteration, the developer should set a lower retention that reflects how much of the early drafts survived (a rebuilt-from-scratch collection is often ~40–60%, not 100%). Always surface the computed value **and** invite the developer to adjust it, exactly like the production headline.

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

Writing to JIRA is outward-facing. **Show exactly what will be posted and set, and ask for confirmation before writing.** Present the comment body, the tag change (`customfield_10613` will include the tags in `[TAGS]`), the structured record written to the AI-usage field (`customfield_10745`), and the target ticket.

Include an artifact bullet only for categories that actually changed. Fill line counts from `by_category[c].added`, and the test/Postman counts from `artifacts`.

Comment body (**code** ticket):

```
AI usage (Claude Code) — measured on <last commit HEAD | uncommitted changes>:
- AI contribution: [CONTRIBUTION]% of the added production code originated from AI.
- AI retention: [RETENTION]% of the AI-suggested code was preserved (the remainder was superseded by AI's own iterative fixes).
- Reviewer rework: <rework>% (share of the AI-authored lines changed in the post-review phase).

Breakdown by artifact:
- Production code: <p_lines> lines — contribution <pc>%, retention <pr>%
- DB migration: <m_lines> lines — contribution <mc>%, retention <mr>%
- Unit tests: <t_lines> lines, <t_added> test(s) added / <t_mod> modified — contribution <tc>%, retention <tr>%
- Postman: <pm_lines> lines, <pm_add> request(s) added (<pm_add_assert> asserting / <pm_add_tc> test cases; <pm_setup> setup/cleanup) — contribution <pmc>%

Planning/analysis effort: [PLANNING-BAND]
- <rounds> plan iteration(s) with the developer
- <n> code/ticket lookups during planning
- ~<w>-word design plan
- ~<min> min in the planning phase

Developer↔AI interactions: <total> prompts across <sessions> session(s) (avg <avg>/session).
<if [USEFULNESS] given:>Developer-rated usefulness: [USEFULNESS]/5

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

### 6c. Record the structured metrics (AI-usage field)

Write the machine-readable record to the **"AI metrics"** custom field (**`customfield_10745`**) so a reporting tool can aggregate across tickets without parsing comments. It holds one JSON document per ticket. If the field errors (renamed/removed/not on this project) or the payload cannot fit, skip this step with a note — the comment and tags still post.

> **Field type.** `customfield_10745` is a **Text Field (multi-line)** (`...:textarea`) — enough capacity for the JSON (a single-line field's 255-char cap would be too small; if the field is ever the wrong type the write is skipped with a warning). On this Jira instance a multi-line text field can be **rich-text (ADF)**, which **rejects a raw string**; the write step below tries a plain string first and, on rejection, retries with the JSON wrapped in a minimal ADF `codeBlock` (the reporting tool recovers the JSON from that text node). The read step accepts either form.

1. **Identity** — call `atlassianUserInfo` for the developer's `accountId` **and display name**; the record is keyed `backend/<accountId>/<name>` (domain + user id + readable name all live in the key, not the record body).
2. **Build the lean `[RECORD]`** per the **AI-usage record schema (v1)** below — the compact keys, from the analyzer output plus the developer-confirmed values: `at` (`date -u +%Y-%m-%d`), `ver` (tool version from `plugin.json`), `scope` (`[COMMIT-REF]` short, or `working`), `work`, `contrib`/`retain` (the confirmed production headline), `rework`, `lines`, `cat` (per-category `{l: added lines, c: contribution%, r: retention%}` — **always include `r`, including for Postman** (the developer-confirmed, possibly-adjusted value)), the test counts, the planning fields, `turns`/`sessions`, `useful` (`[USEFULNESS]` or `null`), `adj` (`true` if the developer changed any number). Keep the **rich detail (per-category %, planning notes) in the comment, not the field**.
3. **Read-merge-upsert** (latest-only, keyed by `backend/<accountId>/<name>`):
   - `getJiraIssue` with `fields: ["customfield_10745"]`. The value may be a **plain string** (plain-renderer field) or an **ADF document** (rich-text field). If it is ADF, recover the JSON from the first `codeBlock`/`paragraph` text node. Parse it; if empty or unparseable, start from `{ "schema": "opencell.ai-usage/v1", "records": {} }`.
   - **First delete any existing key that starts with `backend/<accountId>/`** (same developer under an old display name), then set `records["backend/<accountId>/<name>"] = [RECORD]`. Matching the id-prefix — not the full key — keeps it latest-only even if the developer's display name changed between runs (no duplicate record). Every other key stays intact (other developers, and the `frontend/<accountId>/<name>` records the future `/oc-fe-calculate-ai-use` writes).
   - Read immediately before writing to minimise the (rare) two-writers race; last write wins.
4. **Size guard** — if the resulting document exceeds ~3900 chars (the field caps at 4000), drop the record with the oldest `at` until it fits, and warn the developer (the comment keeps the full history). This is a rare safety net — latest-only keying caps growth at one record per domain×developer (~10 fit).
5. **Write** — `editJiraIssue` with the compact JSON of the whole document, **renderer-agnostic**:
   - **Attempt 1 (plain):** `{ "fields": { "customfield_10745": "<compact JSON>" } }`.
   - **Attempt 2 (rich-text fallback):** if attempt 1 is rejected because the field is rich-text/ADF, retry with the JSON wrapped in a minimal ADF code block:
     ```json
     { "fields": { "customfield_10745": { "type": "doc", "version": 1,
       "content": [ { "type": "codeBlock",
         "content": [ { "type": "text", "text": "<compact JSON>" } ] } ] } } }
     ```
   - If both attempts fail, or the value is rejected for length (single-line 255-char field), **skip with a warning** recommending the field be recreated as a multi-line Text Field — the comment and tags still post.

### 6d. Confirm

```
Posted to [TICKET-NUMBER]:
  ✓ Comment added (contribution [CONTRIBUTION]% · retention [RETENTION]% · planning [PLANNING-BAND])
  ✓ Tagged [TAGS] on customfield_10613   (or: already present — no change)
  ✓ Recorded backend/<user> in customfield_10745   (or: field not configured — skipped)
```

If the developer declines, print the comment body, the intended tag change, and the record JSON so they can apply them manually, and stop without writing.

---

## AI-usage record schema (v1)

The "AI metrics" field (`customfield_10745`) is a **4000-character** text field, so the payload is deliberately **lean** — reporting-essential scalars with compact keys. Per-category metrics use a small map (`{l,c,r}`) with keys omitted when not measurable; the prose breakdown and planning notes live in the **human comment**, so the field and the comment are *not* duplicates. Each record ≈ **430 chars** (including the `domain/accountId/name` key), so **~9 records fit** — enough for backend + frontend × several developers on one ticket.

The field holds one JSON document per ticket: an envelope with a `records` **map keyed by `"<domain>/<accountId>/<name>"`**. The key encodes domain + user id + readable display name, so the record body does **not** repeat them. The **accountId is the stable identity** (upsert matches on the `"<domain>/<accountId>/"` prefix, so a changed display name never creates a duplicate); the name is there purely so the raw JSON is human-readable. Backend and the future frontend command emit the **identical** record shape under `"backend/…"` vs `"frontend/…"` keys, so a reporting tool reads one field per ticket and flattens `records` into rows (split the key: `parts[0]` = domain, `parts[1]` = accountId, `parts[2:]` = name).

```json
{
  "schema": "opencell.ai-usage/v1",
  "records": {
    "backend/5dbb097eb6788b0c37755176/Andrius Karpavičius": {
      "at": "2026-07-28", "ver": "1.7.0", "scope": "6529c39", "work": "code",
      "contrib": 100, "retain": 95, "rework": 20, "lines": 1534,
      "cat": { "prod": {"l":676,"c":100,"r":95}, "mig": {"l":83,"c":100,"r":100}, "test": {"l":397,"c":100,"r":95}, "pm": {"l":378,"c":100,"r":50} },
      "utAdd": 17, "utMod": 11, "pmAdd": 80, "pmAssert": 56, "pmTests": 79,
      "plan": "High", "planRounds": 1, "planWords": 520, "planMin": 150,
      "turns": 148, "sessions": 3,
      "useful": 4, "adj": true
    }
  }
}
```

Key legend (all per (domain,user), latest run only):

| Key | Meaning | Key | Meaning |
|-----|---------|-----|---------|
| `at` | measured date (YYYY-MM-DD) | `cat` | per category (`prod`/`mig`/`test`/`pm`): `{l: added lines, c: contribution%, r: retention%}` — `r` is **always present, including for Postman** (developer-confirmed; low-confidence for Postman, see the retention note in Task 5) |
| `ver` | tool version | `utAdd`/`utMod` | unit tests added / modified |
| `scope` | commit ref (or `working`) | `pmAdd`/`pmAssert`/`pmTests` | Postman requests added / of which asserting / test cases added |
| `work` | `code`/`planning-dominant`/`minimal-change` | `plan` | planning effort band |
| `contrib` | AI contribution % (production headline) | `planRounds`/`planWords`/`planMin` | plan iterations / words / minutes |
| `retain` | AI retention % | `turns`/`sessions` | genuine human prompts / sessions that worked on the commit |
| `rework` | reviewer-rework % | `useful` | 1–5 rating (or `null`) |
| `lines` | total added lines | `adj` | developer adjusted the numbers? |

- **`domain` + user id + name come from the map key** `"<domain>/<accountId>/<name>"` — that is what lets multiple developers and both domains coexist on one ticket; the reporting tool splits the key (accountId is the stable id, name is for readability).
- **Latest-only**: re-running replaces that key's record (new `at`); no history.
- **Nulls** allowed where unknown. Percentages are the developer-confirmed, 5%-rounded values.
- **Size guard**: after upsert, if the document would exceed ~3900 chars, warn the developer and drop the **oldest** record (smallest `at`) to stay under 4000; the per-run comment remains the full audit trail. (Latest-only keying already caps growth at one record per domain×developer — ~9 fit — so this is a rare safety net.)
- Bump `schema` (`opencell.ai-usage/v2`, …) only for breaking shape changes. If a ticket ever needs more than ~9 records, switch to single-character keys to shrink each record further.

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
- **Contribution vs. retention.** Contribution is complete with manifests; retention is content-based and defined for files whose line content was captured — the sub-agent first-pass **snapshot** (`snapshots/*.diff`), the main-context transcript, or file-history. A sub-agent file with none of these (e.g. an old run created before snapshots existed) is counted for contribution and reported as retention-unknown.
- **Attribution.** A final line is `fix` if it appears in a main-context edit, else `agent` if the file is in a manifest or the line is in file-history, else `human`. Whitespace-normalized, pure-punctuation lines ignored, distinct-line based per file (heavy rewrites de-duplicated).
- **Squashed / cross-branch commits.** When many sessions/branches are squashed into one commit, file-history alone under-covers it; manifests restore coverage for the parts built via `/oc-be-implement`.
- **Artifact counts are commit-derived, not AI-attributed.** Unit-test add/modify counts come from a heuristic `@Test` method-body diff (base vs final); overloaded names and unusual formatting can be miscounted slightly. Postman assertion detection keys off `test`-event scripts; a request whose assertions live elsewhere (or a pure `console.log` test script) may be misclassified. `added_*` compares request **names** against the base collection, so a renamed request reads as added. Good enough for the ticket record; the developer can correct.
- **Tag semantics.** `ai_test_back_dev` triggers on newly *added* tests/Postman requests (not modifications). A commit that only edits existing tests gets `ai_Dev_back` (if it also touches code) but not `ai_test_back_dev` — adjust in review if that is not what you want.
- **AI-usage field (reporting).** The canonical machine-readable store is the JSON document in the **"AI metrics"** field (`customfield_10745`; payload schema `opencell.ai-usage/v1`), keyed by `domain/accountId/name` (accountId is the stable identity, name is for readability) so backend, frontend and multiple developers coexist on one ticket; the comment is only for humans. It is latest-only (no history) and uses read-merge-upsert. **The field must be a multi-line Text Field** (a single-line field's 255-char cap is too small) and may be **rich-text (ADF)** on this instance — the write is renderer-agnostic (plain string, then an ADF `codeBlock` fallback) and the read accepts either. If two developers write the same ticket within the same moment, last-write-wins could drop one record; the per-run comment is the audit fallback.
- **Planning effort is effort, not a percentage.** The requirements-gathering and architecture-plan work produces no committed artifact, so it can only be quantified as activity (rounds, lookups, plan size, time) rolled into a Low/Medium/High band. The band thresholds are seed values in `planning_band()` — tune them against your real runs. Reconstruction from the transcript is a fallback; the `/oc-be-implement` planning manifest is authoritative for revision rounds and plan size.
- Always defer to the developer's adjusted numbers — the automatic figures are a starting point, not an audit.
```
