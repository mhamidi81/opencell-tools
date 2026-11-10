#!/usr/bin/env bash
# Fast path of the oc-be-tools edit gate (PreToolUse on Edit/Write/MultiEdit).
#
# The gate (ai_use_watch.py --pre-edit) holds an edit at most once per session, ticket and layer
# (analysis checkpoint, layer guidelines) and then always allows. Once it has decided, it leaves a
# marker file:
#
#   ~/.claude/oc-be-tools/gate/<session>/<ticket|none>/<layer>    that ticket + layer is cleared
#   ~/.claude/oc-be-tools/gate/<session>/skip                     not a backend repository
#
# This script answers from those markers without starting Python (~0.3 s on Windows). It uses bash
# builtins only: on Windows every extra process (grep, sed, tr, cat) costs ~60 ms, which would make
# the "fast" path slower than Python. Anything it cannot decide is passed to the Python gate. The
# layer names and patterns below must match layer_key() in ai_use_watch.py.

[[ -n $OC_BE_TOOLS_ISOLATED_REVIEW ]] && exit 0            # inside an isolated /oc-be-review run
IFS= read -r -d '' input                                   # the whole hook input, without forking cat

run_gate() {
  if command -v python >/dev/null 2>&1; then py=python; else py=python3; fi
  printf '%s' "$input" | "$py" "${CLAUDE_PLUGIN_ROOT}/hooks/ai_use_watch.py" --pre-edit
  exit $?
}

(( BASH_VERSINFO[0] >= 4 )) || run_gate                  # ${var,,} needs bash 4 (macOS ships 3.2)
case "$input" in *'"agent_id"'*) exit 0;; esac          # sub-agents load their own guidelines

field() {  # field <json name> <variable>: first "<name>": "<string>"; JSON-escaped backslashes become /
  local re="\"$1\"[[:space:]]*:[[:space:]]*\"([^\"]*)\""
  [[ $input =~ $re ]] || return 1
  local value=${BASH_REMATCH[1]}
  printf -v "$2" '%s' "${value//\\\\//}"
}

field session_id session && field cwd cwd_raw && field file_path path_raw || run_gate
path=${path_raw,,}
cwd=${cwd_raw,,}
cwd=${cwd%/}

case "$path" in "$cwd"/*) ;; *) exit 0;; esac            # outside the project: never gated
rel=${path#"$cwd"/}
case "$rel" in .claude/*|docs/*|*.md) exit 0;; esac

gate="$HOME/.claude/oc-be-tools/gate/$session"
[[ -f $gate/skip ]] && exit 0

case "$rel" in
  opencell-model/src/main/*.java|opencell-model/*/src/main/*.java) layer=entity ;;
  */db_resources/changelog/*.xml) layer=db ;;
  opencell-admin/ejbs/src/main/*.java|opencell-admin/ejbs/*/src/main/*.java) layer=service ;;
  opencell-api/src/main/*.java|opencell-api/*/src/main/*.java|opencell-api-dto/src/main/*.java|opencell-api-dto/*/src/main/*.java) layer=api ;;
  */src/test/*.java) layer=unittest ;;
  *.postman_collection.json) layer=postman ;;
  *) layer=other ;;
esac

ticket=none
if read -r head < "$cwd_raw/.git/HEAD" 2>/dev/null && [[ $head =~ ([A-Z][A-Z0-9]*-[0-9]+) ]]; then
  ticket=${BASH_REMATCH[1]}
fi
[[ -f $gate/$ticket/$layer ]] && exit 0
run_gate
