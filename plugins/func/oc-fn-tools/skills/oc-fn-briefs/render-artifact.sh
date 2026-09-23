#!/usr/bin/env bash
#
# render-artifact.sh — render a Tier-1 oc-fn-briefs `.md` to a branded claude.ai Artifact page.
#
# Same source, same vocabulary, same brand as the A4 PDF lane; different output: an HTML
# fragment that follows the Artifact page contract (no doctype/head/body, <title> first,
# theme-aware, phone-width safe, brand CSS inlined, Montserrat from Google Fonts).
#
# Reproducibility guard: an Artifact is a render, never the source. Unless --draft is given,
# the script refuses to render a source that is uncommitted, or whose last commit is not on
# its branch's upstream — so every published page can be rebuilt from git alone. The render
# records that source (remote · path @ commit) in an HTML comment at the top of the page.
#
# Usage:
#   render-artifact.sh <source.md> -o <output.html> [--draft]
#
#   -o <path>   Output fragment (required). Render into the session scratchpad, not the repo:
#               the page is regenerated on every publish and is never committed.
#   --draft     Skip the git guard, for a local preview only. A draft render is marked as
#               such in its provenance comment and must not be published.
#
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
TEMPLATE="$SKILL_DIR/templates/artifact.pandoc.html"
FONTS='https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;800&display=swap'

die() { echo "render-artifact: $*" >&2; exit 1; }

SRC="" OUT="" DRAFT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) OUT="${2:-}"; shift 2 ;;
    --draft) DRAFT=1; shift ;;
    -h|--help) sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "${BASH_SOURCE[0]}"; exit 0 ;;
    -*) die "unknown option: $1 (try -h)" ;;
    *) [[ -z "$SRC" ]] && SRC="$1" || die "unexpected argument: $1"; shift ;;
  esac
done

[[ -n "$SRC" ]] || die "no source given (try -h)"
[[ -n "$OUT" ]] || die "-o <output.html> is required — render into the scratchpad, not the repo"
[[ -f "$SRC" ]] || die "source not found: $SRC"
command -v pandoc >/dev/null 2>&1 || die "pandoc is not installed"

SRC_ABS="$(readlink -f "$SRC")"
SKILL_VERSION="$(sed -n 's/^version:[[:space:]]*//p' "$SKILL_DIR/SKILL.md" | head -1)"

# ── Provenance + reproducibility guard ────────────────────────────────────────────────────
REMOTE="(not in git)" RELPATH="$SRC_ABS" COMMIT="uncommitted"
if TOP="$(git -C "$(dirname "$SRC_ABS")" rev-parse --show-toplevel 2>/dev/null)"; then
  RELPATH="$(realpath --relative-to="$TOP" "$SRC_ABS")"
  BRANCH="$(git -C "$TOP" branch --show-current)"
  RNAME="$(git -C "$TOP" config --get "branch.$BRANCH.remote" || echo origin)"
  # Strip any credentials embedded in an https remote before it goes into a published page.
  REMOTE="$(git -C "$TOP" remote get-url "$RNAME" 2>/dev/null | sed -E 's#(://)[^/@]+@#\1#' || true)"
  [[ -n "$REMOTE" ]] || REMOTE="(no remote)"
  if [[ -z "$(git -C "$TOP" status --porcelain -- "$RELPATH")" ]]; then
    COMMIT="$(git -C "$TOP" log -1 --format=%h -- "$RELPATH")"
    [[ -n "$COMMIT" ]] || COMMIT="uncommitted"
  fi
fi

if [[ -z "$DRAFT" ]]; then
  [[ -n "${TOP:-}" ]] || die "$SRC is not in a git repository — an Artifact must be reproducible from git"
  [[ "$COMMIT" != "uncommitted" ]] || die "$RELPATH has uncommitted changes — commit and push it first (or --draft for a local preview)"
  git -C "$TOP" rev-parse --verify -q '@{u}' >/dev/null || die "branch '$BRANCH' has no upstream — push it first"
  git -C "$TOP" merge-base --is-ancestor "$COMMIT" '@{u}' \
    || die "$RELPATH @ $COMMIT is not pushed to $(git -C "$TOP" rev-parse --abbrev-ref '@{u}') — push first"
  # The page is source × skill: a render from locally modified templates or CSS would not
  # reproduce from git either. Checked only where the skill itself lives in a git work tree
  # (the author's clone); an installed plugin copy is pinned by the version in the stamp.
  if git -C "$SKILL_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
     && [[ -n "$(git -C "$SKILL_DIR" status --porcelain -- .)" ]]; then
    die "the oc-fn-briefs skill has uncommitted changes — commit them first (or --draft for a local preview)"
  fi
fi

# ── Render ────────────────────────────────────────────────────────────────────────────────
HDR="$(mktemp)"; trap 'rm -f "$HDR"' EXIT
{
  printf '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
  printf '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
  printf '<link rel="stylesheet" href="%s">\n' "$FONTS"
  printf '<style>\n'; cat "$SKILL_DIR/theme/brand.css" "$SKILL_DIR/theme/artifact.css"; printf '</style>\n'
} > "$HDR"

pandoc "$SRC_ABS" \
  --from markdown \
  --template "$TEMPLATE" \
  --lua-filter "$SKILL_DIR/theme/oc-brief.lua" \
  --lua-filter "$SKILL_DIR/theme/oc-artifact.lua" \
  --include-in-header "$HDR" \
  -V source-remote="$REMOTE" -V source-path="$RELPATH" -V source-commit="$COMMIT" \
  -V skill-version="$SKILL_VERSION" ${DRAFT:+-V draft=true} \
  -o "$OUT"

echo "→ $OUT${DRAFT:+  (DRAFT — do not publish)}"

# Tell the publisher where this page lives, from the source's own front matter.
FM="$(awk 'NR==1&&/^---$/{f=1;next} f&&/^---$/{exit} f' "$SRC_ABS")"
URL="$(sed -n 's/^artifact:[[:space:]]*"\{0,1\}\([^"]*\)"\{0,1\}[[:space:]]*$/\1/p' <<<"$FM" | head -1)"
if [[ -n "$URL" ]]; then
  echo "  republish to: $URL"
else
  echo "  first publish: write the returned URL back into the front matter as 'artifact:' and commit it"
fi
grep -q '^pagetitle:' <<<"$FM" \
  || echo "  note: no 'pagetitle:' — the gallery name falls back to 'title:' (keep it a 2–4 word name)"
