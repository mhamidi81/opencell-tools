#!/usr/bin/env bash
#
# render-artifact.sh — render an oc-fn-decks Marp `.md` to a branded claude.ai Artifact page.
#
# Same source, same theme, same slides as the Marp HTML lane; different output: an HTML
# fragment that follows the Artifact page contract (no doctype/head/body, <title> first),
# light by default with a light/dark switch in Marp's on-screen controls, and a dark slide
# variant derived from the Charte palette only. See artifact.md for the design.
#
# Reproducibility guard: an Artifact is a render, never the source. Unless --draft is given,
# the script refuses to render a deck that is uncommitted, or whose last commit is not on its
# branch's upstream, or whose repo theme copy has uncommitted changes — so every published
# page can be rebuilt from git alone. The render records the deck (remote · path @ commit) and
# the theme it used in an HTML comment at the top of the page.
#
# Usage:
#   render-artifact.sh <deck.md> -o <output.html> [--theme-set <theme.css>] [--draft]
#
#   -o <path>        Output fragment (required). Render into the session scratchpad, not the
#                    repo: the page is regenerated on every publish and is never committed.
#   --theme-set <f>  The Marp theme CSS. Default: the nearest `assets/marp/opencell.css` found
#                    walking up from the deck to its repo root (the repo's working copy).
#   --draft          Skip the git guard, for a local preview only. A draft render is marked as
#                    such in its provenance comment and must not be published.
#
# Environment: MARP_CLI_VERSION (default below) pins the marp-cli used, so a re-render from
# the same commit produces the same page.
#
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
ART="$SKILL_DIR/artifact"
MARP_CLI_VERSION="${MARP_CLI_VERSION:-4.5.1}"

die() { echo "render-artifact: $*" >&2; exit 1; }

SRC="" OUT="" DRAFT="" THEME=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) OUT="${2:-}"; shift 2 ;;
    --theme-set) THEME="${2:-}"; shift 2 ;;
    --draft) DRAFT=1; shift ;;
    -h|--help) sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "${BASH_SOURCE[0]}"; exit 0 ;;
    -*) die "unknown option: $1 (try -h)" ;;
    *) [[ -z "$SRC" ]] && SRC="$1" || die "unexpected argument: $1"; shift ;;
  esac
done

[[ -n "$SRC" ]] || die "no deck given (try -h)"
[[ -n "$OUT" ]] || die "-o <output.html> is required — render into the scratchpad, not the repo"
[[ -f "$SRC" ]] || die "deck not found: $SRC"
command -v npx >/dev/null 2>&1 || die "npx (Node.js) is not installed — marp-cli runs through it"
command -v python3 >/dev/null 2>&1 || die "python3 is not installed — it assembles the fragment"

SRC_ABS="$(readlink -f "$SRC")"
SRC_DIR="$(dirname "$SRC_ABS")"
SKILL_VERSION="$(sed -n 's/^version:[[:space:]]*//p' "$SKILL_DIR/SKILL.md" | head -1)"
TOP="$(git -C "$SRC_DIR" rev-parse --show-toplevel 2>/dev/null || true)"

# ── Theme: the repo's working copy, never the skill master (a deck re-renders from its repo) ──
if [[ -z "$THEME" ]]; then
  d="$SRC_DIR"
  while :; do
    [[ -f "$d/assets/marp/opencell.css" ]] && { THEME="$d/assets/marp/opencell.css"; break; }
    [[ "$d" == "/" || ( -n "$TOP" && "$d" == "$TOP" ) ]] && break
    d="$(dirname "$d")"
  done
  [[ -n "$THEME" ]] || die "no assets/marp/opencell.css between the deck and its repo root — pass --theme-set"
fi
[[ -f "$THEME" ]] || die "theme not found: $THEME"
THEME_ABS="$(readlink -f "$THEME")"

