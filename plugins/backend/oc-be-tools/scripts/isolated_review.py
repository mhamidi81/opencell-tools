#!/usr/bin/env python3
"""Isolated, reproducible backend review for /oc-be-review.

Why: a review run inside the developer's session sees the conversation that produced the code and the
developer's personal memory, and an unconstrained reviewer builds its own checklist every time, so the
developer, a re-run and the dev lead get different reports. This runner removes the variable inputs:

- prepare  freezes the input into a bundle: the diff (uncommitted changes incl. new source files, a
           commit range, or a PR diff), the ticket's acceptance items split *by script* into a numbered
           list, the agreed scope, the guideline rule catalogue, and the results of deterministic
           mechanical checks (javax, var, AGPL header, Liquibase current/rebuild pairing, ...).
- run      starts headless `claude -p` reviews in parallel, each in a fresh process with no conversation,
           no user CLAUDE.md, no auto-memory, no personal settings and no plugin hooks, pinned to one
           model and effort, reading only the bundle (+ the repository, read-only tools), and answering
           in a JSON schema that requires a status for every rule and every acceptance item.
- verdict  computes the score and APPROVE / CHANGES_REQUESTED from those statuses with fixed rules
           (the model never picks the verdict), writes report.md/report.json, and records the reviewed
           code state in a ledger that the commit hold and /oc-be-calculate-ai-use check.

Reports are never reused: every review is a fresh run. The ledger only remembers *that* a code state
was reviewed and with which verdict.
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL, EFFORT = "opus", "high"
SOURCE_EXT = (".java", ".xml", ".properties", ".sql", ".xhtml", ".jrxml", ".postman_collection.json",
              ".postman_environment.json", ".json", ".yaml", ".yml")
SKIP_UNTRACKED = (".claude/", "docs/", "target/", ".idea/", ".settings/")

# ---- guideline rule catalogue (from oc-be-pr-reviewer's criteria; severity decides the verdict) ----
RULES = [
    ("CR-LICENSE", "critical", "New Java files carry the AGPL license header"),
    ("CR-JAKARTA", "critical", "jakarta.* packages, never javax.* for Jakarta EE APIs"),
    ("CR-NO-VAR", "critical", "No `var`; explicit types everywhere"),
    ("CR-JAVADOC", "major", "Every method has Javadoc"),
    ("CR-SWAGGER", "major", "REST endpoints and DTOs carry Swagger annotations"),
    ("ENT-BASE", "major", "Entity extends the correct base class (EnableBusinessCFEntity, AuditableCFEntity, BaseEntity)"),
    ("ENT-NAMING", "minor", "Table and sequence naming conventions"),
    ("ENT-TYPES", "major", "Correct field types (@JdbcTypeCode for JSON, @Convert for boolean, @Enumerated for enums)"),
    ("ENT-ANNOTATIONS", "major", "Proper JPA annotations (@Entity, @Table, @Column)"),
    ("ENT-NO-REDECLARE", "major", "No redeclared inherited fields/accessors/constants; inherited column changes via @AttributeOverride"),
    ("ENT-LAZY", "major", "Lazy fetching for relationships"),
    ("ENT-CASCADE", "major", "No CascadeType.ALL"),
    ("ENT-EMBEDDED", "minor", "@Embedded column names match the embeddable"),
    ("SVC-BASE", "major", "Service extends the correct base (BusinessService or PersistenceService)"),
    ("SVC-EXCEPTIONS", "major", "Services throw BusinessException/ValidationException, not API exceptions"),
    ("SVC-MESSAGE-CONTEXT", "minor", "Exception messages include the entity code/id"),
    ("SVC-VALIDATION-PLACE", "minor", "Validation methods live in the right service"),
    ("SVC-LOGIC", "critical", "Business rules implemented correctly; no logic errors"),
    ("SVC-UPDATE-RETURN", "minor", "Service methods calling update() return the updated entity"),
    ("API-SCOPES", "major", "REST resources @RequestScoped; API services @Stateless extending BaseCrudApi"),
    ("API-SPEC", "critical", "REST endpoints match the specification (URLs, parameters, action names)"),
    ("API-STATUS-CODES", "major", "Proper HTTP status codes (201, 200, 204, 400, 404)"),
    ("API-DTO-SHAPE", "major", "DTOs immutable (@Value.Immutable extending Resource / ResourceWithId); id-only references typed ResourceWithId"),
    ("API-DTO-WRAPPERS", "minor", "DTOs use wrapper types (Boolean, Integer, Long)"),
    ("API-DTO-FIELDS", "major", "DTOs expose all entity fields"),
    ("API-DTO-NO-REDECLARE", "major", "No redeclared inherited getters in DTOs (getId, getLinks, getCode, getNewCode, getType)"),
    ("API-FROMDTO-NULLS", "major", "fromDto() distinguishes null from empty string"),
    ("API-STATUS-FIELD", "major", "Status not accepted in create/update; disabled not accepted in update"),
    ("API-NO-TRY-CATCH", "minor", "No try-catch in REST resource methods (ExceptionMappers handle errors)"),
    ("API-REGISTRATION", "major", "V2 REST resources registered in JaxRsActivatorApiV0123"),
    ("DB-CHANGESET-ID", "minor", "Liquibase changesets carry the ticket number and date"),
    ("DB-CURRENT-REBUILD", "critical", "Changes in both current/structure.xml and rebuild/structure.xml"),
    ("DB-TYPES", "major", "Proper column types (${type.boolean}, ${type.json}, numeric(23,12))"),
    ("DB-PK-NAMING", "minor", "Primary key named <table>_pkey"),
    ("DB-NO-FK-MASSIVE", "major", "No foreign keys to massive/partitioned tables"),
    ("DB-MULTITENANCY", "major", "${db.schema.adapted} in XML, {h-schema} in native queries"),
    ("DB-LOWER-INDEX", "minor", "Lowercase indexes for case-insensitive search"),
    ("CQ-WIDTH", "minor", "Formatted to 220 characters"),
    ("CQ-BRACES", "minor", "Curly braces for single-line if statements"),
    ("CQ-RESOURCES", "major", "try-with-resources for resource management"),
    ("CQ-CATCH", "major", "Specific exception types; original exception preserved when wrapping; no empty catch; no log-and-throw"),
    ("CQ-EMPTY-COLLECTIONS", "minor", "Return empty collections instead of null"),
    ("CQ-NULL-SAFE-EQUALS", "minor", "Null-safe string comparison (\"literal\".equals(variable))"),
    ("CQ-DEPENDENCIES", "minor", "Existing libraries checked before adding dependencies"),
    ("TST-PRESENT", "major", "Unit tests for the main scenarios and edge cases of the changed logic"),
    ("TST-QUALITY", "minor", "Meaningful data; class under test not mocked; doReturn().when() for spies; validation methods not mocked"),
    ("TST-SERVICE-API", "minor", "EntityManager mocked for service CRUD tests; ArgumentCaptor in API tests"),
    ("TST-EXCEPTION-MESSAGES", "minor", "Exception tests verify the message context"),
    ("TST-POSTMAN", "major", "Postman coverage for API changes (iteration_nr codes, no {{$timestamp}}, negative tests named ' - fail')"),
]
SEVERITY = {rid: sev for rid, sev, _ in RULES}
PENALTY = {"critical": 3.0, "major": 1.0, "minor": 0.5}


# ------------------------------------------------------------------ helpers
def plugin_version():
    with open(os.path.join(PLUGIN_ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        return json.load(fh)["version"]


def git(repo, *args, check=False):
    res = subprocess.run(["git", "-C", repo, *args], capture_output=True, timeout=120)
    if check and res.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {res.stderr.decode('utf-8', 'replace')}")
    return res.stdout.decode("utf-8", "replace") if res.returncode == 0 else ""


def git_bytes(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, timeout=120).stdout


def repo_slug(top):
    return re.sub(r"[^A-Za-z0-9]", "-", top)


def ledger_path(top):
    return os.path.join(os.path.expanduser("~"), ".claude", "oc-be-tools", "reviews", repo_slug(top) + ".json")


def load_ledger(top):
    try:
        with open(ledger_path(top), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"reviews": []}


def save_ledger(top, data):
    os.makedirs(os.path.dirname(ledger_path(top)), exist_ok=True)
    data["reviews"] = data["reviews"][-100:]
    with open(ledger_path(top), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def patch_id(diff_bytes):
    if not diff_bytes.strip():
        return ""
    out = subprocess.run(["git", "patch-id", "--stable"], input=diff_bytes, capture_output=True).stdout.split()
    return out[0].decode() if out else hashlib.sha1(diff_bytes).hexdigest()


def untracked_sources(top):
    files = git(top, "ls-files", "--others", "--exclude-standard").splitlines()
    return [f for f in files if f.endswith(SOURCE_EXT) and not f.startswith(SKIP_UNTRACKED)
            and not f.endswith((".factorypath", ".classpath", ".project"))]


def new_file_diff(top, rel):
    """A unified 'new file' diff built in Python: no git call per file, and the index is never touched."""
    with open(os.path.join(top, rel), "rb") as fh:
        data = fh.read()
    lines = data.decode("utf-8", "replace").splitlines()
    body = "".join(f"+{l}\n" for l in lines)
    return (f"diff --git a/{rel} b/{rel}\nnew file mode 100644\n--- /dev/null\n+++ b/{rel}\n"
            f"@@ -0,0 +1,{len(lines)} @@\n{body}").encode("utf-8")


def working_diff(top):
    """The uncommitted change set Mode LOCAL reviews: tracked changes vs HEAD + new untracked source files."""
    diff = git_bytes(top, "diff", "HEAD", "--no-color", "--no-ext-diff")
    for rel in sorted(untracked_sources(top)):
        diff += new_file_diff(top, rel)
    return diff


def code_state(top):
    """(head, patch-id of the uncommitted change set): what the commit hold and the ledger compare."""
    return git(top, "rev-parse", "HEAD").strip(), patch_id(working_diff(top))


def commit_state(top, ref):
    """The state that, reviewed before committing, became commit `ref`: (parent, patch-id of parent..ref)."""
    sha = git(top, "rev-parse", ref).strip()
    parent = git(top, "rev-parse", f"{sha}^").strip()
    return sha, parent, patch_id(git_bytes(top, "diff", f"{parent}..{sha}", "--no-color", "--no-ext-diff"))


def find_review(top, head, pid):
    for r in reversed(load_ledger(top)["reviews"]):
        if r.get("head") == head and r.get("patch_id") == pid:
            return r
    return None


# ------------------------------------------------------------------ ticket -> numbered acceptance items
def adf_text(node, depth=0):
    """Atlassian Document Format -> plain text with '- ' bullets and '#' headings (deterministic)."""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    t, kids = node.get("type"), node.get("content") or []
    if t == "text":
        return node.get("text", "")
    if t == "hardBreak":
        return "\n"
    inner = "".join(adf_text(k, depth + 1) for k in kids)
    if t == "heading":
        return "\n# " + inner.strip() + "\n"
    if t == "listItem":
        return "\n- " + " ".join(inner.split()) + "\n"
    if t in ("paragraph", "codeBlock", "blockquote", "tableRow", "panel"):
        return "\n" + inner.strip() + "\n"
    if t == "tableCell" or t == "tableHeader":
        return inner.strip() + " | "
    return inner


def field_text(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        return adf_text(value)
    if isinstance(value, list):
        return "\n".join(field_text(v) for v in value)
    return str(value)


def clean_lines(text):
    return [re.sub(r"\s+", " ", l).strip() for l in text.replace("\r", "").split("\n") if l.strip()]


def table_rows(node):
    """Data rows of every ADF table in a field (header rows skipped), cells joined with ' | '."""
    rows = []
    if isinstance(node, dict):
        if node.get("type") == "tableRow":
            cells = node.get("content") or []
            if cells and not all(c.get("type") == "tableHeader" for c in cells):
                text = " | ".join(" ".join(adf_text(c).split()).rstrip(" |") for c in cells)
                if text.strip(" |"):
                    rows.append(text)
            return rows
        for child in node.get("content") or []:
            rows += table_rows(child)
    return rows


def split_scenarios(text):
    """Gherkin: one item per Scenario / Scenario Outline block."""
    items, current = [], None
    for line in clean_lines(text):
        bare = re.sub(r"^[*#>\-\s]+|[*_]+", "", line).strip()
        if re.match(r"(?i)^scenario( outline)?\b", bare):
            if current:
                items.append(" ".join(current))
            current = [bare]
        elif current is not None:
            current.append(bare)
    if current:
        items.append(" ".join(current))
    return items


def split_points(text):
    """Bullets/numbered lines when present, otherwise paragraphs of 5+ words; headings skipped."""
    lines = clean_lines(text)
    bullets = [re.sub(r"^([-*•]|\d+[.)])\s+", "", l) for l in lines if re.match(r"^([-*•]|\d+[.)])\s+", l)]
    if bullets:
        return bullets
    return [l for l in lines if not l.startswith("#") and len(l.split()) >= 5]


def extract_items(ticket, scopes):
    """Numbered acceptance criteria (C#) and scenarios (S#) from the ticket fields and the agreed scope."""
    f = ticket.get("fields", ticket)
    criteria, scenarios = [], []

    def add(lst, prefix, text, source):
        text = text.strip()
        if text and text not in [i["text"] for i in lst]:
            lst.append({"id": f"{prefix}{len(lst) + 1}", "text": text, "source": source})

    # Scenarios: test-case table rows, else Gherkin blocks, else bullets. Dataset bullets beside a table
    # are test data (context in ticket.md), never items.
    acceptance = f.get("customfield_10136")
    for text in (table_rows(acceptance) if isinstance(acceptance, dict) else []) \
            or split_scenarios(field_text(acceptance)) or split_points(field_text(acceptance)):
        add(scenarios, "S", text, "Jira Acceptance")
    # Criteria: the Functional design (behaviour); the Requirement (story, context, scope) only when it is empty.
    for key, label in (("customfield_10135", "Jira Functional design"), ("customfield_10134", "Jira Requirement")):
        for text in split_points(field_text(f.get(key))):
            add(criteria, "C", text, label)
        if criteria:
            break
    description = field_text(f.get("description"))
    if description.strip():
        m = re.search(r"(?is)expected[^\n]*\n(.*?)(\n#|\Z)", description)
        points = split_points(m.group(1)) if m else []
        for text in points:
            add(criteria, "C", text, "Jira description (expected)")
    for scope in scopes:
        for text in scope.get("acceptance") or []:
            add(criteria, "C", text, f"agreed scope ({scope.get('run_id', '')})")
        for kind, value in (scope.get("deliverables") or {}).items():
            if isinstance(value, str) and value.lower().startswith("required"):
                add(scenarios, "S", f"{kind.replace('_', ' ')}: {value}", f"agreed scope ({scope.get('run_id', '')})")
    if not criteria and not scenarios:
        add(criteria, "C", f"The ticket's goal is met: {f.get('summary', '')}", "Jira summary (no structured criteria)")
    return criteria, scenarios


# ------------------------------------------------------------------ deterministic mechanical checks
JAVAX_EE = re.compile(r"^\+\s*import\s+(static\s+)?javax\.(inject|ws\.rs|ejb|persistence|enterprise|validation|"
                      r"transaction|servlet|faces|json|xml\.bind|annotation\.(PostConstruct|PreDestroy|Resource|Priority))\b")
VAR_DECL = re.compile(r"^\+(?!\s*(//|\*|/\*)).*?(?<![\w.])var\s+[a-zA-Z_]\w*\s*(=|:)")
EXISTENCE_ONLY = re.compile(r"\.to\.(not\.be\.undefined|exist)\b")
STRING_LITERAL = re.compile(r'"(?:\\.|[^"\\])*"')
METHOD_DECL = re.compile(r"^\+\s*(public|protected|private)\s+(static\s+|final\s+|abstract\s+|synchronized\s+|default\s+)*"
                         r"[\w<>\[\],.? ]+\s+\w+\s*\([^;]*$")


def parse_diff(diff_text):
    """Per file: {file, new, added: [(line_no, '+text')], side: [(line_no, text, is_added)]} — `side` is the
    visible new-side content (added + context lines), so a check can look at what precedes an added line."""
    files, cur = [], None
    new_no = 0
    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            cur = {"file": raw.split(" b/", 1)[-1], "new": False, "added": [], "side": []}
            files.append(cur)
        elif cur is None:
            continue
        elif raw.startswith("new file mode"):
            cur["new"] = True
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            new_no = int(m.group(1)) if m else 0
            cur["side"].append((new_no, "@@", False))     # hunk break: look-back stops here
        elif raw.startswith("+++") or raw.startswith("---"):
            continue
        elif raw.startswith("+"):
            cur["added"].append((new_no, raw))
            cur["side"].append((new_no, raw[1:], True))
            new_no += 1
        elif raw.startswith(" "):
            cur["side"].append((new_no, raw[1:], False))
            new_no += 1
    return files


def has_javadoc(side, index):
    """True if the lines before side[index] (skipping annotations and blanks) end a /** ... */ block.
    Unknown (hunk starts right above) counts as documented: never report what the diff does not show."""
    i = index - 1
    while i >= 0:
        text = side[i][1].strip()
        if side[i][1] == "@@":
            return True
        if not text or text.startswith("@"):
            i -= 1
            continue
        return text.endswith("*/")
    return True


def mechanical_checks(diff_text):
    findings = []

    def hit(rule, file, line, problem):
        findings.append({"rule": rule, "file": file, "line": line, "problem": problem})

    files = parse_diff(diff_text)
    for f in files:
        name = f["file"]
        if name.endswith(".java"):
            if f["new"] and "/src/main/" in name:
                head = "\n".join(t for _, t in f["added"][:40])
                if "GNU Affero" not in head and "AGPL" not in head:
                    hit("CR-LICENSE", name, 1, "New Java file without the AGPL license header")
            for line_no, text in f["added"]:
                if JAVAX_EE.match(text):
                    hit("CR-JAKARTA", name, line_no, "javax import of a Jakarta EE API: " + text[1:].strip())
                if VAR_DECL.match(STRING_LITERAL.sub('""', text)):
                    hit("CR-NO-VAR", name, line_no, "`var` declaration: " + text[1:].strip()[:120])
            if "/src/main/" in name:
                for idx, (line_no, text, added) in enumerate(f["side"]):
                    if (added and METHOD_DECL.match("+" + text) and " class " not in text
                            and "=" not in text.split("(")[0] and not has_javadoc(f["side"], idx)):
                        hit("CR-JAVADOC", name, line_no, "Method added without a Javadoc block: " + text.strip()[:120])
    changed = {f["file"] for f in files}
    for f in files:
        name = f["file"]
        if name.endswith("/current/structure.xml") and f["added"]:
            twin = name.replace("/current/structure.xml", "/rebuild/structure.xml")
            if twin not in changed:
                hit("DB-CURRENT-REBUILD", name, f["added"][0][0], f"Changed without {twin}")
        if name.endswith("/rebuild/structure.xml") and f["added"]:
            twin = name.replace("/rebuild/structure.xml", "/current/structure.xml")
            if twin not in changed:
                hit("DB-CURRENT-REBUILD", name, f["added"][0][0], f"Changed without {twin}")
        if name.endswith(".postman_collection.json"):
            for line_no, text in f["added"]:
                if "{{$timestamp}}" in text:
                    hit("TST-POSTMAN", name, line_no, "{{$timestamp}} used for a code (use the iteration_nr sequence)")
                m = EXISTENCE_ONLY.search(text)
                if m:
                    hit("TST-POSTMAN", name, line_no, f"Existence-only assertion `{m.group(0)}`; POSTMAN_TESTING.md: never use "
                        ".to.not.be.undefined / .to.exist, assert the exact value or a concrete shape")
    return findings


# ------------------------------------------------------------------ prepare
JIRA_SITE = "https://opencellsoft.atlassian.net"
JIRA_FIELDS = "summary,description,comment,customfield_10134,customfield_10135,customfield_10136,customfield_10137"


def fetch_jira(key, path):
    """The ticket's requirement fields over Jira REST (JIRA_EMAIL + JIRA_API_TOKEN, as the report plugins use)."""
    import base64
    import urllib.request
    email, token = os.environ.get("JIRA_EMAIL"), os.environ.get("JIRA_API_TOKEN")
    if not email or not token:
        sys.exit("--fetch-jira needs JIRA_EMAIL and JIRA_API_TOKEN; otherwise pass the getJiraIssue result with --ticket-json")
    req = urllib.request.Request(f"{JIRA_SITE}/rest/api/3/issue/{key}?fields={JIRA_FIELDS}", headers={
        "Accept": "application/json",
        "Authorization": "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()})
    with urllib.request.urlopen(req, timeout=60) as res:
        data = json.load(res)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return path


def cmd_prepare(a):
    top = git(a.repo, "rev-parse", "--show-toplevel", check=True).strip()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = a.out or os.path.join(os.path.expanduser("~"), ".claude", "oc-be-tools", "reviews", repo_slug(top),
                                f"{a.ticket or 'NOTICKET'}-{stamp}")
    os.makedirs(out, exist_ok=True)

    head, state_pid = None, None
    if a.diff_file:
        with open(a.diff_file, "rb") as fh:
            diff = fh.read()
        scope_label = f"provided diff ({os.path.basename(a.diff_file)})"
    elif a.range:
        diff = git_bytes(top, "diff", a.range, "--no-color", "--no-ext-diff")
        scope_label = f"commit range {a.range}"
        head = git(top, "rev-parse", a.range.split("..")[-1] or "HEAD").strip()
        state_pid = ""                                            # recorded as "reviewed at commit <tip>"
    else:
        diff = working_diff(top)
        head, state_pid = git(top, "rev-parse", "HEAD").strip(), patch_id(diff)
        scope_label = "uncommitted changes (tracked changes vs HEAD + new untracked source files)"
    if not diff.strip():
        sys.exit("Nothing to review: the diff is empty.")
    with open(os.path.join(out, "diff.patch"), "wb") as fh:
        fh.write(diff)
    diff_text = diff.decode("utf-8", "replace")
    files = [f["file"] for f in parse_diff(diff_text)]
    with open(os.path.join(out, "files.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(files) + "\n")

    ticket = {}
    if a.fetch_jira:
        a.ticket_json = fetch_jira(a.ticket, os.path.join(out, "ticket.json"))
    if a.ticket_json and os.path.isfile(a.ticket_json):
        with open(a.ticket_json, encoding="utf-8") as fh:
            ticket = json.load(fh)
        nodes = (ticket.get("issues") or {}).get("nodes") if isinstance(ticket.get("issues"), dict) else None
        if nodes:
            ticket = nodes[0]                         # Atlassian MCP getJiraIssue wraps the issue
    scopes = []
    for p in sorted(glob.glob(os.path.join(top, ".claude", "cache", "ai-stats", f"{a.ticket}-*", "_planning.json"))):
        try:
            with open(p, encoding="utf-8") as fh:
                scopes.append(json.load(fh))
        except (OSError, ValueError):
            pass
    criteria, scenarios = extract_items(ticket, scopes)
    f = ticket.get("fields", ticket)
    context = [f"# {a.ticket}: {f.get('summary', '')}"]
    for key, label in (("description", "Description"), ("customfield_10134", "Requirement"),
                       ("customfield_10135", "Functional design"), ("customfield_10136", "Acceptance"),
                       ("customfield_10137", "Technical design")):
        text = field_text(f.get(key)).strip()
        if text:
            context.append(f"\n## {label}\n{text}")
    comments = (f.get("comment") or {}).get("comments", []) if isinstance(f.get("comment"), dict) else []
    for c in comments:
        context.append(f"\n## Comment by {(c.get('author') or {}).get('displayName', '?')} ({c.get('created', '')[:10]})\n"
                       + field_text(c.get("body")).strip())
    for s in scopes:
        context.append(f"\n## Agreed scope ({s.get('run_id', '')})\n{s.get('plan_text', '')}")
    with open(os.path.join(out, "ticket.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(context) + "\n")

    mech = mechanical_checks(diff_text)
    bundle = {
        "ticket": a.ticket, "scope": scope_label, "files": files,
        "criteria": criteria, "scenarios": scenarios,
        "rules": [{"id": r, "severity": s, "rule": t} for r, s, t in RULES],
        "mechanical": mech,
        "plugin_version": plugin_version(),
        "model": MODEL, "effort": EFFORT,
        "repo": top, "head": head, "state_patch_id": state_pid,
        "judge_on": "diff" if a.diff_file else "repository",
    }
    digest = hashlib.sha256(diff + json.dumps({k: bundle[k] for k in ("criteria", "scenarios", "rules", "plugin_version",
                                                                      "model", "effort")}, sort_keys=True).encode()).hexdigest()
    bundle["input_hash"] = digest[:16]
    with open(os.path.join(out, "bundle.json"), "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2)
    print(json.dumps({"bundle": out.replace("\\", "/"), "files": len(files), "criteria": len(criteria),
                      "scenarios": len(scenarios), "mechanical_findings": len(mech), "input_hash": bundle["input_hash"]}))


# ------------------------------------------------------------------ run
GUIDELINE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "rules", "suggestions"],
    "properties": {
        "summary": {"type": "string"},
        "rules": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "status", "findings"],
            "properties": {
                "id": {"type": "string", "enum": [r for r, _, _ in RULES]},
                "status": {"type": "string", "enum": ["PASS", "FAIL", "NA"]},
                "findings": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["file", "line", "problem", "fix"],
                    "properties": {"file": {"type": "string"}, "line": {"type": "integer"},
                                   "problem": {"type": "string"}, "fix": {"type": "string"}}}}}}},
        "suggestions": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["file", "line", "text"],
            "properties": {"file": {"type": "string"}, "line": {"type": "integer"}, "text": {"type": "string"}}}},
    },
}


