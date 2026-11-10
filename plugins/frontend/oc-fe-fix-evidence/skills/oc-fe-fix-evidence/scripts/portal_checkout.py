#!/usr/bin/env python3
"""Pick and prepare the opencell-portal checkout a fix is recorded from.

    portal_checkout.py state   --path <checkout>
    portal_checkout.py select  --ticket INTRD-1 [--cwd .] [--root <dir>] [--line 15.X]
    portal_checkout.py prepare --path <checkout>

`select` answers "where is the code that contains this fix?":

  * the current directory, when it is a portal checkout holding work that is not
    on a version line yet (uncommitted changes, or commits no line contains) —
    the fix exists nowhere else;
  * otherwise the developer's checkout of the version line (dev, 15.X, 16.X, ...)
    the ticket was merged into, found among the checkouts under --root. That
    checkout must be ON the line branch and clean; it is then fast-forwarded to
    origin. Nothing is ever switched, stashed or reset.

`prepare` makes that checkout startable: the Node version it needs (.nvmrc, or
Node <= 16 for the webpack-4 lines) and its dependencies (`oc-install`, which
links them from the shared pnpm store).

Every command prints one JSON object. Exit 0 = done, 4 = a person must decide
(the JSON `ask` field says what), 2 = usage / environment.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

LINE_RE = re.compile(r"^(dev|\d+(\.\d+)*\.X)$")
REPO_RE = re.compile(r"opencell-portal(\.git)?/?$")
IGNORED = ":(exclude).claude"          # tooling cache, never part of a fix


class Ask(Exception):
    """A decision only the developer can make."""


def git(path, *args, check=True):
    done = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True)
    if check and done.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed in {path}: {done.stderr.strip()}")
    return done.stdout.strip()


def is_portal(path):
    if not os.path.isdir(path):
        return False
    return bool(REPO_RE.search(git(path, "remote", "get-url", "origin", check=False)))


def dirty(path):
    """Changed or new files, ignoring the .claude/ tooling folder."""
    return git(path, "status", "--porcelain", "--", ".", IGNORED)


def code_state(path):
    """Identity of the code being proven: HEAD, plus a hash of uncommitted work."""
    head = git(path, "rev-parse", "--short=7", "HEAD")
    if not dirty(path):
        return {"state": head, "uncommitted": False}
    import hashlib
    blob = git(path, "diff", "HEAD", "--", ".", IGNORED) + "\n" + git(
        path, "ls-files", "--others", "--exclude-standard", "--", ".", IGNORED)
    return {"state": f"{head}+{hashlib.sha1(blob.encode()).hexdigest()[:8]}",
            "uncommitted": True}


def lines_on_origin(path):
    refs = git(path, "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin")
    names = [r.split("/", 1)[1] for r in refs.splitlines() if "/" in r]
    return [n for n in names if LINE_RE.match(n)]


def lines_with_ticket(path, ticket, lines):
    found = []
    for line in lines:
        if git(path, "log", f"origin/{line}", "-1", "--format=%h", "-F",
               f"--grep={ticket}", check=False):
            found.append(line)
    return found


def on_a_line(path, lines):
    """True when HEAD is already contained in a version line on origin."""
    contains = git(path, "branch", "-r", "--contains", "HEAD", check=False)
    names = {b.strip().split("/", 1)[-1] for b in contains.splitlines()}
    return any(line in names for line in lines)


def worktrees(any_checkout):
    out, current = [], {}
    for row in git(any_checkout, "worktree", "list", "--porcelain").splitlines() + [""]:
        if not row:
            if current:
                out.append(current)
            current = {}
        elif row.startswith("worktree "):
            current["path"] = row[9:]
        elif row.startswith("branch "):
            current["branch"] = row[7:].replace("refs/heads/", "")
    return out


def find_checkouts(root):
    first = next((os.path.join(root, d) for d in sorted(os.listdir(root))
                  if is_portal(os.path.join(root, d))), None)
    if not first:
        raise Ask(f"no opencell-portal checkout found under {root}")
    seen = {w["path"]: w for w in worktrees(first)}
    for d in sorted(os.listdir(root)):               # separate clones, if any
        p = os.path.join(root, d)
        if p not in seen and is_portal(p):
            seen[p] = {"path": p, "branch": git(p, "branch", "--show-current")}
    return list(seen.values())


def select(cwd, root, ticket, line=None):
    cwd = os.path.abspath(cwd)
    if is_portal(cwd):
        top = git(cwd, "rev-parse", "--show-toplevel")
        git(top, "fetch", "-q", "origin", check=False)
        if dirty(top) or not on_a_line(top, lines_on_origin(top)):
            return {"mode": "current", "path": top,
                    "branch": git(top, "branch", "--show-current"),
                    "why": "this checkout holds work that is not on a version line yet"}
    if not root or not os.path.isdir(root):
        raise Ask("the folder holding the per-version portal checkouts is not known "
                  "(set OC_PORTAL_ROOT or pass --root)")
    checkouts = find_checkouts(root)
    anchor = checkouts[0]["path"]
    git(anchor, "fetch", "-q", "origin", check=False)
    lines = lines_on_origin(anchor)
    merged = lines_with_ticket(anchor, ticket, lines)
    if line:
        if line not in merged:
            raise Ask(f"{ticket} is not merged into {line} (merged into: {merged or 'no line'})")
    elif not merged:
        raise Ask(f"no commit mentioning {ticket} on any version line ({', '.join(lines)}) "
                  "and the current directory holds no unmerged portal work")
    elif len(merged) > 1:
        raise Ask(f"{ticket} is merged into several lines: {', '.join(merged)} — which one?")
    line = line or merged[0]
    target = next((c for c in checkouts if c.get("branch") == line), None)
    if not target:
        raise Ask(f"no checkout under {root} is on branch {line}; "
                  "check one out on that branch, or name the checkout to use")
    path = target["path"]
    if dirty(path):
        raise Ask(f"{path} has uncommitted changes; it is left untouched")
    behind = int(git(path, "rev-list", "--count", f"HEAD..origin/{line}") or 0)
    if behind:
        git(path, "merge", "-q", "--ff-only", f"origin/{line}")
    return {"mode": "line", "path": path, "branch": line, "fastForwarded": behind,
            "why": f"{ticket} is merged into {line}"}


def nvm_versions(home=None):
    base = os.path.join(home or os.path.expanduser("~"), ".nvm", "versions", "node")
    found = []
    for d in glob.glob(os.path.join(base, "v*")):
        m = re.match(r"v(\d+)\.(\d+)\.(\d+)$", os.path.basename(d))
        if m and os.path.exists(os.path.join(d, "bin", "node")):
            found.append((tuple(map(int, m.groups())), os.path.join(d, "bin")))
    return sorted(found)


def node_rule(path):
    """(wanted major or None, max major or None, reason) for this checkout."""
    nvmrc = os.path.join(path, ".nvmrc")
    if os.path.exists(nvmrc):
        m = re.search(r"\d+", open(nvmrc).read())
        if m:
            return int(m.group()), None, ".nvmrc"
    with open(os.path.join(path, "package.json")) as handle:
        start = json.load(handle).get("scripts", {}).get("start", "")
    if "react-app-rewired" in start or "react-scripts" in start:
        return None, 16, "webpack 4 does not start on Node 17+"
    return None, None, "current Node"


def pick_node(path, versions):
    wanted, ceiling, reason = node_rule(path)
    if wanted is None and ceiling is None:
        return None, reason
    fits = [(v, b) for v, b in versions
            if (wanted is None or v[0] == wanted) and (ceiling is None or v[0] <= ceiling)]
    if not fits:
        need = f"Node {wanted}" if wanted else f"Node {ceiling} or older"
        raise Ask(f"{need} is required ({reason}) and is not installed — "
                  f"run: nvm install {wanted or ceiling}")
    return fits[-1][1], reason


def start_command(path):
    with open(os.path.join(path, "package.json")) as handle:
        start = json.load(handle).get("scripts", {}).get("start", "")
    if start.strip().startswith("vite"):
        return {"kind": "vite", "argv": ["npm", "run", "start", "--", "--port", "3000", "--strictPort"],
                "env": {"BROWSER": "none"}, "port": 3000}
    return {"kind": "cra", "argv": ["npm", "run", "start"],
            "env": {"BROWSER": "none", "PORT": "3000"}, "port": 3000}


def prepare(path):
    path = os.path.abspath(path)
    node_bin, reason = pick_node(path, nvm_versions())
    installer = shutil.which("oc-install")
    if not installer:
        raise Ask("`oc-install` is not on PATH — install the dependencies of "
                  f"{path} yourself, then re-run")
    # oc-install runs on the developer's default Node: pnpm itself needs a recent
    # one. Only the dev server is started with `nodeBin` (see the result).
    done = subprocess.run([installer], cwd=path, capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError("oc-install failed:\n" + (done.stdout + done.stderr)[-1500:])
    return {"path": path, "nodeBin": node_bin, "nodeReason": reason,
            "installed": "oc-install", "tracked_changes": dirty(path),
            "start": start_command(path)}


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("state"); p.add_argument("--path", required=True)
    p = sub.add_parser("select")
    p.add_argument("--ticket", required=True); p.add_argument("--cwd", default=".")
    p.add_argument("--root", default=os.environ.get("OC_PORTAL_ROOT")); p.add_argument("--line")
    p = sub.add_parser("prepare"); p.add_argument("--path", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "state":
            result = code_state(args.path)
        elif args.command == "select":
            result = select(args.cwd, args.root, args.ticket, args.line)
            result.update(code_state(result["path"]))
        else:
            result = prepare(args.path)
        print(json.dumps(result, indent=2))
        return 0
    except Ask as ask:
        print(json.dumps({"ask": str(ask)}, indent=2))
        return 4
    except RuntimeError as error:
        print(json.dumps({"error": str(error)}, indent=2))
        return 2


if __name__ == "__main__":
    sys.exit(main())
