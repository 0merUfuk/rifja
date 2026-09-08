#!/bin/sh
# Rifja SessionStart hook - best-effort context injection for coding agents.
#
# Fail-open by design: any failure prints nothing and exits 0 so an agent
# session never stalls. Two output bounds apply: `head -c` here and the
# caller's own hook timeout (set "timeout": 10 in the hook configuration).
# The injected text is quoted historical evidence (data-only), never
# instructions. Usage: session-start.sh PROJECT, or set RIFJA_PROJECT.
set -u
project=${1:-${RIFJA_PROJECT:-}}
[ -n "$project" ] || exit 0
command -v rifja >/dev/null 2>&1 || exit 0
rifja resume "$project" --cached --limit 20 2>/dev/null | head -c 12000
exit 0