def conformance_schema(kind):
    status = ["PRESENT", "PARTIAL", "ABSENT", "NA_FRONTEND"] if kind == "criteria" else \
             ["COVERED", "PARTIAL", "NOT_COVERED", "NA_FRONTEND"]
    return {
        "type": "object", "additionalProperties": False, "required": ["items"],
        "properties": {"items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["id", "status", "evidence", "note"],
            "properties": {"id": {"type": "string"}, "status": {"type": "string", "enum": status},
                           "evidence": {"type": "string"}, "note": {"type": "string"}}}}},
    }


def agent_body(name):
    with open(os.path.join(PLUGIN_ROOT, "agents", name + ".md"), encoding="utf-8") as fh:
        text = fh.read()
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return text.replace("${CLAUDE_PLUGIN_ROOT}", PLUGIN_ROOT.replace("\\", "/"))


ISOLATION_NOTE = """

## Isolated review mode (overrides the Output Format above)

You run in an isolated, non-interactive review. Everything you need is in the review bundle directory given in
the prompt; the repository is the working directory, for reading surrounding code only. Do not run git; use Read,
Grep and Glob. Answer ONLY through the structured output (JSON schema). Ignore any markdown output format,
score, badge or Status line described above: the score and the verdict are computed from your structured answer
by a script. Be exhaustive and literal: judge every listed item, cite file:line evidence (new-side line numbers of
the diff), and report a FAIL / ABSENT / NOT_COVERED only with concrete evidence of the gap.

Use the labels exactly as defined here (they override any wording above):
- Rules — FAIL: the changed code violates the rule as written in the guideline files; cite file:line and quote the
  guideline sentence in `problem`. PASS: the rule applies to some changed file and you checked EVERY changed line it
  applies to (every added method, every added test assertion, every added request — not a sample) without finding a
  violation. NA: the rule applies to none of the changed files.
- Criteria — PRESENT: the code implements every stated part of the item. PARTIAL: at least one stated part is
  implemented and at least one is missing (name it). ABSENT: nothing implements the item's distinguishing behaviour.
- Scenarios — COVERED: a test sets up the scenario's distinguishing condition (its "given"/context) AND asserts its
  expected outcome (the key values or result of its "then"). PARTIAL: a test sets up the distinguishing condition but
  does not assert the full expected outcome (name what is not asserted). NOT_COVERED: no test sets up the
  distinguishing condition, even if neighbouring scenarios are tested.
- NA_FRONTEND: the item is purely portal/GUI wording, layout or Figma, with no backend behaviour.
"""