# ── Provenance + reproducibility guard ────────────────────────────────────────────────────
REMOTE="(not in git)" RELPATH="$SRC_ABS" COMMIT="uncommitted" THEME_REF="$THEME_ABS"
if [[ -n "$TOP" ]]; then
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
  case "$THEME_ABS" in
    "$TOP"/*)
      THEME_REL="$(realpath --relative-to="$TOP" "$THEME_ABS")"
      THEME_REF="$THEME_REL @ $(git -C "$TOP" log -1 --format=%h -- "$THEME_REL" 2>/dev/null || echo '?')" ;;
  esac
fi

if [[ -z "$DRAFT" ]]; then
  [[ -n "$TOP" ]] || die "$SRC is not in a git repository — an Artifact must be reproducible from git"
  [[ "$COMMIT" != "uncommitted" ]] || die "$RELPATH has uncommitted changes — commit and push it first (or --draft for a local preview)"
  git -C "$TOP" rev-parse --verify -q '@{u}' >/dev/null || die "branch '$BRANCH' has no upstream — push it first"
  git -C "$TOP" merge-base --is-ancestor "$COMMIT" '@{u}' \
    || die "$RELPATH @ $COMMIT is not pushed to $(git -C "$TOP" rev-parse --abbrev-ref '@{u}') — push first"
  case "$THEME_ABS" in
    "$TOP"/*) [[ -z "$(git -C "$TOP" status --porcelain -- "$THEME_ABS")" ]] \
                || die "the theme $THEME_REL has uncommitted changes — commit it first" ;;
    *) die "the theme $THEME_ABS is outside the deck's repo — a render from it would not reproduce from git" ;;
  esac
  # The page is deck × theme × this skill's artifact layer: a render from a locally modified
  # layer would not reproduce from git either. Checked only where the skill itself lives in a
  # git work tree (the author's clone); an installed plugin copy is pinned by the version stamp.
  if git -C "$SKILL_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 \
     && [[ -n "$(git -C "$SKILL_DIR" status --porcelain -- .)" ]]; then
    die "the oc-fn-decks skill has uncommitted changes — commit them first (or --draft for a local preview)"
  fi
fi

# ── Render ────────────────────────────────────────────────────────────────────────────────
# The dark slide variant must pass through Marp so its selectors get the same scoping as the
# theme's: it is appended to a temporary copy of the deck as a global <style>. The copy sits
# beside the deck so relative paths resolve the same way; it is removed on exit.
TMP_MD="$(mktemp "$SRC_DIR/.render-artifact.XXXXXX.md")"
TMP_HTML="$(mktemp --suffix=.html)"
trap 'rm -f "$TMP_MD" "$TMP_HTML"' EXIT
{ cat "$SRC_ABS"; printf '\n\n<style>\n'; cat "$ART/slides.css"; printf '\n</style>\n'; } > "$TMP_MD"

# --no-stdin: marp-cli otherwise waits on a non-TTY stdin forever (it reads a deck from it).
npx -y "@marp-team/marp-cli@$MARP_CLI_VERSION" --no-stdin "$TMP_MD" -o "$TMP_HTML" \
  --html --theme-set "$THEME_ABS" < /dev/null >/dev/null 2>&1 \
  || die "marp-cli failed — rerun it by hand on $SRC for the error"

# Front matter the fragment needs: pagetitle (the gallery name) falls back to Marp's title.
FM="$(awk 'NR==1&&/^---$/{f=1;next} f&&/^---$/{exit} f' "$SRC_ABS")"
fm() { sed -n "s/^$1:[[:space:]]*[\"']\{0,1\}\([^\"']*\)[\"']\{0,1\}[[:space:]]*\$/\1/p" <<<"$FM" | head -1; }
PAGETITLE="$(fm pagetitle)"

STAMP="Source: $REMOTE · $RELPATH @ $COMMIT · theme $THEME_REF · rendered by oc-fn-decks $SKILL_VERSION (render-artifact.sh, marp-cli $MARP_CLI_VERSION)"
[[ -n "$DRAFT" ]] && STAMP="$STAMP · DRAFT: uncommitted source, not for publishing"

python3 "$ART/fragment.py" "$TMP_HTML" "$OUT" --art "$ART" --stamp "$STAMP" --pagetitle "$PAGETITLE"

echo "→ $OUT${DRAFT:+  (DRAFT — do not publish)}"

URL="$(fm artifact)"
if [[ -n "$URL" ]]; then
  echo "  republish to: $URL"
else
  echo "  first publish: write the returned URL back into the front matter as 'artifact:' and commit it"
fi
[[ -n "$PAGETITLE" ]] \
  || echo "  note: no 'pagetitle:' — the gallery name falls back to 'title:' (keep it a 2–4 word name)"
