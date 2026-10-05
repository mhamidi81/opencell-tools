#!/usr/bin/env bash
# render-internal-pptx.sh — a Marp deck as an editable PowerPoint in the INTERNAL look: the deck's
# own Marp theme (opencell.css), not the official Opencell template (that is pptx/deck2pptx.py).
#
#   render-internal-pptx.sh <deck.md> [-o <out.pptx>] [--theme-set <theme.css>] [--keep-centring] [--qa <dir>]
#
#   -o <out.pptx>     Default: next to the deck, same basename.
#   --theme-set <f>   The Marp theme CSS. Default: the nearest assets/marp/opencell.css walking up
#                     from the deck to its repo root (the repo's working copy).
#   --keep-centring   Keep Marp's vertical centring of slide content. By default non-lead slides
#                     are top-aligned, so every title sits at one position on one layout.
#   --qa <dir>        Also render the PPTX to PNGs (LibreOffice, brand fonts loaded) for review.
#
# How: marp-cli renders the deck (bare template); internal-pptx/measure.js lays it out in headless
# Chromium and records geometry and computed styles; internal-pptx/build.js places native PPTX
# objects at the same positions (text boxes, tables, shapes, images, a title placeholder per
# layout, speaker notes); internal-pptx/finish.py embeds the brand fonts and repairs pptxgenjs'
# paragraph properties. The .pptx is a render of the .md: regenerate it, never hand-edit it.
#
# Needs node + npx, python3 and Chromium or Chrome (found on PATH, or CHROME_PATH). The first run
# needs network: the pinned npm packages and the brand TTFs go to $OC_DECKS_CACHE (default
# ~/.cache/oc-fn-decks/internal-pptx). The theme's Google Fonts @import is fetched at every run;
# the cached TTFs stand in when offline. MARP_CLI_VERSION pins marp-cli, as in render-artifact.sh.
set -euo pipefail

HERE=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
MARP_CLI_VERSION="${MARP_CLI_VERSION:-4.5.1}"
PPTXGENJS_VERSION=3.12.0
PUPPETEER_VERSION=24.43.1
CACHE="${OC_DECKS_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/oc-fn-decks/internal-pptx}"

die() { echo "render-internal-pptx: $*" >&2; exit 1; }
usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; }

SRC="" OUT="" THEME="" CENTRE="" QA=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o)               OUT="${2:?-o needs a path}"; shift 2 ;;
    --theme-set)      THEME="${2:?--theme-set needs a path}"; shift 2 ;;
    --keep-centring)  CENTRE=--keep-centring; shift ;;
    --qa)             QA="${2:?--qa needs a directory}"; shift 2 ;;
    -h|--help)        usage; exit 0 ;;
    -*)               die "unknown option: $1 (try -h)" ;;
    *)                [[ -z "$SRC" ]] || die "one deck at a time"; SRC="$1"; shift ;;
  esac
done
[[ -n "$SRC" ]] || { usage >&2; exit 2; }
[[ -f "$SRC" ]] || die "no such deck: $SRC"
SRC=$(realpath "$SRC"); OUT=$(realpath -m "${OUT:-${SRC%.md}.pptx}"); DECKDIR=$(dirname "$SRC")

command -v npx >/dev/null 2>&1 || die "npx (Node.js) is not installed"
command -v python3 >/dev/null 2>&1 || die "python3 is not installed"
CHROME_PATH="${CHROME_PATH:-$(command -v chromium || command -v chromium-browser || command -v google-chrome || true)}"
[[ -n "$CHROME_PATH" ]] || die "no Chromium or Chrome on PATH — set CHROME_PATH"
export CHROME_PATH

if [[ -z "$THEME" ]]; then
  d="$DECKDIR"
  while :; do
    [[ -f "$d/assets/marp/opencell.css" ]] && { THEME="$d/assets/marp/opencell.css"; break; }
    [[ -e "$d/.git" || "$d" == / ]] && break
    d=$(dirname "$d")
  done
  [[ -n "$THEME" ]] || die "no assets/marp/opencell.css between the deck and its repo root — pass --theme-set"
fi
[[ -f "$THEME" ]] || die "theme not found: $THEME"