def launch(bundle_dir, name, agent, prompt, schema):
    sys_file = os.path.join(bundle_dir, f"{name}.system.md")
    with open(sys_file, "w", encoding="utf-8") as fh:
        fh.write(agent_body(agent) + ISOLATION_NOTE)
    env = dict(os.environ, CLAUDE_CODE_DISABLE_AUTO_MEMORY="1", OC_BE_TOOLS_ISOLATED_REVIEW="1")
    with open(os.path.join(bundle_dir, "bundle.json"), encoding="utf-8") as fh:
        repo = json.load(fh)["repo"]
    cmd = ["claude", "-p", "--no-session-persistence", "--setting-sources", "project",
           "--model", MODEL, "--effort", EFFORT, "--tools", "Read,Grep,Glob", "--permission-mode", "dontAsk",
           "--add-dir", bundle_dir, "--add-dir", os.path.join(PLUGIN_ROOT, "guidelines"),
           "--append-system-prompt-file", sys_file,
           "--output-format", "json", "--json-schema", json.dumps(schema), prompt]
    out = open(os.path.join(bundle_dir, f"{name}.out.json"), "wb")
    err = open(os.path.join(bundle_dir, f"{name}.err.txt"), "wb")
    cmd[0] = shutil.which("claude") or "claude"
    return subprocess.Popen(cmd, cwd=repo, env=env, stdout=out, stderr=err), out, err


