#!/bin/sh
# reap-idle-browser.sh — close oc-fn-portal Chrome trees that have gone idle.
#
# WHY THIS EXISTS
# A headless Chrome launched by the Playwright MCP server outlives the task that needed it. It is
# not orphaned — the MCP server is alive and owns it — so nothing cleans it up, and it sits there
# holding ~500-800 MB resident indefinitely. On a small host that is the difference between working
# and thrashing (see the 2026-08-04 memory-reclaim livelock post-mortem). `browser_close` is the
# primary discipline; this is the backstop for when a session is simply abandoned at a prompt.
#
# HOW IDLENESS IS DECIDED  — two non-obvious findings, both measured:
#
#   1. CPU, never file mtime. A browser observed with ZERO CPU ticks over a 6-second window had
#      written its GPU shader cache 60 seconds earlier and its cookie jar 3 minutes earlier. Chrome
#      flushes lazily long after going quiet, so profile mtimes report "active" for a tree doing
#      nothing at all. They are useless as a liveness signal.
#
#   2. Sustained, never instantaneous. A browser is also at 0% CPU during the pause between two
#      tool calls while the model thinks. Killing on a single idle sample would reap browsers
#      mid-task. So idleness must persist across invocations, which is why this script keeps state
#      and why it must run on a timer to be reliable — a single run can never conclude anything.
#      On first sight a browser is recorded and never killed.
#
# WHAT IT KILLS
# Only the Chrome *browser* process (the one with no --type=), which takes its whole tree with it,
# including the reparented crashpad handlers. The MCP server is deliberately left alone: it is what
# relaunches the browser on the next navigation, and the profile is on disk so the login survives.
#
# Usage: reap-idle-browser.sh [--status] [--dry-run] [--idle-minutes N] [--hook] [--help]
#   --status         show what is known about each browser; change nothing
#   --dry-run        report what would be killed; kill nothing
#   --idle-minutes   idle threshold before a kill (default 15, or $OC_PORTAL_IDLE_MINUTES)
#   --hook           emit a Claude Code systemMessage JSON when something was reaped, else stay
#                    silent — the form used by the SessionStart hook
#
# Env: OC_PORTAL_PROFILE (default ~/.local/state/oc-fn-portal/profile)
#      OC_PORTAL_IDLE_MINUTES

set -eu

PROFILE="${OC_PORTAL_PROFILE:-$HOME/.local/state/oc-fn-portal/profile}"
STATE_DIR="$(dirname "$PROFILE")"
STATE="$STATE_DIR/reaper-state"
IDLE_MINUTES="${OC_PORTAL_IDLE_MINUTES:-15}"
MODE=reap

while [ $# -gt 0 ]; do
    case $1 in
        --status)   MODE=status ;;
        --dry-run)  MODE=dryrun ;;
        --hook)     MODE=hook ;;
        --idle-minutes)
            [ $# -ge 2 ] || { echo "reap-idle-browser: --idle-minutes needs a value" >&2; exit 2; }
            IDLE_MINUTES=$2; shift ;;
        --help|-h)  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)          echo "reap-idle-browser: unknown option $1" >&2; exit 2 ;;
    esac
    shift
done

case $IDLE_MINUTES in
    ''|*[!0-9]*) echo "reap-idle-browser: --idle-minutes must be an integer" >&2; exit 2 ;;
esac
IDLE_SECONDS=$(( IDLE_MINUTES * 60 ))

# Identify the Chrome browser process by its EXECUTABLE, not by its command line.
#
# Matching on "--user-data-dir=<profile>" alone is actively dangerous: the `npm exec @playwright/mcp`
# wrapper and the playwright-mcp node server both carry that flag in their own argv, so a
# command-line match selects the MCP servers — precisely the processes this script must never touch.
# Observed for real: with no Chrome running at all, a command-line match returned nine MCP-stack
# processes belonging to three live sessions.
#
# An executable allowlist is used rather than excluding node/npm, because playwright-mcp accepts
# `--browser chrome`, which would put the string "chrome" into a node process's command line.
# Two further filters: no --type= (only the browser process lacks it; renderers and utilities
# carry it) and the profile path, so other Chrome instances on the machine are left alone.
is_browser_exe() {   # $1 = basename of argv[0]
    case $1 in
        chrome|chromium|chromium-browser|chrome.exe|headless_shell|msedge) return 0 ;;
        Chromium|Chrome) return 0 ;;
        *) return 1 ;;
    esac
}

list_browsers() {
    ps -eo pid=,args= 2>/dev/null | awk -v prof="$PROFILE" '
        index($0, "--user-data-dir=" prof) && !index($0, "--type=") {
            n = split($2, seg, "/")
            base = seg[n]
            if (base == "chrome" || base == "chromium" || base == "chromium-browser" ||
                base == "chrome.exe" || base == "headless_shell" || base == "msedge" ||
                base == "Chromium" || base == "Chrome")
                print $1
        }'
}