# ---- pinned dependencies and brand fonts, cached
mkdir -p "$CACHE/fonts" "$CACHE/fontconfig" "$(dirname "$OUT")"
STAMP="$CACHE/.deps-pptxgenjs-$PPTXGENJS_VERSION-puppeteer-$PUPPETEER_VERSION"
if [[ ! -f "$STAMP" ]]; then
  echo "render-internal-pptx: installing pptxgenjs $PPTXGENJS_VERSION + puppeteer-core $PUPPETEER_VERSION into $CACHE" >&2
  npm install --prefix "$CACHE" --silent --no-audit --no-fund \
    "pptxgenjs@$PPTXGENJS_VERSION" "puppeteer-core@$PUPPETEER_VERSION" >/dev/null || die "npm install failed"
  touch "$STAMP"
fi
# Montserrat from its upstream repo (static TTFs whose name table says "Montserrat"); Playfair
# Display from fontsource. Named <Family without spaces>-<Style>.ttf, which finish.py expects.
M=https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf
F=https://cdn.jsdelivr.net/fontsource/fonts/playfair-display@latest
for s in Regular:Regular Italic:Italic Bold:Bold BoldItalic:BoldItalic; do
  f="$CACHE/fonts/Montserrat-${s%%:*}.ttf"
  [[ -s "$f" ]] || curl -sfL -o "$f" "$M/Montserrat-${s#*:}.ttf" || die "could not fetch Montserrat ${s%%:*}"
done
for s in Regular:400-normal Italic:400-italic Bold:700-normal BoldItalic:700-italic; do
  f="$CACHE/fonts/PlayfairDisplay-${s%%:*}.ttf"
  [[ -s "$f" ]] || curl -sfL -o "$f" "$F/latin-${s#*:}.ttf" || die "could not fetch Playfair Display ${s%%:*}"
done

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/fonts.conf" <<EOF
<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include><dir>$CACHE/fonts</dir><cachedir>$CACHE/fontconfig</cachedir></fontconfig>
EOF
export FONTCONFIG_FILE="$TMP/fonts.conf"

# ---- render, measure, build, finish
# --no-stdin: marp-cli otherwise waits on a non-TTY stdin forever.
npx -y "@marp-team/marp-cli@$MARP_CLI_VERSION" --no-stdin "$SRC" -o "$TMP/deck.html" \
  --html --template bare --theme-set "$THEME" < /dev/null > "$TMP/marp.log" 2>&1 \
  || { cat "$TMP/marp.log" >&2; die "marp-cli failed"; }
# A <base> so the deck's relative image paths resolve from the temporary copy.
python3 - "$TMP/deck.html" "$DECKDIR" <<'EOF'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); s = p.read_text(encoding="utf-8")
base = '<base href="' + pathlib.Path(sys.argv[2]).as_uri() + '/">'
p.write_text(s.replace("<head>", "<head>" + base, 1) if "<head>" in s else base + s, encoding="utf-8")
EOF
OC_PPTX_FONTS="$CACHE/fonts" NODE_PATH="$CACHE/node_modules" node "$HERE/internal-pptx/measure.js" "$TMP/deck.html" "$TMP/model" $CENTRE
NODE_PATH="$CACHE/node_modules" node "$HERE/internal-pptx/build.js" "$TMP/model/model.json" "$SRC" "$OUT"
python3 "$HERE/internal-pptx/finish.py" "$OUT" "$CACHE/fonts"

if [[ -n "$QA" ]]; then
  command -v soffice >/dev/null 2>&1 || die "--qa needs LibreOffice (soffice)"
  command -v pdftoppm >/dev/null 2>&1 || die "--qa needs pdftoppm (poppler-utils)"
  mkdir -p "$QA"
  # A private LibreOffice profile: a running instance would otherwise swallow the conversion.
  soffice "-env:UserInstallation=file://$TMP/lo-profile" --headless --convert-to pdf --outdir "$TMP/qa" "$OUT" >/dev/null 2>&1 \
    || die "LibreOffice could not convert $OUT"
  pdftoppm -png -r 96 "$TMP/qa/$(basename "${OUT%.pptx}").pdf" "$QA/slide"
  echo "render-internal-pptx: QA images → $QA/slide-*.png"
fi
echo "render-internal-pptx: $OUT"