def cmd_run(a):
    bundle_dir = a.bundle
    with open(os.path.join(bundle_dir, "bundle.json"), encoding="utf-8") as fh:
        bundle = json.load(fh)
    b = bundle_dir.replace("\\", "/")
    jobs = []
    rules_prompt = (f"Review bundle: {b}. Read {b}/bundle.json (the rule catalogue `rules`, the changed `files`, and "
                    f"`mechanical` findings already detected by a script; do not re-report those), {b}/diff.patch and the "
                    f"guideline files your instructions list. Give a status for EVERY rule id in `rules` (PASS, FAIL or NA "
                    f"when the rule does not apply to these changes), with findings for each FAIL. Put improvements that "
                    f"break no rule in `suggestions`.")
    jobs.append(("guidelines", launch(bundle_dir, "guidelines", "oc-be-pr-reviewer", rules_prompt, GUIDELINE_SCHEMA)))
    if bundle.get("judge_on") == "diff":
        basis = ("The repository checkout is NOT the reviewed branch: judge from diff.patch only, and report what the "
                 "diff does not show as ABSENT / NOT_COVERED. ")
    else:
        basis = ("Judge the code as it stands in the repository (the working directory), not only the diff: a ticket "
                 "often spans several commits, and items done in an earlier commit count as PRESENT / COVERED with "
                 "their file:line. diff.patch shows what this change adds. ")
    item_prompt = (f"Review bundle: {b}. Read {b}/bundle.json, {b}/ticket.md (context: the ticket, its test data and the "
                   f"agreed scope) and {b}/diff.patch, and read the implementation and tests in the repository as needed. "
                   + basis + "Items about portal/GUI wording, layout or Figma are NA_FRONTEND. ")
    if bundle["criteria"]:
        jobs.append(("criteria", launch(bundle_dir, "criteria", "oc-be-conformance-reviewer",
                                        item_prompt + "Judge EVERY item in `criteria` (by its id): is it implemented by these "
                                        "changes? Use exactly those ids; do not add, merge or split items.",
                                        conformance_schema("criteria"))))
    if bundle["scenarios"]:
        jobs.append(("scenarios", launch(bundle_dir, "scenarios", "oc-be-conformance-reviewer",
                                         item_prompt + "Judge EVERY item in `scenarios` (by its id): is it covered by a test "
                                         "(unit test method @ file:line and/or Postman request name)? Use exactly those ids; "
                                         "do not add, merge or split items.",
                                         conformance_schema("scenarios"))))
    started = time.time()
    status = {}
    for name, (proc, out, err) in jobs:
        try:
            proc.wait(timeout=max(60, a.timeout - (time.time() - started)))
        except subprocess.TimeoutExpired:
            proc.kill()
        out.close(); err.close()
        status[name] = proc.returncode
    print(json.dumps({"bundle": b, "runs": status, "seconds": round(time.time() - started)}))