# Re-verified immediately before any kill. list_browsers is the only caller feeding pids in, so this
# is redundant by construction — which is exactly why it is here: the failure mode it guards against
# (killing an MCP server) costs a colleague their session, and the check costs one ps.
verify_browser() {   # $1 = pid
    exe=$(ps -o args= -p "$1" 2>/dev/null | awk '{ n = split($1, s, "/"); print s[n] }')
    [ -n "$exe" ] || return 1
    is_browser_exe "$exe"
}

# Cumulative CPU seconds and RSS kB for a pid plus every descendant.
# `time` is the POSIX-portable CPU column; its format varies ([dd-]hh:mm:ss on Linux, m:ss.cc on
# macOS), so it is normalised to whole seconds here. One-second resolution is deliberate: a page
# doing real work burns seconds, and sub-second noise from idle timers should read as "unchanged".
tree_stat() {
    ps -eo pid=,ppid=,time=,rss= 2>/dev/null | awk -v root="$1" '
        function secs(t,   d, n, a, b, s, i) {
            d = 0
            if (t ~ /-/) { split(t, a, "-"); d = a[1]; t = a[2] }
            n = split(t, b, ":")
            s = 0
            for (i = 1; i <= n; i++) s = s * 60 + b[i] + 0
            return int(d * 86400 + s)
        }
        { pid[NR] = $1; ppid[NR] = $2; cpu[NR] = secs($3); rss[NR] = $4; N = NR }
        END {
            desc[root] = 1
            changed = 1
            while (changed) {                 # fixpoint: the process table is small
                changed = 0
                for (i = 1; i <= N; i++)
                    if (!desc[pid[i]] && desc[ppid[i]]) { desc[pid[i]] = 1; changed = 1 }
            }
            c = 0; r = 0
            for (i = 1; i <= N; i++) if (desc[pid[i]]) { c += cpu[i]; r += rss[i] }
            print c + 0, r + 0
        }'
}

prev_state() {   # $1 = pid -> "cpu last_change", empty if unknown
    [ -f "$STATE" ] || return 0
    awk -v p="$1" '$1 == p { print $2, $3; exit }' "$STATE"
}

now=$(date +%s)
mkdir -p "$STATE_DIR"
tmp="$STATE.$$"
: > "$tmp"

reaped=0
freed_kb=0

for pid in $(list_browsers); do
    stat=$(tree_stat "$pid")
    cpu=${stat% *}
    rss=${stat#* }

    prev=$(prev_state "$pid")
    if [ -n "$prev" ]; then
        prev_cpu=${prev% *}
        last_change=${prev#* }
    else
        prev_cpu=''
        last_change=$now
    fi

    # Any change — up OR down — counts as activity. A decrease means the pid was reused by a
    # relaunched browser, which must not inherit the old one's idle clock.
    [ "$cpu" = "$prev_cpu" ] || last_change=$now
    idle=$(( now - last_change ))

    case $MODE in
        status)
            if [ -n "$prev_cpu" ]; then seen="idle ${idle}s"; else seen="first sight"; fi
            printf 'pid %-7s cpu %-7s rss %6s MB  %s (threshold %ss)\n' \
                "$pid" "${cpu}s" "$(( rss / 1024 ))" "$seen" "$IDLE_SECONDS"
            printf '%s %s %s\n' "$pid" "$cpu" "$last_change" >> "$tmp"
            continue ;;
    esac

    # Never kill on first sight: with no history, "idle" is unknowable.
    if [ -n "$prev_cpu" ] && [ "$idle" -ge "$IDLE_SECONDS" ]; then
        if [ "$MODE" = dryrun ]; then
            printf 'would reap pid %s (idle %ss, ~%s MB)\n' "$pid" "$idle" "$(( rss / 1024 ))"
            printf '%s %s %s\n' "$pid" "$cpu" "$last_change" >> "$tmp"
        elif ! verify_browser "$pid"; then
            echo "reap-idle-browser: pid $pid is not a browser, refusing to kill" >&2
            printf '%s %s %s\n' "$pid" "$cpu" "$last_change" >> "$tmp"
        else
            if kill "$pid" 2>/dev/null; then
                reaped=$(( reaped + 1 ))
                freed_kb=$(( freed_kb + rss ))
                [ "$MODE" = hook ] || printf 'reaped pid %s (idle %ss, ~%s MB)\n' \
                    "$pid" "$idle" "$(( rss / 1024 ))"
                continue          # killed: drop its state entry
            fi
            printf '%s %s %s\n' "$pid" "$cpu" "$last_change" >> "$tmp"
        fi
        continue
    fi

    printf '%s %s %s\n' "$pid" "$cpu" "$last_change" >> "$tmp"
done

mv "$tmp" "$STATE"

if [ "$MODE" = hook ] && [ "$reaped" -gt 0 ]; then
    if [ "$reaped" = 1 ]; then plural=''; else plural=es; fi
    printf '{"systemMessage":"oc-fn-portal: reaped %s idle browser%s, ~%s MB reclaimed"}\n' \
        "$reaped" "$plural" "$(( freed_kb / 1024 ))"
fi

exit 0