# ------------------------------------------------------------------ verdict
def load_structured(bundle_dir, name):
    path = os.path.join(bundle_dir, f"{name}.out.json")
    if not os.path.isfile(path):
        return None, "not run"
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except ValueError:
        return None, "unreadable output"
    if d.get("is_error"):
        return None, f"error: {str(d.get('result'))[:200]}"
    return d.get("structured_output"), d.get("total_cost_usd")


def cmd_verdict(a):
    bundle_dir = a.bundle
    with open(os.path.join(bundle_dir, "bundle.json"), encoding="utf-8") as fh:
        bundle = json.load(fh)
    g, g_cost = load_structured(bundle_dir, "guidelines")
    c, c_cost = load_structured(bundle_dir, "criteria") if bundle["criteria"] else ({"items": []}, 0)
    s, s_cost = load_structured(bundle_dir, "scenarios") if bundle["scenarios"] else ({"items": []}, 0)
    problems = [f"{n}: {cost}" for n, v, cost in (("guidelines", g, g_cost), ("criteria", c, c_cost), ("scenarios", s, s_cost))
                if v is None]

    # guideline axis: every catalogue rule must have a status; mechanical findings force FAIL
    by_rule = {r["id"]: r for r in (g or {}).get("rules", [])}
    rules = []
    for rid, sev, text in RULES:
        r = by_rule.get(rid, {"id": rid, "status": "NOT_EVALUATED", "findings": []})
        mech = [m for m in bundle["mechanical"] if m["rule"] == rid]
        findings = [dict(m, fix="", source="mechanical") for m in mech] + \
                   [dict(f, source="review") for f in r.get("findings", [])]
        status = "FAIL" if mech else r["status"]
        rules.append({"id": rid, "severity": sev, "rule": text, "status": status, "findings": findings})
    failed = [r for r in rules if r["status"] == "FAIL"]
    missing = [r["id"] for r in rules if r["status"] == "NOT_EVALUATED"]
    score = max(1, min(10, round(10 - sum(PENALTY[r["severity"]] for r in failed))))
    guideline_ok = not any(r["severity"] in ("critical", "major") for r in failed) and not missing and g is not None

    # conformance axis: every item must be judged; ABSENT / NOT_COVERED fail it
    def judge(items, judged, bad):
        by_id = {i["id"]: i for i in (judged or {}).get("items", [])}
        out = []
        for it in items:
            j = by_id.get(it["id"], {"status": "NOT_EVALUATED", "evidence": "", "note": ""})
            out.append(dict(it, status=j["status"], evidence=j.get("evidence", ""), note=j.get("note", "")))
        return out, [i for i in out if i["status"] in (bad, "NOT_EVALUATED")]
    crit, crit_bad = judge(bundle["criteria"], c, "ABSENT")
    scen, scen_bad = judge(bundle["scenarios"], s, "NOT_COVERED")
    conformance_ok = not crit_bad and not scen_bad and c is not None and s is not None

    verdict = "APPROVE" if guideline_ok and conformance_ok and not problems else "CHANGES_REQUESTED"
    report = {"ticket": bundle["ticket"], "scope": bundle["scope"], "verdict": verdict, "score": score,
              "guideline_status": "APPROVE" if guideline_ok else "CHANGES_REQUESTED",
              "conformance": "CONFORMANT" if conformance_ok else "NONCONFORMANT",
              "summary": (g or {}).get("summary", ""), "rules": rules, "criteria": crit, "scenarios": scen,
              "suggestions": (g or {}).get("suggestions", []), "problems": problems,
              "isolation": {"model": MODEL, "effort": EFFORT, "plugin_version": bundle["plugin_version"],
                            "input_hash": bundle["input_hash"], "user_memory": "excluded", "conversation": "excluded"},
              "cost_usd": round(sum(x for x in (g_cost, c_cost, s_cost) if isinstance(x, (int, float))), 2)}
    with open(os.path.join(bundle_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    md = render(report)
    with open(os.path.join(bundle_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    if bundle.get("head") and a.record:
        led = load_ledger(bundle["repo"])
        led["reviews"].append({"head": bundle["head"], "patch_id": bundle["state_patch_id"], "verdict": verdict,
                               "score": score, "ticket": bundle["ticket"], "report": os.path.join(bundle_dir, "report.md"),
                               "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "acknowledged": False, "skipped": False})
        save_ledger(bundle["repo"], led)
    print(md)


def render(r):
    out = [f"# Isolated review — {r['ticket']}: {r['verdict']} (score {r['score']}/10)", "",
           f"Scope: {r['scope']}  ",
           f"Isolation: model {r['isolation']['model']}/{r['isolation']['effort']}, oc-be-tools {r['isolation']['plugin_version']}, "
           f"no conversation, no user memory; input {r['isolation']['input_hash']}  ",
           f"Guidelines: {r['guideline_status']} · Requirements: {r['conformance']} · cost ${r['cost_usd']}", ""]
    if r["problems"]:
        out += ["**Review runs that did not complete (the verdict cannot be APPROVE):** " + "; ".join(r["problems"]), ""]
    if r["summary"]:
        out += [r["summary"], ""]
    failed = [x for x in r["rules"] if x["status"] in ("FAIL", "NOT_EVALUATED")]
    out += ["## Guideline rules", "", f"{sum(1 for x in r['rules'] if x['status'] == 'PASS')} pass · "
            f"{sum(1 for x in r['rules'] if x['status'] == 'NA')} n/a · {len(failed)} fail/not evaluated", ""]
    for x in sorted(failed, key=lambda x: ("critical", "major", "minor").index(x["severity"])):
        out.append(f"- **{x['id']}** ({x['severity']}, {x['status']}): {x['rule']}")
        for f in x["findings"]:
            out.append(f"  - `{f['file']}:{f['line']}` {f['problem']}" + (f" — fix: {f['fix']}" if f.get("fix") else "")
                       + (" *(mechanical check)*" if f.get("source") == "mechanical" else ""))
    for title, items in (("Acceptance criteria", r["criteria"]), ("Test scenarios", r["scenarios"])):
        if items:
            out += ["", f"## {title}", "", "| # | Item | Status | Evidence | Note |", "|---|---|---|---|---|"]
            for i in items:
                text = i["text"] if len(i["text"]) <= 140 else i["text"][:137] + "..."
                out.append(f"| {i['id']} | {text} *({i['source']})* | {i['status']} | {i['evidence']} | {i['note']} |")
    if r["suggestions"]:
        out += ["", "## Suggestions (do not affect the verdict)", ""]
        out += [f"- `{s['file']}:{s['line']}` {s['text']}" for s in r["suggestions"]]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ gate / mark (used by the hooks and /oc-be-calculate-ai-use)
def review_for(top, mode="working", ref=None):
    """The ledger entry covering the current uncommitted change set (working) or commit `ref` (commit)."""
    if mode == "commit":
        sha, parent, pid = commit_state(top, ref or "HEAD")
        return find_review(top, parent, pid) or find_review(top, sha, "")
    return find_review(top, *code_state(top))


def cmd_gate(a):
    top = git(a.repo, "rev-parse", "--show-toplevel", check=True).strip()
    r = review_for(top, a.mode, a.ref)
    print(json.dumps({"reviewed": bool(r), "verdict": (r or {}).get("verdict"), "score": (r or {}).get("score"),
                      "acknowledged": (r or {}).get("acknowledged"), "skipped": (r or {}).get("skipped"),
                      "report": (r or {}).get("report")}))


def cmd_mark(a):
    """skipped: commit this change set without a review; acknowledged: commit it despite CHANGES_REQUESTED."""
    top = git(a.repo, "rev-parse", "--show-toplevel", check=True).strip()
    head, pid = code_state(top)
    led = load_ledger(top)
    entry = next((r for r in reversed(led["reviews"]) if r.get("head") == head and r.get("patch_id") == pid), None)
    if entry is None:
        entry = {"head": head, "patch_id": pid, "verdict": None, "ticket": a.ticket,
                 "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "acknowledged": False, "skipped": False}
        led["reviews"].append(entry)
    entry[a.what] = True
    save_ledger(top, led)
    print(f"{a.what}: {head[:10]} / {pid[:10]}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")     # ticket text holds arrows, Greek letters...; Windows consoles default to cp1252
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--repo", default="."); p.add_argument("--ticket", required=True)
    p.add_argument("--ticket-json"); p.add_argument("--fetch-jira", action="store_true")
    p.add_argument("--diff-file"); p.add_argument("--range")
    p.add_argument("--out")
    r = sub.add_parser("run"); r.add_argument("--bundle", required=True); r.add_argument("--timeout", type=int, default=1800)
    v = sub.add_parser("verdict"); v.add_argument("--bundle", required=True); v.add_argument("--record", action="store_true")
    g = sub.add_parser("gate"); g.add_argument("--repo", default="."); g.add_argument("--mode", choices=["working", "commit"],
                                                                                      default="working"); g.add_argument("--ref")
    m = sub.add_parser("mark"); m.add_argument("--repo", default="."); m.add_argument("what", choices=["skipped", "acknowledged"])
    m.add_argument("--ticket")
    a = ap.parse_args()
    {"prepare": cmd_prepare, "run": cmd_run, "verdict": cmd_verdict, "gate": cmd_gate, "mark": cmd_mark}[a.cmd](a)


if __name__ == "__main__":
    main()
